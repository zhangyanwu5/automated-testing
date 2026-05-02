"""全局插件注册表。

用法：
  # 获取全局单例
  from openguard.integrations.registry import get_registry
  registry = get_registry()

  # 注册插件（在程序入口执行一次）
  from openguard.integrations.openspec.integration import OpenSpecIntegration
  registry.register(OpenSpecIntegration())

  # 获取已注册的规格提供者（可能为 None）
  provider = registry.get_spec_provider()
  if provider:
      info = provider.detect(project_root)

  # 遍历所有规格提供者
  for p in registry.get_all_spec_providers():
      ...

设计原则：
  - 注册表是全局单例，程序启动时按需注册。
  - 核心模块通过 get_registry() 解耦，不直接 import 具体插件。
  - 未注册任何插件时，所有 get_*() 方法返回 None/空列表，核心流程不崩溃。
  - 插件可以随时注册/注销，方便测试（用 mock 替换）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from openguard.integrations.base import SpecProvider

# ── NullSpecProvider：无插件时的安全降级实现 ──────────────────────────────────

class _NullSpecProvider:
    """当没有安装任何规格插件时，作为安全降级实现。

    所有方法返回空/False，不抛异常，不输出任何内容。
    """
    name = "null"
    display_name = "None (no spec provider)"

    def detect(self, project_root: Path) -> dict[str, Any]:
        return {"installed": False, "root": "", "changes_dir": "", "detected_from": []}

    def list_changes(self, project_root: Path) -> list[str]:
        return []

    def write_link(self, change_dir: Path, spec_change_id: str, project_root: Path) -> Path:
        return change_dir / "spec_link.yaml"

    def read_link(self, change_dir: Path) -> dict[str, Any] | None:
        return None

    def extract_requirements(self, spec_change_id: str, project_root: Path) -> str:
        return ""

    def validate_consistency(self, change_dir: Path, spec_change_id: str, project_root: Path) -> dict[str, Any]:
        return {"checks": [], "summary": {}, "note": "无规格提供者"}

    def check_changed(self, change_dir: Path, project_root: Path) -> dict[str, Any]:
        return {"changed": False, "changed_artifacts": [], "detail": "无规格提供者"}

    def generate_archive_clearance(self, change_dir: Path, gate_report: dict[str, Any]) -> dict[str, Any]:
        return {"cleared": False, "conclusion": "NO_PROVIDER", "note": "无规格提供者"}

    def generate_fix_suggestions(self, gate_report: dict[str, Any], change_dir: Path) -> list[dict[str, Any]]:
        return []


# ── PluginRegistry ────────────────────────────────────────────────────────────

class PluginRegistry:
    """全局插件注册表（单例）。"""

    def __init__(self) -> None:
        self._spec_providers: dict[str, Any] = {}
        self._null_provider = _NullSpecProvider()

    # ── 注册/注销 ──────────────────────────────────────────────────────────────

    def register(self, plugin: Any) -> None:
        """注册一个插件。plugin 必须实现 SpecProvider 协议。"""
        if not hasattr(plugin, "name"):
            raise ValueError(f"插件缺少 name 属性：{plugin!r}")
        # 任何实现了 SpecProvider 方法的对象都可以注册
        self._spec_providers[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        """注销插件（测试时用于替换 mock）。"""
        self._spec_providers.pop(name, None)

    def clear(self) -> None:
        """清除所有插件（测试时重置用）。"""
        self._spec_providers.clear()

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_spec_provider(self, name: str | None = None) -> Any:
        """获取规格提供者。

        - name=None：返回第一个已注册的规格提供者；无则返回 NullSpecProvider。
        - name='openspec'：返回指定名称的提供者；未注册则返回 NullSpecProvider。
        """
        if name:
            return self._spec_providers.get(name, self._null_provider)
        if self._spec_providers:
            return next(iter(self._spec_providers.values()))
        return self._null_provider

    def get_all_spec_providers(self) -> list[Any]:
        """返回所有已注册的规格提供者列表。"""
        return list(self._spec_providers.values())

    def has_spec_provider(self, name: str | None = None) -> bool:
        """判断是否有已注册的规格提供者。"""
        if name:
            return name in self._spec_providers
        return bool(self._spec_providers)

    def list_registered(self) -> list[str]:
        """返回所有已注册插件的名称列表。"""
        return list(self._spec_providers.keys())

    # ── 便捷方法：自动探测并注册已安装的插件 ────────────────────────────────

    def auto_register(self, project_root: Path | None = None) -> list[str]:
        """尝试自动检测并注册所有支持的规格插件。

        调用时机：openguard init / openguard new 开始时。
        project_root 为 None 时不做任何注册（需要明确的项目路径才能检测）。
        Returns list of registered plugin names.
        """
        if project_root is None:
            return []

        registered: list[str] = []

        # 尝试注册 OpenSpec 插件
        if "openspec" not in self._spec_providers:
            try:
                from openguard.integrations.openspec.integration import OpenSpecIntegration
                plugin = OpenSpecIntegration()
                if plugin.detect(project_root).get("installed"):
                    self.register(plugin)
                    registered.append("openspec")
            except ImportError:
                pass  # openspec 插件未安装，跳过

        return registered


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_global_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """获取全局插件注册表单例。"""
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
    return _global_registry


def reset_registry() -> None:
    """重置全局注册表（仅用于测试）。"""
    global _global_registry
    _global_registry = None
