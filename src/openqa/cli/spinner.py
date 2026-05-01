"""Spinner + Step 输出工具（REQ-01-23~27）。

提供两层反馈机制：
  1. TTY 模式：Spinner 动画（旋转字符），完成后原地替换为 ✓ / ✗ + 耗时（>3s 时）。
  2. CI / 非 TTY / --yes 模式：禁用动画，改为 [cmd] step... / done (xs) 格式逐行输出。

核心用法（上下文管理器）：

    from openqa.cli.spinner import step

    with step("Scanning project", cmd="init") as s:
        result = do_scan()
        s.set_label(f"Scanning project — {result.file_count} files")
    # 自动打印 ✓ Scanning project — 42 files  (1.2s)

    with step("Installing commands", cmd="init") as s:
        install()
    # 自动打印 ✓ Installing commands

    # 失败时：
    with step("Running tests", cmd="apply") as s:
        ok = run_tests()
        if not ok:
            s.fail("2 tests failed")
    # 打印 ✗ Running tests — 2 tests failed  (4.1s)

全局 yes 模式控制：
    from openqa.cli.spinner import set_plain_mode
    set_plain_mode(True)   # 强制纯文本（--yes / CI）
"""
from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Generator

# ──────────────────────────────────────────────────────────────────────────────
# 全局配置
# ──────────────────────────────────────────────────────────────────────────────

_plain_mode: bool = False  # True = CI / --yes 模式，禁用 spinner


def set_plain_mode(enabled: bool) -> None:
    """全局设置纯文本模式（在 main() 入口根据 --yes / TTY 状态调用）。"""
    global _plain_mode
    _plain_mode = enabled


def is_plain_mode() -> bool:
    global _plain_mode
    if _plain_mode:
        return True
    # 自动检测：非 TTY 时强制纯文本
    return not (sys.stdout.isatty() and sys.stderr.isatty())


# ──────────────────────────────────────────────────────────────────────────────
# ANSI / 符号
# ──────────────────────────────────────────────────────────────────────────────

_SPINNER_FRAMES = ("⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏", "⠋", "⠙", "⠹")
_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED   = "\033[31m"
_DIM   = "\033[2m"
_BOLD  = "\033[1m"
_ERASE = "\r\033[K"          # 回车 + 清除当前行

_SLOW_THRESHOLD = 3.0        # 超过此秒数才追加耗时


def _color(text: str, *codes: str) -> str:
    if is_plain_mode():
        return text
    try:
        return "".join(codes) + text + _RESET
    except Exception:
        return text


def _fmt_elapsed(secs: float) -> str:
    if secs >= 10:
        return f"{secs:.0f}s"
    return f"{secs:.1f}s"


# ──────────────────────────────────────────────────────────────────────────────
# Step 状态句柄
# ──────────────────────────────────────────────────────────────────────────────

class StepHandle:
    """在 `step()` 上下文中可调用，用于更新标签或标记失败。"""

    def __init__(self, label: str, cmd: str) -> None:
        self._label = label
        self._cmd = cmd
        self._failed = False
        self._fail_detail = ""

    def set_label(self, label: str) -> None:
        """更新步骤描述（完成行将使用新标签）。"""
        self._label = label

    def fail(self, detail: str = "") -> None:
        """将步骤标记为失败。"""
        self._failed = True
        self._fail_detail = detail


# ──────────────────────────────────────────────────────────────────────────────
# Spinner 线程
# ──────────────────────────────────────────────────────────────────────────────

class _SpinnerThread(threading.Thread):
    def __init__(self, label: str) -> None:
        super().__init__(daemon=True)
        self._label = label
        self._stop_event = threading.Event()

    def run(self) -> None:
        i = 0
        while not self._stop_event.is_set():
            frame = _color(_SPINNER_FRAMES[i % len(_SPINNER_FRAMES)], _DIM)
            sys.stdout.write(f"{_ERASE}{frame} {self._label}...")
            sys.stdout.flush()
            self._stop_event.wait(0.08)
            i += 1

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=0.5)
        # 清除 spinner 行（等待调用者打印最终行）
        sys.stdout.write(_ERASE)
        sys.stdout.flush()


# ──────────────────────────────────────────────────────────────────────────────
# 主接口
# ──────────────────────────────────────────────────────────────────────────────

@contextmanager
def step(
    label: str,
    cmd: str = "",
) -> Generator[StepHandle, None, None]:
    """步骤执行上下文管理器（REQ-01-23~27）。

    TTY 模式：启动 spinner，完成后原地替换为 ✓/✗ 行（慢步骤追加耗时）。
    CI 模式：打印 "[cmd] label..." 开始行，完成后打印 "done (xs)" 或 "failed"。

    Args:
        label: 步骤描述文字，如 "Scanning project"
        cmd:   命令名称前缀，CI 模式使用，如 "init" → "[init]"
    """
    handle = StepHandle(label, cmd)
    t_start = time.monotonic()
    prefix = f"[{cmd}] " if cmd else ""
    spinner: _SpinnerThread | None = None

    plain = is_plain_mode()

    if plain:
        # CI 模式：打印开始行
        sys.stdout.write(f"{prefix}{label}...\n")
        sys.stdout.flush()
    else:
        # TTY 模式：启动 spinner
        spinner = _SpinnerThread(label)
        spinner.start()

    try:
        yield handle
    except Exception:
        # 异常也要先停 spinner
        if spinner:
            spinner.stop()
        elapsed = time.monotonic() - t_start
        _print_result(handle, elapsed, failed=True, plain=plain, prefix=prefix)
        raise
    else:
        if spinner:
            spinner.stop()
        elapsed = time.monotonic() - t_start
        _print_result(handle, elapsed, failed=handle._failed, plain=plain, prefix=prefix)


def _print_result(
    handle: StepHandle,
    elapsed: float,
    *,
    failed: bool,
    plain: bool,
    prefix: str,
) -> None:
    """打印步骤最终状态行。"""
    label = handle._label
    detail = f" — {handle._fail_detail}" if handle._fail_detail else ""
    slow = elapsed >= _SLOW_THRESHOLD
    elapsed_str = f"  {_color(_fmt_elapsed(elapsed), _DIM)}" if slow else ""

    if plain:
        # CI 纯文本
        if failed:
            suffix = f" failed{detail}"
            if slow:
                suffix += f" ({_fmt_elapsed(elapsed)})"
            sys.stdout.write(f"{prefix}{label}...{suffix}\n")
        else:
            suffix = f" done"
            if slow:
                suffix += f" ({_fmt_elapsed(elapsed)})"
            sys.stdout.write(f"{prefix}{label}...{suffix}\n")
    else:
        # TTY 模式
        if failed:
            mark = _color("✗", _RED, _BOLD)
            detail_colored = _color(detail, _DIM)
            sys.stdout.write(f"{mark} {label}{detail_colored}{elapsed_str}\n")
        else:
            mark = _color("✓", _GREEN, _BOLD)
            sys.stdout.write(f"{mark} {label}{elapsed_str}\n")

    sys.stdout.flush()


# ──────────────────────────────────────────────────────────────────────────────
# 便捷函数：直接打印完成行（无 spinner，用于即时完成的步骤）
# ──────────────────────────────────────────────────────────────────────────────

def ok(label: str, cmd: str = "") -> None:
    """直接打印 ✓ 行（无 spinner，适合瞬时完成的步骤）。"""
    prefix = f"[{cmd}] " if (cmd and is_plain_mode()) else ""
    if is_plain_mode():
        sys.stdout.write(f"{prefix}{label}\n")
    else:
        mark = _color("✓", _GREEN, _BOLD)
        sys.stdout.write(f"{mark} {label}\n")
    sys.stdout.flush()


def warn(label: str, cmd: str = "") -> None:
    """打印 ⚠ 警告行。"""
    prefix = f"[{cmd}] " if (cmd and is_plain_mode()) else ""
    if is_plain_mode():
        sys.stdout.write(f"{prefix}[warn] {label}\n")
    else:
        sys.stdout.write(f"  \033[33m⚠\033[0m  {label}\n")
    sys.stdout.flush()
