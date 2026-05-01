"""OpenQA 插件系统。

架构：
  openqa/plugins/
    __init__.py         — 导出 PluginRegistry 和 get_registry()
    base.py             — SpecProvider 抽象协议
    registry.py         — 全局插件注册表
    openspec/
      __init__.py
      plugin.py         — OpenSpec 实现

快速使用：

  from openqa.plugins import get_registry

  # 获取规格提供者（无插件时返回 NullSpecProvider，不崩溃）
  provider = get_registry().get_spec_provider()
  info = provider.detect(project_root)

  # 手动注册 OpenSpec 插件
  from openqa.plugins.openspec.plugin import OpenSpecPlugin
  get_registry().register(OpenSpecPlugin())

  # 测试时重置
  from openqa.plugins import reset_registry
  reset_registry()
"""
from openqa.plugins.registry import get_registry, reset_registry, PluginRegistry
from openqa.plugins.base import SpecProvider

__all__ = ["get_registry", "reset_registry", "PluginRegistry", "SpecProvider"]
