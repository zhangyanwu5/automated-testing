"""代码 Review 计划生成器（REQ-06-01）。

生成 review_plan.md：描述 Review 范围、检查项和阻断策略。
内容来自 impact_graph.json + config.yaml，供 Agent 宿主执行 Review。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from openqa.utils import now_iso as _now_iso


def generate_review_plan(
    change_dir: Path,
    openqa_dir: Path,
    config: dict[str, Any],
    review_level: str = "changed",
) -> Path:
    """生成 review_plan.md 并写盘，返回路径。"""
    impact_graph = _load_json(change_dir / "impact_graph.json") or {}
    project_type = config.get("project", {}).get("type", "unknown")

    review_scope = impact_graph.get("review_scope", {})
    changed_files = impact_graph.get("changed_files", [])
    requirements_mapping = impact_graph.get("requirements_mapping", [])

    # 按 review_level 过滤范围
    files_in_scope = _filter_by_level(review_scope.get("files", []), review_level, changed_files)
    focus_areas = review_scope.get("focus_areas", _default_focus_areas(project_type))

    front_matter: dict[str, Any] = {
        "change_id": change_dir.name,
        "generated_at": _now_iso(),
        "review_level": review_level,
        "project_type": project_type,
        "file_count": len(files_in_scope),
        "status": "draft",
        "blocking_policy": "blocking findings block acceptance execution (REQ-06-05)",
    }
    fm_str = yaml.dump(front_matter, default_flow_style=False, allow_unicode=True, sort_keys=False)

    lines: list[str] = [f"---\n{fm_str}---\n"]
    lines.append(f"# Review 计划 — {change_dir.name}\n")
    lines.append(f"> review_level: `{review_level}` | 文件数: {len(files_in_scope)}\n")

    # 范围
    lines.append("\n## Review 范围\n")
    if files_in_scope:
        lines.append("| 文件 | 变更类型 | 风险级别 |")
        lines.append("| --- | --- | --- |")
        for f in files_in_scope:
            risk = f.get("risk_level", "medium")
            change_type = f.get("change_type", "unknown")
            lines.append(f"| `{f['path']}` | {change_type} | {risk} |")
    else:
        lines.append("_未检测到需要 Review 的变更文件。_")

    # 检查项（REQ-06-03）
    lines.append("\n## 检查项\n")
    check_items = [
        ("需求一致性", "代码变更是否与 requirements.md 中的 EARS 验收项一致"),
        ("影响面覆盖", "变更是否超出预期范围，是否有隐性依赖"),
        ("边界条件", "边界值、空值、最大/最小值的处理"),
        ("异常处理", "错误路径、异常捕获、降级策略"),
        ("并发/性能", "线程安全、资源竞争、内存/时间复杂度"),
        ("安全", "输入验证、权限检查、敏感数据处理"),
        ("可测试性", "是否易于单元测试或集成测试"),
        ("可维护性", "代码清晰度、命名规范、注释"),
    ]
    lines.append("| 检查维度 | 重点关注 | 严重级别 |")
    lines.append("| --- | --- | --- |")
    for dim, focus in check_items:
        lines.append(f"| {dim} | {focus} | warning |")

    # 项目类型专属检查项
    type_checks = _type_specific_checks(project_type)
    if type_checks:
        lines.append("\n### 项目特定检查项\n")
        for item in type_checks:
            lines.append(f"- {item}")

    # 需求映射
    if requirements_mapping:
        lines.append("\n## 需求一致性映射\n")
        lines.append("| 需求 ID | 受影响文件（前 3 个） |")
        lines.append("| --- | --- |")
        for node in requirements_mapping[:10]:
            files_str = ", ".join(f"`{f}`" for f in node.get("affected_files", [])[:3])
            lines.append(f"| {node['requirement_id']} | {files_str} |")

    # 阻断策略
    lines.append("\n## 阻断策略\n")
    lines.append("- **blocking** finding：默认阻止进入验收执行（REQ-06-05）")
    lines.append("- **warning** finding：记录但不阻断执行")
    lines.append("- 显式豁免需在 `report_overlay.yaml` 中记录原因")

    lines.append("\n## Agent 操作指南\n")
    lines.append("1. 对范围内每个文件，按检查维度逐项审查。")
    lines.append("2. 发现问题时，在 `review_findings.sarif.json` 中记录 finding。")
    lines.append("3. 生成 `review_report.md` 摘要。")
    lines.append("4. **不直接修改产品代码**（REQ-06-07）。")

    content = "\n".join(lines) + "\n"
    path = change_dir / "review_plan.md"
    path.write_text(content, encoding="utf-8")
    return path


def _filter_by_level(
    files: list[dict[str, Any]],
    review_level: str,
    changed_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if review_level == "off":
        return []
    if review_level == "changed":
        changed_paths = {f["path"] for f in changed_files}
        return [f for f in files if f.get("path") in changed_paths] or files
    if review_level == "risk-based":
        return [f for f in files if f.get("risk_level") == "high"] or files
    # full
    return files


def _default_focus_areas(project_type: str) -> list[str]:
    base = ["需求一致性", "边界条件", "异常处理", "可测试性"]
    extras: dict[str, list[str]] = {
        "unity": ["引擎 API 正确使用", "资源引用完整性", "内存管理"],
        "unreal": ["Blueprint 依赖", "GC 安全", "网络同步"],
        "web": ["XSS/CSRF 防护", "State 管理", "异步错误处理"],
        "backend": ["SQL 注入", "认证鉴权", "幂等性"],
        "api": ["参数校验", "错误码一致性", "限流"],
    }
    return base + extras.get(project_type, [])


def _type_specific_checks(project_type: str) -> list[str]:
    checks: dict[str, list[str]] = {
        "unity": [
            "Scene 引用是否完整，无 Missing Reference",
            "Awake/Start/OnEnable 执行顺序是否正确",
            "协程和异步操作是否有适当的取消处理",
        ],
        "unreal": [
            "UFUNCTION / UPROPERTY 宏是否正确",
            "GC 弱引用是否安全",
            "网络复制属性是否标注",
        ],
        "web": [
            "React hooks 依赖项是否完整",
            "async/await 错误处理是否覆盖",
            "敏感信息是否通过环境变量注入",
        ],
        "backend": [
            "数据库事务边界是否正确",
            "外部服务调用是否有超时和重试",
            "日志中是否有敏感信息泄漏风险",
        ],
    }
    return checks.get(project_type, [])


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
