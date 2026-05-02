"""执行报告生成器（REQ-07-05 / REQ-07-06 / REQ-07-08 / REQ-07-10 / REQ-07-11）。

生成：
  run_report.json      — Agent/工具消费的主报告
  run_report.junit.xml — CI 平台展示
  run_report.md        — 人工阅读摘要
  events.jsonl         — 流式事件（追加写入）
  timeline.md          — 过程时间线
  evidence_index.yaml  — 证据索引
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml
from openguard.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 事件流（REQ-07-08）
# ──────────────────────────────────────────────────────────────────────────────

def append_event(
    run_dir: Path,
    *,
    phase: str,
    step: str,
    status: str,
    message: str = "",
    duration_ms: int = 0,
    task_id: str = "",
    evidence_refs: list[str] | None = None,
) -> None:
    """向 events.jsonl 追加一条事件（REQ-07-08）。"""
    event: dict[str, Any] = {
        "event_id": uuid.uuid4().hex[:16],
        "timestamp": _now_iso(),
        "phase": phase,
        "step": step,
        "status": status,
        "duration_ms": duration_ms,
    }
    if message:
        event["message"] = message
    if task_id:
        event["task_id"] = task_id
    if evidence_refs:
        event["evidence_refs"] = evidence_refs

    events_path = run_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# 证据索引（REQ-07-11）
# ──────────────────────────────────────────────────────────────────────────────

def register_evidence(
    run_dir: Path,
    evidence_id: str,
    evidence_type: str,
    path: str,
    *,
    step: str = "",
    hash_value: str = "",
    summary: str = "",
) -> None:
    """向 evidence_index.yaml 登记证据（REQ-07-11）。"""
    index_path = run_dir / "evidence_index.yaml"
    index: dict[str, Any] = {}
    if index_path.exists():
        with index_path.open(encoding="utf-8") as f:
            index = yaml.safe_load(f) or {}

    entries: list[dict[str, Any]] = index.get("entries", [])
    entries.append({
        "id": evidence_id,
        "type": evidence_type,
        "path": path,
        "registered_at": _now_iso(),
        "step": step,
        "hash": hash_value,
        "summary": summary,
    })
    index["entries"] = entries
    index["updated_at"] = _now_iso()

    index_path.write_text(
        yaml.dump(index, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────────────────────────────────────
# 主报告生成（REQ-07-05）
# ──────────────────────────────────────────────────────────────────────────────

def build_run_report(
    run_id: str,
    change_id: str | None,
    suite_name: str | None,
    task_results: list[dict[str, Any]],
    *,
    gate: str = "local",
    code_version: str = "",
    run_dir: Path,
    config: dict[str, Any],
    pre_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 run_report.json 数据（REQ-07-05 / REQ-07-06）。"""
    passed = [t for t in task_results if t.get("result") == "passed"]
    failed = [t for t in task_results if t.get("result") == "failed"]
    skipped = [t for t in task_results if t.get("result") == "skipped"]
    blocked_tasks = [t for t in task_results if t.get("result") == "blocked"]
    unknown = [t for t in task_results if t.get("result") == "unknown"]

    # 失败分桶（REQ-07-03）
    # script_timeout: 脚本本身超时（死循环/逻辑错误）
    # target_timeout: 测试目标响应超时（游戏/服务太慢，脚本在等待中被 kill）
    failure_buckets: dict[str, list[str]] = {
        "env": [], "precondition": [], "script": [],
        "script_timeout": [], "target_timeout": [],
        "product": [], "data": [], "unknown": [],
    }
    for t in failed + unknown:
        bucket = t.get("failure_type", "unknown")
        failure_buckets.setdefault(bucket, []).append(t.get("task_id", ""))

    # 整体结论
    if pre_check and pre_check.get("is_blocked"):
        overall = "blocked"
    elif failed or unknown:
        overall = "failed"
    elif skipped or blocked_tasks:
        overall = "partial"
    else:
        overall = "passed"

    # 收集证据引用
    evidence_index_path = run_dir / "evidence_index.yaml"
    evidence_refs: list[dict[str, Any]] = []
    if evidence_index_path.exists():
        with evidence_index_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f) or {}
            evidence_refs = idx.get("entries", [])

    report: dict[str, Any] = {
        "schema_version": "openguard/run_report/v1",
        "run_id": run_id,
        "suite": suite_name or change_id,
        "change_id": change_id,
        "generated_at": _now_iso(),
        "gate": gate,
        "code_version": code_version,
        "result": overall,
        "summary": {
            "total": len(task_results),
            "passed": len(passed),
            "failed": len(failed),
            "skipped": len(skipped),
            "blocked": len(blocked_tasks),
            "unknown": len(unknown),
        },
        "runtime": {
            "status": config.get("runtime", {}).get("status", "unknown"),
            "mode": config.get("runtime", {}).get("mode"),
        },
        "precondition": {
            "result": "passed" if not (pre_check or {}).get("is_blocked") else "failed",
            "blockers": (pre_check or {}).get("blockers", []),
        },
        "acceptance": task_results,
        "failure_buckets": {k: v for k, v in failure_buckets.items() if v},
        "evidence_refs": evidence_refs[:20],  # 摘要引用，不内嵌大对象
        "attribution_hints": [],  # 由 Agent overlay 填充
        "trace_refs": {
            "events_jsonl": str((run_dir / "events.jsonl").relative_to(run_dir.parent.parent.parent)
                                if run_dir.parent.parent.parent.exists() else "events.jsonl"),
            "timeline_md": "timeline.md",
            "operation_log": str(Path(change_id or "change") / "operation_log.jsonl")
                             if change_id else "",
        },
        "pre_check": pre_check,
    }
    return report


def write_run_report_json(run_dir: Path, report: dict[str, Any]) -> Path:
    path = run_dir / "run_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_run_report_junit(run_dir: Path, report: dict[str, Any]) -> Path:
    """生成 JUnit XML（REQ-07-05）。"""
    summary = report.get("summary", {})
    run_id = report.get("run_id", "unknown")
    suite_name = report.get("suite", "openguard")

    testsuite = ET.Element("testsuite", {
        "name": suite_name,
        "tests": str(summary.get("total", 0)),
        "failures": str(summary.get("failed", 0)),
        "errors": str(summary.get("unknown", 0)),
        "skipped": str(summary.get("skipped", 0) + summary.get("blocked", 0)),
        "timestamp": report.get("generated_at", _now_iso()),
        "id": run_id,
    })

    for task in report.get("acceptance", []):
        tc = ET.SubElement(testsuite, "testcase", {
            "name": task.get("name", task.get("task_id", "unknown")),
            "classname": task.get("type", "openguard"),
            "time": str(task.get("duration_ms", 0) / 1000.0),
        })
        result = task.get("result", "unknown")
        req_id = task.get("requirement_id", "")
        if result == "failed":
            failure = ET.SubElement(tc, "failure", {"message": task.get("error", "failed")})
            failure.text = f"task_id: {task.get('task_id')}\nrequirement: {req_id}"
        elif result in ("skipped", "blocked"):
            ET.SubElement(tc, "skipped", {"message": task.get("skip_reason", result)})
        elif result == "unknown":
            err = ET.SubElement(tc, "error", {"message": "UNKNOWN result — 不得当 PASS 处理"})
            err.text = task.get("error", "")

    tree = ET.ElementTree(testsuite)
    ET.indent(tree, space="  ")
    path = run_dir / "run_report.junit.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(testsuite, encoding="unicode"),
        encoding="utf-8",
    )
    return path


def write_run_report_md(run_dir: Path, report: dict[str, Any]) -> Path:
    """生成人可读摘要（REQ-07-05）。"""
    run_id = report.get("run_id", "")
    result = report.get("result", "unknown")
    summary = report.get("summary", {})
    gate = report.get("gate", "local")

    result_emoji = {"passed": "✅", "failed": "❌", "blocked": "⛔", "partial": "⚠️", "unknown": "❓"}
    emoji = result_emoji.get(result, "❓")

    lines: list[str] = [
        f"# 执行报告 {emoji}\n",
        f"| 字段 | 值 |",
        f"| --- | --- |",
        f"| Run ID | `{run_id}` |",
        f"| 结果 | **{result}** |",
        f"| 套件/Change | {report.get('suite', '')} |",
        f"| Gate | {gate} |",
        f"| 代码版本 | `{report.get('code_version', 'N/A')}` |",
        f"| 生成时间 | {report.get('generated_at', '')} |",
        "",
        "## 执行摘要\n",
        f"| 状态 | 数量 |",
        f"| --- | --- |",
        f"| ✅ Passed | {summary.get('passed', 0)} |",
        f"| ❌ Failed | {summary.get('failed', 0)} |",
        f"| ⏭ Skipped | {summary.get('skipped', 0)} |",
        f"| ⛔ Blocked | {summary.get('blocked', 0)} |",
        f"| ❓ Unknown | {summary.get('unknown', 0)} |",
        f"| 总计 | {summary.get('total', 0)} |",
        "",
    ]

    # 失败分桶
    buckets = report.get("failure_buckets", {})
    if buckets:
        lines.append("## 失败分桶\n")
        for bucket, task_ids in buckets.items():
            lines.append(f"- **{bucket}**：{', '.join(task_ids[:5])}")
        lines.append("")

    # 阻断原因
    pre_check = report.get("pre_check") or {}
    blockers = pre_check.get("blockers", [])
    if blockers:
        lines.append("## ⛔ 阻断原因\n")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    # Unknown 警告
    unknown_tasks = [t for t in report.get("acceptance", []) if t.get("result") == "unknown"]
    if unknown_tasks:
        lines.append("## ❓ Unknown 结果（不得当 PASS）\n")
        for t in unknown_tasks[:5]:
            lines.append(f"- `{t.get('task_id')}` — {t.get('error', '需补充证据')}")
        lines.append("")

    # APP_LAUNCH 失败时的特殊说明
    env_failed = [
        t for t in report.get("acceptance", [])
        if t.get("task_id") == "APP_LAUNCH" and t.get("result") == "failed"
    ]
    if env_failed:
        error_msg = env_failed[0].get("error", "")
        lines.append("## 失败详情\n")
        lines.append("| 步骤 | 类型 | 原因 |")
        lines.append("| --- | --- | --- |")
        lines.append(f"| APP_LAUNCH | env | {error_msg} |")
        lines.append("")
        lines.append("## 归因\n")
        lines.append("类型：**env**（环境问题），非产品 Bug，非脚本错误。\n")
        # 根据错误原因提供自动化建议
        if "多实例" in error_msg or "another Unity instance" in error_msg.lower():
            lines.append("根本原因：检测到多个 Unity Editor 实例同时打开同一工程，导致冲突弹窗阻断启动。\n")
            lines.append("**OpenGuard 将在下次执行时自动处理**：")
            lines.append("- 自动终止冲突的新启动实例")
            lines.append("- 复用已有的 Unity Editor 实例")
            lines.append("- 自动触发 PlayMode（通过注入 AutoPlay 脚本）\n")
            lines.append("建议操作：直接重新执行 `@command://openguard-apply`，无需人工介入。\n")
        elif "PlayMode" in error_msg or "playmode" in error_msg.lower():
            lines.append("根本原因：Unity Editor 启动后未能自动进入 PlayMode。\n")
            lines.append("**OpenGuard 将在下次执行时自动处理**：")
            lines.append("- 检测当前场景配置（scene_map）")
            lines.append("- 自动注入 AutoPlay 脚本触发 PlayMode")
            lines.append("- 监听 PlayMode 就绪信号\n")
            lines.append("建议操作：直接重新执行 `@command://openguard-apply`，无需人工介入。\n")
        elif "超时" in error_msg or "timeout" in error_msg.lower():
            lines.append("根本原因：Unity Editor 启动或就绪超时。\n")
            lines.append("**自动化建议**：")
            lines.append("- 确认 `config.yaml` 中 `startup_timeout_seconds` 是否足够（建议 180s+）")
            lines.append("- 检查 Unity Editor 日志（`Logs/Editor.log`）确认无编译错误\n")
            lines.append("建议操作：确认 Editor 正常后重新执行 `@command://openguard-apply`。\n")
        else:
            lines.append("建议操作：检查 Unity Editor 状态后重新执行 `@command://openguard-apply`。\n")

    lines.append("---\n*前置失败不归类为验收失败（REQ-07-03）。UNKNOWN 不得默认当 PASS（REQ-07-03）。*")

    path = run_dir / "run_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Timeline 生成（REQ-07-10）
# ──────────────────────────────────────────────────────────────────────────────

def write_timeline(run_dir: Path, report: dict[str, Any]) -> Path:
    """生成 timeline.md 让用户看清测试过程（REQ-07-10）。"""
    run_id = report.get("run_id", "")
    lines: list[str] = [
        f"# 执行时间线 — {run_id}\n",
        "> 本文档回答：测试如何执行、在哪里失败、失败原因是什么。\n",
    ]

    # 执行前校验
    pre_check = report.get("pre_check") or {}
    lines.append("## [1] 执行前校验\n")
    if pre_check.get("is_blocked"):
        lines.append(f"❌ **执行被阻断**：{', '.join(pre_check.get('blockers', []))}")
        for c in pre_check.get("checks", []):
            if c["status"] == "fail":
                lines.append(f"  - {c['check']}: {c.get('reason', '')}")
        lines.append("")
        lines.append("---\n*执行因前置校验失败而终止。*")
        path = run_dir / "timeline.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
    else:
        lines.append("✅ 执行前校验通过\n")

    # Runtime 状态
    rt = report.get("runtime", {})
    lines.append("## [2] 运行时状态\n")
    lines.append(f"- 模式：{rt.get('mode', 'N/A')}")
    lines.append(f"- 状态：{rt.get('status', 'N/A')}\n")

    # 任务执行
    lines.append("## [3] 任务执行\n")
    lines.append("| 任务 | 需求 ID | 结果 | 失败原因 |")
    lines.append("| --- | --- | --- | --- |")
    for t in report.get("acceptance", []):
        task_id = t.get("task_id", "")
        req_id = t.get("requirement_id", "—")
        result = t.get("result", "unknown")
        error = t.get("error", "") or t.get("skip_reason", "")
        result_icon = {"passed": "✅", "failed": "❌", "skipped": "⏭", "blocked": "⛔", "unknown": "❓"}.get(result, "❓")
        lines.append(f"| `{task_id}` | {req_id} | {result_icon} {result} | {error[:60] if error else '—'} |")
    lines.append("")

    # 结论
    lines.append("## [4] 结论\n")
    lines.append(f"**总结果：{report.get('result', 'unknown')}**")
    summary = report.get("summary", {})
    lines.append(
        f"通过 {summary.get('passed', 0)} / 失败 {summary.get('failed', 0)} / "
        f"跳过 {summary.get('skipped', 0)} / 未知 {summary.get('unknown', 0)}"
    )

    path = run_dir / "timeline.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
