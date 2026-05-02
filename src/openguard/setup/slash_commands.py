"""生成并安装 /opg:* slash command 模板。

OpenGuard 将命令存根安装到各 AI 宿主的命令目录。
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
命令模板内容统一定义在 openguard/prompts/<lang>/slash_commands.py。
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple



class HostSpec(NamedTuple):
    name: str
    commands_dir: str           # 相对于项目根目录（宿主的 commands 根目录）
    file_ext: str               # 如 ".md"
    prefix_filename: bool       # 文件名是否加 "opg_" 前缀
    subdir: str                 # 安装到 commands_dir 下的子目录名（空串表示直接放根目录）


_SUPPORTED_HOSTS: dict[str, HostSpec] = {
    "codebuddy": HostSpec(
        name="codebuddy",
        commands_dir=".codebuddy/commands",
        file_ext=".md",
        prefix_filename=False,
        subdir="opg",           # → .codebuddy/commands/opg/
    ),
    "workbuddy": HostSpec(
        name="workbuddy",
        commands_dir=".workbuddy/commands",
        file_ext=".md",
        prefix_filename=False,
        subdir="opg",           # → .workbuddy/commands/opg/
    ),
    "cursor": HostSpec(
        name="cursor",
        commands_dir=".cursor/rules",
        file_ext=".mdc",
        prefix_filename=True,
        subdir="",              # cursor 用 opg_ 文件名前缀区分，不用子目录
    ),
    "claude-code": HostSpec(
        name="claude-code",
        commands_dir=".claude/commands",
        file_ext=".md",
        prefix_filename=False,
        subdir="opg",           # → .claude/commands/opg/
    ),
    "windsurf": HostSpec(
        name="windsurf",
        commands_dir=".windsurf/rules",
        file_ext=".md",
        prefix_filename=True,
        subdir="",              # windsurf 用 opg_ 文件名前缀区分，不用子目录
    ),
    "gemini": HostSpec(
        name="gemini",
        commands_dir=".gemini/commands",
        file_ext=".md",
        prefix_filename=False,
        subdir="opg",           # → .gemini/commands/opg/
    ),
    "codex": HostSpec(
        name="codex",
        commands_dir=".codex/commands",
        file_ext=".md",
        prefix_filename=False,
        subdir="opg",           # → .codex/commands/opg/
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
    openguard_dir: Path,
) -> dict[str, list[Path]]:
    """将 /opg:* 命令文件安装到各 AI 宿主目录（REQ-01-09 / REQ-02-13）。

    支持子目录安装（spec.subdir 非空时写入 commands_dir/subdir/）。
    迁移时自动清理根目录的旧散落文件。

    返回 host_name → 已写入文件路径列表 的映射。
    """
    from openguard.prompts import get_commands
    commands = get_commands()

    root = Path(project_root).resolve()
    written: dict[str, list[Path]] = {}

    for host_key in ai_hosts:
        host_key_lower = host_key.lower()
        spec = _SUPPORTED_HOSTS.get(host_key_lower)
        if spec is None:
            continue

        host_root = root / spec.commands_dir  # commands 根目录（如 .codebuddy/commands/）

        # 实际写入目录：有 subdir 时写入子目录，否则直接写根目录
        if spec.subdir:
            install_dir = host_root / spec.subdir  # 如 .codebuddy/commands/opg/
        else:
            install_dir = host_root

        install_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for cmd_name, description, body in commands:
            content = _render_command_file(cmd_name, description, body, spec)
            base = cmd_name.split(":")[-1]
            filename = (f"opg_{base}" if spec.prefix_filename else base) + spec.file_ext
            dest = install_dir / filename
            dest.write_text(content, encoding="utf-8")
            paths.append(dest)

        # 清理 install_dir 内属于 openguard 的旧文件
        _cleanup_stale_commands(install_dir, paths, spec.file_ext)

        # 迁移清理：如果本次写入了子目录，清理根目录里的旧散落文件
        if spec.subdir and host_root.exists():
            _cleanup_stale_commands(host_root, [], spec.file_ext)

        written[host_key_lower] = paths

    # Fallback：无宿主时写入 openguard/commands/opg/
    if not ai_hosts:
        commands_dir = openguard_dir / "commands" / "opg"
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
        # 清理 openguard/commands/ 根目录的旧散落文件
        _cleanup_stale_commands(openguard_dir / "commands", [], ".md")

    return written


def _cleanup_stale_commands(
    commands_dir: Path,
    current_paths: list[Path],
    file_ext: str,
) -> None:
    """删除同目录下属于 openguard 但不在本次写入列表里的旧命令文件。

    识别规则（满足其一即视为 openguard 写入）：
    1. 文件名以 `opg_` 开头（cursor/windsurf 的前缀格式）
    2. 文件内容含 `name: opg:` 或 `description:` 行且内含 openguard 关键词
       （匹配 YAML front matter 特征，覆盖无前缀的 codebuddy/claude-code 格式）

    只删除确定属于 openguard 的文件，不误删用户自定义命令。
    """
    if not commands_dir.exists():
        return

    current_names = {p.name for p in current_paths}

    for f in commands_dir.iterdir():
        if f.name in current_names:
            continue  # 当前版本文件，保留
        if f.suffix != file_ext:
            continue
        if not f.is_file():
            continue
        if _is_openguard_command_file(f):
            f.unlink(missing_ok=True)


def _is_openguard_command_file(path: Path) -> bool:
    """判断一个命令文件是否由 openguard 写入。

    检测逻辑：
    - 文件名以 opg_ 开头（cursor/windsurf 前缀格式）→ 直接判定
    - 否则读取文件头部（最多 20 行），检测 YAML front matter 里是否有
      'name: opg:' 标记（codebuddy/claude-code/gemini/codex 格式）
    """
    # 规则1：文件名前缀
    if path.stem.startswith("opg_"):
        return True

    # 规则2：YAML front matter 内容特征
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]
        in_front_matter = False
        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                in_front_matter = not in_front_matter
                continue
            if in_front_matter and stripped.startswith("name:") and "opg:" in stripped:
                return True
    except Exception:
        pass
    return False


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
