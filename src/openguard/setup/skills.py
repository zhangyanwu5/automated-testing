"""生成并安装 OpenGuard Agent Skill 文件（REQ-01-19 / REQ-14）。

Skill 是 OpenGuard 与 AI 宿主之间的协议层，告诉 AI 在每个高层指令下：
- 调用哪些 CLI
- 读哪些文件
- 输出什么
- 何时追问用户
- 遵守哪些 guardrails

安装路径（REQ-14-01 / REQ-14-08）：
  - CodeBuddy  → .codebuddy/skills/openguard-<name>/SKILL.md
  - Cursor     → .cursor/skills/openguard-<name>/SKILL.md
  - Claude Code → .claude/skills/openguard-<name>/SKILL.md
  - Windsurf   → .windsurf/skills/openguard-<name>/SKILL.md
  - Gemini CLI → .gemini/skills/openguard-<name>/SKILL.md
  - Codex CLI  → .codex/skills/openguard-<name>/SKILL.md
  - 通用 fallback → openguard/commands/<name>.md

`openguard update` 可刷新 skill 内容，不覆盖 openguard/ 产物（REQ-14-02）。
Skill 内容统一定义在 openguard/prompts/<lang>/skills.py。
"""
from __future__ import annotations

from pathlib import Path

# Skill 名称由 en 版本定义（权威来源）
from openguard.prompts.en.skills import SKILL_NAMES


# ──────────────────────────────────────────────────────────────────────────────
# 宿主 Skill 目录映射
# ──────────────────────────────────────────────────────────────────────────────

_HOST_SKILL_DIRS: dict[str, str] = {
    "codebuddy":  ".codebuddy/skills",
    "workbuddy":  ".workbuddy/skills",
    "cursor":     ".cursor/skills",
    "claude-code": ".claude/skills",
    "windsurf":   ".windsurf/skills",
    "gemini":     ".gemini/skills",
    "codex":      ".codex/skills",
}


# ──────────────────────────────────────────────────────────────────────────────
# 安装逻辑
# ──────────────────────────────────────────────────────────────────────────────

def install_skills(
    project_root: str | Path,
    ai_hosts: list[str],
    openguard_dir: Path,
) -> dict[str, list[Path]]:
    """将 skill 文件安装到各 AI 宿主的 skill 目录（REQ-14-01 / REQ-14-08 / REQ-02-13）。

    主路径：安装到宿主隐藏目录（.codebuddy/skills/ 等）。
    Fallback：若未指定任何宿主，写入 openguard/commands/<name>.md。
    更新时会删除同目录下属于 openguard 的旧 skill 目录（如 openguard-new/）。
    返回 host_name → 写入文件路径列表。
    """
    from openguard.prompts import get_skill
    import shutil

    root = Path(project_root).resolve()
    written: dict[str, list[Path]] = {}

    for host_key in ai_hosts:
        host_key_lower = host_key.lower()
        skills_base = _HOST_SKILL_DIRS.get(host_key_lower)
        if skills_base is None:
            continue

        skills_root = root / skills_base
        paths: list[Path] = []
        for skill_name in SKILL_NAMES:
            skill_dir = skills_root / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            dest = skill_dir / "SKILL.md"
            dest.write_text(get_skill(skill_name), encoding="utf-8")
            paths.append(dest)

        # 清理旧的 openguard-* skill 目录（改名后残留，如 openguard-new/）
        _cleanup_stale_skills(skills_root, set(SKILL_NAMES))

        written[host_key_lower] = paths

    if not ai_hosts:
        commands_dir = openguard_dir / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        for skill_name in SKILL_NAMES:
            dest = commands_dir / f"{skill_name}.md"
            dest.write_text(get_skill(skill_name), encoding="utf-8")

    return written


def _cleanup_stale_skills(skills_root: Path, current_skill_names: set[str]) -> None:
    """删除 skills_root 下属于 openguard 但不在当前列表里的旧 skill 目录。

    只清理 openguard-* 前缀的目录，不误删用户自定义 skill。
    """
    if not skills_root.exists():
        return
    for d in skills_root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith("openguard-") and d.name not in current_skill_names:
            import shutil as _shutil
            _shutil.rmtree(d, ignore_errors=True)


def detect_installed_skill_hosts(project_root: str | Path) -> list[str]:
    """返回 skill 目录已存在的 AI 宿主名称列表。"""
    root = Path(project_root).resolve()
    found: list[str] = []
    for host_key, skills_base in _HOST_SKILL_DIRS.items():
        if (root / skills_base).exists():
            found.append(host_key)
    return found
