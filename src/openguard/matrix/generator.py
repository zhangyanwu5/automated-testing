"""测试矩阵生成器（REQ-05）。

输入：
  - requirements.md（EARS 验收项）
  - test_knowledge.md（Agent 填充的断言线索、前置条件）
  - impact_graph.json（影响图）
  - config.yaml（项目画像、runtime、automation）
  - test_assets/（已验证稳定脚本）

输出：test_matrix.json

矩阵结构：
  tasks[]               — 可执行任务列表，支持 DAG 依赖
  execution_strategy    — 套件、门禁、超时、并发预算
  runtime_requirements  — 执行前必需配置
  script_references[]   — 引用的稳定脚本（含锚点状态）
  blockers[]            — 阻断执行的问题

设计原则（REQ-05）：
- 同一策略和输入生成的矩阵稳定可复现（REQ-05 验收标准）。
- 无法执行项必须标记 skipped/blocked，不得静默省略（REQ-05-04）。
- runtime 配置缺失时任务标记 blocked（REQ-05-09）。
- 优先引用 verified 脚本（REQ-05-11）。
- 每个引用脚本的任务记录锚点状态和哈希（REQ-05-12）。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from openguard.utils import now_iso as _now_iso

MATRIX_SCHEMA_VERSION = "openguard/test_matrix/v1"

# 合法的 test_suite 值（REQ-05-01）
VALID_TEST_SUITES = {"smoke", "incremental", "requirement-full", "regression", "full"}


# ──────────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────────

def build_test_matrix(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    test_suite: str | None = None,
) -> dict[str, Any]:
    """生成 test_matrix.json 数据（不写盘）。"""
    # 读取输入产物
    snapshot = _load_json(change_dir / "snapshot.json") or {}
    impact_graph = _load_json(change_dir / "impact_graph.json") or {}
    test_knowledge = _load_md_structured(change_dir / "test_knowledge.md")
    requirements = _parse_requirements(change_dir / "requirements.md")

    # 确定策略
    defaults = config.get("defaults", {})
    suite = _resolve_suite(test_suite, defaults.get("test_suite", "smoke"))
    gate = defaults.get("gate", "local")
    review_level = defaults.get("review_level", "changed")

    # 项目画像
    project_type = config.get("project", {}).get("type", "unknown")
    runtime_cfg = config.get("runtime", {})
    automation_cfg = config.get("automation", {})

    # Runtime 就绪检查（REQ-05-09）
    runtime_blockers = _check_runtime_blockers(runtime_cfg, automation_cfg)

    # 加载稳定脚本（REQ-05-11）
    script_refs = _load_script_references(openguard_dir, suite)

    # 生成任务列表
    tasks = _generate_tasks(
        requirements=requirements,
        impact_graph=impact_graph,
        test_knowledge=test_knowledge,
        project_type=project_type,
        suite=suite,
        runtime_blockers=runtime_blockers,
        script_refs=script_refs,
        snapshot=snapshot,
    )

    # 查询接口知识，补充断言方式和证据策略（REQ-05-14）
    interface_knowledge_summary = _query_interface_knowledge(openguard_dir)

    # 为每个任务绑定前置路径（REQ-05-13）
    tasks = _bind_preconditions_to_tasks(tasks, openguard_dir)

    # 执行策略配置
    execution_strategy = _build_execution_strategy(suite, gate, config)

    matrix: dict[str, Any] = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "change_id": change_dir.name,
        "generated_at": _now_iso(),
        "snapshot_version": snapshot.get("analyzer_version", ""),
        "test_suite": suite,
        "gate": gate,
        "review_level": review_level,
        "project_type": project_type,
        "execution_strategy": execution_strategy,
        "runtime_requirements": {
            "status": "incomplete" if runtime_blockers else "complete",
            "blockers": runtime_blockers,
        },
        "script_references": script_refs,
        "tasks": tasks,
        "interface_knowledge_summary": interface_knowledge_summary,
        "summary": {
            "total": len(tasks),
            "runnable": sum(1 for t in tasks if t["status"] == "ready"),
            "blocked": sum(1 for t in tasks if t["status"] == "blocked"),
            "skipped": sum(1 for t in tasks if t["status"] == "skipped"),
            "needs_confirmation": sum(1 for t in tasks if t["status"] == "needs-confirmation"),
        },
    }
    return matrix


def write_test_matrix(change_dir: Path, matrix: dict[str, Any]) -> Path:
    """将矩阵写入 test_matrix.json。"""
    path = change_dir / "test_matrix.json"
    path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_matrix_generation(
    change_dir: Path,
    openguard_dir: Path,
    config: dict[str, Any],
    test_suite: str | None = None,
) -> Path:
    """生成并写入 test_matrix.json，返回路径。"""
    matrix = build_test_matrix(change_dir, openguard_dir, config, test_suite)
    return write_test_matrix(change_dir, matrix)


# ──────────────────────────────────────────────────────────────────────────────
# 策略解析
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_suite(requested: str | None, default: str) -> str:
    suite = (requested or default or "smoke").lower()
    return suite if suite in VALID_TEST_SUITES else "smoke"


def _build_execution_strategy(
    suite: str,
    gate: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """按套件和门禁构建执行策略（REQ-05-03 / REQ-05-07）。"""
    defaults = config.get("defaults", {})

    # 各套件默认超时和并发（秒）
    timeout_map = {
        "smoke": 120,
        "incremental": 300,
        "requirement-full": 600,
        "regression": 900,
        "full": 3600,
    }
    concurrency_map = {
        "smoke": 1,
        "incremental": 2,
        "requirement-full": 2,
        "regression": 3,
        "full": 4,
    }

    return {
        "suite": suite,
        "gate": gate,
        "timeout_seconds": defaults.get("timeout_seconds", timeout_map.get(suite, 300)),
        "max_parallel": defaults.get("max_parallel", concurrency_map.get(suite, 2)),
        "fail_fast": suite == "smoke",   # 冒烟测试失败立即停止（REQ-05-07）
        "retry_count": 1 if suite in ("smoke", "incremental") else 0,
        "selection_basis": _selection_basis_for_suite(suite),
    }


def _selection_basis_for_suite(suite: str) -> str:
    """说明各套件的选择依据（REQ-05-06）。"""
    basis_map = {
        "smoke": "核心 happy path、环境启动验证、最小数据准备",
        "incremental": "delta.json 变更文件、impact_graph.json 影响子图、Review 风险、历史失败",
        "requirement-full": "requirements.md 全部 EARS 验收项、边界条件、异常路径",
        "regression": "历史高价值用例、历史缺陷路径、核心业务链路",
        "full": "全部可执行矩阵、基线检查、兼容性、长稳、性能门禁",
    }
    return basis_map.get(suite, "auto")


# ──────────────────────────────────────────────────────────────────────────────
# Runtime 就绪检查（REQ-05-09）
# ──────────────────────────────────────────────────────────────────────────────

def _check_runtime_blockers(
    runtime_cfg: dict[str, Any],
    automation_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """检查真实执行所需配置，缺失项生成 blocker（REQ-05-09）。"""
    blockers: list[dict[str, Any]] = []

    if runtime_cfg.get("status") == "incomplete":
        for missing in runtime_cfg.get("missing", []):
            blockers.append({
                "type": "missing_runtime_config",
                "field": missing,
                "reason": f"runtime.{missing} 未配置，真实执行将失败",
                "impact": "blocked",
            })

    for missing in automation_cfg.get("missing", []):
        blockers.append({
            "type": "missing_automation_config",
            "field": missing,
            "reason": f"automation.{missing} 未配置，无法连接控制通道",
            "impact": "needs-confirmation",
        })

    return blockers


# ──────────────────────────────────────────────────────────────────────────────
# 脚本引用（REQ-05-11 / REQ-05-12）
# ──────────────────────────────────────────────────────────────────────────────

def _load_script_references(
    openguard_dir: Path,
    suite: str,
) -> list[dict[str, Any]]:
    """加载 test_assets/ 中适用于当前套件的脚本（REQ-05-11）。

    - verified：直接引用
    - needs-review：引用但标注
    - stale / broken：不引用（REQ-05-11）
    """
    scripts_dir = openguard_dir / "test_assets" / "scripts"
    if not scripts_dir.is_dir():
        return []

    refs: list[dict[str, Any]] = []
    for meta_file in sorted(scripts_dir.glob("**/*.meta.yaml")):
        try:
            with meta_file.open(encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue

        status = meta.get("status", "verified")
        applicable_suites = meta.get("applicable_suites", list(VALID_TEST_SUITES))

        # stale / broken 不引用（REQ-05-11）
        if status in ("stale", "broken"):
            continue

        # 套件适用性检查
        if suite not in applicable_suites and "full" not in applicable_suites:
            continue

        ref: dict[str, Any] = {
            "script_path": meta.get("script_path", ""),
            "anchor_status": status,
            "anchor_hash": meta.get("anchor_hash", ""),  # REQ-05-12
            "confidence": meta.get("confidence", "medium"),
            "applicable_suites": applicable_suites,
        }
        if status == "needs-review":
            ref["warning"] = "脚本状态为 needs-review，执行结果仅供参考，不得阻断 release/nightly gate"
        refs.append(ref)

    return refs


# ──────────────────────────────────────────────────────────────────────────────
# 任务生成（REQ-05-02 / REQ-05-03 / REQ-05-04 / REQ-05-05）
# ──────────────────────────────────────────────────────────────────────────────

def _generate_tasks(
    requirements: list[dict[str, Any]],
    impact_graph: dict[str, Any],
    test_knowledge: dict[str, Any],
    project_type: str,
    suite: str,
    runtime_blockers: list[dict[str, Any]],
    script_refs: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """生成任务列表。"""
    tasks: list[dict[str, Any]] = []

    # 任务状态：若有 runtime blocker 则 blocked
    has_hard_blocker = any(b["impact"] == "blocked" for b in runtime_blockers)
    has_soft_blocker = any(b["impact"] == "needs-confirmation" for b in runtime_blockers)

    def _task_status(base: str = "ready") -> str:
        if has_hard_blocker:
            return "blocked"
        if has_soft_blocker:
            return "needs-confirmation"
        return base

    # ── Task 1：环境准备（所有套件均有）────────────────────────────────────────
    tasks.append(_make_task(
        task_id="T-ENV-001",
        name="环境准备与健康检查",
        type="precondition",
        subtype="env-setup",
        priority=0,
        status=_task_status(),
        depends_on=[],
        project_type=project_type,
        runtime_blockers=runtime_blockers,
    ))

    # ── Task 2+：需求验收项（requirement-full 时全部；其他套件取 P0）──────────
    for req in requirements:
        req_id = req.get("id", "")
        priority = 0 if req.get("priority", "P0") == "P0" else 1

        if suite == "smoke" and priority > 0:
            tasks.append(_make_task(
                task_id=f"T-REQ-{req_id}-SKIPPED",
                name=f"验收：{req_id}（{req.get('text', '')[:40]}）",
                type="acceptance",
                subtype="ears-acceptance",
                priority=priority,
                status="skipped",
                depends_on=["T-ENV-001"],
                skip_reason=f"suite=smoke 只执行 P0 用例，{req_id} 为 {req.get('priority','P0')}",
                requirement_id=req_id,
            ))
            continue

        if suite == "incremental":
            # 只执行影响图中标注的验收项
            impacted_ids = {
                node["requirement_id"]
                for node in impact_graph.get("requirements_mapping", [])
            }
            if req_id and impacted_ids and req_id not in impacted_ids:
                tasks.append(_make_task(
                    task_id=f"T-REQ-{req_id}-SKIPPED",
                    name=f"验收：{req_id}",
                    type="acceptance",
                    subtype="ears-acceptance",
                    priority=priority,
                    status="skipped",
                    depends_on=["T-ENV-001"],
                    skip_reason=f"incremental 模式下 {req_id} 不在影响图中",
                    requirement_id=req_id,
                ))
                continue

        # 为该需求匹配脚本引用
        matched_scripts = [
            s for s in script_refs
            if req_id in s.get("script_path", "")
        ]

        # 从 test_knowledge.cases 中读取 AI 填写的 produces_tags / required_precondition_tags
        # AI 不填则为空，CLI 不做任何推断
        tk_cases: list[dict[str, Any]] = test_knowledge.get("cases", [])
        tk_case = next((c for c in tk_cases if c.get("id") == req_id), {})
        produces = tk_case.get("produces_tags") or None
        required_precond = tk_case.get("required_precondition_tags") or None

        tasks.append(_make_task(
            task_id=f"T-REQ-{req_id}",
            name=f"验收：{req_id}（{req.get('text', '')[:40]}）",
            type="acceptance",
            subtype="ears-acceptance",
            priority=priority,
            status=_task_status(),
            depends_on=["T-ENV-001"],
            requirement_id=req_id,
            script_refs=matched_scripts,
            produces_tags=produces,
            required_precondition_tags=required_precond,
        ))

    # ── Task：冒烟 happy path（无需求时提供默认冒烟任务）─────────────────────
    if suite in ("smoke", "incremental") and not requirements:
        tasks.append(_make_task(
            task_id="T-SMOKE-001",
            name="核心 Happy Path 冒烟",
            type="functional",
            subtype="happy-path",
            priority=0,
            status=_task_status(),
            depends_on=["T-ENV-001"],
            note="需求未定义，Agent 请根据 test_knowledge.md 填充具体验收步骤",
        ))

    # ── Task：测试知识扩展任务（来自 test_knowledge.md 解析）─────────────────
    for item in test_knowledge.get("items", [])[:10]:
        if item.get("status") == "draft":
            tasks.append(_make_task(
                task_id=f"T-KN-{item['id']}",
                name=item.get("name", f"知识任务 {item['id']}"),
                type=item.get("type", "functional"),
                subtype=item.get("subtype", "unknown"),
                priority=2,
                status="needs-confirmation",
                depends_on=["T-ENV-001"],
                note="来自 test_knowledge.md，Agent 请确认前置条件和断言",
            ))

    return tasks


def _make_task(
    task_id: str,
    name: str,
    type: str,
    subtype: str,
    priority: int,
    status: str,
    depends_on: list[str],
    *,
    project_type: str = "",
    runtime_blockers: list[dict[str, Any]] | None = None,
    skip_reason: str = "",
    requirement_id: str = "",
    script_refs: list[dict[str, Any]] | None = None,
    note: str = "",
    produces_tags: list[str] | None = None,
    required_precondition_tags: list[str] | None = None,
) -> dict[str, Any]:
    task: dict[str, Any] = {
        "task_id": task_id,
        "name": name,
        "type": type,
        "subtype": subtype,
        "priority": priority,
        "status": status,
        "depends_on": depends_on,
        "timeout_seconds": 60,
        "retry": 0,
    }
    if requirement_id:
        task["requirement_id"] = requirement_id
    if script_refs:
        task["script_refs"] = script_refs   # REQ-05-12
    if skip_reason:
        task["skip_reason"] = skip_reason
    if runtime_blockers:
        task["runtime_blockers"] = runtime_blockers
    if note:
        task["note"] = note
    if produces_tags:
        task["produces_tags"] = produces_tags
    if required_precondition_tags:
        task["required_precondition_tags"] = required_precondition_tags
    return task


# ──────────────────────────────────────────────────────────────────────────────
# 输入解析辅助
# ──────────────────────────────────────────────────────────────────────────────

def _parse_requirements(req_path: Path) -> list[dict[str, Any]]:
    """从 requirements.md 解析 EARS 验收项列表。"""
    if not req_path.exists():
        return []
    import re
    items: list[dict[str, Any]] = []
    content = req_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        id_cell, text_cell = cells[0], cells[1] if len(cells) > 1 else ""
        priority_cell = cells[2] if len(cells) > 2 else "P0"
        if re.match(r"[\w]+-\w+-\w+", id_cell) and "---" not in id_cell and "<!--" not in text_cell:
            items.append({
                "id": id_cell,
                "text": text_cell,
                "priority": priority_cell,
            })
    return items


def _load_md_structured(path: Path) -> dict[str, Any]:
    """从 test_knowledge.md 提取结构化数据。

    AI Agent 在 test_knowledge.md 中写入如下结构化块：

    ```yaml
    # test_knowledge.md front matter
    external_preconditions:
      - logged_in          # 需要外部前置路径的状态标签
    ```

    以及 ## Cases 区块内的 JSON 块：

    ```json
    [
      {
        "id": "TC-LOGIN-001",
        "title": "正常登录",
        "produces_tags": ["logged_in"],
        "required_precondition_tags": []
      },
      {
        "id": "TC-LOGIN-005",
        "title": "断线重连",
        "produces_tags": [],
        "required_precondition_tags": ["logged_in"]
      }
    ]
    ```

    CLI 只读取、不推断。AI 不填则对应字段为空，不影响执行。
    """
    if not path.exists():
        return {"items": [], "cases": [], "external_preconditions": []}

    content = path.read_text(encoding="utf-8")
    result: dict[str, Any] = {"items": [], "cases": [], "external_preconditions": []}

    # 解析 YAML front matter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            try:
                fm = yaml.safe_load(content[3:end]) or {}
                result["external_preconditions"] = fm.get("external_preconditions", [])
            except Exception:
                pass

    # 解析 ## Cases 区块中的 JSON 代码块
    import re
    cases_section = re.search(
        r"##\s*Cases?\s*\n.*?```(?:json)?\s*\n(.*?)```",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if cases_section:
        try:
            cases = json.loads(cases_section.group(1).strip())
            if isinstance(cases, list):
                result["cases"] = cases
        except Exception:
            pass

    # 兼容旧格式：表格行解析（items）
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and re.match(r"TK-\d+", cells[0]):
            result["items"].append({
                "id": cells[0],
                "name": cells[1],
                "type": cells[2] if len(cells) > 2 else "functional",
                "subtype": cells[3] if len(cells) > 3 else "unknown",
                "status": "draft",
            })

    return result


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 前置路径绑定（REQ-05-13）
# ──────────────────────────────────────────────────────────────────────────────

def _bind_preconditions_to_tasks(
    tasks: list[dict[str, Any]],
    openguard_dir: Path,
) -> list[dict[str, Any]]:
    """为任务绑定前置路径（REQ-05-13 / REQ-13-32）。

    优先级：
    1. 外部已验证前置路径（preconditions.yaml）
    2. 同 change 内能产出所需状态的上游用例（建立 depends_on 依赖）
    3. 以上都没有 → 标记 blocked

    这样"测试登录流程"里，TC-005/006/007 依赖 logged_in，
    而 TC-001 能产出 logged_in，系统自动建立 TC-005 depends_on TC-001，
    而不是报 Unknown。
    """
    try:
        from openguard.knowledge.preconditions import find_preconditions
        knowledge_dir = openguard_dir / "knowledge"
    except ImportError:
        return tasks

    # 建立 task_id → produces_tags 的索引，用于同 change 内依赖推导
    produces_index: dict[str, list[str]] = {}
    for task in tasks:
        tags = task.get("produces_tags", [])
        if tags:
            produces_index[task["task_id"]] = tags

    updated_tasks: list[dict[str, Any]] = []
    for task in tasks:
        required_tags: list[str] = task.get("required_precondition_tags", [])

        if not required_tags:
            updated_tasks.append(task)
            continue

        # 1. 尝试外部已验证前置路径
        matches = find_preconditions(knowledge_dir, required_tags)
        if matches:
            best_match = matches[0]
            task["precondition_ref"] = {
                "tags": best_match.get("tags", []),
                "setup_path": best_match.get("setup_path"),
                "mode": best_match.get("mode", "unknown"),
                "status": best_match.get("status", "unknown"),
                "source": "preconditions.yaml",
            }
            if best_match.get("status") == "needs-review":
                task["precondition_warning"] = "前置路径为 needs-review 状态，请确认有效性"
            updated_tasks.append(task)
            continue

        # 2. 在同 change 内寻找能产出所需状态的上游用例
        required_set = set(required_tags)
        intra_providers: list[str] = []
        for provider_id, provided_tags in produces_index.items():
            if required_set.issubset(set(provided_tags)):
                intra_providers.append(provider_id)

        if intra_providers:
            # 找到同 change 内的上游用例，建立依赖
            best_provider = intra_providers[0]  # 取第一个（通常只有一个）
            if best_provider not in task.get("depends_on", []):
                task.setdefault("depends_on", []).append(best_provider)
            task["precondition_ref"] = {
                "tags": required_tags,
                "source": "intra_change",
                "provided_by": best_provider,
            }
            updated_tasks.append(task)
            continue

        # 3. 以上都找不到 → blocked
        if task.get("status") == "ready":
            task["status"] = "blocked"
        task["blockers"] = task.get("blockers", []) + [{
            "type": "missing_precondition",
            "reason": (
                f"所需前置状态 {required_tags} 在 preconditions.yaml 中无匹配路径，"
                f"同 change 内也无用例能产出该状态，"
                f"需要建立前置路径（REQ-13-30）"
            ),
        }]
        task["precondition_ref"] = None
        updated_tasks.append(task)

    return updated_tasks


def _infer_produces_tags(req_text: str) -> list[str]:
    """已废弃：不再做关键词推断。

    produces_tags 由 AI Agent 在 test_knowledge.md 的 cases 字段中填写。
    保留函数签名避免破坏现有调用，始终返回空列表。
    """
    return []


def _infer_required_precondition_tags(req_text: str, self_produces: list[str]) -> list[str]:
    """已废弃：不再做关键词推断。

    required_precondition_tags 由 AI Agent 在 test_knowledge.md 的 cases 字段中填写。
    保留函数签名避免破坏现有调用，始终返回空列表。
    """
    return []


def _query_interface_knowledge(
    openguard_dir: Path,
) -> dict[str, Any]:
    """查询接口知识，用于推断断言方式和证据采集策略（REQ-05-14）。

    inferred 状态的接口知识只能生成候选，不得直接用于执行矩阵。
    """
    knowledge_dir = openguard_dir / "knowledge"
    summary: dict[str, Any] = {
        "event_catalog_count": 0,
        "protocol_catalog_count": 0,
        "state_schema_count": 0,
        "verified_count": 0,
        "inferred_count": 0,
        "note": "inferred 状态的接口知识只能用于生成候选矩阵（REQ-09-15）",
    }

    try:
        from openguard.knowledge.manager import get_interface_knowledge, INTERFACE_KNOWLEDGE_FILES
        catalog_map = {
            "event_catalog_count": "event_catalog.yaml",
            "protocol_catalog_count": "protocol_catalog.yaml",
            "state_schema_count": "state_schema.yaml",
        }
        for key, fname in catalog_map.items():
            items = get_interface_knowledge(knowledge_dir, fname)
            summary[key] = len(items)
            summary["verified_count"] += sum(1 for i in items if i.get("status") == "verified")
            summary["inferred_count"] += sum(1 for i in items if i.get("status") == "inferred")
    except Exception:
        pass

    return summary
