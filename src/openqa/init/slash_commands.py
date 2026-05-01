"""生成并安装 /oqa:* slash command 模板。

OpenQA 将命令存根安装到各 AI 宿主的命令目录。
当前支持的宿主：
  - codebuddy   → .codebuddy/commands/
  - workbuddy   → .workbuddy/commands/
  - cursor       → .cursor/rules/（.mdc 格式）
  - claude-code  → .claude/commands/
  - windsurf     → .windsurf/rules/（.md 格式，Cascade rules）
  - gemini       → .gemini/commands/（.md 格式）
  - codex        → .codex/commands/（.md 格式，AGENTS.md 风格）

每条命令是带 YAML front matter 的 Markdown 文件，
描述命令用途、参数以及 AI Agent 被调用时应执行的操作。
命令模板内容统一定义在 openqa/prompts/<lang>/slash_commands.py。
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class HostSpec(NamedTuple):
    name: str
    commands_dir: str           # 相对于项目根目录
    file_ext: str               # 如 ".md"
    prefix_filename: bool       # 文件名是否加 "oqa_" 前缀


_SUPPORTED_HOSTS: dict[str, HostSpec] = {
    "codebuddy": HostSpec(
        name="codebuddy",
        commands_dir=".codebuddy/commands",
        file_ext=".md",
        prefix_filename=False,
    ),
    "workbuddy": HostSpec(
        name="workbuddy",
        commands_dir=".workbuddy/commands",
        file_ext=".md",
        prefix_filename=False,
    ),
    "cursor": HostSpec(
        name="cursor",
        commands_dir=".cursor/rules",
        file_ext=".mdc",
        prefix_filename=True,
    ),
    "claude-code": HostSpec(
        name="claude-code",
        commands_dir=".claude/commands",
        file_ext=".md",
        prefix_filename=False,
    ),
    "windsurf": HostSpec(
        name="windsurf",
        commands_dir=".windsurf/rules",
        file_ext=".md",
        prefix_filename=True,
    ),


    "gemini": HostSpec(
        name="gemini",
        commands_dir=".gemini/commands",
        file_ext=".md",
        prefix_filename=False,
    ),
    "codex": HostSpec(
        name="codex",
        commands_dir=".codex/commands",
        file_ext=".md",
        prefix_filename=False,
    ),
}




# ──────────────────────────────────────────────────────────────────────────────
# 渲染与安装
# ──────────────────────────────────────────────────────────────────────────────

def _render_command_file(
    cmd_name: str,
    description: str,
    body: str,
    host: HostSpec,
) -> str:
    """为指定宿主渲染命令模板文件内容。"""
    if host.name in ("codebuddy", "workbuddy", "claude-code", "gemini", "codex"):
        # YAML front matter + Markdown 正文
        return (
            f"---\n"
            f"name: {cmd_name}\n"
            f"description: >\n"
            f"  {description}\n"
            f"---\n\n"
            f"{body}"
        )
    if host.name == "cursor":
        # Cursor .mdc 格式
        return (
            f"---\n"
            f"description: >\n"
            f"  {description}\n"
            f"alwaysApply: false\n"
            f"---\n\n"
            f"{body}"
        )
    if host.name == "windsurf":
        # Windsurf rules：globs 限定触发范围，不设 alwaysApply
        return (
            f"---\n"
            f"description: >\n"
            f"  {description}\n"
            f"alwaysApply: false\n"
            f"---\n\n"
            f"{body}"
        )
    return body


def install_commands(
    project_root: str | Path,
    ai_hosts: list[str],
    openqa_dir: Path,
) -> dict[str, list[Path]]:
    """将 /oqa:* 命令文件安装到各 AI 宿主目录（REQ-01-09 / REQ-02-13）。

    主路径：安装到宿主隐藏目录（.codebuddy/commands/ / .cursor/rules/ 等）。
    Fallback：若未指定任何宿主，写入 openqa/commands/ 作为通用 fallback。

    更新时会清理同目录下属于 openqa 的旧文件（前缀 oqa_ 或已知旧命令名），
    避免改名后旧文件残留。

    返回 host_name → 已写入文件路径列表 的映射。
    """
    from openqa.prompts import get_commands
    commands = get_commands()   # 按当前语言获取，缺失 fallback 到 en

    root = Path(project_root).resolve()
    written: dict[str, list[Path]] = {}

    # 安装到各 AI 宿主隐藏目录（主路径，REQ-02-13）
    for host_key in ai_hosts:
        host_key_lower = host_key.lower()
        spec = _SUPPORTED_HOSTS.get(host_key_lower)
        if spec is None:
            continue

        host_dir = root / spec.commands_dir
        host_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for cmd_name, description, body in commands:
            content = _render_command_file(cmd_name, description, body, spec)
            # oqa:run → "run"；prefix_filename 时 → "oqa_run"
            base = cmd_name.split(":")[-1]
            filename = (f"oqa_{base}" if spec.prefix_filename else base) + spec.file_ext
            dest = host_dir / filename
            dest.write_text(content, encoding="utf-8")
            paths.append(dest)

        # 清理旧的 openqa 命令文件（改名后残留）
        _cleanup_stale_commands(host_dir, paths, spec.file_ext)

        written[host_key_lower] = paths

    # Fallback：无宿主时写入 openqa/commands/（REQ-02-13 通用 fallback）
    if not ai_hosts:
        commands_dir = openqa_dir / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        fallback_paths: list[Path] = []
        for cmd_name, description, body in commands:
            base = cmd_name.split(":")[-1]
            dest = commands_dir / f"{base}.md"
            dest.write_text(
                f"---\nname: {cmd_name}\ndescription: >\n  {description}\n---\n\n{body}",
                encoding="utf-8",
            )
            fallback_paths.append(dest)
        _cleanup_stale_commands(commands_dir, fallback_paths, ".md")

    return written


def _cleanup_stale_commands(
    commands_dir: Path,
    current_paths: list[Path],
    file_ext: str,
) -> None:
    """删除同目录下属于 openqa 但不在本次写入列表里的旧命令文件。

    判断规则：文件名以 `oqa_` 开头，或匹配已知旧命令名（new/continue/run/apply/archive）。
    只清理确定属于 openqa 的文件，不误删用户自定义文件。
    """
    if not commands_dir.exists():
        return

    current_names = {p.name for p in current_paths}

    # 已知的 openqa 命令名（含历史改名）
    _known_bases = {"new", "run", "continue", "apply", "archive"}

    for f in commands_dir.iterdir():
        if f.name in current_names:
            continue  # 当前版本的文件，保留
        if not f.suffix == file_ext:
            continue
        stem = f.stem  # e.g. "oqa_new" or "new"
        # 匹配 oqa_* 前缀
        if stem.startswith("oqa_"):
            base = stem[4:]  # 去掉 oqa_ 前缀
            if base in _known_bases:
                f.unlink(missing_ok=True)
                continue
        # 匹配裸命令名（无前缀）
        if stem in _known_bases:
            f.unlink(missing_ok=True)


def detect_installed_hosts(project_root: str | Path) -> list[str]:
    """返回配置目录已存在的 AI 宿主名称列表。"""
    root = Path(project_root).resolve()
    found: list[str] = []
    for host_key, spec in _SUPPORTED_HOSTS.items():
        host_dir = root / spec.commands_dir
        # 父目录存在即视为"已安装"（如 .codebuddy/）
        if host_dir.parent.exists():
            found.append(host_key)
    return found


def get_supported_hosts() -> list[str]:
    return list(_SUPPORTED_HOSTS.keys())
