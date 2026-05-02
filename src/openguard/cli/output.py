"""跨平台安全输出工具。

Windows 的 cmd/PowerShell 默认使用 GBK/CP936，不支持部分 Unicode 符号。
使用 sys.stdout.buffer.write + UTF-8 编码确保中文和特殊符号均能正确输出。
"""
from __future__ import annotations

import sys


def safe_print(*args: object, sep: str = " ", end: str = "\n", file=None) -> None:
    """兼容 Windows GBK 终端的安全打印。

    若终端编码不支持 Unicode，自动回退到替换字符模式，而不是崩溃。
    """
    target = file or sys.stdout
    text = sep.join(str(a) for a in args) + end
    try:
        target.write(text)
        target.flush()
    except UnicodeEncodeError:
        # 回退：将无法编码的字符替换为 '?'
        encoded = text.encode(target.encoding or "utf-8", errors="replace")
        target.buffer.write(encoded)
        target.buffer.flush()


def setup_utf8_stdout() -> None:
    """在程序入口设置 stdout/stderr 为 UTF-8 + 行缓冲，解决 Windows GBK 和重定向缓冲问题。

    推荐在 main() 最开始调用一次。
    line_buffering=True 确保重定向时每行输出都立即 flush（等价于 python -u）。
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace",
                                   line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace",
                                   line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass
