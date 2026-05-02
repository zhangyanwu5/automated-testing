"""影响分析：基于 snapshot + delta 生成 impact_graph.json（REQ-04-04）。

影响图描述：
- 变更文件集合
- 受影响的需求验收项
- 需要 Review 的范围与风险点
- 推荐的测试类型和优先级
- 受影响的基线和测试数据

设计：纯确定性逻辑，不调用大模型。
Agent 宿主读取 impact_graph.json 后可通过 overlay 补充更精确的分析。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from openguard.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 影响图生成
# ──────────────────────────────────────────────────────────────────────────────

def build_impact_graph(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """基于 snapshot.json 和 delta.json 生成影响图数据（不写盘）。"""
    snapshot = _load_json(change_dir / "snapshot.json") or {}
    delta = _load_json(change_dir / "delta.json") or {}
    project_type = (
        config.get("project", {}).get("type")
        or snapshot.get("project_type", "unknown")
    )

    # 变更文件集合（delta 优先；无 delta 则视所有文件为变更）
    changed_files = _collect_changed_files(delta, snapshot)

    # 需求映射
    requirements_nodes = _map_requirements(change_dir, changed_files)

    # Review 范围
    review_scope = _build_review_scope(changed_files, project_type)

    # 测试类型推荐
    test_types = _recommend_test_types(changed_files, project_type, requirements_nodes)

    # 受影响基线
    affected_baselines = _find_affected_baselines(openguard_dir, changed_files)

    graph: dict[str, Any] = {
        "schema_version": "openguard/impact_graph/v1",
        "change_id": change_dir.name,
        "generated_at": _now_iso(),
        "project_type": project_type,
        "summary": {
            "changed_file_count": len(changed_files),
            "affected_requirement_count": len(requirements_nodes),
            "review_scope_file_count": len(review_scope.get("files", [])),
            "recommended_test_type_count": len(test_types),
        },
        "changed_files": changed_files,
        "requirements_mapping": requirements_nodes,
        "review_scope": review_scope,
        "test_types": test_types,
        "affected_baselines": affected_baselines,
        "status": "complete",
        "note": (
            "影响图由确定性规则生成，Agent 宿主可通过 report_overlay.yaml "
            "补充更精确的依赖分析、风险评估和测试建议。"
        ),
    }
    return graph


def write_impact_graph(change_dir: Path, graph: dict[str, Any]) -> Path:
    """将影响图写入 impact_graph.json。"""
    path = change_dir / "impact_graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_impact_analysis(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
) -> Path:
    """执行影响分析并写盘，返回 impact_graph.json 路径。"""
    graph = build_impact_graph(change_dir, openguard_dir, config)
    return write_impact_graph(change_dir, graph)


# ──────────────────────────────────────────────────────────────────────────────
# 内部分析函数
# ──────────────────────────────────────────────────────────────────────────────

def _collect_changed_files(
    delta: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """收集变更文件，含变更类型和语言信息。"""
    file_info: dict[str, dict[str, Any]] = {
        r["path"]: r
        for r in snapshot.get("code_files", [])
    }

    result: list[dict[str, Any]] = []

    # 有 delta 时优先使用
    if delta.get("status") == "complete":
        for path in delta.get("added", []):
            info = file_info.get(path, {})
            result.append({
                "path": path,
                "change_type": "added",
                "language": info.get("language", "unknown"),
                "symbols": info.get("symbols", []),
                "hash": info.get("hash", ""),
            })
        for path in delta.get("modified", []):
            info = file_info.get(path, {})
            result.append({
                "path": path,
                "change_type": "modified",
                "language": info.get("language", "unknown"),
                "symbols": info.get("symbols", []),
                "hash": info.get("hash", ""),
            })
        for path in delta.get("deleted", []):
            result.append({
                "path": path,
                "change_type": "deleted",
                "language": "unknown",
                "symbols": [],
                "hash": "",
            })
    else:
        # 无有效 delta，将所有扫描到的文件视为待分析变更
        for r in snapshot.get("code_files", [])[:100]:   # 限制数量避免过大
            result.append({
                "path": r["path"],
                "change_type": "unknown",
                "language": r.get("language", "unknown"),
                "symbols": r.get("symbols", []),
                "hash": r.get("hash", ""),
            })

    return result


def _map_requirements(
    change_dir: Path,
    changed_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将变更文件与 requirements.md 中的验收项建立关联（REQ-04-04）。

    当前实现：骨架映射（全部变更文件关联全部验收项）。
    Agent 宿主应通过 overlay 提供精确映射。
    """
    req_path = change_dir / "requirements.md"
    if not req_path.exists():
        return []

    content = req_path.read_text(encoding="utf-8")
    import re

    req_ids: list[str] = []
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 1:
            id_cell = cells[0]
            if re.match(r"[\w]+-\w+-\w+", id_cell) and "---" not in id_cell:
                req_ids.append(id_cell)

    if not req_ids or not changed_files:
        return []

    # 骨架映射：所有变更文件 → 所有验收项
    return [
        {
            "requirement_id": rid,
            "affected_files": [f["path"] for f in changed_files[:10]],
            "mapping_confidence": "low",
            "mapping_source": "auto-skeleton",
            "note": "骨架映射，Agent 请通过 overlay 补充精确映射关系",
        }
        for rid in req_ids
    ]


def _build_review_scope(
    changed_files: list[dict[str, Any]],
    project_type: str,
) -> dict[str, Any]:
    """构建代码 Review 范围（REQ-04-04）。"""
    # 高风险文件模式（按语言/路径判断）
    high_risk_patterns = [
        "auth", "payment", "security", "crypto", "permission",
        "admin", "config", "secret", "token", "password",
    ]

    files: list[dict[str, Any]] = []
    for f in changed_files:
        path_lower = f["path"].lower()
        risk = "high" if any(p in path_lower for p in high_risk_patterns) else "medium"
        if f["change_type"] == "deleted":
            risk = "high"
        files.append({
            "path": f["path"],
            "change_type": f["change_type"],
            "risk_level": risk,
            "language": f["language"],
        })

    # 检查重点（按项目类型）
    focus_areas = _review_focus_for_type(project_type)

    return {
        "files": files,
        "focus_areas": focus_areas,
        "estimated_review_size": len(files),
    }


def _review_focus_for_type(project_type: str) -> list[str]:
    """不同项目类型的 Review 关注重点。"""
    focus_map: dict[str, list[str]] = {
        "unity": [
            "scene 依赖变更",
            "输入管线修改",
            "引擎状态机变更",
            "资源引用完整性",
            "PlayMode 测试覆盖",
        ],
        "unreal": [
            "Blueprint 变更",
            "GameMode / GameState 修改",
            "Automation Spec 覆盖",
            "crash dump 路径",
        ],
        "web": [
            "路由变更",
            "API 接口契约",
            "状态管理",
            "XSS / CSRF 防护",
            "浏览器兼容性",
        ],
        "webgl": [
            "JS bridge 接口",
            "WebSocket 通信",
            "资源加载策略",
            "跨域策略",
        ],
        "backend": [
            "API 契约变更",
            "数据库 schema 变更",
            "认证/鉴权逻辑",
            "错误处理与日志",
            "幂等性与并发安全",
        ],
        "api": [
            "接口签名变更",
            "参数校验",
            "错误码一致性",
            "限流与熔断",
        ],
    }
    common = [
        "需求一致性验证",
        "边界条件覆盖",
        "异常处理完整性",
        "可测试性",
    ]
    return focus_map.get(project_type, []) + common


def _recommend_test_types(
    changed_files: list[dict[str, Any]],
    project_type: str,
    requirements_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """根据变更内容和项目类型推荐测试类型（REQ-04-04 / REQ-05-08）。"""
    type_map: dict[str, list[dict[str, Any]]] = {
        "unity": [
            {"type": "功能测试", "subtype": "PlayMode", "priority": 1},
            {"type": "状态校验", "subtype": "scene-state", "priority": 2},
            {"type": "性能基线", "subtype": "frame-rate", "priority": 3},
        ],
        "unreal": [
            {"type": "功能测试", "subtype": "AutomationSpec", "priority": 1},
            {"type": "回归测试", "subtype": "map-load", "priority": 2},
        ],
        "web": [
            {"type": "端到端测试", "subtype": "playwright", "priority": 1},
            {"type": "集成测试", "subtype": "api-mock", "priority": 2},
            {"type": "兼容性测试", "subtype": "browser", "priority": 3},
        ],
        "webgl": [
            {"type": "端到端测试", "subtype": "browser-webgl", "priority": 1},
            {"type": "性能基线", "subtype": "fps-memory", "priority": 2},
        ],
        "backend": [
            {"type": "契约测试", "subtype": "api-contract", "priority": 1},
            {"type": "集成测试", "subtype": "service-chain", "priority": 2},
            {"type": "单元测试", "subtype": "unit", "priority": 3},
        ],
        "api": [
            {"type": "契约测试", "subtype": "openapi", "priority": 1},
            {"type": "功能测试", "subtype": "endpoint", "priority": 2},
        ],
    }

    types = list(type_map.get(project_type, [
        {"type": "功能测试", "subtype": "black-box", "priority": 1},
    ]))

    # 若有需求映射，补充需求验收测试
    if requirements_nodes:
        types.append({
            "type": "需求验收",
            "subtype": "ears-acceptance",
            "priority": 0,  # 最高优先级
        })

    return sorted(types, key=lambda x: x["priority"])


def _find_affected_baselines(
    openguard_dir: Path,
    changed_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """查找可能受影响的基线（简单实现：扫描 baselines/ 目录的 metadata）。"""
    baselines_dir = openguard_dir / "baselines"
    if not baselines_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for meta_file in sorted(baselines_dir.glob("**/*.yaml"))[:20]:
        try:
            with meta_file.open(encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue
        results.append({
            "baseline_id": meta.get("id", meta_file.stem),
            "type": meta.get("type", "unknown"),
            "path": str(meta_file.relative_to(openguard_dir)),
        })

    return results


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
