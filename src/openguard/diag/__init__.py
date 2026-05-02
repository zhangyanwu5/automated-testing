"""诊断日志模块：记录 CLI 调用、agent 推进轨迹、执行事件，供问题排查使用。

三层记录体系：
  层一：cli_log      — 每次 openguard 命令调用的完整输入/输出/耗时（全局滚动文件）
  层二：agent_trace  — _advance 每次推进的决策链和产物变化（per-change）
  层三：events.jsonl — 执行阶段的步骤事件，已在 executor/reporter.py 实现

公开 API：
  get_cli_logger(openguard_dir)  → CliLogger（层一）
  get_trace_writer(change_dir)   → TraceWriter（层二）
"""
from openguard.diag.cli_logger import CliLogger, get_cli_logger
from openguard.diag.trace_writer import TraceWriter, get_trace_writer

__all__ = [
    "CliLogger", "get_cli_logger",
    "TraceWriter", "get_trace_writer",
]
