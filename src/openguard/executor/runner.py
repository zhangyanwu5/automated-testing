"""执行编排主入口（REQ-07-02 / REQ-07-17 / REQ-16-01）。

设计原则（REQ-07-17）：
- 执行器通过 subprocess 调用测试脚本，不在进程内调用大模型。
- AI 宿主通过读取执行报告参与归因，不直接操作目标应用。
- 执行器根据 runtime.mode 自动启动目标应用（REQ-16-01），无需用户手动操作。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openguard.executor.run_id import (
    make_run_id,
    ensure_run_dir,
    update_suite_index,
    update_change_run_index,
)
from openguard.executor.preflight import pre_apply_check
from openguard.executor.reporter import (
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
    openguard_dir: Path,
    config: dict[str, Any],
    *,
    change_id: str | None = None,
    suite_name: str | None = None,
    gate: str = "local",
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行 apply 流程，返回执行摘要。

    dry_run=False（默认）：真实执行，自动启动应用，调用测试脚本。
    dry_run=True：跳过实际执行，生成骨架报告（仅用于 CI 预检或测试）。

    返回：{"run_id": ..., "result": ..., "run_dir": str}
    """
    run_id = make_run_id()
    change_dir = openguard_dir / "changes" / change_id if change_id else None

    run_dir = ensure_run_dir(
        openguard_dir, run_id,
        change_id=change_id,
        suite_name=suite_name,
    )

    # 事件接收器：将启动器事件写入 events.jsonl
    def event_sink(step: str, status: str, message: str) -> None:
        append_event(run_dir, phase="runtime", step=step, status=status, message=message)

    # [1] 执行前校验（REQ-07-01 / REQ-07-12 / REQ-07-13）
    append_event(run_dir, phase="preflight", step="pre_apply_check", status="running")
    pre_check = pre_apply_check(
        change_dir, openguard_dir, config,
        suite_name=suite_name, gate=gate,
    )
    if pre_check["is_blocked"]:
        append_event(
            run_dir, phase="preflight", step="pre_apply_check",
            status="blocked",
            message=f"执行被阻断：{pre_check['blockers']}",
        )
        return _finish_blocked(
            run_id, run_dir, change_id, suite_name, gate, config, pre_check, openguard_dir
        )
    append_event(run_dir, phase="preflight", step="pre_apply_check", status="passed")

    # [2] 启动目标应用（REQ-16-01，非 dry_run 时）
    launcher = None
    if not dry_run:
        launcher_result = _start_application(
            openguard_dir, config, change_dir, run_dir, event_sink
        )
        if not launcher_result["ok"]:
            # 应用启动失败 → env 类型失败，不执行测试
            task_results = [{
                "task_id": "APP_LAUNCH",
                "name": "目标应用启动",
                "type": "precondition",
                "result": "failed",
                "failure_type": "env",
                "error": launcher_result["error"],
                "duration_ms": 0,
            }]
            launcher_result["launcher"] = None
            return _finish_with_results(
                run_id, run_dir, change_id, suite_name, gate, config,
                pre_check, task_results, openguard_dir
            )
        launcher = launcher_result.get("launcher")

    try:
        # [3] 执行任务矩阵
        task_results = _load_and_execute_tasks(
            change_dir, openguard_dir, config, run_dir, gate, dry_run
        )
    finally:
        # [4] 无论成功失败，都清理应用进程
        if launcher is not None:
            try:
                launcher.stop()
            except Exception:
                pass

    # [5] 生成代码 Review（apply 时执行，REQ-06-02）
    if change_dir and change_dir.is_dir():
        _run_review(change_dir, config)

    return _finish_with_results(
        run_id, run_dir, change_id, suite_name, gate, config,
        pre_check, task_results, openguard_dir
    )


# ──────────────────────────────────────────────────────────────────────────────
# 应用启动
# ──────────────────────────────────────────────────────────────────────────────

def _start_application(
    openguard_dir: Path,
    config: dict[str, Any],
    change_dir: Path | None,
    run_dir: Path,
    event_sink,
) -> dict[str, Any]:
    """根据 runtime.mode 启动目标应用，返回 {"ok": bool, "error": str, "launcher": ...}。"""
    from openguard.launcher import get_launcher

    project_root = openguard_dir.parent

    # 读取 test_knowledge.md 中的 scene_map
    test_knowledge: dict[str, Any] = {}
    if change_dir and (change_dir / "test_knowledge.md").exists():
        test_knowledge = _load_test_knowledge(change_dir / "test_knowledge.md")

    append_event(run_dir, phase="runtime", step="app_launch", status="running",
                 message=f"启动目标应用（mode={config.get('runtime', {}).get('mode', '?')}）…")

    launcher = get_launcher(
        project_root, config, test_knowledge,
        event_sink=event_sink,
    )

    result = launcher.start()
    if result["ok"]:
        append_event(run_dir, phase="runtime", step="app_launch", status="passed",
                     message="目标应用已就绪")
        return {"ok": True, "launcher": launcher}
    else:
        append_event(run_dir, phase="runtime", step="app_launch", status="failed",
                     message=result.get("error", "应用启动失败"))
        return {"ok": False, "error": result.get("error", "应用启动失败"), "launcher": None}


def _load_test_knowledge(tk_path: Path) -> dict[str, Any]:
    """从 test_knowledge.md 读取 YAML front matter（含 scene_map 等字段）。"""
    import yaml as _yaml
    try:
        content = tk_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                return _yaml.safe_load(content[3:end]) or {}
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# 内部实现
# ──────────────────────────────────────────────────────────────────────────────

def _finish_with_results(
    run_id: str,
    run_dir: Path,
    change_id: str | None,
    suite_name: str | None,
    gate: str,
    config: dict[str, Any],
    pre_check: dict[str, Any],
    task_results: list[dict[str, Any]],
    openguard_dir: Path,
) -> dict[str, Any]:
    """生成报告、更新索引、返回摘要。"""
    code_version = _get_code_version(openguard_dir)
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

    script_count = len(task_results)
    if suite_name:
        update_suite_index(
            openguard_dir, suite_name, run_id,
            result=report["result"],
            script_count=script_count,
            code_version=code_version,
            gate=gate,
        )
    if change_id:
        update_change_run_index(
            openguard_dir, change_id, run_id,
            result=report["result"],
            script_count=script_count,
            code_version=code_version,
            gate=gate,
        )

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


def _finish_blocked(
    run_id: str,
    run_dir: Path,
    change_id: str | None,
    suite_name: str | None,
    gate: str,
    config: dict[str, Any],
    pre_check: dict[str, Any],
    openguard_dir: Path,
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
    return _finish_with_results(
        run_id, run_dir, change_id, suite_name, gate, config,
        pre_check, [blocked_task], openguard_dir
    )


def _load_and_execute_tasks(
    change_dir: Path | None,
    openguard_dir: Path,
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
            tasks = matrix.get("tasks", matrix.get("cases", []))
        except Exception:
            tasks = []

    if not tasks:
        tasks = [{"task_id": "T-ENV-001", "name": "环境准备", "type": "precondition",
                  "status": "ready", "depends_on": [], "priority": 0}]

    tasks_sorted = sorted(tasks, key=lambda t: t.get("priority", 99))
    results: list[dict[str, Any]] = []
    fail_fast = config.get("defaults", {}).get("test_suite") == "smoke"

    for task in tasks_sorted:
        task_id = task.get("task_id", "")
        task_status = task.get("status", "ready")
        append_event(run_dir, phase="test", step=task_id, status="running", task_id=task_id)

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

        task_result = _execute_task(task, run_dir, dry_run)
        results.append(task_result)
        append_event(
            run_dir, phase="test", step=task_id,
            status=task_result["result"], task_id=task_id,
            duration_ms=task_result.get("duration_ms", 0),
        )

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

    if dry_run:
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "requirement_id": task.get("requirement_id", ""),
            "result": "unknown",
            "failure_type": None,
            "duration_ms": 0,
            "script_refs": script_refs,
            "note": "dry_run 模式，跳过真实执行",
        }

    if not script_refs:
        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "requirement_id": task.get("requirement_id", ""),
            "result": "unknown",
            "failure_type": None,
            "duration_ms": 0,
            "script_refs": [],
            "error": "无可执行测试脚本（需在 test_scripts/ 生成）",
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
    timeout_s: int = task.get("timeout_seconds", 60)

    # 以 Popen 代替 subprocess.run，以便超时后能读取 waiting_for.json 再 kill
    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)

            # 读取脚本上报的"等待状态"文件，区分超时类型
            waiting_for = _read_waiting_for(run_dir)
            if waiting_for:
                failure_type = "target_timeout"
                error_msg = (
                    f"脚本等待测试目标超时（>{timeout_s}s）。"
                    f"等待状态：{waiting_for.get('waiting_for', '未知')}，"
                    f"详情：{waiting_for.get('detail', '')}"
                )
            else:
                failure_type = "script_timeout"
                error_msg = (
                    f"脚本执行超时（>{timeout_s}s），且无等待状态上报。"
                    f"可能是脚本本身死循环或逻辑错误。"
                )

            return {
                "task_id": task_id,
                "name": task.get("name", ""),
                "type": task.get("type", ""),
                "requirement_id": task.get("requirement_id", ""),
                "result": "failed",
                "failure_type": failure_type,
                "error": error_msg,
                "waiting_for": waiting_for,
                "duration_ms": duration_ms,
                "script_refs": script_refs,
                "stdout": (stdout or "")[:500],
                "stderr": (stderr or "")[:500],
            }

        duration_ms = int((time.monotonic() - start) * 1000)
        result = "passed" if proc.returncode == 0 else "failed"

        # 完整输出写入独立文件（供诊断），报告中只保留尾部摘要
        _write_script_output(run_dir, task_id, stdout or "", stderr or "")

        return {
            "task_id": task_id,
            "name": task.get("name", ""),
            "type": task.get("type", ""),
            "requirement_id": task.get("requirement_id", ""),
            "result": result,
            "failure_type": "product" if result == "failed" else None,
            "duration_ms": duration_ms,
            "script_refs": script_refs,
            "stdout_tail": (stdout or "")[-2000:],   # 尾部 2KB 摘要，供 AI 快速定位
            "stderr_tail": (stderr or "")[-2000:],
            "output_file": f"script_output/{task_id}.txt",  # 完整输出的路径引用
            "returncode": proc.returncode,
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
        from openguard.review.findings import run_review_generation
        run_review_generation(change_dir, change_dir.parent.parent, config)


def _write_script_output(run_dir: Path, task_id: str, stdout: str, stderr: str) -> None:
    """将测试脚本的完整输出写入 run_dir/script_output/<task_id>.txt。

    格式：
      === STDOUT ===
      <stdout 全文>
      === STDERR ===
      <stderr 全文>

    供诊断使用，写入失败静默处理（不影响主流程）。
    """
    try:
        out_dir = run_dir / "script_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)
        out_file = out_dir / f"{safe_id}.txt"
        content = f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}\n"
        out_file.write_text(content, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _read_waiting_for(run_dir: Path) -> dict[str, Any] | None:
    """读取测试脚本上报的等待状态文件（waiting_for.json）。

    测试脚本约定：在等待游戏/服务特定状态时，向 run_dir/waiting_for.json 写入：
      {"waiting_for": "<状态名>", "since": "<ISO时间>", "detail": "<可选补充>"}
    等待结束（无论成功或失败）后删除该文件。

    Runner 在超时后读取此文件：
    - 文件存在 → 测试目标响应超时（target_timeout），而非脚本自身问题
    - 文件不存在 → 脚本可能本身死循环或逻辑错误（script_timeout）

    返回文件内容 dict，或 None（文件不存在/解析失败）。
    """
    import json as _json
    waiting_file = run_dir / "waiting_for.json"
    if not waiting_file.exists():
        return None
    try:
        return _json.loads(waiting_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_code_version(openguard_dir: Path) -> str:
    """尝试获取代码版本（Git commit hash），失败时返回空串。"""
    try:
        import subprocess as _sp
        result = _sp.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
            cwd=str(openguard_dir.parent),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
