"""``openguard help`` – 显示详细帮助和下一步建议。"""
from __future__ import annotations

import sys
from pathlib import Path

from openguard.workspace.layout import find_openguard_dir, is_initialized


def run_help(project_dir: str = ".") -> int:
    from openguard.prompts import get_cli
    print(get_cli("HELP_USAGE"))

    # 根据当前项目状态给出上下文感知的下一步建议
    root = Path(project_dir).resolve()
    openguard_dir = find_openguard_dir(root)

    if openguard_dir is None:
        print("Next step:")
        print("  openguard init    Initialize OpenGuard in this project.")
        print()
        return 0

    # openguard/ exists, give change-aware suggestions
    changes_dir = openguard_dir / "changes"
    active_changes: list[Path] = []
    if changes_dir.is_dir():
        for change in sorted(changes_dir.iterdir()):
            state_file = change / "state.yaml"
            if state_file.is_file():
                active_changes.append(change)

    print("Current project:")
    print(f"  openguard/ at: {openguard_dir}")

    if active_changes:
        latest = active_changes[-1]
        print(f"  Active change: {latest.name}")
        print()
        print("Suggested next steps:")
        print("  openguard continue    Advance the active change.")
        print("  openguard apply       Run Review and tests when ready.")
    else:
        print()
        print("Suggested next steps:")
        print("  openguard new <goal>  Start a new QA change.")
        print("  openguard update      Refresh /opg:* commands after upgrading OpenGuard.")

    print()
    return 0
