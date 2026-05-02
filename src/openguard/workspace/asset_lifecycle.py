"""测试脚本资产生命周期管理（REQ-13）。

包含：
- 锚点状态机（verified / needs-review / stale / broken）（REQ-13-15~18）
- suite.yaml 管理（REQ-13-04）
- 锚点新鲜度检查，联动 freshness.json（REQ-13-15/16/17/18）
- 侵入策略校验（REQ-13-06~09）
- suite 执行前脚本过滤（REQ-13-25 / REQ-13-19）

状态机转换规则：
  verified
    → needs-review  : 绑定代码符号哈希变化（未消失）
    → stale         : 绑定符号消失 OR 需求指纹变化
  needs-review
    → verified      : Agent/人工确认更新锚点哈希
    → stale         : 绑定符号消失 OR 需求指纹变化
  stale
    → verified      : 需求对齐后重新验证
    → broken        : 接口/符号完全断裂（无法映射）
  broken
    → verified      : 修复并重新通过验证
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from openguard.utils import now_iso as _now_iso

# 四种合法状态
STATUS_VERIFIED = "verified"
STATUS_NEEDS_REVIEW = "needs-review"
STATUS_STALE = "stale"
STATUS_BROKEN = "broken"

# gate 级别与允许的脚本状态（REQ-13-19）
GATE_ALLOWED_STATUSES: dict[str, set[str]] = {
    "local": {STATUS_VERIFIED, STATUS_NEEDS_REVIEW},
    "ci":    {STATUS_VERIFIED, STATUS_NEEDS_REVIEW},
    "requirement": {STATUS_VERIFIED, STATUS_NEEDS_REVIEW},
    "release": {STATUS_VERIFIED},
    "nightly": {STATUS_VERIFIED},
}


# ──────────────────────────────────────────────────────────────────────────────
# 锚点读写
# ──────────────────────────────────────────────────────────────────────────────

def read_meta(meta_path: Path) -> dict[str, Any]:
    """读取脚本 .meta.yaml 锚点文件，返回空字典若不存在。"""
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    """写入 .meta.yaml，自动更新 last_checked_at。"""
    meta["last_checked_at"] = _now_iso()
    meta_path.write_text(
        yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def get_meta_path(openguard_dir: Path, script_name: str) -> Path:
    """根据脚本文件名返回对应的 .meta.yaml 路径。"""
    stem = Path(script_name).stem
    return openguard_dir / "test_assets" / "scripts" / f"{stem}.meta.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# 锚点新鲜度检查（REQ-13-15~18）
# ──────────────────────────────────────────────────────────────────────────────

def check_anchor_freshness(
    openguard_dir: Path,
    current_symbols: dict[str, str] | None = None,
    current_req_fingerprints: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """对 test_assets/scripts/ 中所有脚本执行锚点新鲜度检查。

    参数：
        current_symbols: {符号路径: 当前 hash}，来自 snapshot.json。
        current_req_fingerprints: {req_id: 当前指纹}。

    返回锚点变化报告列表，每项含：
        script, old_status, new_status, changes
    """
    scripts_dir = openguard_dir / "test_assets" / "scripts"
    if not scripts_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    current_symbols = current_symbols or {}
    current_req_fingerprints = current_req_fingerprints or {}

    for meta_path in scripts_dir.glob("*.meta.yaml"):
        meta = read_meta(meta_path)
        if not meta:
            continue

        old_status = meta.get("status", STATUS_VERIFIED)
        bound_to: list[dict[str, Any]] = meta.get("bound_to", [])

        # REQ-13-13 兼容旧格式（binding_symbol 单字段）
        if not bound_to and meta.get("binding_symbol"):
            bound_to = [{
                "type": "code_symbol",
                "path": meta.get("binding_file", ""),
                "symbol": meta.get("binding_symbol", ""),
                "hash": meta.get("anchor_hash", ""),
            }]

        symbol_missing: list[str] = []
        symbol_changed: list[str] = []
        req_changed: list[str] = []

        for binding in bound_to:
            btype = binding.get("type", "")
            if btype == "code_symbol":
                sym = binding.get("symbol") or binding.get("path", "")
                expected_hash = binding.get("hash", "")
                if sym and expected_hash:
                    current_hash = current_symbols.get(sym, "")
                    if not current_hash:
                        # 符号消失
                        symbol_missing.append(sym)
                    elif current_hash != expected_hash:
                        symbol_changed.append(sym)
            elif btype == "requirement":
                req_id = binding.get("id", "")
                expected_fp = binding.get("fingerprint", "")
                if req_id and expected_fp:
                    current_fp = current_req_fingerprints.get(req_id, "")
                    if current_fp and current_fp != expected_fp:
                        req_changed.append(req_id)

        # 状态转换（REQ-13-16/17/18）
        new_status = old_status
        changes: list[str] = []

        if symbol_missing:
            # 符号消失 → stale 或 broken
            new_status = STATUS_BROKEN if old_status == STATUS_STALE else STATUS_STALE
            changes.append(f"符号消失：{symbol_missing}")
        elif req_changed:
            # 需求指纹变化 → stale
            if old_status in (STATUS_VERIFIED, STATUS_NEEDS_REVIEW):
                new_status = STATUS_STALE
            changes.append(f"需求指纹变化：{req_changed}")
        elif symbol_changed:
            # 代码符号哈希变化（未消失）→ needs-review
            if old_status == STATUS_VERIFIED:
                new_status = STATUS_NEEDS_REVIEW
            changes.append(f"符号哈希变化：{symbol_changed}")

        if new_status != old_status or changes:
            # 更新 meta 文件状态
            meta["status"] = new_status
            if changes:
                meta["anchor_changes"] = changes
                meta["anchor_changed_at"] = _now_iso()
            write_meta(meta_path, meta)

            reports.append({
                "script": meta.get("script_path", meta_path.stem),
                "old_status": old_status,
                "new_status": new_status,
                "changes": changes,
            })

    return reports


# ──────────────────────────────────────────────────────────────────────────────
# 脚本晋升的完整 meta.yaml（REQ-13-13/14）
# ──────────────────────────────────────────────────────────────────────────────

def build_full_meta(
    script_path: str,
    anchor_hash: str,
    change_id: str,
    run_ids: list[str],
    bound_symbols: list[dict[str, Any]] | None = None,
    bound_requirements: list[dict[str, Any]] | None = None,
    suite_membership: list[str] | None = None,
    confidence: str = "medium",
) -> dict[str, Any]:
    """生成符合 REQ-13-13/14 要求的完整 .meta.yaml 内容。

    bound_symbols: [{path, symbol, hash}, ...]
    bound_requirements: [{id, fingerprint}, ...]
    suite_membership: ['smoke', 'regression', ...]
    """
    now = _now_iso()
    bound_to: list[dict[str, Any]] = []

    for sym in (bound_symbols or []):
        bound_to.append({
            "type": "code_symbol",
            "path": sym.get("path", ""),
            "symbol": sym.get("symbol", ""),
            "hash": sym.get("hash", ""),
        })

    for req in (bound_requirements or []):
        bound_to.append({
            "type": "requirement",
            "id": req.get("id", ""),
            "fingerprint": req.get("fingerprint", ""),
        })

    return {
        "schema_version": "openguard/script_meta/v2",
        "script": script_path,
        "status": STATUS_VERIFIED,
        "confidence": confidence,
        "created_from_change": change_id,
        "created_at": now,
        "last_verified_at": now,
        "last_verified_change": change_id,
        "bound_to": bound_to,
        "suite_membership": suite_membership or ["smoke"],
        "run_ids": run_ids,
        "anchor_hash": anchor_hash,
    }


# ──────────────────────────────────────────────────────────────────────────────
# suite.yaml 管理（REQ-13-04）
# ──────────────────────────────────────────────────────────────────────────────

def load_suite(suite_path: Path) -> dict[str, Any]:
    """读取 suite.yaml；不存在返回空骨架。"""
    if not suite_path.exists():
        return {
            "schema_version": "openguard/suite/v1",
            "name": suite_path.parent.name,
            "scripts": [],
        }
    with suite_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_suite(suite_path: Path, suite: dict[str, Any]) -> None:
    """写入 suite.yaml。"""
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    suite_path.write_text(
        yaml.dump(suite, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def add_script_to_suite(
    openguard_dir: Path,
    suite_name: str,
    script_path: str,
    *,
    execution_order: int | None = None,
) -> bool:
    """将脚本添加到指定 suite.yaml（REQ-13-04）。

    脚本引用必须指向 test_assets/scripts/，不得引用 change 工作区草稿。
    返回 True 如果添加成功（或已存在）。
    """
    # 只允许引用 test_assets/ 中的脚本（REQ-13-04）
    if "changes/" in script_path:
        return False  # 不允许在 suite 中直接引用草稿脚本

    # requirement/<req-id> 形式的套件支持子目录
    suite_dir = openguard_dir / "suites"
    for part in suite_name.split("/"):
        suite_dir = suite_dir / part
    suite_file = suite_dir / "suite.yaml"

    suite = load_suite(suite_file)
    scripts: list[dict[str, Any]] = suite.get("scripts", [])

    # 去重
    existing_paths = {s.get("path", "") for s in scripts}
    if script_path in existing_paths:
        return True

    entry: dict[str, Any] = {"path": script_path}
    if execution_order is not None:
        entry["execution_order"] = execution_order
    scripts.append(entry)
    suite["scripts"] = scripts
    save_suite(suite_file, suite)
    return True


def remove_script_from_suite(
    openguard_dir: Path,
    suite_name: str,
    script_path: str,
) -> bool:
    """从 suite.yaml 中移除脚本引用（用于 broken/stale 清理）。"""
    suite_dir = openguard_dir / "suites"
    for part in suite_name.split("/"):
        suite_dir = suite_dir / part
    suite_file = suite_dir / "suite.yaml"

    if not suite_file.exists():
        return False

    suite = load_suite(suite_file)
    scripts = suite.get("scripts", [])
    original_len = len(scripts)
    suite["scripts"] = [s for s in scripts if s.get("path") != script_path]

    if len(suite["scripts"]) < original_len:
        save_suite(suite_file, suite)
        return True
    return False


def list_suite_scripts(
    openguard_dir: Path,
    suite_name: str,
    gate: str = "local",
) -> list[dict[str, Any]]:
    """列出套件内所有可执行脚本，按 gate 过滤状态（REQ-13-19 / REQ-13-25）。

    返回：[{path, status, skipped, skip_reason}, ...]
    """
    suite_dir = openguard_dir / "suites"
    for part in suite_name.split("/"):
        suite_dir = suite_dir / part
    suite_file = suite_dir / "suite.yaml"

    if not suite_file.exists():
        return []

    suite = load_suite(suite_file)
    allowed = GATE_ALLOWED_STATUSES.get(gate, {STATUS_VERIFIED, STATUS_NEEDS_REVIEW})

    result: list[dict[str, Any]] = []
    for entry in suite.get("scripts", []):
        path = entry.get("path", "")
        # 读取 meta 状态
        script_name = Path(path).name
        meta_path = get_meta_path(openguard_dir, script_name)
        meta = read_meta(meta_path)
        status = meta.get("status", STATUS_VERIFIED)

        skipped = status not in allowed
        skip_reason = ""
        if status == STATUS_BROKEN:
            skip_reason = "脚本已 broken，必须修复后才能执行（REQ-13-18）"
        elif status == STATUS_STALE:
            skip_reason = "脚本已 stale，等待需求对齐（REQ-13-17）"
        elif status == STATUS_NEEDS_REVIEW and gate in ("release", "nightly"):
            skip_reason = f"needs-review 脚本不得用于 {gate} gate（REQ-13-19）"

        result.append({
            "path": path,
            "status": status,
            "skipped": skipped,
            "skip_reason": skip_reason,
            "execution_order": entry.get("execution_order"),
        })

    return result


def update_suites_after_promote(
    openguard_dir: Path,
    script_path: str,
    suite_membership: list[str],
) -> None:
    """脚本晋升后，将其加入所有指定 suite（REQ-13-04 / REQ-03-08）。"""
    for suite_name in suite_membership:
        add_script_to_suite(openguard_dir, suite_name, script_path)


def update_suites_after_demote(
    openguard_dir: Path,
    script_path: str,
    new_status: str,
) -> None:
    """脚本降级为 broken 时，从所有 suite 的可执行列表中移除。

    不物理删除 suite.yaml 中的条目，而是让 list_suite_scripts 在运行时过滤。
    仅在 broken 状态时从 suite.yaml 中清除，避免误导（REQ-13-18）。
    """
    if new_status != STATUS_BROKEN:
        return
    # 找到所有包含此脚本的 suites
    suites_dir = openguard_dir / "suites"
    if not suites_dir.exists():
        return
    for suite_yaml in suites_dir.rglob("suite.yaml"):
        suite = load_suite(suite_yaml)
        scripts = suite.get("scripts", [])
        if any(s.get("path") == script_path for s in scripts):
            remove_script_from_suite(
                openguard_dir,
                suite_yaml.parent.relative_to(suites_dir).as_posix(),
                script_path,
            )


# ──────────────────────────────────────────────────────────────────────────────
# 侵入策略校验（REQ-13-06~09）
# ──────────────────────────────────────────────────────────────────────────────

INTRUSION_NONE = "external-only"
INTRUSION_BUILD_BRIDGE = "build-time-bridge"
INTRUSION_RUNTIME_PATCH = "runtime-patch"


def check_intrusion_strategy(
    config: dict[str, Any],
    change_dir: Path | None = None,
) -> dict[str, Any]:
    """校验侵入策略合规性（REQ-13-06~09）。

    返回：{ok: bool, strategy, blockers, warnings}
    """
    runtime = config.get("runtime", {})
    strategy = runtime.get("intrusion_strategy", INTRUSION_NONE)
    blockers: list[str] = []
    warnings: list[str] = []

    if strategy == INTRUSION_BUILD_BRIDGE:
        # 必须有显式授权记录（REQ-13-07）
        if not runtime.get("intrusion_authorized_by"):
            blockers.append(
                "build-time-bridge 侵入必须在 config.yaml 中记录 runtime.intrusion_authorized_by"
            )
        if not runtime.get("bridge_source"):
            warnings.append(
                "build-time-bridge 需记录 runtime.bridge_source（bridge 代码来源，REQ-13-07）"
            )

    elif strategy == INTRUSION_RUNTIME_PATCH:
        # 必须有还原步骤（REQ-13-08）
        if not runtime.get("intrusion_authorized_by"):
            blockers.append(
                "runtime-patch 侵入必须在 config.yaml 中记录 runtime.intrusion_authorized_by"
            )
        if not runtime.get("restore_command"):
            blockers.append(
                "runtime-patch 必须有 runtime.restore_command（REQ-13-08）"
            )

    elif strategy != INTRUSION_NONE:
        warnings.append(f"未知侵入策略：{strategy}，建议显式声明为 external-only / build-time-bridge / runtime-patch")

    return {
        "ok": len(blockers) == 0,
        "strategy": strategy,
        "blockers": blockers,
        "warnings": warnings,
    }


def check_intrusion_strategy_changed(
    openguard_dir: Path,
    config: dict[str, Any],
) -> bool:
    """检查侵入策略是否变化（变化时需触发全量扫描，REQ-13-09）。"""
    cache_path = openguard_dir / ".intrusion_strategy_sig"
    strategy = config.get("runtime", {}).get("intrusion_strategy", INTRUSION_NONE)
    sig = hashlib.sha256(strategy.encode()).hexdigest()[:16]

    if cache_path.exists():
        if cache_path.read_text(encoding="utf-8").strip() != sig:
            cache_path.write_text(sig, encoding="utf-8")
            return True
    else:
        cache_path.write_text(sig, encoding="utf-8")

    return False


# ──────────────────────────────────────────────────────────────────────────────
# 全局 suite 执行前脚本过滤与报告标注（REQ-13-24~26）
# ──────────────────────────────────────────────────────────────────────────────

def build_suite_execution_manifest(
    openguard_dir: Path,
    suite_name: str,
    gate: str = "local",
    code_version: str = "",
) -> dict[str, Any]:
    """生成套件执行清单（REQ-13-24~26）。

    包含：套件名、脚本版本、锚点哈希、执行时代码版本、skipped 原因。
    """
    scripts = list_suite_scripts(openguard_dir, suite_name, gate)
    runnable = [s for s in scripts if not s["skipped"]]
    skipped = [s for s in scripts if s["skipped"]]

    # 附加锚点哈希（REQ-13-26）
    for script in scripts:
        script_name = Path(script["path"]).name
        meta_path = get_meta_path(openguard_dir, script_name)
        meta = read_meta(meta_path)
        script["anchor_hash"] = meta.get("anchor_hash", "")
        script["last_verified_change"] = meta.get("last_verified_change", "")

    return {
        "schema_version": "openguard/suite_manifest/v1",
        "suite_name": suite_name,
        "gate": gate,
        "code_version": code_version,
        "generated_at": _now_iso(),
        "total_scripts": len(scripts),
        "runnable_count": len(runnable),
        "skipped_count": len(skipped),
        "scripts": scripts,
        "skipped_reasons": {s["path"]: s["skip_reason"] for s in skipped if s["skip_reason"]},
    }


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────


