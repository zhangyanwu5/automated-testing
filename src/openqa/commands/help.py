"""``openqa help`` – 显示详细帮助和下一步建议。"""
from __future__ import annotations

import sys
from pathlib import Path

from openqa.workspace.layout import find_openqa_dir, is_initialized


def run_help(project_dir: str = ".") -> int:
    from openqa.prompts import get_cli
    print(get_cli("HELP_USAGE"))

    # 根据当前项目状态给出上下文感知的下一步建议
    root = Path(project_dir).resolve()
    openqa_dir = find_openqa_dir(root)

    if openqa_dir is None:
        print("Next step:")
        print("  openqa init    Initialize OpenQA in this project.")
        print()
        return 0

    # openqa/ exists, give change-aware suggestions
    changes_dir = openqa_dir / "changes"
    active_changes: list[Path] = []
    if changes_dir.is_dir():
        for change in sorted(changes_dir.iterdir()):
            state_file = change / "state.yaml"
            if state_file.is_file():
                active_changes.append(change)

    print("Current project:")
    print(f"  openqa/ at: {openqa_dir}")

    if active_changes:
        latest = active_changes[-1]
        print(f"  Active change: {latest.name}")
        print()
        print("Suggested next steps:")
        print("  openqa continue    Advance the active change.")
        print("  openqa apply       Run Review and tests when ready.")
    else:
        print()
        print("Suggested next steps:")
        print("  openqa new <goal>  Start a new QA change.")
        print("  openqa update      Refresh /oqa:* commands after upgrading OpenQA.")

    print()
    return 0
