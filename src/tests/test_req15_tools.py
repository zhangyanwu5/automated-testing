"""工具模块测试（REQ-15）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# registry / ToolResult / call_tool / list_tools
# ──────────────────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_tool_result_ok(self):
        from openguard.tools.registry import ToolResult
        r = ToolResult(ok=True, data="abc")
        assert bool(r) is True
        assert r.data == "abc"
        assert r.error is None

    def test_tool_result_fail(self):
        from openguard.tools.registry import ToolResult
        r = ToolResult(ok=False, error="something failed")
        assert bool(r) is False
        assert r.error == "something failed"

    def test_list_tools_returns_metas(self):
        from openguard.tools import list_tools
        tools = list_tools()
        assert len(tools) > 0
        for m in tools:
            assert m.name
            assert m.description
            assert isinstance(m.is_read_only, bool)

    def test_list_tools_filter_by_tag(self):
        from openguard.tools import list_tools
        fs_tools = list_tools(tags=["fs"])
        assert all("fs" in m.tags for m in fs_tools)
        assert len(fs_tools) > 0

    def test_call_tool_not_found(self):
        from openguard.tools import call_tool
        result = call_tool("nonexistent.tool")
        assert result.ok is False
        assert "not found" in result.error.lower()

    def test_call_tool_success(self, tmp_path):
        from openguard.tools import call_tool
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        result = call_tool("fs.read_text", {"path": str(f)})
        assert result.ok is True
        assert result.data == "hello"
        assert result.elapsed_ms >= 0

    def test_call_tool_never_raises(self):
        """call_tool 对不存在的文件不应抛出异常。"""
        from openguard.tools import call_tool
        result = call_tool("fs.file_hash", {"path": "/nonexistent/path/file.txt"})
        # file_hash 对不存在的文件返回 "error" 字符串，不抛异常
        assert result.ok is True  # 函数本身成功执行
        assert result.data == "error"  # 文件不存在时返回 "error"


# ──────────────────────────────────────────────────────────────────────────────
# fs 工具
# ──────────────────────────────────────────────────────────────────────────────

class TestFsTools:
    def test_read_text_ok(self, tmp_path):
        from openguard.tools.fs.read import read_text
        f = tmp_path / "a.txt"
        f.write_text("hello\nworld", encoding="utf-8")
        assert read_text(f) == "hello\nworld"

    def test_read_text_missing(self, tmp_path):
        from openguard.tools.fs.read import read_text
        assert read_text(tmp_path / "nonexistent.txt") is None

    def test_read_yaml_ok(self, tmp_path):
        from openguard.tools.fs.read import read_yaml
        f = tmp_path / "cfg.yaml"
        f.write_text("key: value\n", encoding="utf-8")
        result = read_yaml(f)
        assert result == {"key": "value"}

    def test_read_json_ok(self, tmp_path):
        from openguard.tools.fs.read import read_json
        f = tmp_path / "data.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        result = read_json(f)
        assert result == {"x": 1}

    def test_file_hash_stable(self, tmp_path):
        from openguard.tools.fs.hash import file_hash
        f = tmp_path / "f.txt"
        f.write_bytes(b"abc")
        h1 = file_hash(f)
        h2 = file_hash(f)
        assert h1 == h2
        assert len(h1) == 32
        assert h1 != "error"

    def test_file_hash_missing(self, tmp_path):
        from openguard.tools.fs.hash import file_hash
        assert file_hash(tmp_path / "no.txt") == "error"

    def test_content_hash(self):
        from openguard.tools.fs.hash import content_hash
        h = content_hash("hello world", length=16)
        assert len(h) == 16
        assert content_hash("hello world") == content_hash("hello world")
        assert content_hash("a") != content_hash("b")

    def test_load_ignore(self, tmp_path):
        from openguard.tools.fs.ignore import load_ignore
        openguard_dir = tmp_path / "openguard"
        openguard_dir.mkdir()
        (openguard_dir / "ignore").write_text("*.pyc\n# comment\n__pycache__/\n", encoding="utf-8")
        patterns = load_ignore(openguard_dir)
        assert "*.pyc" in patterns
        assert "__pycache__/" in patterns
        assert "# comment" not in patterns

    def test_is_ignored_file(self, tmp_path):
        from openguard.tools.fs.ignore import is_ignored
        f = tmp_path / "foo.pyc"
        f.touch()
        assert is_ignored(f, tmp_path, ["*.pyc"]) is True
        assert is_ignored(f, tmp_path, ["*.py"]) is False

    def test_find_files_basic(self, tmp_path):
        from openguard.tools.fs.search import find_files
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        results = find_files(tmp_path, ["*.py"])
        assert "a.py" in results
        assert "b.txt" not in results

    def test_find_files_with_ignore(self, tmp_path):
        from openguard.tools.fs.search import find_files
        (tmp_path / "a.py").write_text("")
        (tmp_path / "ignore_me.py").write_text("")
        results = find_files(tmp_path, ["*.py"], ignore=["ignore_me.py"])
        assert "a.py" in results
        assert "ignore_me.py" not in results

    def test_find_executables_depth_limit(self, tmp_path):
        from openguard.tools.fs.search import find_executables
        deep = tmp_path / "d1" / "d2" / "d3"
        deep.mkdir(parents=True)
        (deep / "Unity.exe").write_bytes(b"")
        # max_depth=2 不应找到深度 3 的文件
        results = find_executables(tmp_path, ["Unity.exe"], max_depth=2)
        assert all("d3" not in r["path"] for r in results)


# ──────────────────────────────────────────────────────────────────────────────
# runtime 工具
# ──────────────────────────────────────────────────────────────────────────────

class TestRuntimeTools:
    def test_check_executable_python(self):
        from openguard.tools.runtime.process import check_executable
        import sys
        # Python 可执行文件本身应该是可执行的
        assert check_executable(sys.executable) is True

    def test_check_executable_missing(self, tmp_path):
        from openguard.tools.runtime.process import check_executable
        assert check_executable(tmp_path / "nonexistent.exe") is False

    def test_run_command_success(self):
        from openguard.tools.runtime.process import run_command
        result = run_command(["python", "--version"], timeout=10)
        assert result.ok is True
        assert result.data["returncode"] == 0
        assert "Python" in (result.data["stdout"] + result.data["stderr"])

    def test_run_command_failure(self):
        from openguard.tools.runtime.process import run_command
        result = run_command(["python", "-c", "exit(1)"], timeout=5)
        assert result.ok is False
        assert result.data["returncode"] == 1

    def test_run_command_never_raises(self):
        from openguard.tools.runtime.process import run_command
        result = run_command(["nonexistent_command_xyz_12345"], timeout=5)
        assert result.ok is False
        assert result.error is not None

    def test_get_env(self, monkeypatch):
        from openguard.tools.runtime.process import get_env
        monkeypatch.setenv("TEST_OPENGUARD_KEY", "test_value_42")
        assert get_env("TEST_OPENGUARD_KEY") == "test_value_42"
        assert get_env("NONEXISTENT_KEY_XYZ", fallback="default") == "default"

    def test_find_unity_editors_returns_list(self, tmp_path):
        """find_unity_editors 在无 editor 时返回空列表，不抛异常。"""
        from openguard.tools.runtime.unity import find_unity_editors
        # 在随机 tmp 目录下，没有任何 Unity editor，应返回空列表
        results = find_unity_editors(str(tmp_path))
        assert isinstance(results, list)

    def test_find_unity_editors_detects_sibling(self, tmp_path):
        """find_unity_editors 能找到同级目录下的 editor。"""
        from openguard.tools.runtime.unity import find_unity_editors
        # 创建仿真项目结构
        project = tmp_path / "MyGame"
        project.mkdir()
        editor_dir = tmp_path / "UnityEditorWin" / "WindowsEditor"
        editor_dir.mkdir(parents=True)
        (editor_dir / "Unity.exe").write_bytes(b"")

        # 需要清除 lru_cache
        find_unity_editors.cache_clear()
        results = find_unity_editors(str(project))
        assert any("Unity.exe" in r["path"] for r in results)
        assert any(r["source"] == "compiled" for r in results)
        find_unity_editors.cache_clear()

    def test_find_unity_editors_caches(self, tmp_path):
        """相同参数的第二次调用应命中缓存（elapsed_ms ≈ 0 或极小）。"""
        from openguard.tools import call_tool
        from openguard.tools.runtime.unity import find_unity_editors
        find_unity_editors.cache_clear()

        r1 = call_tool("runtime.find_unity_editors", {"project_root": str(tmp_path)})
        r2 = call_tool("runtime.find_unity_editors", {"project_root": str(tmp_path)})
        # 第二次比第一次快（缓存命中）
        assert r2.elapsed_ms <= r1.elapsed_ms + 5  # 宽松 5ms 容忍
        find_unity_editors.cache_clear()


# ──────────────────────────────────────────────────────────────────────────────
# analysis 工具
# ──────────────────────────────────────────────────────────────────────────────

class TestAnalysisTools:
    def test_detect_language_known(self, tmp_path):
        from openguard.tools.analysis.symbols import detect_language
        assert detect_language("foo.py") == "python"
        assert detect_language("bar.cs") == "csharp"
        assert detect_language("baz.ts") == "typescript"
        assert detect_language("x.proto") == "protobuf"

    def test_detect_language_unknown(self):
        from openguard.tools.analysis.symbols import detect_language
        assert detect_language("file.xyz") == "unknown"

    def test_extract_symbols_python(self, tmp_path):
        from openguard.tools.analysis.symbols import extract_symbols
        f = tmp_path / "mod.py"
        f.write_text("class Foo:\n    pass\ndef bar(): pass\nasync def baz(): pass\n", encoding="utf-8")
        syms = extract_symbols(str(f), "python")
        assert "Foo" in syms
        assert "bar" in syms
        assert "baz" in syms

    def test_extract_symbols_missing_file(self):
        from openguard.tools.analysis.symbols import extract_symbols
        # 不存在的文件返回空列表
        result = extract_symbols("/nonexistent/file.py", "python")
        assert result == []

    def test_extract_symbols_max_limit(self, tmp_path):
        from openguard.tools.analysis.symbols import extract_symbols
        lines = "\n".join(f"def fn_{i}(): pass" for i in range(100))
        f = tmp_path / "many.py"
        f.write_text(lines, encoding="utf-8")
        syms = extract_symbols(str(f), "python", max_symbols=10)
        assert len(syms) <= 10
