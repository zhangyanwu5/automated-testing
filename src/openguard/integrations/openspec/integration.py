"""OpenSpec 集成插件（实现 SpecProvider 协议）。

OpenSpec 的完整实现，包含检测、联动、校验和门禁逻辑。
核心代码通过 get_registry().get_spec_provider() 调用，不直接 import 本模块。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from openguard.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────────────────────

_OPENSPEC_MARKERS = [
    ".openspec",
    "openspec/changes",
    "openspec.config.yaml",
]

OPENSPEC_STATUS_CONSISTENT      = "consistent"
OPENSPEC_STATUS_STALE           = "stale"
OPENSPEC_STATUS_NOT_IMPLEMENTED = "not_implemented"
OPENSPEC_STATUS_MEDIUM          = "medium"


# ──────────────────────────────────────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _detect(project_root: Path) -> dict[str, Any]:
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
        openspec_root = project_root / "openspec"
    if installed and changes_dir is None:
        candidate_changes = (openspec_root or project_root) / "changes"
        changes_dir = candidate_changes if candidate_changes.exists() else project_root / "openspec" / "changes"

    return {
        "installed": installed,
        "root": str(openspec_root) if openspec_root else "",
        "changes_dir": str(changes_dir) if changes_dir else "",
        "detected_from": detected_from,
    }


def _changes_dir(project_root: Path) -> Path:
    info = _detect(project_root)
    return Path(info["changes_dir"]) if info["changes_dir"] else project_root / "openspec" / "changes"


def _read_link(change_dir: Path) -> dict[str, Any] | None:
    link_path = change_dir / "openspec_link.yaml"
    if not link_path.exists():
        return None
    with link_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _extract_interface_names(spec_content: str) -> list[str]:
    names: list[str] = []
    for m in re.finditer(r'`(\w+(?:\.\w+)+)`|`(\w+[A-Z]\w+)`', spec_content):
        name = m.group(1) or m.group(2)
        if name and len(name) > 4:
            names.append(name)
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result[:5]


def _find_in_code(project_root: Path, name: str) -> bool:
    search_dirs = [project_root / d for d in ("src", "Assets", "Source", "app")]
    for sd in search_dirs:
        if not sd.exists():
            continue
        for f in sd.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".cs", ".cpp", ".py", ".ts", ".js", ".go", ".java"):
                continue
            try:
                if name in f.read_text(encoding="utf-8", errors="ignore"):
                    return True
            except Exception:
                continue
    return False


# ──────────────────────────────────────────────────────────────────────────────
# OpenSpecIntegration
# ──────────────────────────────────────────────────────────────────────────────

class OpenSpecIntegration:
    """OpenSpec 规格提供者，实现 SpecProvider 协议。"""

    name = "openspec"
    display_name = "OpenSpec"

    # ── 检测 ──────────────────────────────────────────────────────────────────

    def detect(self, project_root: Path) -> dict[str, Any]:
        return _detect(project_root)

    def list_changes(self, project_root: Path) -> list[str]:
        info = _detect(project_root)
        if not info["installed"]:
            return []
        cd = Path(info["changes_dir"])
        if not cd.exists():
            return []
        return [d.name for d in sorted(cd.iterdir()) if d.is_dir()]

    # ── 联动 ──────────────────────────────────────────────────────────────────

    def write_link(self, change_dir: Path, spec_change_id: str, project_root: Path) -> Path:
        """写入 openspec_link.yaml（REQ-12-04）。"""
        ocd = _changes_dir(project_root) / spec_change_id
        artifacts: dict[str, Any] = {}
        for aname in ("proposal.md", "specs", "design.md", "tasks.md"):
            ap = ocd / aname
            if ap.is_file():
                content = ap.read_bytes()
                artifacts[aname] = {
                    "path": str(ap.relative_to(project_root)),
                    "hash": hashlib.sha256(content).hexdigest()[:32],
                }
            elif ap.is_dir():
                spec_files = []
                for sf in sorted(ap.glob("*.md")):
                    content = sf.read_bytes()
                    spec_files.append({
                        "path": str(sf.relative_to(project_root)),
                        "hash": hashlib.sha256(content).hexdigest()[:32],
                    })
                artifacts[aname] = spec_files

        link: dict[str, Any] = {
            "schema_version": "openguard/openspec_link/v1",
            "openspec_change_id": spec_change_id,
            "synced_at": _now_iso(),
            "artifacts": artifacts,
        }
        link_path = change_dir / "openspec_link.yaml"
        link_path.write_text(
            yaml.dump(link, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return link_path

    def read_link(self, change_dir: Path) -> dict[str, Any] | None:
        return _read_link(change_dir)

    def extract_requirements(self, spec_change_id: str, project_root: Path) -> str:
        """从 OpenSpec specs/ 提取需求（REQ-12-03）。"""
        ocd = _changes_dir(project_root) / spec_change_id
        lines: list[str] = [
            "# requirements.md", "",
            f"<!-- 来源：OpenSpec change {spec_change_id} (REQ-12-03) -->",
            "<!-- 以下验收项从 OpenSpec specs/ 提取，Agent 应补充 EARS 句式并确认验收点 -->", "",
        ]

        proposal_path = ocd / "proposal.md"
        if proposal_path.exists():
            lines += ["## 变更目标（来自 OpenSpec proposal）", "",
                      f"<!-- 来源：{proposal_path.name} -->", ""]
            lines.append(proposal_path.read_text(encoding="utf-8"))
            lines.append("")

        specs_dir = ocd / "specs"
        if specs_dir.exists() and specs_dir.is_dir():
            lines += ["## 验收项（来自 OpenSpec specs）", ""]
            for sf in sorted(specs_dir.glob("*.md")):
                lines += [f"### {sf.stem}", "", f"<!-- 来源：specs/{sf.name} -->", "",
                          sf.read_text(encoding="utf-8"), ""]

        tasks_path = ocd / "tasks.md"
        if tasks_path.exists():
            lines += ["## 测试范围（来自 OpenSpec tasks）", "",
                      f"<!-- 来源：{tasks_path.name} — Agent 参考任务划分 -->", "",
                      tasks_path.read_text(encoding="utf-8"), ""]

        if not any([proposal_path.exists(), specs_dir.exists(), tasks_path.exists()]):
            lines += ["<!-- OpenSpec change 产物不存在，请手动填写验收项 -->", "",
                      "## 验收项", "",
                      "| ID | EARS 句式 | 优先级 |",
                      "|----|-----------|--------|",
                      "| REQ-001 | <!-- WHEN ... THE ... SHALL ... --> | P1 |"]

        return "\n".join(lines)

    # ── 有效性校验 ────────────────────────────────────────────────────────────

    def validate_consistency(
        self, change_dir: Path, spec_change_id: str, project_root: Path,
    ) -> dict[str, Any]:
        """对 OpenSpec 内容做有效性校验（REQ-12-08/09/10）。"""
        info = _detect(project_root)
        if not info["installed"]:
            return {"checks": [], "summary": {}, "note": "未检测到 OpenSpec"}

        ocd = _changes_dir(project_root) / spec_change_id
        if not ocd.exists():
            return {"checks": [], "summary": {}, "note": f"OpenSpec change {spec_change_id} 不存在"}

        is_in_progress = not (ocd / ".archived").exists()
        specs_dir = ocd / "specs"
        spec_files = list(specs_dir.glob("*.md")) if specs_dir.exists() else []

        checks: list[dict[str, Any]] = []
        for sf in spec_files:
            spec_content = sf.read_text(encoding="utf-8", errors="replace")
            ifaces = _extract_interface_names(spec_content)
            if not ifaces:
                status = OPENSPEC_STATUS_MEDIUM if is_in_progress else OPENSPEC_STATUS_CONSISTENT
                checks.append({"spec": sf.name, "status": status,
                                "confidence": "medium" if is_in_progress else "low",
                                "reason": "无法从 spec 提取接口名" + ("（change 进行中）" if is_in_progress else ""),
                                "interfaces_checked": []})
                continue

            found = [i for i in ifaces[:5] if _find_in_code(project_root, i)]
            missing = [i for i in ifaces[:5] if not _find_in_code(project_root, i)]

            if missing and not found:
                status, confidence = OPENSPEC_STATUS_NOT_IMPLEMENTED, "high"
            elif missing:
                status, confidence = OPENSPEC_STATUS_STALE, "medium"
            elif is_in_progress:
                status, confidence = OPENSPEC_STATUS_MEDIUM, "medium"
            else:
                status, confidence = OPENSPEC_STATUS_CONSISTENT, "high"

            checks.append({"spec": sf.name, "spec_name": sf.stem, "status": status,
                            "confidence": confidence, "interfaces_checked": ifaces[:5],
                            "found": found, "missing": missing, "in_progress": is_in_progress})

        # 写回 openspec_link.yaml
        link_path = change_dir / "openspec_link.yaml"
        if link_path.exists():
            with link_path.open(encoding="utf-8") as f:
                link = yaml.safe_load(f) or {}
            link["validation"] = {"validated_at": _now_iso(),
                                   "openspec_change_id": spec_change_id, "checks": checks}
            link_path.write_text(
                yaml.dump(link, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

        # stale/not_implemented 写入 unknowns.md
        problematic = [c for c in checks if c["status"] in
                       (OPENSPEC_STATUS_STALE, OPENSPEC_STATUS_NOT_IMPLEMENTED)]
        if problematic:
            unknowns_path = change_dir / "unknowns.md"
            content = unknowns_path.read_text(encoding="utf-8") if unknowns_path.exists() else \
                "# Unknowns\n\n<!-- 待确认项 -->\n\n"
            entries = ["\n## OpenSpec 规格有效性问题（REQ-12-10）\n"]
            for c in problematic:
                spec, miss = c.get("spec", ""), c.get("missing", [])
                if c["status"] == OPENSPEC_STATUS_NOT_IMPLEMENTED:
                    entries.append(f"- **{spec}**（规格存在但代码缺失）：接口 {miss} 未找到实现。")
                else:
                    entries.append(f"- **{spec}**（规格过期）：接口 {miss} 已变更或消失。")
            unknowns_path.write_text(content + "\n".join(entries) + "\n", encoding="utf-8")

        summary = {
            OPENSPEC_STATUS_CONSISTENT:      sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_CONSISTENT),
            OPENSPEC_STATUS_STALE:           sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_STALE),
            OPENSPEC_STATUS_NOT_IMPLEMENTED: sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_NOT_IMPLEMENTED),
            OPENSPEC_STATUS_MEDIUM:          sum(1 for c in checks if c["status"] == OPENSPEC_STATUS_MEDIUM),
        }
        return {"checks": checks, "summary": summary}

    def check_changed(self, change_dir: Path, project_root: Path) -> dict[str, Any]:
        """检测 OpenSpec 产物是否在上次同步后发生变化（REQ-12-07）。"""
        link = _read_link(change_dir)
        if not link:
            return {"changed": False, "changed_artifacts": [], "detail": "无 openspec_link.yaml"}

        spec_change_id = link.get("openspec_change_id", "")
        ocd = _changes_dir(project_root) / spec_change_id
        changed_artifacts: list[str] = []

        for aname, old_info in link.get("artifacts", {}).items():
            ap = ocd / aname
            if ap.is_file():
                cur = hashlib.sha256(ap.read_bytes()).hexdigest()[:32]
                old = old_info.get("hash", "") if isinstance(old_info, dict) else ""
                if old and cur != old:
                    changed_artifacts.append(aname)
            elif ap.is_dir() and isinstance(old_info, list):
                for old_spec in old_info:
                    sp = project_root / old_spec.get("path", "")
                    if sp.exists():
                        cur = hashlib.sha256(sp.read_bytes()).hexdigest()[:32]
                        if cur != old_spec.get("hash", ""):
                            changed_artifacts.append(old_spec["path"])

        return {
            "changed": bool(changed_artifacts),
            "changed_artifacts": changed_artifacts,
            "detail": f"变化产物：{changed_artifacts}" if changed_artifacts else "无变化",
        }

    # ── 门禁联动 ──────────────────────────────────────────────────────────────

    def generate_archive_clearance(
        self, change_dir: Path, gate_report: dict[str, Any],
    ) -> dict[str, Any]:
        """生成 OpenSpec archive 可用的质量结论（REQ-12-06）。"""
        gate_result = gate_report.get("result", "")
        waived = gate_report.get("waived", False)
        link = _read_link(change_dir)
        cleared = gate_result == "passed" or waived
        conclusion = "PASS" if gate_result == "passed" else ("WAIVED" if waived else "FAIL")
        return {
            "schema_version": "openguard/archive_clearance/v1",
            "cleared": cleared,
            "conclusion": conclusion,
            "gate": gate_report.get("gate", ""),
            "change_id": gate_report.get("change_id", ""),
            "openspec_change_id": link.get("openspec_change_id", "") if link else "",
            "gate_report_path": str(change_dir / "gate_report.yaml"),
            "generated_at": _now_iso(),
            "note": ("PASS：质量门禁通过，可执行 /opsx:archive。" if cleared
                     else "FAIL：质量门禁未通过，需修复问题或人工豁免后再执行 /opsx:archive。"),
        }

    def generate_fix_suggestions(
        self, gate_report: dict[str, Any], change_dir: Path,
    ) -> list[dict[str, Any]]:
        """门禁失败时生成修复建议（REQ-12-05）。"""
        suggestions: list[dict[str, Any]] = []
        for blocker in gate_report.get("blockers", []):
            category = blocker.get("category", "unknown")
            message = blocker.get("message", "")
            if category == "test_failure":
                suggestions.append({"type": "test_failure_fix", "description": f"测试失败：{message}",
                                     "suggested_action": "检查失败用例的 evidence 文件，定位产品代码问题",
                                     "target": "product_code", "write_to_openspec": False})
            elif category == "blocking_review":
                suggestions.append({"type": "review_fix", "description": f"Review 阻断：{message}",
                                     "suggested_action": "修复 review_findings.sarif.json 中标注的问题",
                                     "target": "product_code", "write_to_openspec": False})
            elif category == "unknown_results":
                suggestions.append({"type": "evidence_supplement", "description": f"存在 UNKNOWN 结果：{message}",
                                     "suggested_action": "补充证据文件或改善日志采集，重新执行 /opg:apply",
                                     "target": "test_scripts_or_logging", "write_to_openspec": False})
            else:
                suggestions.append({"type": "general_fix", "description": message,
                                     "suggested_action": "查看 gate_report.yaml 获取详细信息",
                                     "target": "varies", "write_to_openspec": False})
        return suggestions

    # ── OpenSpec 专有方法（非协议）────────────────────────────────────────────

    def detect_hint_for_init(self, project_root: Path) -> str | None:
        """init 时给出 OpenSpec 联动提示文本。"""
        info = self.detect(project_root)
        if not info.get("installed"):
            return None
        changes = self.list_changes(project_root)
        lines = [f"OpenSpec detected (source: {info['detected_from']})"]
        if changes:
            lines.append(f"  {len(changes)} OpenSpec change(s) found: {changes[:5]}")
        lines.append("  Use `openguard new --from-openspec <change-id>` to link a QA change.")
        lines.append("  After OpenGuard gates pass, OpenSpec can run /opsx:archive (REQ-12-06).")
        return "\n".join(lines)
