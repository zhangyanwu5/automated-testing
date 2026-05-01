"""Artifact skeleton content — English."""
from __future__ import annotations


def intent_md(
    change_id: str,
    target: str,
    scan_scope: str,
    created_at: str,
    from_openspec: str | None = None,
    test_suite: str | None = None,
) -> str:
    import yaml as _yaml
    front: dict = {
        "change_id": change_id,
        "created_at": created_at,
        "target": target,
        "scan_scope": scan_scope,
    }
    if test_suite:
        front["test_suite"] = test_suite
    if from_openspec:
        front["from_openspec"] = from_openspec

    fm = _yaml.dump(front, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body = (
        f"---\n{fm}---\n\n"
        f"## Goal\n\n{target}\n\n"
        "## Scope\n\n"
        "<!-- Agent: fill in affected modules, files and acceptance scope based on impact analysis -->\n\n"
        "## Source\n\n"
    )
    if from_openspec:
        body += f"Linked OpenSpec change: `{from_openspec}`\n"
    else:
        body += "<!-- Link to requirement doc, bug report or code PR -->\n"
    body += "\n## Notes\n\n<!-- Manual additions -->\n"
    return body


def requirements_md(change_id: str, created_at: str) -> str:
    import yaml as _yaml
    fm = _yaml.dump(
        {"change_id": change_id, "status": "draft", "created_at": created_at},
        default_flow_style=False, allow_unicode=True, sort_keys=False,
    )
    return (
        f"---\n{fm}---\n\n"
        "# Acceptance Criteria\n\n"
        "> Write each acceptance criterion in EARS form, with a stable ID.\n\n"
        "## EARS reference\n\n"
        "```\n"
        "WHEN <trigger> THEN <system> SHALL <response>\n"
        "IF <precondition> THEN <system> SHALL <response>\n"
        "WHILE <state> THE <system> SHALL <ongoing behavior>\n"
        "```\n\n"
        "## Criteria\n\n"
        "| ID | EARS statement | Priority | Status |\n"
        "| --- | --- | --- | --- |\n"
        f"| {change_id}-AC-001 | <!-- Agent: fill in EARS statement --> | P0 | draft |\n"
    )


def unknowns_md(change_id: str) -> str:
    return (
        f"# Unknowns — {change_id}\n\n"
        "> List items that cannot be determined by scanning and need Agent or manual input.\n"
        "> Remove resolved items; unresolved unknowns block the apply phase.\n\n"
        "## Open items\n\n"
        "<!-- Agent: fill in specific unknowns based on intent.md and snapshot.json -->\n\n"
        "| # | Question | Affects phase | Status |\n"
        "| --- | --- | --- | --- |\n"
    )
