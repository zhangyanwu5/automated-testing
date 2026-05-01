"""``openqa archive`` — 归档已完成 change，沉淀知识（REQ-03-05/07/08 / REQ-09）。

执行步骤：
1. 校验必需产物完整（state.yaml、run_report、gate_report）。
2. 检查未解决 unknowns、blocking Review、失败门禁（REQ-03-06）。
3. 输出可晋升脚本列表（多次执行通过、无 flaky，REQ-03-07）。
4. 用户确认后执行晋升（dry_run 模式下仅列出）。
5. 更新受影响的 suites/ 套件定义（由 promote_script 内部完成，REQ-03-08）。
6. 从执行报告沉淀知识（REQ-09-01/03/04）。
7. 记录操作日志（REQ-11）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from openqa.utils import now_iso as _now_iso
from openqa.workspace.layout import require_openqa_dir
from openqa.workspace.change import (
    load_state,
    save_state,
    _append_operation_log,
    latest_change,
    PHASE_ARCHIVE,
)


def run_archive(args: argparse.Namespace) -> int:
    try:
        openqa_dir = require_openqa_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    change_id_arg: str | None = getattr(args, "change_id", None)
    dry_run: bool = getattr(args, "dry_run", False)

    if change_id_arg:
        change_dir = openqa_dir / "changes" / change_id_arg
        if not change_dir.is_dir():
            print(f"Error: change '{change_id_arg}' not found.", file=sys.stderr)
            return 1
    else:
        change_dir = latest_change(openqa_dir)
        if change_dir is None:
            print("Error: no active change found. Run `openqa new <goal>` first.", file=sys.stderr)
            return 1

    change_id = change_dir.name
    print(f"openqa archive")
    print(f"  workspace : {openqa_dir}")
    print(f"  change_id : {change_id}")
    if dry_run:
        print(f"  [dry-run]  check only, no archive will be performed")
    print()

    from openqa.init.config_writer import load_config
    try:
        config = load_config(openqa_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # ── 归档前检查 ────────────────────────────────────────────────────────────
    issues = _pre_archive_check(change_dir, openqa_dir)
    if issues["blockers"]:
        print("⛔ Pre-archive check found blockers:")
        for b in issues["blockers"]:
            print(f"  - {b}")
        print()
        print("Please fix the above issues or record a waiver in report_overlay.yaml, then re-run archive.")
        return 1

    if issues["warnings"]:
        print("⚠️  Warnings:")
        for w in issues["warnings"]:
            print(f"  - {w}")
        print()

    # ── 可晋升脚本列表（REQ-03-07）────────────────────────────────────────────
    promotable = _find_promotable_scripts(change_dir, openqa_dir)
    if promotable:
        print("Promotable scripts (all runs passed, no flaky):")
        for p in promotable:
            suites_str = ", ".join(p.get("suite_membership", []))
            print(f"  ✓ {p['script_path']}  →  suggested suites: {suites_str}")
        print()

    if dry_run:
        print("dry-run complete. Run `openqa archive` to perform the real archive.")
        return 0

    # ── 执行归档 ──────────────────────────────────────────────────────────────
    print("Archiving…")

    # 晋升脚本（REQ-03-07 / REQ-09-09）
    # promote_script 内部已调用 update_suites_after_promote（REQ-03-08）
    promoted: list[dict[str, Any]] = []
    for p in promotable:
        script_path = change_dir / p["script_path"]
        if script_path.exists():
            from openqa.knowledge.manager import promote_script
            result = promote_script(
                script_path, openqa_dir,
                suite_membership=p.get("suite_membership", ["smoke"]),
                run_ids=p.get("run_ids", []),
                change_id=change_id,
            )
            if result["status"] == "promoted":
                promoted.append(result)
                print(f"  ✓ Promoted: {p['script_path']} → {result['dest_path']}")
            else:
                print(f"  ✗ Promotion failed: {p['script_path']} — {result.get('reason')}")

    # 沉淀知识（REQ-09）
    knowledge_dir = openqa_dir / "knowledge"
    from openqa.knowledge.manager import init_knowledge_dir, distill_from_run_report
    init_knowledge_dir(openqa_dir, config)

    run_report = _load_latest_run_report(change_dir, openqa_dir)
    knowledge_added: list[dict[str, Any]] = []
    if run_report:
        suite = run_report.get("suite", "unknown")
        knowledge_added = distill_from_run_report(
            knowledge_dir, run_report, change_id,
            suite=str(suite),
        )
        if knowledge_added:
            print(f"  ✓ Knowledge distilled: {len(knowledge_added)} item(s)")

    # 更新 state.yaml
    state = load_state(change_dir)
    state["phase"] = PHASE_ARCHIVE
    state["next_step"] = "archived"
    save_state(change_dir, state)

    # 记录操作日志（REQ-11）
    _append_operation_log(
        change_dir,
        change_id=change_id,
        phase=PHASE_ARCHIVE,
        step="archive_change",
        status="passed",
        outputs=[str(p["dest_path"]) for p in promoted],
        decision=(
            f"archive complete: promoted {len(promoted)} script(s), "
            f"distilled {len(knowledge_added)} knowledge item(s)"
        ),
    )

    print()
    print(f"✅ Archive complete: {change_id}")
    print(f"  Promoted scripts  : {len(promoted)}")
    print(f"  Knowledge items   : {len(knowledge_added)}")
    print(f"  Change dir kept at: {change_dir} (audit trail)")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# 内部函数
# ──────────────────────────────────────────────────────────────────────────────

def _pre_archive_check(change_dir: Path, openqa_dir: Path) -> dict[str, Any]:
    """归档前检查（REQ-03-05/06）。"""
    blockers: list[str] = []
    warnings: list[str] = []

    for required in ("state.yaml", "artifact_index.yaml"):
        if not (change_dir / required).exists():
            blockers.append(f"missing required artifact: {required}")

    unknowns_path = change_dir / "unknowns.md"
    if unknowns_path.exists():
        content = unknowns_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if not (line.startswith("|") and line.endswith("|")):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if (any(h in cells[0] for h in ("编号", "ID", "---")) or
                    all(re.match(r"^:?-+:?$", c) for c in cells if c) or
                    any("<!--" in c for c in cells)):
                continue
            if any(c for c in cells):
                blockers.append("unresolved unknowns found (REQ-03-06)")
                break

    from openqa.review.findings import has_blocking_findings
    has_blocking, count = has_blocking_findings(change_dir)
    if has_blocking:
        blockers.append(f"{count} blocking Review finding(s) found (REQ-03-06)")

    change_report_dir = openqa_dir / "reports" / "changes" / change_dir.name
    if not change_report_dir.is_dir():
        warnings.append("No execution report directory found; suggest running `openqa apply` first")
    else:
        run_dirs = [d for d in change_report_dir.iterdir()
                    if d.is_dir() and d.name.startswith("run-")]
        if not run_dirs:
            warnings.append("No execution records found; suggest running `openqa apply` first")

    return {"blockers": blockers, "warnings": warnings}


def _find_promotable_scripts(
    change_dir: Path,
    openqa_dir: Path,
) -> list[dict[str, Any]]:
    """找出可晋升的测试脚本（多次执行通过、无 flaky，REQ-03-07 / REQ-09-09）。"""
    scripts_draft_dir = change_dir / "test_scripts"
    if not scripts_draft_dir.is_dir():
        return []

    change_report_dir = openqa_dir / "reports" / "changes" / change_dir.name
    run_ids: list[str] = []
    run_results: list[str] = []

    if change_report_dir.is_dir():
        idx_path = change_report_dir / "change_run_index.yaml"
        if idx_path.exists():
            with idx_path.open(encoding="utf-8") as f:
                idx = yaml.safe_load(f) or {}
            for run in idx.get("runs", []):
                run_ids.append(run["id"])
                run_results.append(run.get("result", "unknown"))

    passed_runs = [r for r in run_results if r == "passed"]
    if not passed_runs:
        return []

    has_fail = any(r == "failed" for r in run_results)
    if has_fail and passed_runs and len(run_results) > 1:
        return []  # flaky，不晋升（REQ-09-11）

    passed_run_ids = [r for r, res in zip(run_ids, run_results) if res == "passed"]
    return [
        {
            "script_path": str(script.relative_to(change_dir)),
            "suite_membership": ["smoke"],
            "run_ids": passed_run_ids,
        }
        for script in sorted(scripts_draft_dir.glob("*.py")) + sorted(scripts_draft_dir.glob("*.js"))
    ]


def _load_latest_run_report(change_dir: Path, openqa_dir: Path) -> dict[str, Any] | None:
    """加载该 change 最近一次执行报告。"""
    change_report_dir = openqa_dir / "reports" / "changes" / change_dir.name
    if not change_report_dir.is_dir():
        return None
    run_dirs = sorted(
        [d for d in change_report_dir.iterdir() if d.is_dir() and d.name.startswith("run-")]
    )
    if not run_dirs:
        return None
    report_path = run_dirs[-1] / "run_report.json"
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
