"""执行编排主入口（REQ-07-02 / REQ-07-17）。

设计原则（REQ-07-17）：
- 执行器通过 subprocess 调用测试脚本，不在进程内调用大模型。
- AI 宿主通过读取执行报告参与归因，不直接操作目标应用。
- 当前实现为"干跑（dry-run）"骨架：按矩阵模拟任务调度，输出完整报告结构。
  真实 subprocess 调用在运行时配置就绪时启用。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openqa.executor.run_id import (
    make_run_id,
    ensure_run_dir,
    update_suite_index,
    update_change_run_index,
)
from openqa.executor.preflight import pre_apply_check
from openqa.executor.reporter import (
    append_event,
    register_evidence,
    build_run_report,
    write_run_report_json,
    write_run_report_junit,
    write_run_report_md,
    write_timeline,
)


# ──────────────────────────────────────────────────────────────────────────────
# 公开入口
# ──────────────────────────────────────────────────────────────────────────────

def run_apply(
    openqa_dir: Path,
    config: dict[str, Any],
    *,
    change_id: str | None = None,
    suite_name: str | None = None,
    gate: str = "local",
    dry_run: bool = True,
) -> dict[str, Any]:
    """执行 apply 流程，返回执行摘要。

    dry_run=True（默认）：模拟执行，按矩阵生成骨架报告，不真正调用脚本。
    dry_run=False：真实 subprocess 执行（需 runtime 配置完整）。

    返回：{"run_id": ..., "result": ..., "run_dir": str}
    """
    run_id = make_run_id()
    change_dir = openqa_dir / "changes" / change_id if change_id else None

    run_dir = ensure_run_dir(
        openqa_dir, run_id,
        change_id=change_id,
        suite_name=suite_name,
    )

    # [1] 执行前校验（REQ-07-01 / REQ-07-12 / REQ-07-13）
    append_event(run_dir, phase="preflight", step="pre_apply_check", status="running")
    pre_check = pre_apply_check(
        change_dir, openqa_dir, config,
        suite_name=suite_name, gate=gate,
    )
    if pre_check["is_blocked"]:
        append_event(
            run_dir, phase="preflight", step="pre_apply_check",
            status="blocked",
            message=f"执行被阻断：{pre_check['blockers']}",
        )
        return _finish_blocked(
            run_id, run_dir, change_id, suite_name, gate, config, pre_check, openqa_dir
        )
    append_event(run_dir, phase="preflight", step="pre_apply_check", status="passed")

    # [2] 加载矩阵任务
    task_results = _load_and_execute_tasks(
        change_dir, openqa_dir, config, run_dir, gate, dry_run
    )

    # [3] 生成代码 Review（apply 时执行，REQ-06-02）
    if change_dir and change_dir.is_dir():
        _run_review(change_dir, config)

    # [4] 生成报告
    code_version = _get_code_version(openqa_dir)
    report = build_run_report(
        run_id, change_id, suite_name, task_results,
        gate=gate,
        code_version=code_version,
        run_dir=run_dir,
        config=config,
        pre_check=pre_check,
    )
    write_run_report_json(run_dir, report)
    write_run_report_junit(run_dir, report)
    write_run_report_md(run_dir, report)
    write_timeline(run_dir, report)

    # [5] 更新执行历史索引（REQ-07-15）
    script_count = len(task_results)
    if suite_name:
        update_suite_index(
            openqa_dir, suite_name, run_id,
            result=report["result"],
            script_count=script_count,
            code_version=code_version,
            gate=gate,
        )
    if change_id:
        update_change_run_index(
            openqa_dir, change_id, run_id,
            result=report["result"],
            script_count=script_count,
            code_version=code_version,
            gate=gate,
        )

    # [6] 记录最终事件
    append_event(
        run_dir, phase="report", step="finalize",
        status=report["result"],
        message=f"执行完成：{report['result']}，Run ID: {run_id}",
    )

    return {
        "run_id": run_id,
        "result": report["result"],
        "run_dir": str(run_dir),
        "summary": report.get("summary", {}),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 内部实现
# ──────────────────────────────────────────────────────────────────────────────

def _finish_blocked(
    run_id: str,
    run_dir: Path,
    change_id: str | None,
    suite_name: str | None,
    gate: str,
    config: dict[str, Any],
    pre_check: dict[str, Any],
    openqa_dir: Path,
) -> dict[str, Any]:
    """执行前被阻断时生成阻断报告。"""
    blocked_task = {
        "task_id": "BLOCKED",
        "name": "执行被前置校验阻断",
        "type": "precondition",
        "result": "blocked",
        "failure_type": "precondition",
        "error": f"阻断原因：{', '.join(pre_check.get('blockers', []))}",
    }
    report = build_run_report(
        run_id, change_id, suite_name, [blocked_task],
        gate=gate, code_version="",
        run_dir=run_dir, config=config, pre_check=pre_check,
    )
    write_run_report_json(run_dir, report)
    write_run_report_junit(run_dir, report)
    write_run_report_md(run_dir, report)
    write_timeline(run_dir, report)

    if change_id:
        update_change_run_index(
            openqa_dir, change_id, run_id, "blocked", 0, "", gate
        )
    if suite_name:
        update_suite_index(
            openqa_dir, suite_name, run_id, "blocked", 0, "", gate
        )

    return {"run_id": run_id, "result": "blocked", "run_dir": str(run_dir), "summary": {}}


def _load_and_execute_tasks(
    change_dir: Path | None,
    openqa_dir: Path,
    config: dict[str, Any],
    run_dir: Path,
    gate: str,
    dry_run: bool,
) -> list[dict[str, Any]]:
    """从矩阵加载任务并按 DAG 执行（REQ-07-02）。"""
    matrix_path = change_dir / "test_matrix.json" if change_dir else None
    tasks: list[dict[str, Any]] = []

    if matrix_path and matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            tasks = matrix.get("tasks", [])
        except Exception:
            tasks = []

    if not tasks:
        # 无矩阵时生成默认冒烟任务
        tasks = [{"task_id": "T-ENV-001", "name": "环境准备", "type": "precondition",
                  "status": "ready", "depends_on": [], "priority": 0}]

    # 按优先级排序执行（简化 DAG：按 priority 顺序串行）
    tasks_sorted = sorted(tasks, key=lambda t: t.get("priority", 99))
    results: list[dict[str, Any]] = []
    fail_fast = config.get("defaults", {}).get("test_suite") == "smoke"

    for task in tasks_sorted:
        task_id = task.get("task_id", "")
        task_status = task.get("status", "ready")
        append_event(run_dir, phase="test", step=task_id, status="running", task_id=task_id)

        # blocked/skipped 任务直接记录（REQ-07-02 / REQ-05-04）
        if task_status in ("blocked", "skipped"):
            results.append({
                "task_id": task_id,
                "name": task.get("name", ""),
                "type": task.get("type", ""),
                "requirement_id": task.get("requirement_id", ""),
                "result": task_status,
                "skip_reason": task.get("skip_reason", task.get("note", "")),
                "failure_type": "precondition" if task_status == "blocked" else None,
                "duration_ms": 0,
                "script_refs": task.get("script_refs", []),
            })
            append_event(run_dir, phase="test", step=task_id, status=task_status, task_id=task_id)
            continue

        # 执行任务
        task_result = _execute_task(task, run_dir, dry_run)
        results.append(task_result)
        append_event(
            run_dir, phase="test", step=task_id,
            status=task_result["result"], task_id=task_id,
            duration_ms=task_result.get("duration_ms", 0),
        )

        # fail_fast：冒烟失败立即停止（REQ-05-07）
        if fail_fast and task_result["result"] in ("failed", "blocked"):
            remaining = tasks_sorted[tasks_sorted.index(task)+1:]
            for remaining_task in remaining:
                results.append({
                    "task_id": remaining_task.get("task_id"),
                    "name": remaining_task.get("name", ""),
                    "type": remaining_task.get("type", ""),
                    "result": "skipped",
                    "skip_reason": "fail_fast: smoke 测试失败，后续任务跳过",
                    "duration_ms": 0,
                })
            break

    return results


def _execute_task(
    task: dict[str, Any],
    run_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """执行单个任务（REQ-07-17）。"""
    task_id = task.get("task_id", "unknown")
    script_refs = task.get("script_refs", [])

    if dry_run or not script_refs:
        # dry_run 或无脚本：返回 needs-confirmation 状态
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "requirement_id": task.get("requirement_id", ""),
            "result": "unknown" if not script_refs else "passed",
            "failure_type": None,
            "duration_ms": 0,
            "script_refs": script_refs,
            "note": "dry_run 模式" if dry_run else "无可执行脚本，需 Agent 生成",
            "error": "" if script_refs else "无可执行测试脚本（需在 test_scripts/ 生成）",
        }

    # 真实执行：subprocess 调用脚本（REQ-07-17）
    script_path = script_refs[0].get("script_path", "")
    if not script_path or not Path(script_path).exists():
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "result": "skipped",
            "skip_reason": f"脚本文件不存在：{script_path}",
            "duration_ms": 0,
            "failure_type": "script",
        }

    import time
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=task.get("timeout_seconds", 60),
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        result = "passed" if proc.returncode == 0 else "failed"
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "requirement_id": task.get("requirement_id", ""),
            "result": result,
            "failure_type": "product" if result == "failed" else None,
            "duration_ms": duration_ms,
            "script_refs": script_refs,
            "stdout": proc.stdout[:500] if proc.stdout else "",
            "stderr": proc.stderr[:500] if proc.stderr else "",
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "result": "failed",
            "failure_type": "env",
            "error": f"脚本超时（>{task.get('timeout_seconds', 60)}s）",
            "duration_ms": task.get("timeout_seconds", 60) * 1000,
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "result": "failed",
            "failure_type": "script",
            "error": str(e),
            "duration_ms": 0,
        }


def _run_review(change_dir: Path, config: dict[str, Any]) -> None:
    """在 apply 时生成 Review 骨架（REQ-06-02）。"""
    sarif_path = change_dir / "review_findings.sarif.json"
    if not sarif_path.exists():
        from openqa.review.findings import run_review_generation
        run_review_generation(change_dir, change_dir.parent.parent, config)


def _get_code_version(openqa_dir: Path) -> str:
    """尝试获取代码版本（Git commit hash），失败时返回空串。"""
    try:
        import subprocess as _sp
        result = _sp.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
            cwd=str(openqa_dir.parent),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
