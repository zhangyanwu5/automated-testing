"""前置路径管理：查询、晋升、降级、锚点检查（REQ-09-16/17 / REQ-13-27~32）。

前置路径是"把目标系统从初始状态带到可测试目标功能的状态"的步骤序列。
它是测试资产的一种，独立于当前 change，跨 change 复用。

目录：
  openguard/knowledge/preconditions.yaml   — 已验证前置路径按状态标签索引
  openguard/test_assets/setup_paths/       — 前置路径脚本 + .meta.yaml 锚点

实现模式（REQ-13-29）：
  white-box: 直接通过 RPC/console command 设置目标状态（优先）
  black-box: 模拟真实玩家操作

生命周期（REQ-09-16）：
  inferred → 首次执行验证 → verified → 代码变更 → needs-review/stale
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from openguard.utils import now_iso as _now_iso

STATUS_VERIFIED = "verified"
STATUS_NEEDS_REVIEW = "needs-review"
STATUS_STALE = "stale"
STATUS_INFERRED = "inferred"

MODE_WHITE_BOX = "white-box"
MODE_BLACK_BOX = "black-box"


# ──────────────────────────────────────────────────────────────────────────────
# preconditions.yaml 读写
# ──────────────────────────────────────────────────────────────────────────────

def load_preconditions(knowledge_dir: Path) -> dict[str, Any]:
    """读取 preconditions.yaml；不存在返回空骨架。"""
    path = knowledge_dir / "preconditions.yaml"
    if not path.exists():
        return {
            "schema_version": "openguard/preconditions/v1",
            "preconditions": [],
        }
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"preconditions": []}


def save_preconditions(knowledge_dir: Path, data: dict[str, Any]) -> None:
    """写入 preconditions.yaml。"""
    path = knowledge_dir / "preconditions.yaml"
    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────────────────────────────────────
# 查询前置路径（REQ-09-17 / REQ-13-28）
# ──────────────────────────────────────────────────────────────────────────────

def find_preconditions(
    knowledge_dir: Path,
    required_tags: list[str],
    *,
    include_needs_review: bool = True,
) -> list[dict[str, Any]]:
    """按状态标签查找匹配的已验证前置路径（REQ-09-17）。

    required_tags: 必须包含的状态标签，如 ['logged_in', 'map_a']
    返回匹配的前置路径列表（按匹配度排序）。
    stale 和 broken 状态的路径不返回。
    """
    data = load_preconditions(knowledge_dir)
    all_preconds: list[dict[str, Any]] = data.get("preconditions", [])

    required = set(required_tags)
    matches: list[dict[str, Any]] = []

    for pc in all_preconds:
        status = pc.get("status", STATUS_INFERRED)
        if status in ("stale", "broken"):
            continue
        if status == STATUS_NEEDS_REVIEW and not include_needs_review:
            continue

        tags = set(pc.get("tags", []))
        # 前置路径的 tags 必须是 required_tags 的超集（覆盖全部需求）
        if required.issubset(tags):
            # 匹配分数：覆盖越精确越好（额外标签越少越好）
            matches.append({
                **pc,
                "_match_score": len(tags - required),  # 越小越精确
            })

    # 按匹配精确度排序，verified 优先
    matches.sort(key=lambda p: (
        0 if p.get("status") == STATUS_VERIFIED else 1,
        p.get("_match_score", 99),
    ))
    # 移除临时评分字段
    for m in matches:
        m.pop("_match_score", None)

    return matches


def query_preconditions_for_change(
    knowledge_dir: Path,
    required_tags: list[str],
) -> dict[str, Any]:
    """为 change 查询前置路径，返回查询摘要（REQ-03-10）。

    返回：
      {
        found: bool,
        matches: [...],
        missing_tags: [...],        # 无法满足的标签
        unknown_entry: str | None,  # 写入 unknowns.md 的建议文本
      }
    """
    matches = find_preconditions(knowledge_dir, required_tags)
    found = len(matches) > 0

    unknown_entry: str | None = None
    if not found and required_tags:
        unknown_entry = (
            f"前置路径缺失：所需状态标签 {required_tags} 在 preconditions.yaml 中无匹配路径。\n"
            f"  建议：为以下状态建立前置路径：{required_tags}（REQ-13-30）。\n"
            f"  路径生成后经执行验证方可晋升到 test_assets/setup_paths/。"
        )

    return {
        "found": found,
        "matches": matches,
        "required_tags": required_tags,
        "unknown_entry": unknown_entry,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 前置路径晋升（REQ-13-30 / REQ-09-16）
# ──────────────────────────────────────────────────────────────────────────────

def promote_setup_path(
    script_src: Path,
    openguard_dir: Path,
    *,
    tags: list[str],
    mode: str = MODE_WHITE_BOX,
    run_id: str,
    bound_symbols: list[dict[str, Any]] | None = None,
    change_id: str = "",
) -> dict[str, Any]:
    """将草稿前置路径晋升到 test_assets/setup_paths/（REQ-13-27 / REQ-13-30）。

    必须有至少一次真实执行记录（run_id）。
    """
    if not run_id:
        return {"status": "rejected", "reason": "前置路径必须经过真实执行验证（REQ-13-30）"}
    if not script_src.exists():
        return {"status": "rejected", "reason": f"脚本文件不存在：{script_src}"}
    if not tags:
        return {"status": "rejected", "reason": "前置路径必须有状态标签（REQ-13-28）"}

    setup_paths_dir = openguard_dir / "test_assets" / "setup_paths"
    setup_paths_dir.mkdir(parents=True, exist_ok=True)

    content = script_src.read_bytes()
    anchor_hash = hashlib.sha256(content).hexdigest()[:32]

    dest = setup_paths_dir / script_src.name
    dest.write_bytes(content)

    # 生成 .meta.yaml 锚点文件（REQ-13-27）
    now = _now_iso()
    bound_to: list[dict[str, Any]] = []
    for sym in (bound_symbols or []):
        bound_to.append({
            "type": "code_symbol",
            "path": sym.get("path", ""),
            "symbol": sym.get("symbol", ""),
            "hash": sym.get("hash", ""),
        })

    meta: dict[str, Any] = {
        "schema_version": "openguard/setup_path_meta/v1",
        "script": f"test_assets/setup_paths/{dest.name}",
        "status": STATUS_VERIFIED,
        "mode": mode,
        "tags": tags,
        "confidence": "medium",
        "created_from_change": change_id,
        "created_at": now,
        "last_verified_at": now,
        "last_verified_run": run_id,
        "anchor_hash": anchor_hash,
        "bound_to": bound_to,
    }
    meta_path = setup_paths_dir / f"{script_src.stem}.meta.yaml"
    meta_path.write_text(
        yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # 更新 preconditions.yaml（REQ-09-16）
    knowledge_dir = openguard_dir / "knowledge"
    _upsert_precondition(
        knowledge_dir,
        tags=tags,
        setup_path=f"openguard/test_assets/setup_paths/{dest.name}",
        mode=mode,
        run_id=run_id,
    )

    return {
        "status": "promoted",
        "dest_path": str(dest),
        "meta_path": str(meta_path),
        "tags": tags,
        "anchor_hash": anchor_hash,
    }


def _upsert_precondition(
    knowledge_dir: Path,
    tags: list[str],
    setup_path: str | list[str],
    mode: str,
    run_id: str,
) -> None:
    """在 preconditions.yaml 中新增或更新前置路径条目。"""
    data = load_preconditions(knowledge_dir)
    preconds: list[dict[str, Any]] = data.get("preconditions", [])
    now = _now_iso()

    tag_set = sorted(tags)
    # 查找已有条目（按标签集合去重）
    existing_idx: int | None = None
    for i, pc in enumerate(preconds):
        if sorted(pc.get("tags", [])) == tag_set:
            existing_idx = i
            break

    entry: dict[str, Any] = {
        "tags": tag_set,
        "setup_path": setup_path,
        "status": STATUS_VERIFIED,
        "mode": mode,
        "last_verified": now,
        "last_verified_run": run_id,
    }

    if existing_idx is not None:
        preconds[existing_idx] = {**preconds[existing_idx], **entry}
    else:
        preconds.append(entry)

    data["preconditions"] = preconds
    save_preconditions(knowledge_dir, data)


# ──────────────────────────────────────────────────────────────────────────────
# 前置路径锚点检查（REQ-13-31）
# ──────────────────────────────────────────────────────────────────────────────

def check_setup_path_anchors(
    openguard_dir: Path,
    current_symbols: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """检查所有前置路径脚本的锚点有效性（REQ-13-31）。

    返回状态变化报告列表。
    """
    setup_paths_dir = openguard_dir / "test_assets" / "setup_paths"
    if not setup_paths_dir.exists():
        return []

    reports: list[dict[str, Any]] = []
    current_symbols = current_symbols or {}

    for meta_path in setup_paths_dir.glob("*.meta.yaml"):
        with meta_path.open(encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

        old_status = meta.get("status", STATUS_VERIFIED)
        bound_to: list[dict[str, Any]] = meta.get("bound_to", [])
        changes: list[str] = []
        new_status = old_status

        for binding in bound_to:
            sym = binding.get("symbol", "")
            expected_hash = binding.get("hash", "")
            if not sym or not expected_hash:
                continue
            current_hash = current_symbols.get(sym, "")
            if not current_hash:
                new_status = STATUS_STALE
                changes.append(f"符号消失：{sym}")
            elif current_hash != expected_hash:
                if old_status == STATUS_VERIFIED:
                    new_status = STATUS_NEEDS_REVIEW
                changes.append(f"符号哈希变化：{sym}")

        if new_status != old_status or changes:
            meta["status"] = new_status
            meta["anchor_last_checked"] = _now_iso()
            if changes:
                meta["anchor_changes"] = changes
            meta_path.write_text(
                yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            reports.append({
                "script": meta.get("script", meta_path.stem),
                "tags": meta.get("tags", []),
                "old_status": old_status,
                "new_status": new_status,
                "changes": changes,
            })

            # 同步降级 preconditions.yaml（REQ-13-31）
            if new_status in (STATUS_STALE, STATUS_NEEDS_REVIEW):
                _update_precondition_status(
                    openguard_dir / "knowledge",
                    meta.get("tags", []),
                    new_status,
                )

    return reports


def _update_precondition_status(
    knowledge_dir: Path,
    tags: list[str],
    new_status: str,
) -> None:
    """更新 preconditions.yaml 中对应条目的状态。"""
    data = load_preconditions(knowledge_dir)
    preconds = data.get("preconditions", [])
    tag_set = sorted(tags)
    changed = False
    for pc in preconds:
        if sorted(pc.get("tags", [])) == tag_set:
            pc["status"] = new_status
            changed = True
            break
    if changed:
        data["preconditions"] = preconds
        save_preconditions(knowledge_dir, data)


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────