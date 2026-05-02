"""``openguard report`` — 一键生成上报文件，供问题排查和上报使用。

将所有诊断信息打包成单个结构化文本文件：
  - 最近 CLI 调用记录
  - 活跃 change 的状态和推进轨迹
  - 最近一次执行报告
  - 执行事件流
  - 失败任务的脚本输出
  - operation_log

用法：
  openguard report                       # 打包当前最新 change 的诊断信息
  openguard report --change <id>         # 指定 change
  openguard report --out report.txt      # 指定输出路径
  openguard report --last-runs 3         # 包含最近 3 次 run 的报告（默认 1）
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# 敏感信息脱敏
# ──────────────────────────────────────────────────────────────────────────────

_REDACT_PATTERNS = [
    # API keys / tokens / secrets / passwords
    (re.compile(r'(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*["\']?([\w\-/+]{8,})', re.I),
     lambda m: m.group(0).replace(m.group(2), "***REDACTED***")),
    # Private keys
    (re.compile(r'-----BEGIN .+? PRIVATE KEY-----.+?-----END .+? PRIVATE KEY-----', re.DOTALL),
     lambda m: "***PRIVATE KEY REDACTED***"),
    # Bearer tokens
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-._~+/]{20,}'),
     lambda m: m.group(1) + "***REDACTED***"),
    # AWS-style keys
    (re.compile(r'AKIA[0-9A-Z]{16}'),
     lambda m: "***AWS_KEY_REDACTED***"),
    # GitHub tokens
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{36}'),
     lambda m: "***GITHUB_TOKEN_REDACTED***"),
]


def _redact(text: str) -> str:
    """对文本内容做敏感信息脱敏。"""
    for pattern, replacer in _REDACT_PATTERNS:
        text = pattern.sub(replacer, text)
    return text


# ──────────────────────────────────────────────────────────────────────────────
# 各节内容采集
# ──────────────────────────────────────────────────────────────────────────────

def _section(title: str, content: str) -> str:
    """格式化一个诊断章节。"""
    bar = "=" * 60
    return f"\n{bar}\n=== {title}\n{bar}\n{content.rstrip()}\n"


def _collect_env(openguard_dir: Path | None) -> str:
    """[0] 基础环境信息。"""
    try:
        from openguard import __version__
        version = __version__
    except Exception:
        version = "unknown"

    lines = [
        f"generated_at : {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"openguard    : {version}",
        f"python       : {sys.version.split()[0]}",
        f"platform     : {platform.system()} {platform.release()} {platform.machine()}",
        f"cwd          : {os.getcwd()}",
        f"openguard_dir: {openguard_dir or '(not found)'}",
    ]
    return "\n".join(lines)


def _collect_cli_log(openguard_dir: Path, last_n: int = 50) -> str:
    """[1] 最近 N 条 CLI 调用记录（合并所有日志文件，按时间排序取最新）。"""
    logs_dir = openguard_dir / "logs"
    if not logs_dir.exists():
        return "(no CLI logs found — openguard/logs/ does not exist)"

    records: list[dict[str, Any]] = []
    for log_file in sorted(logs_dir.glob("cli-*.log"), reverse=True)[:3]:
        try:
            for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
        except Exception:
            pass

    if not records:
        return "(no CLI log entries found)"

    # 按时间排序，取最新 N 条
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    records = records[:last_n]

    lines = []
    for r in reversed(records):   # 输出时从旧到新
        ts = r.get("ts", "?")
        argv = " ".join(r.get("argv", []))
        exit_code = r.get("exit_code", "?")
        elapsed = r.get("elapsed_ms", 0)
        lines.append(f"[{ts}] openguard {argv}  →  exit={exit_code}  ({elapsed}ms)")
        # 只展示非零退出或 stderr 不空时的详细输出
        if exit_code != 0 or r.get("stderr", "").strip():
            stdout = _redact(r.get("stdout", "")).strip()
            stderr = _redact(r.get("stderr", "")).strip()
            if stdout:
                lines.append(f"  stdout: {stdout[-800:]}")
            if stderr:
                lines.append(f"  stderr: {stderr[-800:]}")
        lines.append("")

    return "\n".join(lines)


def _collect_change_state(change_dir: Path) -> str:
    """[2] change 当前状态（state.yaml 内容）。"""
    state_file = change_dir / "state.yaml"
    if not state_file.exists():
        return f"(state.yaml not found in {change_dir})"
    content = state_file.read_text(encoding="utf-8", errors="replace")
    return _redact(content)


def _collect_agent_trace(change_dir: Path, last_invocations: int = 3) -> str:
    """[3] _advance 推进轨迹（最近 N 次 invocation）。"""
    trace_file = change_dir / "agent_trace.jsonl"
    if not trace_file.exists():
        return "(agent_trace.jsonl not found — _advance has not been called yet)"

    records: list[dict[str, Any]] = []
    try:
        for line in trace_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    except Exception as e:
        return f"(error reading agent_trace.jsonl: {e})"

    if not records:
        return "(agent_trace.jsonl is empty)"

    # 按 invocation_id 分组，取最近 N 个
    inv_order: list[str] = []
    inv_groups: dict[str, list[dict]] = {}
    for r in records:
        inv_id = r.get("invocation_id", "?")
        if inv_id not in inv_groups:
            inv_order.append(inv_id)
            inv_groups[inv_id] = []
        inv_groups[inv_id].append(r)

    recent_ids = inv_order[-last_invocations:]
    lines = []
    for inv_id in recent_ids:
        lines.append(f"── invocation {inv_id} ──")
        for r in inv_groups[inv_id]:
            ts = r.get("ts", "")
            step = r.get("step", "")
            status = r.get("status", "")
            artifact = r.get("artifact", "")
            decision = r.get("decision", "")
            elapsed = r.get("elapsed_ms", 0)
            error = r.get("error", "")
            parts = [f"  [{ts}] {step}  status={status}"]
            if artifact:
                parts[0] += f"  artifact={artifact}"
            if elapsed:
                parts[0] += f"  ({elapsed}ms)"
            if decision:
                parts.append(f"    decision: {decision}")
            if error:
                parts.append(f"    ERROR: {error}")
            lines.extend(parts)
        lines.append("")

    return "\n".join(lines)


def _collect_run_report(run_dir: Path) -> str:
    """[4] 执行报告（run_report.md 优先，无则用 run_report.json 摘要）。"""
    md_file = run_dir / "run_report.md"
    if md_file.exists():
        return md_file.read_text(encoding="utf-8", errors="replace")

    json_file = run_dir / "run_report.json"
    if json_file.exists():
        try:
            report = json.loads(json_file.read_text(encoding="utf-8"))
            return json.dumps({
                "run_id": report.get("run_id"),
                "result": report.get("result"),
                "summary": report.get("summary"),
                "failure_buckets": report.get("failure_buckets"),
                "pre_check": report.get("pre_check"),
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"(error reading run_report.json: {e})"

    return "(no run report found)"


def _collect_events(run_dir: Path, last_n: int = 100) -> str:
    """[5] 执行事件流（最近 N 条）。"""
    events_file = run_dir / "events.jsonl"
    if not events_file.exists():
        return "(events.jsonl not found)"

    lines_raw: list[str] = []
    try:
        lines_raw = events_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"(error reading events.jsonl: {e})"

    records = []
    for line in lines_raw:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    if not records:
        return "(events.jsonl is empty)"

    recent = records[-last_n:]
    lines = []
    for r in recent:
        ts = r.get("timestamp", r.get("ts", "?"))
        phase = r.get("phase", "")
        step = r.get("step", "")
        status = r.get("status", "")
        msg = r.get("message", "")
        line = f"[{ts}] {phase}/{step}  {status}"
        if msg:
            line += f"  — {msg}"
        lines.append(line)

    total = len(records)
    if total > last_n:
        lines.insert(0, f"(showing last {last_n} of {total} events)\n")

    return "\n".join(lines)


def _collect_script_output(run_dir: Path) -> str:
    """[6] 失败任务的脚本输出（script_output/*.txt）。"""
    out_dir = run_dir / "script_output"
    if not out_dir.exists():
        return "(no script_output directory)"

    files = sorted(out_dir.glob("*.txt"))
    if not files:
        return "(no script output files)"

    sections = []
    for f in files:
        task_id = f.stem
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            content = _redact(content)
            # 只保留最后 4KB（避免单个脚本输出撑爆诊断文件）
            if len(content) > 4096:
                content = f"... [truncated, showing last 4KB] ...\n{content[-4096:]}"
            sections.append(f"--- {task_id} ---\n{content}")
        except Exception as e:
            sections.append(f"--- {task_id} ---\n(error reading: {e})")

    return "\n\n".join(sections)


def _collect_operation_log(change_dir: Path, last_n: int = 30) -> str:
    """[7] operation_log（最近 N 条）。"""
    log_file = change_dir / "operation_log.jsonl"
    if not log_file.exists():
        return "(operation_log.jsonl not found)"

    records = []
    try:
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    except Exception as e:
        return f"(error reading operation_log.jsonl: {e})"

    if not records:
        return "(operation_log.jsonl is empty)"

    recent = records[-last_n:]
    lines = []
    for r in recent:
        ts = r.get("timestamp", r.get("ts", "?"))
        step = r.get("step", "")
        status = r.get("status", "")
        decision = r.get("decision", "")
        error = r.get("error", "")
        line = f"[{ts}] {step}  {status}"
        if decision:
            line += f"  — {decision}"
        if error:
            line += f"  ERROR: {error}"
        lines.append(line)

    total = len(records)
    if total > last_n:
        lines.insert(0, f"(showing last {last_n} of {total} entries)\n")

    return "\n".join(lines)


def _find_latest_run_dir(openguard_dir: Path, change_id: str | None) -> Path | None:
    """找到最近一次 run 的目录。"""
    if change_id:
        base = openguard_dir / "reports" / "changes" / change_id
    else:
        base = openguard_dir / "reports" / "changes"

    if not base.exists():
        return None

    candidates: list[Path] = []
    if change_id:
        # openguard/reports/changes/<change_id>/<run_id>/
        for run_dir in base.iterdir():
            if run_dir.is_dir():
                candidates.append(run_dir)
    else:
        # openguard/reports/changes/<any_change>/<run_id>/
        for change_dir in base.iterdir():
            if change_dir.is_dir():
                for run_dir in change_dir.iterdir():
                    if run_dir.is_dir():
                        candidates.append(run_dir)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


# ──────────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────────

def run_report(args: argparse.Namespace) -> int:
    from openguard.workspace.layout import find_openguard_dir
    from openguard.workspace.change import latest_change

    openguard_dir = find_openguard_dir()
    change_id_arg: str | None = getattr(args, "change_id", None)
    out_path: str | None = getattr(args, "out", None)
    last_runs: int = getattr(args, "last_runs", 1)

    # 确定 change_dir
    change_dir: Path | None = None
    change_id: str | None = change_id_arg
    if openguard_dir:
        if change_id_arg:
            candidate = openguard_dir / "changes" / change_id_arg
            change_dir = candidate if candidate.is_dir() else None
        else:
            change_dir = latest_change(openguard_dir)
            if change_dir:
                change_id = change_dir.name

    # 确定 run_dir（最近一次执行）
    run_dir: Path | None = None
    if openguard_dir:
        run_dir = _find_latest_run_dir(openguard_dir, change_id)

    # 组装诊断报告
    parts: list[str] = []
    header = (
        "OpenGuard Diagnostic Report\n"
        "============================\n"
        "Send this file to the developer for issue analysis.\n"
        "Sensitive information (tokens/passwords) has been automatically redacted."
    )
    parts.append(header)
    parts.append(_section("0] Environment", _collect_env(openguard_dir)))

    if openguard_dir:
        parts.append(_section("1] Recent CLI Calls (last 50)", _collect_cli_log(openguard_dir)))
    else:
        parts.append(_section("1] Recent CLI Calls", "(openguard/ workspace not found)"))

    if change_dir:
        parts.append(_section(f"2] Change State  [{change_id}]",
                               _collect_change_state(change_dir)))
        parts.append(_section(f"3] _advance Trace  [{change_id}] (last 3 invocations)",
                               _collect_agent_trace(change_dir)))
        parts.append(_section(f"7] operation_log  [{change_id}] (last 30)",
                               _collect_operation_log(change_dir)))
    else:
        note = "(no active change found)"
        parts.append(_section("2] Change State", note))
        parts.append(_section("3] _advance Trace", note))
        parts.append(_section("7] operation_log", note))

    if run_dir:
        run_label = f"{run_dir.parent.name}/{run_dir.name}" if openguard_dir else str(run_dir)
        parts.append(_section(f"4] Run Report  [{run_label}]",
                               _collect_run_report(run_dir)))
        parts.append(_section(f"5] Events  [{run_label}] (last 100)",
                               _collect_events(run_dir)))
        parts.append(_section(f"6] Script Output  [{run_label}]",
                               _collect_script_output(run_dir)))
    else:
        note = "(no run found)"
        parts.append(_section("4] Run Report", note))
        parts.append(_section("5] Events", note))
        parts.append(_section("6] Script Output", note))

    report_text = "\n".join(parts) + "\n"

    # 输出路径
    if out_path:
        out_file = Path(out_path)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_file = Path(f"openguard-report-{ts}.txt")
        # 尝试放在 openguard_dir 同级（项目根），如果 openguard_dir 存在
        if openguard_dir:
            out_file = openguard_dir.parent / out_file.name

    try:
        out_file.write_text(report_text, encoding="utf-8")
    except Exception as e:
        print(f"Error: 无法写入上报文件 {out_file}: {e}", file=sys.stderr)
        return 1

    print(f"上报文件已生成：{out_file}")
    print(f"请将此文件发送给开发者进行分析。")
    if change_dir is None:
        print("提示：未找到活跃 change，change 相关信息为空。")
    if run_dir is None:
        print("提示：未找到执行记录，执行相关信息为空。")

    return 0
