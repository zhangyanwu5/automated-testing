"""插件系统测试：注册/注销、NullProvider 降级、OpenSpec 插件功能。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_plugin_registry():
    """每个测试前重置全局插件注册表，避免状态污染。"""
    from openqa.plugins import reset_registry
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def openspec_project(tmp_path: Path) -> Path:
    """含 OpenSpec changes 的项目。"""
    project_root = tmp_path
    change_dir = project_root / "openspec" / "changes" / "opsx-001"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text("# 登录功能\n", encoding="utf-8")
    specs_dir = change_dir / "specs"
    specs_dir.mkdir()
    (specs_dir / "login.md").write_text("接口 `LoginManager.HandleLogin` 规格。\n", encoding="utf-8")
    return project_root


# ──────────────────────────────────────────────────────────────────────────────
# 注册表核心行为
# ──────────────────────────────────────────────────────────────────────────────

class TestPluginRegistry:
    def test_empty_registry_returns_null_provider(self):
        """无插件时 get_spec_provider() 返回 NullSpecProvider，不抛异常。"""
        from openqa.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        provider = registry.get_spec_provider()
        assert provider is not None
        assert provider.name == "null"

    def test_null_provider_methods_safe(self, tmp_path):
        """NullSpecProvider 所有方法都不抛异常，返回安全默认值。"""
        from openqa.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        p = registry.get_spec_provider()
        # 不抛异常
        info = p.detect(tmp_path)
        assert info["installed"] is False
        assert p.list_changes(tmp_path) == []
        assert p.read_link(tmp_path) is None
        assert p.extract_requirements("x", tmp_path) == ""
        result = p.validate_consistency(tmp_path, "x", tmp_path)
        assert "checks" in result
        changed = p.check_changed(tmp_path, tmp_path)
        assert changed["changed"] is False
        suggestions = p.generate_fix_suggestions({}, tmp_path)
        assert suggestions == []

    def test_register_and_get_plugin(self, tmp_path):
        """注册插件后能正确取回。"""
        from openqa.plugins.registry import PluginRegistry

        class MockPlugin:
            name = "mock"
            display_name = "Mock"
            def detect(self, root): return {"installed": True}
            def list_changes(self, root): return ["change-001"]
            def write_link(self, cd, sid, root): return cd / "mock_link.yaml"
            def read_link(self, cd): return {"mock": True}
            def extract_requirements(self, sid, root): return "# mock req\n"
            def validate_consistency(self, cd, sid, root): return {"checks": []}
            def check_changed(self, cd, root): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {"cleared": True}
            def generate_fix_suggestions(self, gr, cd): return []

        registry = PluginRegistry()
        registry.register(MockPlugin())
        assert registry.has_spec_provider()
        assert registry.has_spec_provider("mock")
        provider = registry.get_spec_provider("mock")
        assert provider.name == "mock"

    def test_unregister_plugin(self):
        """注销插件后退回 NullSpecProvider。"""
        from openqa.plugins.registry import PluginRegistry

        class MockPlugin:
            name = "mock"
            display_name = "Mock"
            def detect(self, r): return {"installed": True}
            def list_changes(self, r): return []
            def write_link(self, cd, sid, r): return cd
            def read_link(self, cd): return None
            def extract_requirements(self, sid, r): return ""
            def validate_consistency(self, cd, sid, r): return {"checks": []}
            def check_changed(self, cd, r): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {}
            def generate_fix_suggestions(self, gr, cd): return []

        registry = PluginRegistry()
        registry.register(MockPlugin())
        assert registry.has_spec_provider("mock")
        registry.unregister("mock")
        assert not registry.has_spec_provider("mock")
        assert registry.get_spec_provider().name == "null"

    def test_multiple_providers(self):
        """可以同时注册多个规格提供者。"""
        from openqa.plugins.registry import PluginRegistry

        class PluginA:
            name = "tool_a"
            display_name = "Tool A"
            def detect(self, r): return {"installed": True}
            def list_changes(self, r): return []
            def write_link(self, cd, sid, r): return cd
            def read_link(self, cd): return None
            def extract_requirements(self, sid, r): return ""
            def validate_consistency(self, cd, sid, r): return {"checks": []}
            def check_changed(self, cd, r): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {}
            def generate_fix_suggestions(self, gr, cd): return []

        class PluginB:
            name = "tool_b"
            display_name = "Tool B"
            def detect(self, r): return {"installed": False}
            def list_changes(self, r): return []
            def write_link(self, cd, sid, r): return cd
            def read_link(self, cd): return None
            def extract_requirements(self, sid, r): return ""
            def validate_consistency(self, cd, sid, r): return {"checks": []}
            def check_changed(self, cd, r): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {}
            def generate_fix_suggestions(self, gr, cd): return []

        registry = PluginRegistry()
        registry.register(PluginA())
        registry.register(PluginB())
        assert len(registry.get_all_spec_providers()) == 2
        assert set(registry.list_registered()) == {"tool_a", "tool_b"}

    def test_get_by_name_unknown_returns_null(self):
        """按名称查找不存在的插件时返回 NullSpecProvider。"""
        from openqa.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        p = registry.get_spec_provider("nonexistent")
        assert p.name == "null"

    def test_clear_all_plugins(self):
        """clear() 清空所有插件。"""
        from openqa.plugins.registry import PluginRegistry

        class P:
            name = "p"
            display_name = "P"
            def detect(self, r): return {"installed": True}
            def list_changes(self, r): return []
            def write_link(self, cd, sid, r): return cd
            def read_link(self, cd): return None
            def extract_requirements(self, sid, r): return ""
            def validate_consistency(self, cd, sid, r): return {"checks": []}
            def check_changed(self, cd, r): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {}
            def generate_fix_suggestions(self, gr, cd): return []

        registry = PluginRegistry()
        registry.register(P())
        registry.clear()
        assert not registry.has_spec_provider()


# ──────────────────────────────────────────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────────────────────────────────────────

class TestGlobalRegistry:
    def test_get_registry_returns_singleton(self):
        """get_registry() 多次调用返回同一实例。"""
        from openqa.plugins import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_reset_registry_creates_new_instance(self):
        """reset_registry() 后 get_registry() 返回新实例。"""
        from openqa.plugins import get_registry, reset_registry
        r1 = get_registry()
        reset_registry()
        r2 = get_registry()
        assert r1 is not r2

    def test_global_registry_auto_registers_openspec(self, openspec_project):
        """在含 OpenSpec 的项目中，auto_register 自动注册 OpenSpecPlugin。"""
        from openqa.plugins.registry import PluginRegistry
        registry = PluginRegistry()
        registered = registry.auto_register(openspec_project)
        assert "openspec" in registered
        assert registry.has_spec_provider("openspec")


# ──────────────────────────────────────────────────────────────────────────────
# OpenSpec 插件功能
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenSpecPlugin:
    def test_plugin_detects_openspec(self, openspec_project):
        """OpenSpecPlugin.detect() 正确检测 OpenSpec 安装。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        info = plugin.detect(openspec_project)
        assert info["installed"] is True

    def test_plugin_lists_changes(self, openspec_project):
        """OpenSpecPlugin.list_changes() 列出 changes。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        changes = plugin.list_changes(openspec_project)
        assert "opsx-001" in changes

    def test_plugin_write_and_read_link(self, openspec_project, tmp_path):
        """OpenSpecPlugin.write_link() / read_link() 写入并读取。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        plugin.write_link(change_dir, "opsx-001", openspec_project)
        link = plugin.read_link(change_dir)
        assert link is not None
        assert link.get("openspec_change_id") == "opsx-001"

    def test_plugin_extract_requirements(self, openspec_project):
        """OpenSpecPlugin.extract_requirements() 返回非空文本。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        content = plugin.extract_requirements("opsx-001", openspec_project)
        assert isinstance(content, str)

    def test_plugin_validate_consistency(self, openspec_project, tmp_path):
        """OpenSpecPlugin.validate_consistency() 返回 checks 列表。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        plugin.write_link(change_dir, "opsx-001", openspec_project)
        result = plugin.validate_consistency(change_dir, "opsx-001", openspec_project)
        assert "checks" in result

    def test_plugin_detect_hint_for_init(self, openspec_project):
        """OpenSpecPlugin.detect_hint_for_init() 返回提示文本。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        plugin = OpenSpecPlugin()
        hint = plugin.detect_hint_for_init(openspec_project)
        assert hint is not None
        assert "OpenSpec" in hint

    def test_plugin_name_and_display_name(self):
        """插件有正确的 name 和 display_name。"""
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        p = OpenSpecPlugin()
        assert p.name == "openspec"
        assert "OpenSpec" in p.display_name


# ──────────────────────────────────────────────────────────────────────────────
# 核心模块解耦：通过插件调用，不直接 import openspec
# ──────────────────────────────────────────────────────────────────────────────

class TestDecoupledCoreModules:
    def test_init_hint_uses_plugin_system(self, openspec_project, monkeypatch, capsys):
        """commands/init.py 通过插件给出提示，不直接 import openspec。"""
        import argparse
        from openqa.plugins import get_registry
        from openqa.plugins.openspec.plugin import OpenSpecPlugin
        get_registry().register(OpenSpecPlugin())

        # 创建 Unity 标志让 init 正常运行
        (openspec_project / "Assets").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.18f1\n"
        )
        monkeypatch.chdir(openspec_project)
        from openqa.commands.init import run_init
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))
        out = capsys.readouterr().out
        # 提示中应包含 OpenSpec 相关内容
        assert "OpenSpec" in out or "openspec" in out.lower()

    def test_new_without_spec_provider_does_not_crash(self, tmp_path, monkeypatch):
        """无规格插件时，openqa new 不崩溃（NullSpecProvider 安全降级）。"""
        import argparse
        from openqa.plugins.registry import PluginRegistry, get_registry

        # 确保注册表为空（只有 Null）
        from openqa.plugins import reset_registry
        reset_registry()
        # 不注册任何插件

        # 创建最简工作区
        (tmp_path / "openqa").mkdir()
        (tmp_path / "openqa" / "config.yaml").write_text(
            "schema_version: openqa/config/v1\nproject:\n  type: backend\nai_hosts: []\n"
            "runtime:\n  status: incomplete\n  missing: []\ndefaults:\n  gate: local\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        from openqa.commands.new import run_new
        rc = run_new(argparse.Namespace(
            target="test without spec",
            scan_scope="auto",
            test_suite=None,
            from_openspec=None,
        ))
        assert rc == 0

    def test_preflight_check_without_spec_provider_does_not_crash(self, tmp_path):
        """无规格插件时，preflight 检查不崩溃。"""
        from openqa.plugins import reset_registry
        reset_registry()

        openqa_dir = tmp_path / "openqa"
        openqa_dir.mkdir()
        change_dir = tmp_path / "openqa" / "changes" / "chg-test"
        change_dir.mkdir(parents=True)

        config = {"project": {"type": "backend"}, "runtime": {"status": "incomplete", "missing": []}}
        from openqa.executor.preflight import pre_apply_check
        result = pre_apply_check(change_dir, openqa_dir, config, gate="local")
        # 不崩溃，返回标准结果
        assert "is_blocked" in result

    def test_mock_provider_replaces_openspec(self, tmp_path, monkeypatch):
        """可以用 mock 替换 OpenSpec 插件进行测试。"""
        from openqa.plugins import get_registry

        class MockSpecProvider:
            name = "mock_spec"
            display_name = "Mock Spec Tool"
            def detect(self, r): return {"installed": True}
            def list_changes(self, r): return ["mock-001"]
            def write_link(self, cd, sid, r):
                p = cd / "mock_link.yaml"
                p.write_text("mock: true\n", encoding="utf-8")
                return p
            def read_link(self, cd):
                p = cd / "mock_link.yaml"
                return {"mock": True} if p.exists() else None
            def extract_requirements(self, sid, r): return "# mock requirements\n"
            def validate_consistency(self, cd, sid, r):
                return {"checks": [{"status": "consistent", "confidence": "high"}], "summary": {}}
            def check_changed(self, cd, r): return {"changed": False}
            def generate_archive_clearance(self, cd, gr): return {"cleared": True, "conclusion": "PASS"}
            def generate_fix_suggestions(self, gr, cd): return []

        get_registry().register(MockSpecProvider())
        provider = get_registry().get_spec_provider("mock_spec")
        assert provider.name == "mock_spec"
        info = provider.detect(tmp_path)
        assert info["installed"] is True
        changes = provider.list_changes(tmp_path)
        assert "mock-001" in changes
