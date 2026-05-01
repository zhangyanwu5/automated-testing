"""OpenSpec 检测与联动（REQ-12）。

功能：
1. 检测项目中是否安装 OpenSpec（REQ-12-01）
2. 从 OpenSpec change 产物提取信息创建 QA change（REQ-12-02/03）
3. 写入 openspec_link.yaml（REQ-12-04）
4. 验证需求变化后重新计算指纹（REQ-12-07）
5. 门禁通过后输出可归档结论（REQ-12-06）
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from openqa.utils import now_iso as _now_iso


# OpenSpec 项目根目录下的标志文件/目录
_OPENSPEC_MARKERS = [
    ".openspec",           # OpenSpec 配置目录
    "openspec/changes",    # OpenSpec changes 目录
    "openspec.config.yaml",
]


# ──────────────────────────────────────────────────────────────────────────────
# OpenSpec 检测（REQ-12-01）
# ──────────────────────────────────────────────────────────────────────────────

def detect_openspec(project_root: Path) -> dict[str, Any]:
    """检测项目中是否存在 OpenSpec 配置（REQ-12-01）。

    返回：{installed: bool, root: str, changes_dir: str, detected_from: []}
    """
    detected_from: list[str] = []
    installed = False
    openspec_root: Path | None = None
    changes_dir: Path | None = None

    for marker in _OPENSPEC_MARKERS:
        candidate = project_root / marker
        if candidate.exists():
            installed = True
            detected_from.append(marker)
            if "changes" in marker:
                changes_dir = candidate
            else:
                openspec_root = candidate.parent if candidate.is_file() else candidate

    if installed and openspec_root is None:
        # 默认根目录下 openspec/ 目录
        openspec_root = project_root / "openspec"

    if installed and changes_dir is None:
        candidate_changes = (openspec_root or project_root) / "changes"
        if candidate_changes.exists():
            changes_dir = candidate_changes
        else:
            changes_dir = project_root / "openspec" / "changes"

    return {
        "installed": installed,
        "root": str(openspec_root) if openspec_root else "",
        "changes_dir": str(changes_dir) if changes_dir else "",
        "detected_from": detected_from,
    }


def list_openspec_changes(project_root: Path) -> list[str]:
    """列出所有 OpenSpec change ID。"""
    info = detect_openspec(project_root)
    if not info["installed"]:
        return []
    changes_dir = Path(info["changes_dir"])
    if not changes_dir.exists():
        return []
    return [d.name for d in sorted(changes_dir.iterdir()) if d.is_dir()]


# ──────────────────────────────────────────────────────────────────────────────
# openspec_link.yaml 写入（REQ-12-04）
# ──────────────────────────────────────────────────────────────────────────────

def write_openspec_link(
    change_dir: Path,
    openspec_change_id: str,
    project_root: Path,
) -> Path:
    """写入 openspec_link.yaml，记录来源引用（REQ-12-04）。

    记录：OpenSpec change ID、产物路径、哈希、同步时间。
    """
    info = detect_openspec(project_root)
    changes_dir = Path(info["changes_dir"]) if info["changes_dir"] else project_root / "openspec" / "changes"
    openspec_change_dir = changes_dir / openspec_change_id

    # 扫描 OpenSpec 产物
    artifacts: dict[str, Any] = {}
    for artifact_name in ("proposal.md", "specs", "design.md", "tasks.md"):
        artifact_path = openspec_change_dir / artifact_name
        if artifact_path.exists():
            if artifact_path.is_file():
                content = artifact_path.read_bytes()
                artifacts[artifact_name] = {
                    "path": str(artifact_path.relative_to(project_root)),
                    "hash": hashlib.sha256(content).hexdigest()[:32],
                }
            elif artifact_path.is_dir():
                # specs/ 目录：记录所有 .md 文件
                spec_files = []
                for spec_file in sorted(artifact_path.glob("*.md")):
                    content = spec_file.read_bytes()
                    spec_files.append({
                        "path": str(spec_file.relative_to(project_root)),
                        "hash": hashlib.sha256(content).hexdigest()[:32],
                    })
                artifacts[artifact_name] = spec_files

    link: dict[str, Any] = {
        "schema_version": "openqa/openspec_link/v1",
        "openspec_change_id": openspec_change_id,
        "synced_at": _now_iso(),
        "artifacts": artifacts,
    }

    link_path = change_dir / "openspec_link.yaml"
    link_path.write_text(
        yaml.dump(link, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return link_path


def read_openspec_link(change_dir: Path) -> dict[str, Any] | None:
    """读取 openspec_link.yaml；不存在返回 None。"""
    link_path = change_dir / "openspec_link.yaml"
    if not link_path.exists():
        return None
    with link_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ──────────────────────────────────────────────────────────────────────────────
# 从 OpenSpec 提取需求（REQ-12-03）
# ──────────────────────────────────────────────────────────────────────────────

def extract_requirements_from_openspec(
    openspec_change_id: str,
    project_root: Path,
) -> str:
    """从 OpenSpec specs/ 提取需求内容，转换为 EARS 格式模板（REQ-12-03）。

    返回 requirements.md 的文本内容。
    """
    info = detect_openspec(project_root)
    changes_dir = Path(info["changes_dir"]) if info["changes_dir"] else project_root / "openspec" / "changes"
    openspec_change_dir = changes_dir / openspec_change_id

    lines: list[str] = [
        f"# requirements.md",
        f"",
        f"<!-- 来源：OpenSpec change {openspec_change_id} (REQ-12-03) -->",
        f"<!-- 以下验收项从 OpenSpec specs/ 提取，Agent 应补充 EARS 句式并确认验收点 -->",
        f"",
    ]

    # proposal.md → 目标说明
    proposal_path = openspec_change_dir / "proposal.md"
    if proposal_path.exists():
        lines += [
            "## 变更目标（来自 OpenSpec proposal）",
            "",
            f"<!-- 来源：{proposal_path.name} -->",
            "",
        ]
        lines.append(proposal_path.read_text(encoding="utf-8"))
        lines.append("")

    # specs/ → EARS 验收项模板
    specs_dir = openspec_change_dir / "specs"
    if specs_dir.exists() and specs_dir.is_dir():
        lines += ["## 验收项（来自 OpenSpec specs）", ""]
        for spec_file in sorted(specs_dir.glob("*.md")):
            lines += [
                f"### {spec_file.stem}",
                "",
                f"<!-- 来源：specs/{spec_file.name} -->",
                "",
                spec_file.read_text(encoding="utf-8"),
                "",
            ]

    # tasks.md → 测试范围提示
    tasks_path = openspec_change_dir / "tasks.md"
    if tasks_path.exists():
        lines += [
            "## 测试范围（来自 OpenSpec tasks）",
            "",
            f"<!-- 来源：{tasks_path.name} — Agent 参考任务划分确定执行顺序和验收阶段 -->",
            "",
            tasks_path.read_text(encoding="utf-8"),
            "",
        ]

    if not any([proposal_path.exists(), specs_dir.exists(), tasks_path.exists()]):
        lines += [
            "<!-- OpenSpec change 产物不存在，请手动填写验收项 -->",
            "",
            "## 验收项",
            "",
            "| ID | EARS 句式 | 优先级 |",
            "|----|-----------|--------|",
            "| REQ-001 | <!-- WHEN ... THE ... SHALL ... --> | P1 |",
        ]

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 需求变化检测（REQ-12-07）
# ──────────────────────────────────────────────────────────────────────────────

def check_openspec_changed(
    change_dir: Path,
    project_root: Path,
) -> dict[str, Any]:
    """检测 OpenSpec 产物是否在上次同步后发生变化（REQ-12-07）。

    返回：{changed: bool, changed_artifacts: [], detail}
    """
    link = read_openspec_link(change_dir)
    if not link:
        return {"changed": False, "changed_artifacts": [], "detail": "无 openspec_link.yaml"}

    openspec_change_id = link.get("openspec_change_id", "")
    info = detect_openspec(project_root)
    changes_dir = Path(info["changes_dir"]) if info["changes_dir"] else project_root / "openspec" / "changes"
    openspec_change_dir = changes_dir / openspec_change_id

    changed_artifacts: list[str] = []
    old_artifacts: dict[str, Any] = link.get("artifacts", {})

    for artifact_name, old_info in old_artifacts.items():
        artifact_path = openspec_change_dir / artifact_name
        if artifact_path.is_file():
            current_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()[:32]
            old_hash = old_info.get("hash", "") if isinstance(old_info, dict) else ""
            if old_hash and current_hash != old_hash:
                changed_artifacts.append(artifact_name)
        elif artifact_path.is_dir():
            # specs/ 目录
            if isinstance(old_info, list):
                for old_spec in old_info:
                    spec_path = project_root / old_spec.get("path", "")
                    if spec_path.exists():
                        current_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()[:32]
                        if current_hash != old_spec.get("hash", ""):
                            changed_artifacts.append(old_spec["path"])

    return {
        "changed": len(changed_artifacts) > 0,
        "changed_artifacts": changed_artifacts,
        "detail": f"OpenSpec change {openspec_change_id}，变化产物：{changed_artifacts}" if changed_artifacts else "无变化",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 门禁通过后输出可归档结论（REQ-12-06）
# ──────────────────────────────────────────────────────────────────────────────

def generate_archive_clearance(
    change_dir: Path,
    gate_report: dict[str, Any],
) -> dict[str, Any]:
    """生成 OpenSpec archive 可用的质量结论（REQ-12-06）。

    输出：{cleared: bool, conclusion, gate, change_id, openspec_change_id}
    """
    gate_result = gate_report.get("result", "")
    waived = gate_report.get("waived", False)
    change_id = gate_report.get("change_id", "")

    link = read_openspec_link(change_dir)
    openspec_change_id = link.get("openspec_change_id", "") if link else ""

    cleared = gate_result == "passed" or waived
    conclusion = "PASS" if gate_result == "passed" else ("WAIVED" if waived else "FAIL")

    return {
        "schema_version": "openqa/archive_clearance/v1",
        "cleared": cleared,
        "conclusion": conclusion,
        "gate": gate_report.get("gate", ""),
        "change_id": change_id,
        "openspec_change_id": openspec_change_id,
        "gate_report_path": str(change_dir / "gate_report.yaml"),
        "generated_at": _now_iso(),
        "note": (
            "PASS：质量门禁通过，可执行 /opsx:archive。"
            if cleared else
            "FAIL：质量门禁未通过，需修复问题或人工豁免后再执行 /opsx:archive。"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 修复建议输出（REQ-12-05）
# ──────────────────────────────────────────────────────────────────────────────

def generate_fix_suggestions(
    gate_report: dict[str, Any],
    change_dir: Path,
) -> list[dict[str, Any]]:
    """门禁失败时生成可回写给开发 Agent 的修复建议（REQ-12-05）。

    返回修复建议列表；默认不修改 OpenSpec 产物（只读模式）。
    """
    suggestions: list[dict[str, Any]] = []
    blockers = gate_report.get("blockers", [])

    for blocker in blockers:
        category = blocker.get("category", "unknown")
        message = blocker.get("message", "")

        if category == "test_failure":
            suggestions.append({
                "type": "test_failure_fix",
                "description": f"测试失败：{message}",
                "suggested_action": "检查失败用例的 evidence 文件，定位产品代码问题",
                "target": "product_code",
                "write_to_openspec": False,  # 默认只读（REQ-12）
            })
        elif category == "blocking_review":
            suggestions.append({
                "type": "review_fix",
                "description": f"Review 阻断：{message}",
                "suggested_action": "修复 review_findings.sarif.json 中标注的问题",
                "target": "product_code",
                "write_to_openspec": False,
            })
        elif category == "unknown_results":
            suggestions.append({
                "type": "evidence_supplement",
                "description": f"存在 UNKNOWN 结果：{message}",
                "suggested_action": "补充证据文件或改善日志采集，重新执行 /oqa:apply",
                "target": "test_scripts_or_logging",
                "write_to_openspec": False,
            })
        else:
            suggestions.append({
                "type": "general_fix",
                "description": message,
                "suggested_action": "查看 gate_report.yaml 获取详细信息",
                "target": "varies",
                "write_to_openspec": False,
            })

    return suggestions


# ──────────────────────────────────────────────────────────────────────────────
# OpenSpec 有效性校验（REQ-12-08 / REQ-12-09 / REQ-12-10 / REQ-03-11）
# ──────────────────────────────────────────────────────────────────────────────

# 校验状态值（REQ-12-09）
OPENSPEC_STATUS_CONSISTENT = "consistent"
OPENSPEC_STATUS_STALE = "stale"               # 规格存在但代码已变更
OPENSPEC_STATUS_NOT_IMPLEMENTED = "not_implemented"  # 规格存在但代码缺失
OPENSPEC_STATUS_MEDIUM = "medium"             # 进行中的 change，置信度 medium


def validate_openspec_consistency(
    change_dir: Path,
    openspec_change_id: str,
    project_root: Path,
) -> dict[str, Any]:
    """对 OpenSpec 内容做有效性校验（REQ-12-08/09/10）。

    校验：
    1. 比对 specs 描述的接口与当前代码实现是否一致。
    2. 判断 OpenSpec change 是否处于进行中（未 archive）。
    3. 将结果写入 openspec_link.yaml。
    4. stale / not_implemented 条目写入 unknowns.md（REQ-12-10）。

    返回：{checks: [...], summary: {consistent, stale, not_implemented, medium}}
    """
    info = detect_openspec(project_root)
    if not info["installed"]:
        return {"checks": [], "summary": {}, "note": "未检测到 OpenSpec"}

    changes_dir = Path(info["changes_dir"]) if info["changes_dir"] else project_root / "openspec" / "changes"
    openspec_change_dir = changes_dir / openspec_change_id

    checks: list[dict[str, Any]] = []

    # 1. 检查 OpenSpec change 是否存在
    if not openspec_change_dir.exists():
        return {
            "checks": [],
            "summary": {},
            "note": f"OpenSpec change {openspec_change_id} 不存在",
        }

    # 2. 检查 change 是否处于进行中（未 archive）
    # 简单判断：若 openspec/changes/<id>/ 目录存在但没有 archived 标志
    archived_marker = openspec_change_dir / ".archived"
    is_in_progress = not archived_marker.exists()

    # 3. 扫描 specs/ 目录，逐一比对代码
    specs_dir = openspec_change_dir / "specs"
    spec_files = list(specs_dir.glob("*.md")) if specs_dir.exists() else []

    for spec_file in spec_files:
        spec_content = spec_file.read_text(encoding="utf-8", errors="replace")
        spec_name = spec_file.stem

        # 从 spec 内容中提取接口名（简单模式匹配）
        interface_names = _extract_interface_names_from_spec(spec_content)

        if not interface_names:
            # 无法提取接口，标记为 medium（REQ-12-08 场景3）
            status = OPENSPEC_STATUS_MEDIUM if is_in_progress else OPENSPEC_STATUS_CONSISTENT
            checks.append({
                "spec": spec_file.name,
                "status": status,
                "confidence": "medium" if is_in_progress else "low",
                "reason": "无法从 spec 提取接口名" + ("（change 进行中）" if is_in_progress else ""),
                "interfaces_checked": [],
            })
            continue

        # 在代码中查找接口实现
        found_interfaces: list[str] = []
        missing_interfaces: list[str] = []
        for iface in interface_names[:5]:  # 限制检查数量
            found = _find_interface_in_code(project_root, iface)
            if found:
                found_interfaces.append(iface)
            else:
                missing_interfaces.append(iface)

        # 判断状态
        if missing_interfaces and not found_interfaces:
            status = OPENSPEC_STATUS_NOT_IMPLEMENTED
            confidence = "high"
        elif missing_interfaces:
            status = OPENSPEC_STATUS_STALE
            confidence = "medium"
        elif is_in_progress:
            status = OPENSPEC_STATUS_MEDIUM
            confidence = "medium"
        else:
            status = OPENSPEC_STATUS_CONSISTENT
            confidence = "high"

        checks.append({
            "spec": spec_file.name,
            "spec_name": spec_name,
            "status": status,
            "confidence": confidence,
            "interfaces_checked": interface_names[:5],
            "found": found_interfaces,
            "missing": missing_interfaces,
            "in_progress": is_in_progress,
        })

    # 4. 将校验结果写回 openspec_link.yaml（REQ-12-09）
    _write_validation_to_link(change_dir, checks, openspec_change_id)

    # 5. stale/not_implemented 写入 unknowns.md（REQ-12-10）
    problematic = [c for c in checks if c["status"] in (OPENSPEC_STATUS_STALE, OPENSPEC_STATUS_NOT_IMPLEMENTED)]
    if problematic:
        _write_openspec_unknowns(change_dir, problematic)

    summary = {
        OPENSPEC_STATUS_CONSISTENT: sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_CONSISTENT),
        OPENSPEC_STATUS_STALE: sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_STALE),
        OPENSPEC_STATUS_NOT_IMPLEMENTED: sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_NOT_IMPLEMENTED),
        OPENSPEC_STATUS_MEDIUM: sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_MEDIUM),
    }

    return {"checks": checks, "summary": summary}


def _extract_interface_names_from_spec(spec_content: str) -> list[str]:
    """从 spec Markdown 内容中提取接口/类/函数名（简单模式匹配）。"""
    import re
    names: list[str] = []
    # 查找代码块中的方法/类名
    for m in re.finditer(r'`(\w+(?:\.\w+)+)`|`(\w+[A-Z]\w+)`', spec_content):
        name = m.group(1) or m.group(2)
        if name and len(name) > 4:
            names.append(name)
    # 去重
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result[:5]


def _find_interface_in_code(project_root: Path, interface_name: str) -> bool:
    """在代码中查找接口实现（简单文件扫描）。"""
    # 轻量：只扫描 src/ Assets/ 等主要目录的代码文件
    search_dirs = [
        project_root / "src",
        project_root / "Assets",
        project_root / "Source",
        project_root / "app",
    ]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for code_file in search_dir.rglob("*"):
            if not code_file.is_file():
                continue
            if code_file.suffix.lower() not in (".cs", ".cpp", ".py", ".ts", ".js", ".go", ".java"):
                continue
            try:
                content = code_file.read_text(encoding="utf-8", errors="ignore")
                if interface_name in content:
                    return True
            except Exception:
                continue
    return False


def _write_validation_to_link(
    change_dir: Path,
    checks: list[dict[str, Any]],
    openspec_change_id: str,
) -> None:
    """将校验结果写入 openspec_link.yaml（REQ-12-09）。"""
    link_path = change_dir / "openspec_link.yaml"
    if not link_path.exists():
        return

    with link_path.open(encoding="utf-8") as f:
        link = yaml.safe_load(f) or {}

    link["validation"] = {
        "validated_at": _now_iso(),
        "openspec_change_id": openspec_change_id,
        "checks": checks,
    }
    link_path.write_text(
        yaml.dump(link, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _write_openspec_unknowns(
    change_dir: Path,
    problematic_checks: list[dict[str, Any]],
) -> None:
    """将不一致的 OpenSpec 规格写入 unknowns.md（REQ-12-10）。"""
    unknowns_path = change_dir / "unknowns.md"
    if unknowns_path.exists():
        content = unknowns_path.read_text(encoding="utf-8")
    else:
        content = "# Unknowns\n\n<!-- 待确认项，由 openqa new/continue 自动填充。 -->\n\n"

    entries: list[str] = ["\n## OpenSpec 规格有效性问题（REQ-12-10）\n"]
    for check in problematic_checks:
        status = check["status"]
        spec = check.get("spec", "")
        missing = check.get("missing", [])
        if status == OPENSPEC_STATUS_NOT_IMPLEMENTED:
            entries.append(
                f"- **{spec}**（规格存在但代码缺失）：接口 {missing} 未找到对应实现，"
                f"无法生成测试矩阵，需要补充实现或确认规格变更。"
            )
        elif status == OPENSPEC_STATUS_STALE:
            entries.append(
                f"- **{spec}**（规格过期）：接口 {missing} 代码已变更或消失，"
                f"需确认规格是否仍有效。"
            )

    content += "\n".join(entries) + "\n"
    unknowns_path.write_text(content, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

