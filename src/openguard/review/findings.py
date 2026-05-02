"""代码 Review findings 生成：SARIF JSON + Markdown 摘要（REQ-06-02/04）。

OpenGuard 生成骨架 SARIF，Agent 宿主填充实际 findings。
骨架已包含：
- 规范的 SARIF 2.1.0 schema
- 规则定义（8 个检查维度）
- 空 findings 列表（供 Agent 填入）
- review_report.md 骨架

SARIF finding 字段（REQ-06-04）：
  ruleId、level（error/warning/note）、
  locations（文件路径+行号）、message、
  properties（evidence、suggestion、ears_requirement_id、is_blocking）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from openguard.utils import now_iso as _now_iso

# SARIF 标准规则 ID
SARIF_RULES = [
    {"id": "OPG001", "name": "RequirementsConsistency",  "shortDescription": "需求一致性",        "level": "warning"},
    {"id": "OPG002", "name": "ImpactScope",              "shortDescription": "影响面覆盖",        "level": "warning"},
    {"id": "OPG003", "name": "BoundaryCondition",        "shortDescription": "边界条件",          "level": "warning"},
    {"id": "OPG004", "name": "ExceptionHandling",        "shortDescription": "异常处理",          "level": "warning"},
    {"id": "OPG005", "name": "ConcurrencyPerformance",   "shortDescription": "并发/性能",         "level": "warning"},
    {"id": "OPG006", "name": "Security",                 "shortDescription": "安全",              "level": "error"},
    {"id": "OPG007", "name": "Testability",              "shortDescription": "可测试性",          "level": "note"},
    {"id": "OPG008", "name": "Maintainability",          "shortDescription": "可维护性",          "level": "note"},
]


def make_finding(
    rule_id: str,
    level: str,
    file_path: str,
    line: int,
    message: str,
    *,
    symbol: str = "",
    evidence: str = "",
    suggestion: str = "",
    ears_requirement_id: str = "",
    is_blocking: bool = False,
) -> dict[str, Any]:
    """构造一个 SARIF finding（REQ-06-04）。"""
    result: dict[str, Any] = {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": file_path},
                    "region": {"startLine": max(1, line)},
                }
            }
        ],
        "properties": {
            "is_blocking": is_blocking,
        },
    }
    if symbol:
        result["properties"]["symbol"] = symbol
    if evidence:
        result["properties"]["evidence"] = evidence
    if suggestion:
        result["properties"]["suggestion"] = suggestion
    if ears_requirement_id:
        result["properties"]["ears_requirement_id"] = ears_requirement_id
    return result


def build_sarif_skeleton(
    change_dir: Path,
    config: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造 SARIF 2.1.0 骨架（findings 可后续填充）。"""
    rules = [
        {
            "id": r["id"],
            "name": r["name"],
            "shortDescription": {"text": r["shortDescription"]},
            "defaultConfiguration": {"level": r["level"]},
        }
        for r in SARIF_RULES
    ]

    sarif: dict[str, Any] = {
        "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "openguard-review",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/openguard",
                        "rules": rules,
                    }
                },
                "results": findings or [],
                "properties": {
                    "change_id": change_dir.name,
                    "generated_at": _now_iso(),
                    "project_type": config.get("project", {}).get("type", "unknown"),
                    "review_level": config.get("defaults", {}).get("review_level", "changed"),
                    "status": "skeleton",
                    "note": "骨架 SARIF，Agent 宿主应填充真实 findings 后再执行门禁校验",
                },
            }
        ],
    }
    return sarif


def write_sarif(change_dir: Path, sarif: dict[str, Any]) -> Path:
    """写入 review_findings.sarif.json。"""
    path = change_dir / "review_findings.sarif.json"
    path.write_text(json.dumps(sarif, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def generate_review_report(
    change_dir: Path,
    sarif: dict[str, Any],
) -> Path:
    """从 SARIF 生成 review_report.md（REQ-06-02）。"""
    results: list[dict[str, Any]] = sarif.get("runs", [{}])[0].get("results", [])
    props = sarif.get("runs", [{}])[0].get("properties", {})

    blocking = [r for r in results if r.get("properties", {}).get("is_blocking")]
    warnings = [r for r in results if not r.get("properties", {}).get("is_blocking")
                and r.get("level") in ("error", "warning")]
    notes = [r for r in results if r.get("level") == "note"]

    lines: list[str] = [
        f"# Review 报告 — {change_dir.name}\n",
        f"> 生成时间：{props.get('generated_at', _now_iso())}  ",
        f"> 项目类型：{props.get('project_type', 'unknown')}  ",
        f"> review_level：{props.get('review_level', 'changed')}\n",
        "## 摘要\n",
        f"| 类别 | 数量 |",
        f"| --- | --- |",
        f"| 🔴 Blocking findings | {len(blocking)} |",
        f"| 🟡 Warning findings | {len(warnings)} |",
        f"| 🔵 Note findings | {len(notes)} |",
        f"| 总计 | {len(results)} |",
        "",
    ]

    if not results:
        lines.append(
            "> ⚠️ 骨架报告：当前无 findings。"
            "Agent 宿主应基于 review_plan.md 执行代码 Review 后补充 findings。\n"
        )
    else:
        if blocking:
            lines.append("## 🔴 Blocking Findings（阻断执行）\n")
            for r in blocking:
                lines.extend(_format_finding(r))

        if warnings:
            lines.append("## 🟡 Warning Findings\n")
            for r in warnings:
                lines.extend(_format_finding(r))

        if notes:
            lines.append("## 🔵 Note Findings\n")
            for r in notes:
                lines.extend(_format_finding(r))

    lines.append("\n## 结论\n")
    if blocking:
        lines.append(
            f"⛔ **有 {len(blocking)} 个 blocking finding，默认阻止进入验收执行（REQ-06-05）。**\n"
            "如需豁免，请在 `report_overlay.yaml` 中记录原因。"
        )
    else:
        lines.append("✅ 无 blocking finding，可进入验收执行阶段。")

    lines.append("\n---\n*Review 报告不直接修改产品代码（REQ-06-07）。*")

    path = change_dir / "review_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_review_generation(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """生成 review_findings.sarif.json 和 review_report.md（REQ-06-02）。

    返回 (sarif_path, report_path)。
    """
    sarif = build_sarif_skeleton(change_dir, config, findings)
    sarif_path = write_sarif(change_dir, sarif)
    report_path = generate_review_report(change_dir, sarif)
    return sarif_path, report_path


def has_blocking_findings(change_dir: Path) -> tuple[bool, int]:
    """检查是否有 blocking findings（REQ-06-05），返回 (has_blocking, count)。"""
    sarif_path = change_dir / "review_findings.sarif.json"
    if not sarif_path.exists():
        return False, 0
    try:
        sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
        results = sarif.get("runs", [{}])[0].get("results", [])
        blocking = [r for r in results if r.get("properties", {}).get("is_blocking")]
        return len(blocking) > 0, len(blocking)
    except Exception:
        return False, 0


def _format_finding(r: dict[str, Any]) -> list[str]:
    rule_id = r.get("ruleId", "")
    msg = r.get("message", {}).get("text", "")
    locs = r.get("locations", [])
    loc_str = ""
    if locs:
        phys = locs[0].get("physicalLocation", {})
        uri = phys.get("artifactLocation", {}).get("uri", "")
        line = phys.get("region", {}).get("startLine", 0)
        loc_str = f"`{uri}:{line}`" if uri else ""
    props = r.get("properties", {})
    lines = [f"### [{rule_id}] {msg}\n"]
    if loc_str:
        lines.append(f"- **位置**：{loc_str}")
    if props.get("evidence"):
        lines.append(f"- **证据**：{props['evidence']}")
    if props.get("suggestion"):
        lines.append(f"- **建议**：{props['suggestion']}")
    if props.get("ears_requirement_id"):
        lines.append(f"- **关联需求**：{props['ears_requirement_id']}")
    lines.append("")
    return lines
