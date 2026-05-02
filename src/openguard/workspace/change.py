"""change 工作区管理：ID 生成、目录创建、骨架产物写入、状态读写。

每次 `openguard run` 都会在 openguard/changes/<change-id>/ 下创建完整工作区。
骨架产物由本模块生成，Agent 宿主后续填充实质内容。

产物清单（REQ-03 工作区）：
  artifact_index.yaml   – 本 change 产物清单
  intent.md             – 目标、范围、来源
  requirements.md       – EARS 验收项（骨架）
  state.yaml            – 当前阶段与驱动循环指令
  unknowns.md           – 待补充项（骨架）
  snapshot.json         – 事实快照（骨架，待扫描器填充）
  delta.json            – 增量变化（骨架）
  operation_log.jsonl   – 操作事件流（追加写入）
  test_scripts/         – 草稿脚本目录
  test_fixtures/        – 草稿测试数据目录
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from openguard.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 常量：change 阶段
# ──────────────────────────────────────────────────────────────────────────────

# phase 枚举（REQ-03）
PHASE_PREPARING       = "preparing"        # AI 正在生成准备产物
PHASE_READY_FOR_APPLY = "ready_for_apply"  # 产物就绪，等待用户确认执行
PHASE_RUNNING         = "running"          # apply 执行中
PHASE_DONE            = "done"             # apply 完成
PHASE_ARCHIVED        = "archived"         # 已归档

# 向后兼容别名（仅供旧代码过渡期使用）
PHASE_NEW      = PHASE_PREPARING
PHASE_CONTINUE = PHASE_PREPARING
PHASE_APPLY    = PHASE_RUNNING
PHASE_ARCHIVE  = PHASE_ARCHIVED

# agent_action 枚举
AGENT_ACTION_GENERATE   = "generate"    # AI 需生成 missing 中的产物
AGENT_ACTION_RUN_CLI    = "run_cli"     # AI 直接调用 next_cli
AGENT_ACTION_RESOLVE    = "resolve"     # AI 处理 unknowns.md
AGENT_ACTION_WAIT_USER  = "wait_user"   # 停止，等待用户决策
AGENT_ACTION_DONE       = "done"        # 全部完成

# next_cli 值
NEXT_CLI_ADVANCE = "openguard _advance"
NEXT_CLI_APPLY   = "openguard apply"

# 向后兼容：next_step 建议值
NEXT_CONTINUE = NEXT_CLI_ADVANCE
NEXT_APPLY    = NEXT_CLI_APPLY
NEXT_ARCHIVE  = "openguard archive"

# 产物列表（用于 artifact_index.yaml 和 state.yaml 的 required_artifacts）
REQUIRED_ARTIFACTS: list[str] = [
    "intent.md",
    "requirements.md",
    "state.yaml",
    "snapshot.json",
    "delta.json",
    "impact_graph.json",
    "test_knowledge.md",
    "review_plan.md",
    "test_matrix.json",
]


# ──────────────────────────────────────────────────────────────────────────────
# change-id 生成
# ──────────────────────────────────────────────────────────────────────────────

def make_change_id(target: str) -> str:
    """根据目标描述生成稳定、易读的 change-id。

    格式：chg-<YYYYMMDD>-<slug>
    slug 取目标文本前 32 个字母数字字符（小写），不足则补 uuid 短码。
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")

    # 提取目标中的字母数字作为 slug
    slug_raw = re.sub(r"[^\w]", "-", target.lower())
    slug_raw = re.sub(r"-+", "-", slug_raw).strip("-")
    slug = slug_raw[:32].strip("-") or hashlib.md5(target.encode()).hexdigest()[:8]

    return f"chg-{date_str}-{slug}"


def _unique_change_id(changes_dir: Path, base_id: str) -> str:
    """若 base_id 目录已存在，追加短 uuid 后缀确保唯一。"""
    if not (changes_dir / base_id).exists():
        return base_id
    suffix = uuid.uuid4().hex[:6]
    return f"{base_id}-{suffix}"


# ──────────────────────────────────────────────────────────────────────────────
# 时间戳
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# 骨架产物生成器
# ──────────────────────────────────────────────────────────────────────────────

def _write_intent(
    change_dir: Path,
    target: str,
    from_openspec: str | None,
    scan_scope: str,
    test_suite: str | None,
    created_at: str,
) -> None:
    """写入 intent.md（Markdown + YAML Front Matter）。"""
    from openguard.prompts import get_artifact_fn
    fn = get_artifact_fn("intent_md")
    content = fn(
        change_id=change_dir.name,
        target=target,
        scan_scope=scan_scope,
        created_at=created_at,
        from_openspec=from_openspec,
        test_suite=test_suite,
    )
    (change_dir / "intent.md").write_text(content, encoding="utf-8")


def _write_requirements(change_dir: Path, change_id: str, created_at: str) -> None:
    """写入 requirements.md 骨架（Markdown + EARS）。"""
    from openguard.prompts import get_artifact_fn
    fn = get_artifact_fn("requirements_md")
    (change_dir / "requirements.md").write_text(fn(change_id, created_at), encoding="utf-8")


def _write_state(
    change_dir: Path,
    change_id: str,
    created_at: str,
    scan_scope: str,
    test_suite: str | None,
    missing_artifacts: list[str],
    blockers: list[str] | None = None,
) -> None:
    """写入 state.yaml（REQ-03）。

    agent_action / next_cli 是 AI 驱动循环的核心指令：
      generate   — AI 生成 missing 中的产物，完成后调 next_cli
      run_cli    — AI 直接调用 next_cli
      resolve    — AI 处理 unknowns.md，能自主解答就解答，否则追问用户
      wait_user  — 停止循环，等待用户决策
      done       — 全部完成，停止循环
    """
    state: dict[str, Any] = {
        "schema_version": "openguard/state/v1",
        "change_id": change_id,
        "phase": PHASE_PREPARING,
        "created_at": created_at,
        "updated_at": created_at,
        "scan_scope": scan_scope,
        # AI 驱动循环指令（run 完成后：先跑 _advance 触发初始扫描）
        "agent_action": AGENT_ACTION_RUN_CLI,
        "next_cli": NEXT_CLI_ADVANCE,
        "missing": missing_artifacts,
        "blockers": blockers or [],
        # ready_for_apply 时填充，供 AI 向用户呈现确认摘要
        "summary": None,
        "strategy": {
            "test_suite": test_suite or "(from config)",
            "review_level": "(from config)",
            "gate": "(from config)",
        },
    }
    _write_yaml(change_dir / "state.yaml", state)


def _write_unknowns(change_dir: Path, change_id: str) -> None:
    """写入 unknowns.md 骨架。"""
    from openguard.prompts import get_artifact_fn
    fn = get_artifact_fn("unknowns_md")
    (change_dir / "unknowns.md").write_text(fn(change_id), encoding="utf-8")





def _write_snapshot(
    change_dir: Path,
    change_id: str,
    created_at: str,
    project_root: Path,
    scan_scope: str,
) -> None:
    """写入 snapshot.json 骨架（REQ-03：事实快照，扫描器后续填充）。"""
    snapshot: dict[str, Any] = {
        "schema_version": "openguard/snapshot/v1",
        "change_id": change_id,
        "created_at": created_at,
        "scan_scope": scan_scope,
        "status": "pending",   # pending | complete
        "project_root": str(project_root),
        "requirements": [],    # 扫描器填充：需求文档路径 + 指纹
        "code_files": [],      # 扫描器填充：变更文件路径 + 哈希
        "test_assets": [],     # 扫描器填充：test_assets/ 中已知脚本锚点
        "note": "骨架快照，等待 `openguard continue` 扫描器填充。",
    }
    _write_json(change_dir / "snapshot.json", snapshot)


def _write_delta(change_dir: Path, change_id: str, created_at: str) -> None:
    """写入 delta.json 骨架。"""
    delta: dict[str, Any] = {
        "schema_version": "openguard/delta/v1",
        "change_id": change_id,
        "created_at": created_at,
        "status": "pending",
        "added": [],
        "modified": [],
        "deleted": [],
        "renamed": [],
        "note": "骨架 delta，等待增量扫描填充。",
    }
    _write_json(change_dir / "delta.json", delta)


def _write_artifact_index(
    change_dir: Path,
    change_id: str,
    created_at: str,
    from_openspec: str | None,
) -> None:
    """写入 artifact_index.yaml — 本 change 产物清单（REQ-03）。

    只记录 change 工作区内（openguard/changes/<id>/）的产物。
    执行报告（run_report.*、events.jsonl 等）位于 openguard/reports/changes/<id>/
    不在此索引中，通过 change_run_index.yaml 单独索引（REQ-07-15）。
    """
    # 已在 new 阶段生成的骨架产物
    generated_names = [
        "intent.md", "requirements.md", "state.yaml", "unknowns.md",
        "snapshot.json", "delta.json",
    ]
    artifacts: list[dict[str, Any]] = []
    for name in generated_names:
        path = change_dir / name
        artifacts.append({
            "name": name,
            "path": str(path.relative_to(change_dir)),
            "status": "generated",
            "generated_at": created_at,
        })

    # continue / apply 阶段待生成的产物（change 工作区内）
    pending_names = [
        "impact_graph.json",
        "test_knowledge.md",
        "review_plan.md",
        "test_matrix.json",
        "freshness.json",
        "review_findings.sarif.json",
        "review_report.md",
        "gate_report.yaml",
        "report_overlay.yaml",
    ]
    for name in pending_names:
        artifacts.append({
            "name": name,
            "path": name,
            "status": "pending",
            "generated_at": None,
        })

    index: dict[str, Any] = {
        "schema_version": "openguard/artifact_index/v1",
        "change_id": change_id,
        "created_at": created_at,
        "updated_at": created_at,
        "artifacts": artifacts,
        # 执行报告通过 openguard/reports/changes/<id>/change_run_index.yaml 单独索引
        "reports_dir": f"openguard/reports/changes/{change_id}/",
    }
    if from_openspec:
        index["openspec_change_id"] = from_openspec

    _write_yaml(change_dir / "artifact_index.yaml", index)


def _write_openspec_link(
    change_dir: Path,
    from_openspec: str,
) -> None:
    """通过插件系统写入规格联动文件（REQ-12-04）。

    若有已注册的规格插件，委托插件写入；否则写入基础记录，
    确保 openspec_link.yaml 总是存在（供后续 read_link 消费）。
    """
    from openguard.integrations import get_registry
    provider = get_registry().get_spec_provider()
    if provider.name != "null":
        project_root = change_dir.parent.parent.parent
        provider.write_link(change_dir, from_openspec, project_root)
        return

    # 无插件：写入基础记录
    link: dict[str, Any] = {
        "schema_version": "openguard/openspec_link/v1",
        "change_id": change_dir.name,
        "created_at": _now_iso(),
        "openspec_change_id": from_openspec,
        "status": "linked",
    }
    _write_yaml(change_dir / "openspec_link.yaml", link)


def _append_operation_log(
    change_dir: Path,
    *,
    change_id: str,
    phase: str,
    step: str,
    status: str,
    inputs: dict[str, Any] | None = None,
    outputs: list[str] | None = None,
    decision: str | None = None,
    error: str | None = None,
) -> None:
    """向 operation_log.jsonl 追加一条操作事件（REQ-11）。"""
    event: dict[str, Any] = {
        "event_id": uuid.uuid4().hex[:16],
        "change_id": change_id,
        "phase": phase,
        "step": step,
        "started_at": _now_iso(),
        "ended_at": _now_iso(),
        "inputs": inputs or {},
        "outputs": outputs or [],
        "decision": decision,
        "status": status,
        "evidence_refs": [],
    }
    if error:
        event["error"] = {"message": error}

    log_path = change_dir / "operation_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def create_change(
    openguard_dir: Path,
    target: str,
    *,
    from_openspec: str | None = None,
    scan_scope: str = "auto",
    test_suite: str | None = None,
) -> tuple[str, Path]:
    """创建新的 change 工作区，写入所有骨架产物。

    返回 (change_id, change_dir)。
    """
    from openguard.workspace.layout import ensure_change_subdirs

    changes_dir = openguard_dir / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    base_id = make_change_id(target)
    change_id = _unique_change_id(changes_dir, base_id)
    change_dir = changes_dir / change_id
    change_dir.mkdir(parents=True, exist_ok=True)

    # 创建 test_scripts/ 和 test_fixtures/（REQ-02-04）
    ensure_change_subdirs(change_dir)

    created_at = _now_iso()
    project_root = openguard_dir.parent

    # 写入所有骨架产物
    _write_intent(change_dir, target, from_openspec, scan_scope, test_suite, created_at)
    _write_requirements(change_dir, change_id, created_at)
    _write_unknowns(change_dir, change_id)
    _write_snapshot(change_dir, change_id, created_at, project_root, scan_scope)
    _write_delta(change_dir, change_id, created_at)

    missing = [
        a for a in REQUIRED_ARTIFACTS
        if not (change_dir / a).exists()
    ]
    _write_state(
        change_dir, change_id, created_at, scan_scope, test_suite,
        missing_artifacts=missing,
    )
    _write_artifact_index(change_dir, change_id, created_at, from_openspec)

    # OpenSpec 联动
    if from_openspec:
        _write_openspec_link(change_dir, from_openspec)

    # 记录创建事件
    _append_operation_log(
        change_dir,
        change_id=change_id,
        phase=PHASE_NEW,
        step="create_change",
        status="passed",
        inputs={"target": target, "scan_scope": scan_scope, "from_openspec": from_openspec},
        outputs=[str(p.name) for p in change_dir.iterdir() if p.is_file()],
        decision=f"change 工作区创建完成，next_cli={NEXT_CLI_ADVANCE}",
    )

    return change_id, change_dir


def load_state(change_dir: Path) -> dict[str, Any]:
    """读取 state.yaml，不存在时抛出 FileNotFoundError。"""
    state_path = change_dir / "state.yaml"
    if not state_path.exists():
        raise FileNotFoundError(f"state.yaml 不存在：{state_path}")
    with state_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_state(change_dir: Path, state: dict[str, Any]) -> None:
    """更新 state.yaml，同步更新 updated_at。"""
    state["updated_at"] = _now_iso()
    _write_yaml(change_dir / "state.yaml", state)


def update_artifact_index(
    change_dir: Path,
    artifact_name: str,
    *,
    status: str = "generated",
) -> None:
    """将 artifact_index.yaml 中指定产物标记为 generated。"""
    index_path = change_dir / "artifact_index.yaml"
    if not index_path.exists():
        return
    with index_path.open(encoding="utf-8") as f:
        index = yaml.safe_load(f) or {}

    now = _now_iso()
    index["updated_at"] = now
    for art in index.get("artifacts", []):
        if art["name"] == artifact_name:
            art["status"] = status
            art["generated_at"] = now
            break

    _write_yaml(index_path, index)


def list_active_changes(openguard_dir: Path) -> list[Path]:
    """返回所有含 state.yaml 的活跃 change 目录列表（按名称排序）。"""
    changes_dir = openguard_dir / "changes"
    if not changes_dir.is_dir():
        return []
    return sorted(
        p for p in changes_dir.iterdir()
        if p.is_dir() and (p / "state.yaml").is_file()
    )


def latest_change(openguard_dir: Path) -> Path | None:
    """返回最近创建的活跃 change 目录，无则返回 None。"""
    active = list_active_changes(openguard_dir)
    return active[-1] if active else None


# ──────────────────────────────────────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
