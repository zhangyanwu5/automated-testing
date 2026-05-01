"""知识库管理：初始化、知识项写入/读取、脚本晋升、flaky 治理（REQ-09）。

知识分层（REQ-09 重写）：
  # 项目画像与运行环境
  project_profile.yaml    — 项目结构、宿主形态、技术栈（来自 init-probe）
  control_channels.yaml   — RPC/bridge/输入通道（含运行时验证状态）

  # 游戏接口知识（由 knowledge-scan 建立，绑定代码锚点）（REQ-09-14）
  event_catalog.yaml      — 所有可观察事件名、参数、触发条件
  protocol_catalog.yaml   — 网络协议/RPC 接口定义
  state_schema.yaml       — 核心状态对象字段和类型
  log_patterns.yaml       — 关键日志模式、关键字和含义

  # 前置路径（由首次验证建立，跨 change 复用）（REQ-09-16/17）
  preconditions.yaml      — 已验证的前置准备路径，按状态标签索引

  # 测试执行经验
  test_patterns.yaml      — 已验证测试模式
  assertion_hints.yaml    — 常用断言与状态检查
  failure_taxonomy.yaml   — 失败类型与归因规则
  flaky_rules.yaml        — flaky 用例与处理策略
  review_rules.yaml       — 已验证代码 Review 规则
  baselines_index.yaml    — 截图/状态/性能基线索引

知识项必须包含（REQ-09）：
  source、evidence、confidence、scope、status、expiry_condition、
  created_at、last_verified_at

接口知识条目还必须包含（REQ-09-14）：
  anchor（file_path + symbol + hash）、anchor_last_checked

防止越学越错（REQ-09-07/08/15）：
  - 单次模型输出不得直接晋升
  - inferred 状态接口知识不得用于生成执行测试
  - 代码变更时锚点失效 → needs-review 或 stale
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from openqa.utils import now_iso as _now_iso

# 旧知识文件（保持兼容）
KNOWLEDGE_FILES = [
    "project_profile.yaml",
    "test_patterns.yaml",
    "review_rules.yaml",
    "assertion_hints.yaml",
    "failure_taxonomy.yaml",
    "flaky_rules.yaml",
    "control_channels.yaml",
    "baselines_index.yaml",
]

# 游戏接口知识文件（knowledge-scan 建立，REQ-04-10 / REQ-09-14）
INTERFACE_KNOWLEDGE_FILES = [
    "event_catalog.yaml",
    "protocol_catalog.yaml",
    "state_schema.yaml",
    "log_patterns.yaml",
]

# 接口知识条目状态值
STATUS_INFERRED = "inferred"         # 仅代码分析，不得直接用于执行矩阵
STATUS_VERIFIED = "verified"         # 经过真实执行验证
STATUS_NEEDS_REVIEW = "needs-review" # 锚点变化，待确认
STATUS_STALE = "stale"               # 符号消失或需求变更
STATUS_BROKEN = "broken"             # 完全断裂


# ──────────────────────────────────────────────────────────────────────────────
# 初始化知识库
# ──────────────────────────────────────────────────────────────────────────────

def init_knowledge_dir(openqa_dir: Path, config: dict[str, Any]) -> None:
    """初始化 knowledge/ 目录，写入各文件骨架（REQ-09-08）。

    `openqa init` 生成的项目画像可作为 project_profile.yaml 的初始来源，
    但只有经过执行或人工确认后才晋升为正式知识（REQ-09-08）。
    游戏接口知识文件由 knowledge-scan 按需填充（REQ-04-09）。
    """
    knowledge_dir = openqa_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    now = _now_iso()
    project = config.get("project", {})

    _ensure_yaml(knowledge_dir / "project_profile.yaml", {
        "schema_version": "openqa/knowledge/v1",
        "file": "project_profile",
        "description": "项目结构、宿主形态、技术栈（来自 init-probe，未经执行验证）",
        "items": [{
            "id": "pp-001",
            "key": "project.type",
            "value": project.get("type", "unknown"),
            "source": "openqa_init",
            "evidence": project.get("detected_from", []),
            "confidence": project.get("confidence", "low"),
            "scope": "global",
            "status": "init_only",
            "expiry_condition": "project.type 变更时过期",
            "created_at": now,
            "last_verified_at": now,
        }],
    })

    # 测试执行经验文件
    for fname in ["test_patterns.yaml", "review_rules.yaml", "assertion_hints.yaml",
                  "failure_taxonomy.yaml", "flaky_rules.yaml",
                  "control_channels.yaml", "baselines_index.yaml"]:
        _ensure_yaml(knowledge_dir / fname, {
            "schema_version": "openqa/knowledge/v1",
            "file": fname.replace(".yaml", ""),
            "items": [],
            "note": "知识项必须有 source/evidence/confidence/scope/expiry_condition。"
                    "单次模型输出不得直接晋升（REQ-09-07）。",
        })

    # 游戏接口知识文件（骨架，由 knowledge-scan 按需填充）（REQ-04-09 / REQ-04-10）
    _init_interface_knowledge_files(knowledge_dir, now)

    # 前置路径索引（骨架）（REQ-09-16）
    _ensure_yaml(knowledge_dir / "preconditions.yaml", {
        "schema_version": "openqa/preconditions/v1",
        "description": "已验证的前置准备路径，按状态标签索引（REQ-09-16 / REQ-13-28）。",
        "note": "前置路径必须经过至少一次真实执行验证后才能沉淀（REQ-13-30）。",
        "preconditions": [],
    })


def _init_interface_knowledge_files(knowledge_dir: Path, now: str) -> None:
    """初始化游戏接口知识文件骨架（REQ-04-10）。"""
    interface_descriptions = {
        "event_catalog.yaml": "所有可观察的事件名、参数、触发条件（由 knowledge-scan 提取）",
        "protocol_catalog.yaml": "网络协议/RPC 接口定义（由 knowledge-scan 提取）",
        "state_schema.yaml": "核心状态对象字段和类型（由 knowledge-scan 提取）",
        "log_patterns.yaml": "关键日志模式、关键字和含义（由 knowledge-scan 提取）",
    }
    for fname, description in interface_descriptions.items():
        _ensure_yaml(knowledge_dir / fname, {
            "schema_version": "openqa/knowledge/v1",
            "file": fname.replace(".yaml", ""),
            "description": description,
            "scan_status": "not_scanned",  # not_scanned / scanning / complete
            "last_scanned_at": None,
            "items": [],
            "note": (
                "接口知识条目必须绑定代码锚点（anchor.file_path + anchor.symbol + anchor.hash）。"
                "代码变更时锚点失效，状态降为 needs-review 或 stale（REQ-09-14）。"
                "inferred 状态不得用于生成执行测试（REQ-09-15）。"
            ),
        })


def _ensure_yaml(path: Path, default: dict[str, Any]) -> None:
    """仅在文件不存在时写入骨架。"""
    if not path.exists():
        path.write_text(
            yaml.dump(default, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )




# ──────────────────────────────────────────────────────────────────────────────
# 知识项写入（REQ-09-01~06）
# ──────────────────────────────────────────────────────────────────────────────

def add_knowledge_item(
    knowledge_dir: Path,
    file_name: str,
    item: dict[str, Any],
    *,
    allow_low_confidence: bool = False,
) -> bool:
    """向指定知识文件追加一条知识项。

    低置信度知识只能作建议（REQ-09 防错要求），默认不追加到正式知识库。
    Returns True if added, False if skipped.
    """
    confidence = item.get("confidence", "low")
    if confidence == "low" and not allow_low_confidence:
        return False   # 低置信度不自动晋升（REQ-09 防错）

    # 必须有 source（REQ-09-07）
    if not item.get("source"):
        return False

    # 注入元信息
    now = _now_iso()
    item.setdefault("created_at", now)
    item.setdefault("last_verified_at", now)
    item.setdefault("scope", "global")
    item.setdefault("expiry_condition", "manual")

    path = knowledge_dir / file_name
    if not path.exists():
        return False

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    items: list[dict[str, Any]] = data.get("items", [])
    # 去重（按 id 或 key）
    existing_ids = {i.get("id") or i.get("key") for i in items}
    item_id = item.get("id") or item.get("key")
    if item_id and item_id in existing_ids:
        # 更新已有项
        for i, existing in enumerate(items):
            if (existing.get("id") or existing.get("key")) == item_id:
                items[i] = {**existing, **item, "last_verified_at": now}
                break
    else:
        items.append(item)

    data["items"] = items
    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


# ──────────────────────────────────────────────────────────────────────────────
# 脚本晋升到 test_assets/（REQ-09-09 / REQ-09-10）
# ──────────────────────────────────────────────────────────────────────────────

def promote_script(
    script_src: Path,
    openqa_dir: Path,
    *,
    change_id: str = "",
    bound_symbols: list[dict[str, Any]] | None = None,
    bound_requirements: list[dict[str, Any]] | None = None,
    confidence: str = "medium",
    suite_membership: list[str] | None = None,
    run_ids: list[str] | None = None,
) -> dict[str, Any]:
    """将草稿脚本晋升到 test_assets/scripts/，创建完整 .meta.yaml 锚点（REQ-09-09 / REQ-13-13）。

    必须经过至少一次真实执行（run_ids 非空，REQ-13-23）。
    Returns dict with status and dest_path.
    """
    if not run_ids:
        return {"status": "rejected", "reason": "脚本未经过真实执行验证（REQ-13-23）"}
    if not script_src.exists():
        return {"status": "rejected", "reason": f"脚本文件不存在：{script_src}"}

    scripts_dir = openqa_dir / "test_assets" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    content = script_src.read_bytes()
    anchor_hash = hashlib.sha256(content).hexdigest()[:32]

    dest = scripts_dir / script_src.name
    dest.write_bytes(content)

    suites = suite_membership or ["smoke"]

    # 构建 bound_to 列表（REQ-13-13）
    from openqa.assets.lifecycle import build_full_meta
    meta = build_full_meta(
        script_path=f"test_assets/scripts/{dest.name}",
        anchor_hash=anchor_hash,
        change_id=change_id,
        run_ids=run_ids,
        bound_symbols=list(bound_symbols or []),
        bound_requirements=list(bound_requirements or []),
        suite_membership=suites,
        confidence=confidence,
    )
    meta["script_path"] = f"test_assets/scripts/{dest.name}"
    meta["promoted_at"] = _now_iso()

    meta_path = scripts_dir / f"{script_src.stem}.meta.yaml"
    meta_path.write_text(
        yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # 更新 suite.yaml（REQ-13-04）
    from openqa.assets.lifecycle import update_suites_after_promote
    update_suites_after_promote(
        openqa_dir,
        f"test_assets/scripts/{dest.name}",
        suites,
    )

    return {
        "status": "promoted",
        "dest_path": str(dest),
        "meta_path": str(meta_path),
        "anchor_hash": anchor_hash,
    }


def check_flaky_and_demote(
    openqa_dir: Path,
    script_name: str,
    run_results: list[str],
) -> dict[str, Any]:
    """检查 flaky 并降级脚本状态（REQ-09-11）。

    run_results: list of 'passed' / 'failed'
    - 出现 flaky（有通过也有失败）→ 降为 needs-review，记录 flaky 历史。
    - 已晋升的脚本出现 flaky → 同样降为 needs-review 并写入 flaky_rules.yaml（REQ-09-11）。
    - 单次失败不降级（避免噪音）。
    """
    has_pass = "passed" in run_results
    has_fail = "failed" in run_results
    is_flaky = has_pass and has_fail

    meta_path = openqa_dir / "test_assets" / "scripts" / f"{Path(script_name).stem}.meta.yaml"
    if not meta_path.exists():
        return {"status": "meta_not_found"}

    with meta_path.open(encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    if is_flaky:
        old_status = meta.get("status", "verified")
        meta["status"] = "needs-review"
        meta["flaky_detected_at"] = _now_iso()
        meta["flaky_run_results"] = run_results
        # 累计 flaky 历史
        meta.setdefault("flaky_history", []).append({
            "detected_at": _now_iso(),
            "run_results": run_results,
            "run_count": len(run_results),
            "pass_count": run_results.count("passed"),
            "fail_count": run_results.count("failed"),
        })
        meta_path.write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # 写入 flaky_rules.yaml 知识库（REQ-09-11）
        _record_flaky_in_knowledge(openqa_dir, script_name, run_results, old_status)

        return {
            "status": "demoted_to_needs_review",
            "script": script_name,
            "flaky_history_count": len(meta["flaky_history"]),
        }

    return {"status": "stable", "script": script_name}


def _record_flaky_in_knowledge(
    openqa_dir: Path,
    script_name: str,
    run_results: list[str],
    previous_status: str,
) -> None:
    """将 flaky 信息记录到 knowledge/flaky_rules.yaml（REQ-09-11）。"""
    knowledge_dir = openqa_dir / "knowledge"
    if not knowledge_dir.exists():
        return

    pass_rate = run_results.count("passed") / max(len(run_results), 1)
    fail_rate = run_results.count("failed") / max(len(run_results), 1)

    item: dict[str, Any] = {
        "id": f"flaky-{Path(script_name).stem}-{_now_iso()[:10]}",
        "key": f"flaky.{Path(script_name).stem}",
        "value": (
            f"脚本 {script_name} 检测到 flaky：通过率={pass_rate:.0%}，失败率={fail_rate:.0%}"
            f"（来自 {len(run_results)} 次执行，降级前状态：{previous_status}）"
        ),
        "source": f"flaky_detection:{script_name}",
        "evidence": [script_name],
        "confidence": "high",  # flaky 检测是确定性的
        "scope": f"script={script_name}",
        "expiry_condition": "脚本修复并重新通过多次验证后失效",
        "handling": "隔离重试，降为 needs-review；需 Agent 或人工分析根因后恢复",
        "flaky_stats": {
            "total_runs": len(run_results),
            "pass_count": run_results.count("passed"),
            "fail_count": run_results.count("failed"),
            "pass_rate": round(pass_rate, 3),
        },
    }

    add_knowledge_item(knowledge_dir, "flaky_rules.yaml", item)


def get_flaky_history(openqa_dir: Path, script_name: str) -> list[dict[str, Any]]:
    """读取脚本的 flaky 历史记录。"""
    meta_path = openqa_dir / "test_assets" / "scripts" / f"{Path(script_name).stem}.meta.yaml"
    if not meta_path.exists():
        return []
    try:
        with meta_path.open(encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        return meta.get("flaky_history", [])
    except Exception:
        return []


def should_promote_script(
    openqa_dir: Path,
    script_name: str,
    run_ids: list[str],
    *,
    min_runs: int = 1,
) -> dict[str, Any]:
    """判断脚本是否满足晋升条件（REQ-13-21/22/23）。

    条件：
    - 有至少 min_runs 次真实执行记录（REQ-13-23）
    - 未出现 flaky（REQ-13-22）
    - 在 test_assets/ 中无对应脚本（首次晋升），或锚点状态允许重晋升

    返回：{eligible: bool, reason: str}
    """
    if not run_ids:
        return {"eligible": False, "reason": "无真实执行记录（REQ-13-23）"}
    if len(run_ids) < min_runs:
        return {"eligible": False, "reason": f"执行次数不足（{len(run_ids)}/{min_runs}）（REQ-13-23）"}

    # 检查 flaky 历史
    flaky_history = get_flaky_history(openqa_dir, script_name)
    if flaky_history:
        last_flaky = flaky_history[-1]
        return {
            "eligible": False,
            "reason": (
                f"脚本有 flaky 历史（最近一次：{last_flaky.get('detected_at', '?')}），"
                "不得晋升（REQ-13-22）"
            ),
        }

    return {"eligible": True, "reason": f"满足晋升条件：{len(run_ids)} 次执行通过，无 flaky 记录"}


# ──────────────────────────────────────────────────────────────────────────────
# 从执行报告沉淀知识（REQ-09-01~06 / REQ-09-13）
# ──────────────────────────────────────────────────────────────────────────────

def distill_from_run_report(
    knowledge_dir: Path,
    run_report: dict[str, Any],
    change_id: str,
    suite: str,
) -> list[dict[str, Any]]:
    """从执行报告沉淀知识项（REQ-09-01/03/04）。返回新增知识列表。"""
    added: list[dict[str, Any]] = []
    result = run_report.get("result", "unknown")
    run_id = run_report.get("run_id", "")

    # 成功路径：沉淀稳定断言（REQ-09-01）
    if result == "passed":
        item = {
            "id": f"tp-{run_id[:8]}",
            "key": f"stable_path.{suite}",
            "value": f"suite={suite} 全部通过",
            "source": f"run_report:{run_id}",
            "evidence": [run_id],
            "confidence": "medium",
            "scope": f"suite={suite}",
            "expiry_condition": "suite 配置变更或连续失败",
        }
        if add_knowledge_item(knowledge_dir, "test_patterns.yaml", item):
            added.append(item)

    # 失败模式：沉淀失败分类（REQ-09-03）
    buckets = run_report.get("failure_buckets", {})
    for bucket_type, task_ids in buckets.items():
        if task_ids:
            item = {
                "id": f"ft-{bucket_type}-{run_id[:6]}",
                "key": f"failure.{bucket_type}",
                "value": f"{bucket_type} 类型失败，涉及任务：{task_ids[:3]}",
                "source": f"run_report:{run_id}",
                "evidence": [run_id],
                "confidence": "medium",
                "scope": f"change={change_id}",
                "expiry_condition": "修复后失效",
            }
            if add_knowledge_item(knowledge_dir, "failure_taxonomy.yaml", item):
                added.append(item)

    # 策略选择经验（REQ-09-04）
    item = {
        "id": f"ss-{suite}-{run_id[:6]}",
        "key": f"strategy.{suite}.{result}",
        "value": f"gate={run_report.get('gate')} suite={suite} 结果={result}",
        "source": f"run_report:{run_id}",
        "evidence": [run_id],
        "confidence": "low",  # 单次结果置信度低
        "scope": f"suite={suite}",
        "expiry_condition": "超过 30 次执行后统计可提升置信度",
    }
    add_knowledge_item(knowledge_dir, "test_patterns.yaml", item, allow_low_confidence=True)



    return added


# ──────────────────────────────────────────────────────────────────────────────
# 游戏接口知识条目管理（REQ-09-14 / REQ-04-10~11）
# ──────────────────────────────────────────────────────────────────────────────

def add_interface_knowledge_item(
    knowledge_dir: Path,
    catalog_file: str,
    item: dict[str, Any],
) -> bool:
    """向游戏接口知识文件写入一条条目（REQ-04-10 / REQ-09-14）。

    item 必须包含：
      - id、name（接口/事件/命令名称）
      - anchor: {file_path, symbol, hash}
      - source、confidence、status（默认 inferred）
    inferred 状态条目只能用于生成候选矩阵（REQ-09-15）。
    """
    catalog_path = knowledge_dir / catalog_file
    if not catalog_path.exists():
        return False

    with catalog_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    items: list[dict[str, Any]] = data.get("items", [])
    now = _now_iso()

    # 必须有 anchor（REQ-09-14）
    if not item.get("anchor"):
        return False

    # 注入元信息
    item.setdefault("status", STATUS_INFERRED)
    item.setdefault("created_at", now)
    item.setdefault("last_verified_at", now)
    item.setdefault("anchor_last_checked", now)
    item.setdefault("scope", "global")
    item.setdefault("expiry_condition", "代码锚点符号消失或变更时过期")

    # 去重（按 id 更新）
    existing_ids = {i.get("id") for i in items}
    if item.get("id") and item["id"] in existing_ids:
        for i, existing in enumerate(items):
            if existing.get("id") == item["id"]:
                items[i] = {**existing, **item, "last_verified_at": now}
                break
    else:
        items.append(item)

    data["items"] = items
    data["scan_status"] = "complete"
    data["last_scanned_at"] = now
    catalog_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def check_interface_knowledge_anchors(
    knowledge_dir: Path,
    current_symbols: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """检查所有接口知识条目的锚点有效性（REQ-09-14 / REQ-04-11）。

    返回状态变化报告列表。
    """
    reports: list[dict[str, Any]] = []
    current_symbols = current_symbols or {}

    for catalog_file in INTERFACE_KNOWLEDGE_FILES:
        catalog_path = knowledge_dir / catalog_file
        if not catalog_path.exists():
            continue

        with catalog_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        items: list[dict[str, Any]] = data.get("items", [])
        changed = False

        for item in items:
            anchor = item.get("anchor", {})
            symbol = anchor.get("symbol", "")
            expected_hash = anchor.get("hash", "")
            old_status = item.get("status", STATUS_INFERRED)

            if not symbol or not expected_hash:
                continue

            current_hash = current_symbols.get(symbol, "")
            new_status = old_status

            if not current_hash:
                # 符号消失 → stale（或 broken 如果已是 stale）
                new_status = STATUS_BROKEN if old_status == STATUS_STALE else STATUS_STALE
            elif current_hash != expected_hash:
                # 哈希变化 → needs-review
                if old_status in (STATUS_VERIFIED, STATUS_INFERRED):
                    new_status = STATUS_NEEDS_REVIEW

            if new_status != old_status:
                item["status"] = new_status
                item["anchor_last_checked"] = _now_iso()
                item["anchor_change_detected"] = _now_iso()
                changed = True
                reports.append({
                    "catalog": catalog_file,
                    "item_id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "old_status": old_status,
                    "new_status": new_status,
                    "symbol": symbol,
                })

        if changed:
            data["items"] = items
            catalog_path.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

    return reports


def get_interface_knowledge(
    knowledge_dir: Path,
    catalog_file: str,
    status_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """读取接口知识条目，可按状态过滤（REQ-05-14）。

    注意：inferred 状态条目只能用于候选生成，不得直接用于执行矩阵。
    """
    catalog_path = knowledge_dir / catalog_file
    if not catalog_path.exists():
        return []

    with catalog_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    items = data.get("items", [])
    if status_filter:
        items = [i for i in items if i.get("status") in status_filter]
    return items



