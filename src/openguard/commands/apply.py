"""``openguard apply`` — 执行代码 Review 与测试矩阵（REQ-07）。

两种模式（REQ-01-06）：
  1. Change 上下文模式（默认）：对当前/指定 change 执行 Review + 测试。
  2. 套件模式（--suite <name>）：无 change 上下文，直接执行全局套件。

执行链路（REQ-07）：
  新鲜度校验 → 脚本状态校验 → 代码 Review → 工具链就绪
  → 应用就绪 → 前置条件 → 验收步骤 → 报告归因

执行器模型（REQ-07-17）：
  - 纯确定性流程编排，不调用大模型。
  - 通过 subprocess 调用测试脚本。
  - AI 宿主通过读取报告参与归因，不直接操作目标应用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from openguard.workspace.layout import require_openguard_dir
from openguard.workspace.change import latest_change


def run_apply(args: argparse.Namespace) -> int:
    try:
        openguard_dir = require_openguard_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # 加载 config
    from openguard.setup.config_writer import load_config
    try:
        config = load_config(openguard_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    suite: str | None = getattr(args, "suite", None)
    gate: str = getattr(args, "gate", None) or config.get("defaults", {}).get("gate", "local")
    test_suite: str | None = getattr(args, "test_suite", None)
    review_level: str = getattr(args, "review_level", None) or config.get("defaults", {}).get("review_level", "changed")
    change_id_arg: str | None = getattr(args, "change_id", None)

    if suite:
        return _run_suite_mode(args, openguard_dir, config, suite, gate)
    return _run_change_mode(args, openguard_dir, config, change_id_arg, gate, test_suite, review_level)


def _run_suite_mode(
    args: argparse.Namespace,
    openguard_dir: Path,
    config: dict[str, Any],
    suite_name: str,
    gate: str,
) -> int:
    """REQ-01-06：无 change 上下文的全局套件执行模式。"""
    from openguard.executor.runner import run_apply as executor_run

    suite_dir = openguard_dir / "suites" / suite_name
    if not suite_dir.is_dir():
        available = _list_suites(openguard_dir)
        print(f"Error: suite '{suite_name}' not found. Available suites: {available}", file=sys.stderr)
        return 1

    print(f"openguard apply --suite {suite_name}")
    print(f"  workspace : {openguard_dir}")
    print(f"  gate      : {gate}")
    print()

    result = executor_run(
        openguard_dir, config,
        suite_name=suite_name,
        gate=gate,
        dry_run=False,
    )

    _print_result(result)
    return 0 if result["result"] in ("passed", "partial") else 1


def _run_change_mode(
    args: argparse.Namespace,
    openguard_dir: Path,
    config: dict[str, Any],
    change_id_arg: str | None,
    gate: str,
    test_suite: str | None,
    review_level: str,
) -> int:
    """默认 change 上下文执行模式。"""
    from openguard.executor.runner import run_apply as executor_run

    # 定位 change
    if change_id_arg:
        change_dir = openguard_dir / "changes" / change_id_arg
        if not change_dir.is_dir():
            print(f"Error: change '{change_id_arg}' not found.", file=sys.stderr)
            return 1
        change_id = change_id_arg
    else:
        change_dir = latest_change(openguard_dir)
        if change_dir is None:
            print("Error: no active change found. Run `openguard run <goal>` first.", file=sys.stderr)
            return 1
        change_id = change_dir.name

    print(f"openguard apply")
    print(f"  workspace    : {openguard_dir}")
    print(f"  change_id    : {change_id}")
    print(f"  test_suite   : {test_suite or '(from config)'}")
    print(f"  review_level : {review_level}")
    print(f"  gate         : {gate}")
    print()

    # 执行链路
    print("Execution pipeline:")
    print("  [1] Freshness check → [2] Script status → [3] Code Review")
    print("  [4] Toolchain ready → [5] Preconditions → [6] Acceptance steps → [7] Attribution")
    print()

    result = executor_run(
        openguard_dir, config,
        change_id=change_id,
        gate=gate,
        dry_run=False,
    )

    _print_result(result)
    return 0 if result["result"] in ("passed", "partial") else 1


def _print_result(result: dict[str, Any]) -> None:
    run_id = result.get("run_id", "")
    exec_result = result.get("result", "unknown")
    summary = result.get("summary", {})
    run_dir = result.get("run_dir", "")

    icon = {"passed": "✅", "failed": "❌", "blocked": "⛔", "partial": "⚠️"}.get(exec_result, "❓")
    print(f"{icon} Result: {exec_result}")
    print(f"  Run ID  : {run_id}")
    if summary:
        print(f"  Passed: {summary.get('passed', 0)}  Failed: {summary.get('failed', 0)}  "
              f"Skipped: {summary.get('skipped', 0)}  Unknown: {summary.get('unknown', 0)}")
    if run_dir:
        print(f"  Report dir: {run_dir}")
    print()
    print("Artifacts: run_report.json / run_report.junit.xml / run_report.md / timeline.md")


def _list_suites(openguard_dir: Path) -> str:
    suites_dir = openguard_dir / "suites"
    if not suites_dir.is_dir():
        return "(none)"
    names = [d.name for d in sorted(suites_dir.iterdir()) if d.is_dir()]
    return ", ".join(names) if names else "(none)"
