"""跨平台交互式 TUI 选择组件。

提供类似 OpenSpec / Claude Code 初始化体验的键盘交互菜单：
  - 上下键（↑↓）导航光标
  - 空格键切换选中状态（多选）/ 确认当前项（单选）
  - 回车键确认当前选择
  - Ctrl+C 中止，返回默认值

实现策略：
  - Windows：使用 msvcrt 读取原始按键
  - Unix/macOS：使用 termios + tty 设置 raw mode
  - 非 TTY（CI / pipe）：自动降级为普通文本输入

外部接口：
  multiselect(title, options, preselected) → list[str]
  singleselect(title, options, default)    → str
"""
from __future__ import annotations

import os
import sys
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# 环境检测
# ──────────────────────────────────────────────────────────────────────────────

def _is_tty() -> bool:
    """判断 stdout 是否为真实终端（非 CI pipe）。"""
    return sys.stdout.isatty() and sys.stdin.isatty()


# ──────────────────────────────────────────────────────────────────────────────
# 跨平台按键读取
# ──────────────────────────────────────────────────────────────────────────────

_KEY_UP    = "UP"
_KEY_DOWN  = "DOWN"
_KEY_SPACE = "SPACE"
_KEY_ENTER = "ENTER"
_KEY_CTRL_C = "CTRL_C"
_KEY_OTHER = "OTHER"


def _read_key_windows() -> str:
    import msvcrt
    ch = msvcrt.getch()
    if ch in (b"\r", b"\n"):
        return _KEY_ENTER
    if ch == b" ":
        return _KEY_SPACE
    if ch == b"\x03":
        return _KEY_CTRL_C
    if ch == b"\xe0" or ch == b"\x00":
        # 特殊键的第二个字节
        ch2 = msvcrt.getch()
        if ch2 == b"H":
            return _KEY_UP
        if ch2 == b"P":
            return _KEY_DOWN
    return _KEY_OTHER


def _read_key_unix() -> str:
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\r" or ch == "\n":
            return _KEY_ENTER
        if ch == " ":
            return _KEY_SPACE
        if ch == "\x03":
            return _KEY_CTRL_C
        if ch == "\x1b":
            # ESC 序列
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return _KEY_UP
                if ch3 == "B":
                    return _KEY_DOWN
        return _KEY_OTHER
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    if os.name == "nt":
        return _read_key_windows()
    return _read_key_unix()


# ──────────────────────────────────────────────────────────────────────────────
# 渲染辅助
# ──────────────────────────────────────────────────────────────────────────────

# ANSI 转义码
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_GREEN  = "\033[32m"
_CYAN   = "\033[36m"
_DIM    = "\033[2m"

_CURSOR_UP   = "\033[{}A"
_ERASE_LINE  = "\033[2K\r"


def _supports_ansi() -> bool:
    """Windows 10 1511+ 及所有 Unix 终端均支持 ANSI。"""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # 启用 ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


_ANSI = None  # 延迟初始化


def _ansi() -> bool:
    global _ANSI
    if _ANSI is None:
        _ANSI = _supports_ansi()
    return _ANSI


def _color(text: str, *codes: str) -> str:
    if not _ansi():
        return text
    return "".join(codes) + text + _RESET


# ──────────────────────────────────────────────────────────────────────────────
# 多选组件（空格切换，回车确认）
# ──────────────────────────────────────────────────────────────────────────────

def multiselect(
    title: str,
    options: list[str],
    preselected: list[str] | None = None,
    hint_map: dict[str, str] | None = None,
) -> list[str]:
    """交互式多选菜单。

    Args:
        title:       菜单标题（如 "? Select AI coding tools"）
        options:     选项名称列表
        preselected: 预勾选的选项名称列表
        hint_map:    选项名 → 提示文字（如 "[detected .codebuddy/]"）

    Returns:
        用户选中的选项名称列表。Ctrl+C 时返回 preselected（或空列表）。

    非 TTY 时降级为文本输入。
    """
    preselected = preselected or []
    hint_map = hint_map or {}

    if not _is_tty():
        return _multiselect_fallback(title, options, preselected, hint_map)

    selected: set[str] = set(preselected)
    cursor = 0
    n = len(options)

    def render() -> None:
        """渲染 option 行（不含 title/hint）。"""
        lines: list[str] = []
        for i, opt in enumerate(options):
            is_cursor = i == cursor
            is_checked = opt in selected
            hint = f"  {_color(hint_map[opt], _DIM)}" if opt in hint_map else ""

            if is_checked:
                circle = _color("●", _GREEN)
            else:
                circle = _color("○", _DIM)

            label = _color(opt, _BOLD) if is_cursor else opt
            pointer = _color("> ", _CYAN) if is_cursor else "  "

            lines.append(f"{pointer}{circle} {label}{hint}")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()

    # 首次渲染：title + hint 单独输出，之后只刷新 option 行
    sys.stdout.write("\n")
    sys.stdout.write(_color(title, _BOLD) + "\n")
    hint_line = (
        f"  {_color('↑↓', _CYAN)} navigate  "
        f"{_color('Space', _CYAN)} toggle  "
        f"{_color('Enter', _CYAN)} confirm"
    )
    sys.stdout.write(hint_line + "\n")
    sys.stdout.flush()
    render()

    try:
        while True:
            key = _read_key()

            # 清除已渲染的行（只清选项行，保留 title+hint）
            # 向上移 n 行，逐行清除
            sys.stdout.write(f"\033[{n}A")
            for _ in range(n):
                sys.stdout.write(_ERASE_LINE + "\n")
            sys.stdout.write(f"\033[{n}A")

            if key == _KEY_CTRL_C:
                sys.stdout.write("\n")
                raise KeyboardInterrupt

            elif key == _KEY_UP:
                cursor = (cursor - 1) % n

            elif key == _KEY_DOWN:
                cursor = (cursor + 1) % n

            elif key == _KEY_SPACE:
                opt = options[cursor]
                if opt in selected:
                    selected.discard(opt)
                else:
                    selected.add(opt)

            elif key == _KEY_ENTER:
                # 重新渲染最终状态后退出
                for i, opt in enumerate(options):
                    is_checked = opt in selected
                    circle = _color("●", _GREEN) if is_checked else _color("○", _DIM)
                    hint = f"  {_color(hint_map[opt], _DIM)}" if opt in hint_map else ""
                    sys.stdout.write(_ERASE_LINE + f"  {circle} {opt}{hint}\n")
                sys.stdout.flush()
                break

            # 重新渲染选项
            for i, opt in enumerate(options):
                is_cursor = i == cursor
                is_checked = opt in selected
                circle = _color("●", _GREEN) if is_checked else _color("○", _DIM)
                hint = f"  {_color(hint_map[opt], _DIM)}" if opt in hint_map else ""
                label = _color(opt, _BOLD) if is_cursor else opt
                pointer = _color("> ", _CYAN) if is_cursor else "  "
                sys.stdout.write(_ERASE_LINE + f"{pointer}{circle} {label}{hint}\n")
            sys.stdout.flush()

    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return list(preselected)

    return [opt for opt in options if opt in selected]


# ──────────────────────────────────────────────────────────────────────────────
# 单选组件（上下键导航，回车确认）
# ──────────────────────────────────────────────────────────────────────────────

def singleselect(
    title: str,
    options: list[str],
    default: str | None = None,
) -> str:
    """交互式单选菜单。

    Returns:
        用户选中的选项名称。Ctrl+C 时返回 default（或第一个选项）。

    非 TTY 时降级为文本输入。
    """
    if not options:
        return default or ""

    if not _is_tty():
        return _singleselect_fallback(title, options, default)

    cursor = 0
    if default and default in options:
        cursor = options.index(default)

    n = len(options)

    sys.stdout.write(f"\n{_color(title, _BOLD)}\n")
    hint = (
        f"  {_color('↑↓', _CYAN)} navigate  "
        f"{_color('Enter', _CYAN)} confirm"
    )
    sys.stdout.write(hint + "\n")
    sys.stdout.flush()

    def _render_options() -> None:
        for i, opt in enumerate(options):
            is_cursor = i == cursor
            pointer = _color("> ", _CYAN) if is_cursor else "  "
            label = _color(opt, _BOLD) if is_cursor else opt
            sys.stdout.write(f"{pointer}{label}\n")
        sys.stdout.flush()

    _render_options()

    try:
        while True:
            key = _read_key()

            sys.stdout.write(f"\033[{n}A")
            for _ in range(n):
                sys.stdout.write(_ERASE_LINE + "\n")
            sys.stdout.write(f"\033[{n}A")

            if key == _KEY_CTRL_C:
                sys.stdout.write("\n")
                raise KeyboardInterrupt

            elif key == _KEY_UP:
                cursor = (cursor - 1) % n

            elif key == _KEY_DOWN:
                cursor = (cursor + 1) % n

            elif key in (_KEY_ENTER, _KEY_SPACE):
                for i, opt in enumerate(options):
                    is_cursor = i == cursor
                    pointer = _color("> ", _CYAN) if is_cursor else "  "
                    label = _color(opt, _BOLD) if is_cursor else opt
                    sys.stdout.write(_ERASE_LINE + f"{pointer}{label}\n")
                sys.stdout.flush()
                return options[cursor]

            _render_options()

    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return default or options[0]


# ──────────────────────────────────────────────────────────────────────────────
# 非 TTY 降级实现（CI / pipe / --yes 场景）
# ──────────────────────────────────────────────────────────────────────────────

def _multiselect_fallback(
    title: str,
    options: list[str],
    preselected: list[str],
    hint_map: dict[str, str],
) -> list[str]:
    """非 TTY 时的文本降级多选。"""
    print(f"\n{title}")
    for i, opt in enumerate(options, 1):
        mark = "✓" if opt in preselected else " "
        hint = f"  {hint_map[opt]}" if opt in hint_map else ""
        print(f"  {i}. [{mark}] {opt}{hint}")

    pre_str = ", ".join(preselected) if preselected else "none"
    print(f"\n  Enter numbers (comma-separated), or press Enter for pre-selected ({pre_str}):")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return list(preselected)

    if not raw:
        return list(preselected)

    result: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(options):
                result.append(options[idx])
        elif part.lower() in options:
            result.append(part.lower())
    return list(dict.fromkeys(result))


def _singleselect_fallback(
    title: str,
    options: list[str],
    default: str | None,
) -> str:
    """非 TTY 时的文本降级单选。"""
    print(f"\n{title}")
    for i, opt in enumerate(options, 1):
        mark = " *" if opt == default else "  "
        print(f"  {i}.{mark}{opt}")

    default_str = f" [{default}]" if default else ""
    print(f"\n  Enter number or name{default_str}:")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default or options[0]

    if not raw:
        return default or options[0]
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    if raw in options:
        return raw
    return default or options[0]
