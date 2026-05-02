"""SpecProvider 抽象协议及其他插件接口定义。

SpecProvider 是 OpenGuard 与"规格管理工具"之间的协议层。
核心代码只依赖此协议，不直接 import 任何具体实现。

任何工具（OpenSpec、Jira、Notion、Linear、本地 Markdown...）都可以
实现 SpecProvider 并注册到 PluginRegistry，无需修改 OpenGuard 核心逻辑。

SpecProvider 协议方法说明：

  detect(project_root)
    → 检测项目中是否安装了该规格工具。
    → 返回 {installed, root, changes_dir, detected_from}。

  list_changes(project_root)
    → 列出所有规格 change ID。

  write_link(change_dir, spec_change_id, project_root)
    → 创建并写入 spec_link.yaml，记录关联的规格 change 信息。
    → 返回写入的 Path。

  read_link(change_dir)
    → 读取 spec_link.yaml，返回 dict 或 None。

  extract_requirements(spec_change_id, project_root)
    → 从规格 change 提取需求内容，返回 requirements.md 文本。

  validate_consistency(change_dir, spec_change_id, project_root)
    → 对规格内容做有效性校验，返回 {checks, summary}。

  check_changed(change_dir, project_root)
    → 检测规格产物是否在上次同步后发生变化，返回 {changed, ...}。

  generate_archive_clearance(change_dir, gate_report)
    → 门禁通过后输出可归档结论，供规格工具 archive 使用。

  generate_fix_suggestions(gate_report, change_dir)
    → 门禁失败时生成修复建议列表（不修改规格产物）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SpecProvider(Protocol):
    """规格提供者抽象协议。

    实现此协议的类可注册为 OpenGuard 的规格插件。
    所有方法都应安全降级：未安装时返回空结果而不是抛出异常。
    """

    # ── 元信息 ────────────────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        """插件唯一标识，如 'openspec'、'jira'、'notion'。"""
        ...

    @property
    def display_name(self) -> str:
        """人类可读的名称，如 'OpenSpec'、'Jira'。"""
        ...

    # ── 检测 ──────────────────────────────────────────────────────────────────
    def detect(self, project_root: Path) -> dict[str, Any]:
        """检测项目中是否安装了该规格工具。

        返回：{installed: bool, root: str, changes_dir: str, detected_from: []}
        """
        ...

    def list_changes(self, project_root: Path) -> list[str]:
        """列出所有规格 change ID。"""
        ...

    # ── 联动 ──────────────────────────────────────────────────────────────────
    def write_link(
        self,
        change_dir: Path,
        spec_change_id: str,
        project_root: Path,
    ) -> Path:
        """写入 spec_link.yaml，记录关联的规格 change 信息。"""
        ...

    def read_link(self, change_dir: Path) -> dict[str, Any] | None:
        """读取 spec_link.yaml。"""
        ...

    def extract_requirements(
        self,
        spec_change_id: str,
        project_root: Path,
    ) -> str:
        """从规格 change 提取需求内容，返回 requirements.md 文本。"""
        ...

    # ── 有效性校验 ────────────────────────────────────────────────────────────
    def validate_consistency(
        self,
        change_dir: Path,
        spec_change_id: str,
        project_root: Path,
    ) -> dict[str, Any]:
        """对规格内容做有效性校验，返回 {checks, summary}。"""
        ...

    def check_changed(
        self,
        change_dir: Path,
        project_root: Path,
    ) -> dict[str, Any]:
        """检测规格产物是否变化，返回 {changed, changed_artifacts, detail}。"""
        ...

    # ── 门禁联动 ──────────────────────────────────────────────────────────────
    def generate_archive_clearance(
        self,
        change_dir: Path,
        gate_report: dict[str, Any],
    ) -> dict[str, Any]:
        """门禁通过后生成可归档结论。"""
        ...

    def generate_fix_suggestions(
        self,
        gate_report: dict[str, Any],
        change_dir: Path,
    ) -> list[dict[str, Any]]:
        """门禁失败时生成修复建议（不修改规格产物）。"""
        ...
