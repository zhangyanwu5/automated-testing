"""Agent hints — English.

Strings printed to stdout for AI Agent consumption during `openqa _advance`.
"""
from __future__ import annotations

# 状态机步骤列表（供 openqa _advance 内部使用）
# 格式：(artifact_filename, human_label, agent_hint, is_auto_generated)
ADVANCE_STEPS: list[tuple[str, str, str, bool]] = [
    (
        "intent.md",
        "change intent",
        "Read intent.md, confirm the goal and scope description; fill in any missing parts.",
        False,
    ),
    (
        "requirements.md",
        "EARS acceptance criteria",
        "Read requirements.md, write each acceptance item in EARS sentence form with an ID.",
        False,
    ),
    (
        "snapshot.json",
        "fact snapshot (auto-scan)",
        "snapshot.json is being generated automatically…",
        True,
    ),
    (
        "delta.json",
        "incremental delta (auto-scan)",
        "delta.json is being generated automatically…",
        True,
    ),
    (
        "impact_graph.json",
        "impact analysis (auto-generated)",
        "impact_graph.json is being generated automatically…",
        True,
    ),
    (
        "test_knowledge.md",
        "test knowledge",
        (
            "Based on requirements.md and impact_graph.json, generate test_knowledge.md "
            "(see Cases contract format in openqa-run skill)."
        ),
        False,
    ),
    (
        "review_plan.md",
        "Review plan",
        "Based on impact_graph.json, generate review_plan.md describing Review scope, checklist and blocking rules.",
        False,
    ),
    (
        "test_matrix.json",
        "test matrix (auto-generated)",
        "test_matrix.json is being generated automatically…",
        True,
    ),
]

# 向后兼容别名
CONTINUE_STEPS = ADVANCE_STEPS

UNKNOWNS_HINT = (
    "All artifacts generated, but there are unresolved unknowns.\n"
    "\n"
    "Agent, please:\n"
    "  Read unknowns.md, confirm or answer each item, then update state.\n"
    "  Re-run `openqa _advance` after all unknowns are resolved."
)

READY_FOR_APPLY = (
    "All required artifacts are ready.\n"
    "\n"
    "STOP: Present the following summary to the user and wait for confirmation before running `openqa apply`:"
)

MISSING_ARTIFACT_HEADER = "Agent, please:"

AUTO_GENERATE_FAILED = "  Please resolve manually then re-run `openqa _advance`"

ADVANCE_UNKNOWNS_HINT = "Unresolved unknowns found, please resolve them before continuing."
