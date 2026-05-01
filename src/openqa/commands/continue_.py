"""``openqa continue`` — 手动恢复别名，映射到 openqa _advance 逻辑。

此文件保留向后兼容。新代码请使用 commands/advance.py。
"""
from openqa.commands.advance import run_advance as run_continue

__all__ = ["run_continue"]
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
    PHASE_CONTINUE,
    NEXT_APPLY,
    NEXT_CONTINUE,
    PHASE_APPLY,
)
from openqa.prompts import get_hint as _get_hint

# 状态机步骤列表（按当前语言，缺失 fallback 到 en）
_STEPS = _get_hint("CONTINUE_STEPS")


def _artifact_is_ready(change_dir: Path, artifact: str) -> bool:
    """判断产物是否已生成且不为骨架。"""
    import json as _json
    path = change_dir / artifact
    if not path.exists():
        return False
    # JSON 产物检查 status 字段
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
        from openqa.workspace.change import _append_operation_log
        try:
            snap_path, delta_path = execute_scan(change_dir, openqa_dir, config, scan_scope)
            outputs = [snap_path.name]
            if delta_path:
                outputs.append(delta_path.name)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_CONTINUE,
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
        from openqa.workspace.change import _append_operation_log
        try:
            path = run_impact_analysis(change_dir, openqa_dir, config)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_CONTINUE,
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
        from openqa.workspace.change import _append_operation_log
        test_suite = state.get("strategy", {}).get("test_suite") or None
        try:
            path = run_matrix_generation(change_dir, openqa_dir, config, test_suite)
            _append_operation_log(
                change_dir,
                change_id=change_dir.name,
                phase=PHASE_CONTINUE,
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
    """检查 unknowns.md 是否包含未解决项（含真实数据的表格行）。

    判断规则：
    - 存在表格数据行（非表头、非分隔行、非注释占位行）
    - 行内容不含 '<!--' 占位注释
    """
    unknowns_path = change_dir / "unknowns.md"
    if not unknowns_path.exists():
        return False
    content = unknowns_path.read_text(encoding="utf-8")
    import re
    for line in content.splitlines():
        # 必须是表格行（以 | 开头和结尾）
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # 排除表头行（中文"编号"/"问题"，英文"#"/"Question"/"-"占位）
        if any(h in cells[0] for h in ("编号", "ID", "---", ":---", "#")):
            continue
        # 排除分隔行
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue
        # 排除注释占位行
        if any("<!--" in c for c in cells):
            continue
        # 有实际内容的数据行
        if any(c for c in cells):
            return True
    return False


def run_continue(args: argparse.Namespace) -> int:
    try:
        openqa_dir = require_openqa_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # 定位目标 change
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
                "Error: no active change found. Run `openqa new <goal>` first.",
                file=sys.stderr,
            )
            return 1

    try:
        state = load_state(change_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    change_id: str = state["change_id"]
    print(f"openqa continue")
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
            state["phase"] = PHASE_CONTINUE
            state["updated_at"] = _now_iso()
            still_missing = [a for a, _, _, _ in _STEPS if not _artifact_is_ready(change_dir, a)]
            state["missing_artifacts"] = still_missing
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
                phase=PHASE_CONTINUE,
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

        state["phase"] = PHASE_CONTINUE
        state["next_step"] = NEXT_CONTINUE
        state["agent_action"] = "generate"          # AI 需生成该产物
        still_missing = [
            a for a, _, _, _ in _STEPS
            if not _artifact_is_ready(change_dir, a)
        ]
        state["missing_artifacts"] = still_missing
        save_state(change_dir, state)

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_CONTINUE,
            step="check_artifacts",
            status="passed",
            decision=f"missing artifact: {next_artifact}, waiting for agent",
            outputs=[],
        )

    elif has_unknowns:
        print(_get_hint("UNKNOWNS_HINT"))
        print()

        state["phase"] = PHASE_CONTINUE
        state["next_step"] = NEXT_CONTINUE
        state["agent_action"] = "resolve"           # AI 需解决 unknowns
        state["blockers"] = ["unresolved_unknowns"]
        save_state(change_dir, state)

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_CONTINUE,
            step="check_unknowns",
            status="blocked",
            decision="unresolved unknowns block execution",
        )

    else:
        print(_get_hint("READY_FOR_APPLY"))

        state["phase"] = PHASE_APPLY
        state["next_step"] = NEXT_APPLY
        state["agent_action"] = "run_cli"           # AI 直接执行 openqa apply
        state["missing_artifacts"] = []
        state["blockers"] = []
        save_state(change_dir, state)

        update_artifact_index(change_dir, "state.yaml")

        _append_operation_log(
            change_dir,
            change_id=change_id,
            phase=PHASE_CONTINUE,
            step="check_artifacts",
            status="passed",
            decision="all required artifacts ready, advancing to apply phase",
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
    # 找下一个缺失的非自动产物
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
        state["missing_artifacts"] = [a for a, _, _, _ in _STEPS if not _artifact_is_ready(change_dir, a)]
        state["phase"] = PHASE_CONTINUE
        state["next_step"] = NEXT_CONTINUE
        state["agent_action"] = "generate"
        save_state(change_dir, state)
    elif has_unknowns:
        print(_get_hint("ADVANCE_UNKNOWNS_HINT"))
        state["blockers"] = ["unresolved_unknowns"]
        state["phase"] = PHASE_CONTINUE
        state["next_step"] = NEXT_CONTINUE
        state["agent_action"] = "resolve"
        save_state(change_dir, state)
    else:
        print(_get_hint("READY_FOR_APPLY"))
        state["phase"] = PHASE_APPLY
        state["next_step"] = NEXT_APPLY
        state["agent_action"] = "run_cli"
        state["missing_artifacts"] = []
        state["blockers"] = []
        save_state(change_dir, state)
        update_artifact_index(change_dir, "state.yaml")

    return 0


