"""OpenGuard 插件系统。

架构：
  openguard/plugins/
    __init__.py         — 导出 PluginRegistry 和 get_registry()
    base.py             — SpecProvider 抽象协议
    registry.py         — 全局插件注册表
    openspec/
      __init__.py
      plugin.py         — OpenSpec 实现

快速使用：

  from openguard.integrations import get_registry

  # 获取规格提供者（无插件时返回 NullSpecProvider，不崩溃）
  provider = get_registry().get_spec_provider()
  info = provider.detect(project_root)

  # 手动注册 OpenSpec 插件
  from openguard.integrations.openspec.integration import OpenSpecIntegration
  get_registry().register(OpenSpecIntegration())

  # 测试时重置
  from openguard.integrations import reset_registry
  reset_registry()
"""
from openguard.integrations.registry import get_registry, reset_registry, PluginRegistry
from openguard.integrations.base import SpecProvider

__all__ = ["get_registry", "reset_registry", "PluginRegistry", "SpecProvider"]
