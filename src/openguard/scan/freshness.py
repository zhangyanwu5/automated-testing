"""新鲜度校验：每次 continue / apply 前执行（REQ-04-05 / REQ-04-06）。

校验内容：
1. snapshot.json 存在且 status=complete。
2. 分析器版本与 snapshot 一致（版本升级触发重新扫描）。
3. requirements.md 指纹与 snapshot 中记录一致。
4. config.yaml 中 project.type / scan 配置未变化。
5. test_assets 锚点状态（直接引用 snapshot 中的 anchor_checks）。

输出 freshness.json，供状态机和执行器消费（REQ-04-05）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from openguard.scan.scanner import ANALYZER_VERSION, _file_hash
from openguard.utils import now_iso as _now_iso


def check_freshness(
    change_dir: Path,
    openguard_dir: Path,
) -> dict[str, Any]:
    """执行新鲜度校验，返回 freshness 结果字典（不写盘）。"""
    checks: list[dict[str, Any]] = []
    is_fresh = True

    # 1. snapshot.json 存在且完整
    snapshot: dict[str, Any] = {}
    snapshot_path = change_dir / "snapshot.json"
    if not snapshot_path.exists():
        checks.append(_fail("snapshot_exists", "snapshot.json 不存在，需先执行扫描"))
        is_fresh = False
    else:
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception as e:
            checks.append(_fail("snapshot_readable", f"snapshot.json 解析失败：{e}"))
            is_fresh = False
            snapshot = {}

        if snapshot.get("status") != "complete":
            checks.append(_fail("snapshot_complete", "snapshot.json status 不是 complete"))
            is_fresh = False
        else:
            checks.append(_pass("snapshot_exists"))

        # 2. 分析器版本
        snap_ver = snapshot.get("analyzer_version", "")
        if snap_ver != ANALYZER_VERSION:
            checks.append(_fail(
                "analyzer_version",
                f"分析器版本变化：snapshot={snap_ver}，current={ANALYZER_VERSION}，需重新扫描",
            ))
            is_fresh = False
        else:
            checks.append(_pass("analyzer_version"))

        # 3. requirements.md 指纹
        req_path = change_dir / "requirements.md"
        snap_req = snapshot.get("requirements", {})
        # 兼容骨架（list）和扫描后（dict）两种格式
        if isinstance(snap_req, list):
            snap_req = {}
        if req_path.exists():
            current_hash = _file_hash(req_path)
            snap_hash = snap_req.get("file_hash", "")
            if snap_hash and current_hash != snap_hash:
                checks.append(_fail(
                    "requirements_fingerprint",
                    "requirements.md 已变化，需重新扫描以更新需求指纹",
                ))
                is_fresh = False
            else:
                checks.append(_pass("requirements_fingerprint"))
        else:
            checks.append(_warn("requirements_fingerprint", "requirements.md 不存在，跳过指纹校验"))

    # 4. config.yaml 签名（project.type + scan 配置）
    config_path = openguard_dir / "config.yaml"
    if config_path.exists():
        config_sig = _config_signature(config_path)
        sig_cache_path = change_dir / ".config_sig"
        if sig_cache_path.exists():
            cached_sig = sig_cache_path.read_text(encoding="utf-8").strip()
            if cached_sig != config_sig:
                checks.append(_fail(
                    "config_signature",
                    "config.yaml 中 project.type 或 scan 配置已变化，需重新扫描",
                ))
                is_fresh = False
            else:
                checks.append(_pass("config_signature"))
        else:
            # 首次校验，写入签名
            sig_cache_path.write_text(config_sig, encoding="utf-8")
            checks.append(_pass("config_signature", note="首次记录 config 签名"))
    else:
        checks.append(_warn("config_signature", "config.yaml 不存在，跳过配置签名校验"))

    # 5. test_matrix.json 新鲜度
    matrix_path = change_dir / "test_matrix.json"
    if matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix_snap_ver = matrix.get("snapshot_version", "")
            snap_ver_current = snapshot.get("analyzer_version", "") if "snapshot" in dir() else ""
            if matrix_snap_ver and snap_ver_current and matrix_snap_ver != snap_ver_current:
                checks.append(_fail(
                    "test_matrix_fresh",
                    "test_matrix.json 基于旧快照生成，需重新生成矩阵",
                ))
                is_fresh = False
            else:
                checks.append(_pass("test_matrix_fresh"))
        except Exception:
            checks.append(_warn("test_matrix_fresh", "test_matrix.json 解析失败，跳过校验"))
    else:
        checks.append(_info("test_matrix_fresh", "test_matrix.json 尚未生成"))

    # 6. test_assets 锚点批量新鲜度检查（REQ-04-05 第 5 项 / REQ-13-15）
    # 从 snapshot 中提取当前符号哈希，驱动锚点状态机更新
    anchor_reports = _check_test_assets_anchors(openguard_dir, snapshot)
    if anchor_reports:
        for report in anchor_reports:
            if report["new_status"] in ("stale", "broken"):
                checks.append(_fail(
                    "anchor_freshness",
                    f"脚本 {report['script']} 状态降级：{report['old_status']} → {report['new_status']}，"
                    f"原因：{report['changes']}",
                ))
                # 锚点降级不阻断新鲜度（阻断由 preflight 的脚本状态校验处理）
            elif report["new_status"] == "needs-review":
                checks.append(_warn(
                    "anchor_freshness",
                    f"脚本 {report['script']} 锚点变化，状态降为 needs-review：{report['changes']}",
                ))
    else:
        checks.append(_pass("anchor_freshness", note="test_assets 锚点均与当前代码快照一致"))

    result: dict[str, Any] = {
        "schema_version": "openguard/freshness/v1",
        "checked_at": _now_iso(),
        "is_fresh": is_fresh,
        "checks": checks,
        "anchor_reports": anchor_reports,
    }
    return result


def write_freshness(change_dir: Path, result: dict[str, Any]) -> Path:
    """将 freshness 结果写入 freshness.json。"""
    path = change_dir / "freshness.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_freshness_check(change_dir: Path, openguard_dir: Path) -> tuple[bool, Path]:
    """执行新鲜度校验并写盘，返回 (is_fresh, freshness_json_path)。"""
    result = check_freshness(change_dir, openguard_dir)
    path = write_freshness(change_dir, result)
    return result["is_fresh"], path


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────────────────────

def _config_signature(config_path: Path) -> str:
    """对 config.yaml 中影响扫描的关键字段做签名。"""
    try:
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return ""
    # 只对影响扫描的字段做签名
    key_data = {
        "project_type": cfg.get("project", {}).get("type"),
        "scan": cfg.get("scan", {}),
    }
    return hashlib.sha256(
        json.dumps(key_data, sort_keys=True).encode()
    ).hexdigest()[:32]


def _pass(name: str, note: str = "") -> dict[str, Any]:
    r: dict[str, Any] = {"check": name, "status": "pass"}
    if note:
        r["note"] = note
    return r


def _fail(name: str, reason: str) -> dict[str, Any]:
    return {"check": name, "status": "fail", "reason": reason}


def _warn(name: str, reason: str) -> dict[str, Any]:
    return {"check": name, "status": "warn", "reason": reason}


def _info(name: str, note: str) -> dict[str, Any]:
    return {"check": name, "status": "info", "note": note}


def _check_test_assets_anchors(
    openguard_dir: Path,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """基于 snapshot 中的代码符号哈希批量执行锚点新鲜度检查（REQ-13-15）。

    从 snapshot.code_files 提取当前符号哈希 → 传入 check_anchor_freshness。
    """
    scripts_dir = openguard_dir / "test_assets" / "scripts"
    if not scripts_dir.exists() or not any(scripts_dir.glob("*.meta.yaml")):
        return []

    # 从 snapshot 提取符号哈希表
    current_symbols: dict[str, str] = {}
    for file_info in snapshot.get("code_files", []):
        # scanner 记录的格式：{path, hash, symbols: [{name, hash}, ...]}
        for sym in file_info.get("symbols", []):
            sym_name = sym.get("name", "")
            sym_hash = sym.get("hash", "")
            if sym_name and sym_hash:
                current_symbols[sym_name] = sym_hash

    # 提取需求指纹
    current_req_fps: dict[str, str] = {}
    req_info = snapshot.get("requirements", {})
    if isinstance(req_info, dict):
        for req_id, fp in req_info.get("fingerprints", {}).items():
            current_req_fps[req_id] = fp

    from openguard.workspace.asset_lifecycle import check_anchor_freshness
    return check_anchor_freshness(openguard_dir, current_symbols, current_req_fps)
