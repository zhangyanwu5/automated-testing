"""``openguard continue`` — 手动恢复别名，映射到 openguard _advance 逻辑。

此命令供用户在 AI 驱动循环中断后手动恢复使用。
正常自动化流程中，AI 直接调用 `openguard _advance`。
"""
from openguard.commands.advance import run_advance as run_continue

__all__ = ["run_continue"]
