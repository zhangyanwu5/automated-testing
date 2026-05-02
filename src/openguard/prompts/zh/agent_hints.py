"""Agent 提示语 — 中文。"""
from __future__ import annotations

ADVANCE_STEPS: list[tuple[str, str, str, bool]] = [
    (
        "intent.md",
        "变更意图",
        "读取 intent.md，确认目标和范围描述；补充缺失内容。",
        False,
    ),
    (
        "requirements.md",
        "EARS 验收标准",
        "读取 requirements.md，以 EARS 句式填写每条验收项并标注 ID。",
        False,
    ),
    (
        "snapshot.json",
        "事实快照（自动扫描）",
        "snapshot.json 正在自动生成…",
        True,
    ),
    (
        "delta.json",
        "增量差异（自动扫描）",
        "delta.json 正在自动生成…",
        True,
    ),
    (
        "impact_graph.json",
        "影响分析（自动生成）",
        "impact_graph.json 正在自动生成…",
        True,
    ),
    (
        "test_knowledge.md",
        "测试知识",
        "基于 requirements.md 和 impact_graph.json，生成 test_knowledge.md（见 openguard-run skill 中的 Cases 契约格式）。",
        False,
    ),
    (
        "review_plan.md",
        "Review 计划",
        "基于 impact_graph.json，生成 review_plan.md（Review 范围、检查项、阻断规则）。",
        False,
    ),
    (
        "test_matrix.json",
        "测试矩阵（自动生成）",
        "test_matrix.json 正在自动生成…",
        True,
    ),
]

# 向后兼容别名
CONTINUE_STEPS = ADVANCE_STEPS

UNKNOWNS_HINT = (
    "所有产物已生成，但仍有未解决的 unknowns。\n"
    "\n"
    "Agent，请：\n"
    "  读取 unknowns.md，逐条确认或回答，然后更新状态。\n"
    "  解决所有 unknowns 后重新运行 `openguard _advance`。"
)

READY_FOR_APPLY = (
    "所有必需产物已就绪。\n"
    "\n"
    "停止：向用户呈现以下摘要，等待用户确认后才能执行 `openguard apply`："
)

MISSING_ARTIFACT_HEADER = "Agent，请："

AUTO_GENERATE_FAILED = "  请手动解决后重新运行 `openguard _advance`"

ADVANCE_UNKNOWNS_HINT = "存在未解决的 unknowns，请先解决后再继续。"
