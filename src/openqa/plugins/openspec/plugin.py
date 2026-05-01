"""OpenSpec 规格提供者插件（实现 SpecProvider 协议）。

将 openqa/openspec/detector.py 中的所有功能包装为标准插件接口。
核心代码通过 get_registry().get_spec_provider() 调用，不直接 import 本模块。

注册方式（由 auto_register 自动完成，也可手动）：
  from openqa.plugins.openspec.plugin import OpenSpecPlugin
  from openqa.plugins import get_registry
  get_registry().register(OpenSpecPlugin())
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class OpenSpecPlugin:
    """OpenSpec 规格提供者插件。

    代理 openqa.openspec.detector 中的所有功能，
    并添加 link 文件名映射（spec_link.yaml ↔ openspec_link.yaml）。
    """

    name = "openspec"
    display_name = "OpenSpec"

    # ── 检测 ──────────────────────────────────────────────────────────────────

    def detect(self, project_root: Path) -> dict[str, Any]:
        from openqa.openspec.detector import detect_openspec
        return detect_openspec(project_root)

    def list_changes(self, project_root: Path) -> list[str]:
        from openqa.openspec.detector import list_openspec_changes
        return list_openspec_changes(project_root)

    # ── 联动 ──────────────────────────────────────────────────────────────────

    def write_link(
        self,
        change_dir: Path,
        spec_change_id: str,
        project_root: Path,
    ) -> Path:
        """写入 openspec_link.yaml（OpenSpec 专用命名）。"""
        from openqa.openspec.detector import write_openspec_link
        return write_openspec_link(change_dir, spec_change_id, project_root)

    def read_link(self, change_dir: Path) -> dict[str, Any] | None:
        from openqa.openspec.detector import read_openspec_link
        return read_openspec_link(change_dir)

    def extract_requirements(
        self,
        spec_change_id: str,
        project_root: Path,
    ) -> str:
        from openqa.openspec.detector import extract_requirements_from_openspec
        return extract_requirements_from_openspec(spec_change_id, project_root)

    # ── 有效性校验 ────────────────────────────────────────────────────────────

    def validate_consistency(
        self,
        change_dir: Path,
        spec_change_id: str,
        project_root: Path,
    ) -> dict[str, Any]:
        from openqa.openspec.detector import validate_openspec_consistency
        return validate_openspec_consistency(change_dir, spec_change_id, project_root)

    def check_changed(
        self,
        change_dir: Path,
        project_root: Path,
    ) -> dict[str, Any]:
        from openqa.openspec.detector import check_openspec_changed
        return check_openspec_changed(change_dir, project_root)

    # ── 门禁联动 ──────────────────────────────────────────────────────────────

    def generate_archive_clearance(
        self,
        change_dir: Path,
        gate_report: dict[str, Any],
    ) -> dict[str, Any]:
        from openqa.openspec.detector import generate_archive_clearance
        return generate_archive_clearance(change_dir, gate_report)

    def generate_fix_suggestions(
        self,
        gate_report: dict[str, Any],
        change_dir: Path,
    ) -> list[dict[str, Any]]:
        from openqa.openspec.detector import generate_fix_suggestions
        return generate_fix_suggestions(gate_report, change_dir)

    # ── OpenSpec 专有方法（非协议，插件额外能力）──────────────────────────────

    def detect_hint_for_init(self, project_root: Path) -> str | None:
        """init 时给出 OpenSpec 联动提示文本（可选能力）。"""
        info = self.detect(project_root)
        if not info.get("installed"):
            return None
        changes = self.list_changes(project_root)
        lines = [
            f"OpenSpec detected (source: {info['detected_from']})",
        ]
        if changes:
            lines.append(f"  {len(changes)} OpenSpec change(s) found: {changes[:5]}")
        lines.append("  Use `openqa new --from-openspec <change-id>` to link a QA change.")
        lines.append("  After OpenQA gates pass, OpenSpec can run /opsx:archive (REQ-12-06).")
        return "\n".join(lines)
