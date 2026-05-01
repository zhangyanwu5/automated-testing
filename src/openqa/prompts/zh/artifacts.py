"""产物骨架文字 — 中文。"""
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
        f"## 目标\n\n{target}\n\n"
        "## 范围\n\n"
        "<!-- Agent：根据影响分析填写受影响模块、文件和验收范围 -->\n\n"
        "## 来源\n\n"
    )
    if from_openspec:
        body += f"关联 OpenSpec change：`{from_openspec}`\n"
    else:
        body += "<!-- 可填写需求文档链接、缺陷链接或代码 PR 链接 -->\n"
    body += "\n## 备注\n\n<!-- 人工补充 -->\n"
    return body


def requirements_md(change_id: str, created_at: str) -> str:
    import yaml as _yaml
    fm = _yaml.dump(
        {"change_id": change_id, "status": "draft", "created_at": created_at},
        default_flow_style=False, allow_unicode=True, sort_keys=False,
    )
    return (
        f"---\n{fm}---\n\n"
        "# 需求验收项\n\n"
        "> 使用 EARS 句式表达验收行为，每条需求标注稳定 ID 供矩阵、Review 和报告引用。\n\n"
        "## EARS 句式参考\n\n"
        "```\n"
        "WHEN <触发事件> THEN <系统> SHALL <响应>\n"
        "IF <前置条件> THEN <系统> SHALL <响应>\n"
        "WHILE <状态> THE <系统> SHALL <持续行为>\n"
        "```\n\n"
        "## 验收项\n\n"
        "| ID | EARS 句式 | 优先级 | 状态 |\n"
        "| --- | --- | --- | --- |\n"
        f"| {change_id}-AC-001 | <!-- Agent：填写 EARS 验收句 --> | P0 | draft |\n"
    )


def unknowns_md(change_id: str) -> str:
    return (
        f"# Unknowns — {change_id}\n\n"
        "> 列出无法由扫描自动确定、需要 Agent 或人工补充的信息。\n"
        "> 解决后请更新状态并删除对应条目，未解决的 unknowns 会阻止进入执行阶段。\n\n"
        "## 待确认项\n\n"
        "<!-- Agent：根据 intent.md 和 snapshot.json 填写具体 unknowns -->\n\n"
        "| 编号 | 问题 | 影响阶段 | 状态 |\n"
        "| --- | --- | --- | --- |\n"
    )
