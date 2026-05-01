"""``openqa _advance`` — 内部状态机推进命令（REQ-03-03）。

此命令为内部命令，由 AI 在驱动循环中调用，不出现在 help 或用户文档中。

状态机推进规则：
  缺 intent.md         → 设 agent_action=generate，AI 生成目标说明
  缺 requirements.md   → 设 agent_action=generate，AI 生成 EARS 验收项
  缺 snapshot.json     → 自动执行扫描（REQ-04）
  缺 delta.json        → 自动执行增量扫描（REQ-04）
  缺 impact_graph.json → 自动生成影响分析（REQ-04）
  缺 test_knowledge.md → 设 agent_action=generate，AI 生成测试知识
  缺 review_plan.md    → 设 agent_action=generate，AI 生成 Review 计划
  缺 test_matrix.json  → 自动生成测试矩阵骨架（REQ-05）
  存在未解决 unknowns  → 设 agent_action=resolve
  全部就绪             → 设 phase=ready_for_apply，agent_action=wait_user，填充 summary

设计说明：
- 确定性产物（扫描、影响图、矩阵骨架）由 OpenQA 自动生成；
  推理填充（需求验收、测试知识、Review 计划）由 AI 宿主负责。
- 每次推进都追加 operation_log.jsonl 事件，同步更新新鲜度（REQ-04-05）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from openqa.workspace.layout import require_openqa_dir
from openqa.utils import now_iso as _now_iso
from openqa.workspace.change import (
    latest_change,
    load_state,
    save_state,
    update_artifact_index,
    _append_operation_log,
    PHASE_PREPARING,
    PHASE_READY_FOR_APPLY,
    AGENT_ACTION_GENERATE,
    AGENT_ACTION_RUN_CLI,
    AGENT_ACTION_RESOLVE,
    AGENT_ACTION_WAIT_USER,
    NEXT_CLI_ADVANCE,
    NEXT_CLI_APPLY,
)
from openqa.prompts import get_hint as _get_hint

# 状态机步骤列表（按当前语言，缺失 fallback 到 en）
_STEPS = _get_hint("ADVANCE_STEPS")


def _artifact_is_ready(change_dir: Path, artifact: str) -> bool:
    """判断产物是否已生成且不为骨架。"""
    import json as _json
    path = change_dir / artifact
    if not path.exists():
        return False
    if artifact.endswith(".json"):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            return data.get("status") in ("complete", None)
        except Exception:
            return False
    return True


def _auto_generate(
    artifact: str,
    change_dir: Path,
    openqa_dir: Path,
    state: dict[str, Any],
) -> tuple[bool, str]:
    """自动生成确定性产物，返回 (成功, 消息)。"""
    from openqa.init.config_writer import load_config

    try:
        config = load_config(openqa_dir)
    except FileNotFoundError:
        return False, "config.yaml not found, cannot auto-generate"

    scan_scope = state.get("scan_scope", "auto")

    if artifact in ("snapshot.json", "delta.json"):
        from openqa.scan.scanner import execute_scan
        try:
            snap_path, delta_path = execute_scan(change_dir, openqa_dir, config, scan_scope)
            outputs = [snap_path.name]
            if delta_path:
                outputs.append(delta_path.name)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_PREPARING,
                step=f"auto_scan_{scan_scope}",
                status="passed",
                outputs=outputs,
                decision=f"scan_scope={scan_scope}, auto-scan complete",
            )
            return True, f"Scan complete: {', '.join(outputs)}"
        except Exception as e:
            return False, f"Scan failed: {e}"

    if artifact == "impact_graph.json":
        from openqa.scan.impact import run_impact_analysis
        try:
            path = run_impact_analysis(change_dir, openqa_dir, config)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_PREPARING,
                step="auto_impact_analysis",
                status="passed",
                outputs=[path.name],
                decision="impact graph auto-generated",
            )
            return True, f"Impact analysis complete: {path.name}"
        except Exception as e:
            return False, f"Impact analysis failed: {e}"

    if artifact == "test_matrix.json":
        from openqa.matrix.generator import run_matrix_generation
        test_suite = state.get("strategy", {}).get("test_suite") or None
        try:
            path = run_matrix_generation(change_dir, openqa_dir, config, test_suite)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_PREPARING,
                step="auto_matrix_generation",
                status="passed",
                outputs=[path.name],
                decision=f"test matrix auto-generated, suite={test_suite or 'from config'}",
            )
            return True, f"Test matrix generated: {path.name}"
        except Exception as e:
            return False, f"Test matrix generation failed: {e}"

    return False, f"Auto-generation not supported for: {artifact}"


def _has_unresolved_unknowns(change_dir: Path) -> bool:
    """检查 unknowns.md 是否包含未解决项。"""
    unknowns_path = change_dir / "unknowns.md"
    if not unknowns_path.exists():
        return False
    content = unknowns_path.read_text(encoding="utf-8")
    import re
    for line in content.splitlines():
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if any(h in cells[0] for h in ("编号", "ID", "---", ":---", "#")):
            continue
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue
        if any("<!--" in c for c in cells):
            continue
        if any(c for c in cells):
            return True
    return False


def _build_summary(change_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    """为 ready_for_apply 阶段构建摘要，供 AI 向用户呈现确认信息。"""
    import json as _json

    summary: dict[str, Any] = {
        "cases": 0,
        "review_issues": 0,
        "estimated_minutes": None,
        "notes": [],
    }

    # 统计测试用例数
    matrix_path = change_dir / "test_matrix.json"
    if matrix_path.exists():
        try:
            matrix = _json.loads(matrix_path.read_text(encoding="utf-8"))
            cases = matrix.get("cases", matrix.get("tasks", []))
            summary["cases"] = len([c for c in cases if c.get("status") != "skipped"])
        except Exception:
            pass

    # 统计 Review 问题数
    review_path = change_dir / "review_report.md"
    if review_path.exists():
        content = review_path.read_text(encoding="utf-8")
        import re
        major = len(re.findall(r"### CR-M-\d+", content))
        minor = len(re.findall(r"### CR-N-\d+", content))
        summary["review_issues"] = major + minor
        if major > 0:
            summary["notes"].append(f"{major} major Review issue(s) need attention")

    return summary


def run_advance(args: argparse.Namespace) -> int:
    try:
        openqa_dir = require_openqa_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    change_id_arg: str | None = getattr(args, "change_id", None)
    if change_id_arg:
        change_dir = openqa_dir / "changes" / change_id_arg
        if not change_dir.is_dir():
            print(f"Error: change '{change_id_arg}' not found.", file=sys.stderr)
            return 1
    else:
        change_dir = latest_change(openqa_dir)
        if change_dir is None:
            print(
                "Error: no active change found. Run `openqa run <goal>` first.",
                file=sys.stderr,
            )
            return 1

    try:
        state = load_state(change_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    change_id: str = state["change_id"]
    print(f"openqa _advance")
    print(f"  workspace  : {openqa_dir}")
    print(f"  change_id  : {change_id}")
    print()

    # ── 状态机：找到第一个缺失/未就绪产物 ────────────────────────────────────
    next_artifact: str | None = None
    next_label: str = ""
    next_hint: str = ""
    next_auto: bool = False

    for artifact, label, hint, auto in _STEPS:
        if not _artifact_is_ready(change_dir, artifact):
            next_artifact = artifact
            next_label = label
            next_hint = hint
            next_auto = auto
            break

    # ── 自动生成确定性产物 ────────────────────────────────────────────────────
    if next_artifact and next_auto:
        print(f"Auto-generating: {next_label}…")
        ok, msg = _auto_generate(next_artifact, change_dir, openqa_dir, state)
        if ok:
            print(f"  ✓ {msg}")
            update_artifact_index(change_dir, next_artifact)
            state["phase"] = PHASE_PREPARING
            state["updated_at"] = _now_iso()
            still_missing = [a for a, _, _, _ in _STEPS if not _artifact_is_ready(change_dir, a)]
            state["missing"] = still_missing
            save_state(change_dir, state)
            print(f"  → Continuing…")
            print()
            return _advance_once(change_dir, openqa_dir, state, change_id)
        else:
            print(f"  ✗ Auto-generation failed: {msg}")
            print(_get_hint("AUTO_GENERATE_FAILED"))
            _append_operation_log(
                change_dir,
                change_id=change_id,
                phase=PHASE_PREPARING,
                step=f"auto_generate_{next_artifact}",
                status="failed",
                error=msg,
            )
            return 1

    # ── 检查 unknowns ─────────────────────────────────────────────────────────
    has_unknowns = _has_unresolved_unknowns(change_dir)

    # ── 输出结论 ──────────────────────────────────────────────────────────────
    if next_artifact:
        print(f"Missing: {next_label} ({next_artifact})")
        print()
        print(_get_hint("MISSING_ARTIFACT_HEADER"))
        print(f"  {next_hint}")
        print()

        state["phase"] = PHASE_PREPARING
        state["agent_action"] = AGENT_ACTION_GENERATE
        state["next_cli"] = NEXT_CLI_ADVANCE
        still_missing = [
            a for a, _, _, _ in _STEPS
            if not _artifact_is_ready(change_dir, a)
        ]
        state["missing"] = still_missing
        save_state(change_dir, state)

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_PREPARING,
            step="check_artifacts",
            status="passed",
            decision=f"missing artifact: {next_artifact}, agent_action=generate",
            outputs=[],
        )

    elif has_unknowns:
        print(_get_hint("UNKNOWNS_HINT"))
        print()

        state["phase"] = PHASE_PREPARING
        state["agent_action"] = AGENT_ACTION_RESOLVE
        state["next_cli"] = NEXT_CLI_ADVANCE
        state["blockers"] = ["unresolved_unknowns"]
        save_state(change_dir, state)

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_PREPARING,
            step="check_unknowns",
            status="blocked",
            decision="unresolved unknowns, agent_action=resolve",
        )

    else:
        # 全部就绪 → ready_for_apply
        summary = _build_summary(change_dir, state)
        print(_get_hint("READY_FOR_APPLY"))
        print()
        print(f"  cases          : {summary['cases']}")
        print(f"  review_issues  : {summary['review_issues']}")
        if summary.get("notes"):
            for note in summary["notes"]:
                print(f"  note           : {note}")
        print()

        state["phase"] = PHASE_READY_FOR_APPLY
        state["agent_action"] = AGENT_ACTION_WAIT_USER   # AI 必须停下来等用户确认
        state["next_cli"] = None                          # 等用户确认后才是 openqa apply
        state["missing"] = []
        state["blockers"] = []
        state["summary"] = summary
        save_state(change_dir, state)

        update_artifact_index(change_dir, "state.yaml")

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_PREPARING,
            step="check_artifacts",
            status="passed",
            decision="all artifacts ready, phase=ready_for_apply, agent_action=wait_user",
            outputs=["state.yaml"],
        )

    return 0


def _advance_once(
    change_dir: Path,
    openqa_dir: Path,
    state: dict[str, Any],
    change_id: str,
) -> int:
    """执行一次非自动推进检查（自动生成完成后继续推进用）。"""
    next_artifact = None
    next_label = ""
    next_hint = ""

    for artifact, label, hint, auto in _STEPS:
        if not _artifact_is_ready(change_dir, artifact):
            next_artifact = artifact
            next_label = label
            next_hint = hint
            break

    has_unknowns = _has_unresolved_unknowns(change_dir)

    if next_artifact:
        if not [a for a, _, _, au in _STEPS if a == next_artifact and au][0:1]:
            print(f"Missing: {next_label} ({next_artifact})")
            print()
            print(_get_hint("MISSING_ARTIFACT_HEADER"))
            print(f"  {next_hint}")
        state["missing"] = [a for a, _, _, _ in _STEPS if not _artifact_is_ready(change_dir, a)]
        state["phase"] = PHASE_PREPARING
        state["agent_action"] = AGENT_ACTION_GENERATE
        state["next_cli"] = NEXT_CLI_ADVANCE
        save_state(change_dir, state)
    elif has_unknowns:
        print(_get_hint("ADVANCE_UNKNOWNS_HINT"))
        state["blockers"] = ["unresolved_unknowns"]
        state["phase"] = PHASE_PREPARING
        state["agent_action"] = AGENT_ACTION_RESOLVE
        state["next_cli"] = NEXT_CLI_ADVANCE
        save_state(change_dir, state)
    else:
        summary = _build_summary(change_dir, state)
        print(_get_hint("READY_FOR_APPLY"))
        state["phase"] = PHASE_READY_FOR_APPLY
        state["agent_action"] = AGENT_ACTION_WAIT_USER
        state["next_cli"] = None
        state["missing"] = []
        state["blockers"] = []
        state["summary"] = summary
        save_state(change_dir, state)
        update_artifact_index(change_dir, "state.yaml")

    return 0
