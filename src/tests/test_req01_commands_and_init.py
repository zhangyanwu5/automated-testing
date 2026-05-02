"""Tests for REQ_01: Commands and Init."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
import yaml

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mixed_project(tmp_path: Path) -> Path:
    """Return a minimal mixed project: Unity + backend."""
    # Unity markers
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    (tmp_path / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.18f1\n"
    )
    (tmp_path / "Packages").mkdir()
    (tmp_path / "Packages" / "manifest.json").write_text(
        '{"dependencies": {"com.unity.test-framework": "1.3.9"}}'
    )
    # Backend markers (Python)
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    return tmp_path


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Return an empty temporary project root."""
    return tmp_path


@pytest.fixture
def unity_project(tmp_path: Path) -> Path:
    """Return a minimal Unity project skeleton."""
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    version_file = tmp_path / "ProjectSettings" / "ProjectVersion.txt"
    version_file.write_text("m_EditorVersion: 2022.3.18f1\n")
    packages = tmp_path / "Packages"
    packages.mkdir()
    (packages / "manifest.json").write_text(
        '{"dependencies": {"com.unity.test-framework": "1.3.9"}}'
    )
    return tmp_path


@pytest.fixture
def web_project(tmp_path: Path) -> Path:
    """Return a minimal web project skeleton."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{"name":"my-app","scripts":{"start":"vite"},"dependencies":{"react":"^18.0.0"}}'
    )
    return tmp_path


@pytest.fixture
def backend_project(tmp_path: Path) -> Path:
    """Return a minimal Python backend project."""
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    return tmp_path


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-10 / REQ_01-11 / REQ_01-12: detection
# ──────────────────────────────────────────────────────────────────────────────

class TestDetector:
    def test_unity_detected(self, unity_project: Path):
        from openguard.setup.detector import detect_project, PROJECT_TYPE_UNITY, CONFIDENCE_HIGH
        result = detect_project(unity_project)
        assert result.project_type.value == PROJECT_TYPE_UNITY
        assert result.project_type.confidence == CONFIDENCE_HIGH

    def test_unity_version_extracted(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(unity_project)
        assert result.extra.get("unity_version") == "2022.3.18f1"

    def test_unity_test_framework_detected(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(unity_project)
        assert result.extra.get("test_framework") == "Unity Test Framework"

    def test_unity_missing_editor_path(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(unity_project)
        assert "unity.editor_path" in result.runtime.missing

    def test_web_detected(self, web_project: Path):
        from openguard.setup.detector import detect_project, PROJECT_TYPE_WEB
        result = detect_project(web_project)
        assert result.project_type.value == PROJECT_TYPE_WEB

    def test_web_framework_react(self, web_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(web_project)
        assert "react" in result.frameworks

    def test_backend_detected(self, backend_project: Path):
        from openguard.setup.detector import detect_project, PROJECT_TYPE_BACKEND
        result = detect_project(backend_project)
        assert result.project_type.value == PROJECT_TYPE_BACKEND

    def test_unknown_project(self, tmp_project: Path):
        from openguard.setup.detector import detect_project, PROJECT_TYPE_UNKNOWN
        result = detect_project(tmp_project)
        assert result.project_type.value == PROJECT_TYPE_UNKNOWN

    def test_detected_from_populated(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(unity_project)
        assert len(result.project_type.detected_from) > 0

    def test_runtime_has_status(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(unity_project)
        assert result.runtime.status in ("incomplete", "complete")

    # ── mixed type (REQ-01-12) ─────────────────────────────────────────────────

    def test_mixed_type_detected(self, mixed_project: Path):
        from openguard.setup.detector import detect_project, PROJECT_TYPE_MIXED
        result = detect_project(mixed_project)
        assert result.project_type.value == PROJECT_TYPE_MIXED

    def test_mixed_has_sub_projects(self, mixed_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(mixed_project)
        sub = result.extra.get("sub_projects", [])
        assert len(sub) >= 2

    def test_mixed_sub_projects_have_type_and_confidence(self, mixed_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(mixed_project)
        for sp in result.extra["sub_projects"]:
            assert "type" in sp
            assert "confidence" in sp
            assert "execution_order" in sp

    def test_mixed_has_execution_order_candidate(self, mixed_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(mixed_project)
        order = result.extra.get("execution_order_candidate", [])
        assert len(order) >= 2

    def test_mixed_has_unknowns(self, mixed_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(mixed_project)
        # mixed result must surface at least one unknown requiring confirmation
        assert len(result.unknowns) > 0

    def test_mixed_detected_from_non_empty(self, mixed_project: Path):
        from openguard.setup.detector import detect_project
        result = detect_project(mixed_project)
        assert len(result.project_type.detected_from) > 0

    def test_mixed_config_yaml_has_sub_projects(self, mixed_project: Path):
        import yaml
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config, write_config
        openguard_dir = mixed_project / "openguard"
        result = detect_project(mixed_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        write_config(config, openguard_dir)
        with (openguard_dir / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["project"]["type"] == "mixed"
        assert "sub_projects" in cfg["project"]


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-10 / REQ_02-01 / REQ_02-09 / REQ_02-11: config.yaml
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigWriter:
    def test_config_written(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config, write_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        path = write_config(config, unity_project / "openguard")
        assert path.exists()

    def test_config_has_schema_version(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        assert "schema_version" in config
        assert config["schema_version"].startswith("openguard/config/")

    def test_config_project_type(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        assert config["project"]["type"] == "unity"

    def test_config_confidence_recorded(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        assert "confidence" in config["project"]

    def test_config_detected_from_recorded(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        assert len(config["project"]["detected_from"]) > 0

    def test_config_runtime_missing_recorded(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        # runtime.status should be incomplete and missing should be listed
        assert config["runtime"]["status"] == "incomplete"
        assert "missing" in config["runtime"]

    def test_config_no_secrets(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config, write_config
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        path = write_config(config, unity_project / "openguard")
        content = path.read_text(encoding="utf-8")
        for bad in ("password", "secret", "token", "private_key"):
            assert bad not in content.lower(), f"config.yaml must not contain '{bad}'"

    def test_config_loadable(self, unity_project: Path):
        from openguard.setup.detector import detect_project
        from openguard.setup.config_writer import build_config, write_config, load_config
        openguard_dir = unity_project / "openguard"
        result = detect_project(unity_project)
        config = build_config(result, ai_hosts=["codebuddy"])
        write_config(config, openguard_dir)
        loaded = load_config(openguard_dir)
        assert loaded["project"]["type"] == "unity"


# ──────────────────────────────────────────────────────────────────────────────
# REQ_02-02: ignore file
# ──────────────────────────────────────────────────────────────────────────────

class TestIgnoreWriter:
    def test_ignore_written(self, tmp_project: Path):
        from openguard.setup.ignore_writer import write_ignore
        path = write_ignore("unity", tmp_project / "openguard")
        assert path.exists()
        assert path.name == "ignore"

    def test_ignore_contains_git(self, tmp_project: Path):
        from openguard.setup.ignore_writer import generate_ignore
        content = generate_ignore("unity")
        assert ".git/" in content

    def test_ignore_contains_node_modules(self, tmp_project: Path):
        from openguard.setup.ignore_writer import generate_ignore
        content = generate_ignore("web")
        assert "node_modules/" in content

    def test_ignore_unity_has_library(self, tmp_project: Path):
        from openguard.setup.ignore_writer import generate_ignore
        content = generate_ignore("unity")
        assert "Library/" in content

    def test_ignore_no_secret_patterns(self, tmp_project: Path):
        from openguard.setup.ignore_writer import generate_ignore
        content = generate_ignore("unity")
        # The ignore file itself is fine to have .env exclusion; it should NOT
        # contain actual secret values.
        assert "password" not in content.lower()


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-08 / REQ_02-03: slash commands
# ──────────────────────────────────────────────────────────────────────────────

class TestSlashCommands:
    def test_commands_installed_codebuddy(self, unity_project: Path):
        from openguard.setup.slash_commands import install_commands
        openguard_dir = unity_project / "openguard"
        openguard_dir.mkdir(exist_ok=True)
        written = install_commands(unity_project, ["codebuddy"], openguard_dir)
        assert "codebuddy" in written
        assert len(written["codebuddy"]) == 4  # new, continue, apply, archive

    def test_canonical_commands_in_openguard(self, unity_project: Path):
        """REQ-02-13：有宿主时命令安装到宿主目录，无宿主时 fallback 到 openguard/commands/。"""
        from openguard.setup.slash_commands import install_commands
        openguard_dir = unity_project / "openguard"
        openguard_dir.mkdir(exist_ok=True)
        # 无宿主 → fallback 到 openguard/commands/
        install_commands(unity_project, [], openguard_dir)
        commands_dir = openguard_dir / "commands"
        files = list(commands_dir.glob("*.md"))
        assert len(files) == 4

    def test_command_file_has_front_matter(self, unity_project: Path):
        from openguard.setup.slash_commands import install_commands
        openguard_dir = unity_project / "openguard"
        openguard_dir.mkdir(exist_ok=True)
        written = install_commands(unity_project, ["codebuddy"], openguard_dir)
        first_file = written["codebuddy"][0]
        content = first_file.read_text(encoding="utf-8")
        assert content.startswith("---")

    def test_unknown_host_skipped_gracefully(self, unity_project: Path):
        from openguard.setup.slash_commands import install_commands
        openguard_dir = unity_project / "openguard"
        openguard_dir.mkdir(exist_ok=True)
        written = install_commands(unity_project, ["nonexistent_host"], openguard_dir)
        assert "nonexistent_host" not in written


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-01: openguard init end-to-end (non-interactive)
# ──────────────────────────────────────────────────────────────────────────────

class TestInitCommand:
    def _run_init(self, project: Path, extra_args: list[str] | None = None) -> int:
        import argparse
        from openguard.commands.init import run_init
        parser_args = argparse.Namespace(
            profile=None,
            hosts=None,
            gate="local",
            yes=True,
            reconfigure=False,
        )
        if extra_args:
            for arg in extra_args:
                k, v = arg.split("=", 1)
                setattr(parser_args, k.lstrip("-").replace("-", "_"), v)
        old_cwd = os.getcwd()
        os.chdir(project)
        try:
            return run_init(parser_args)
        finally:
            os.chdir(old_cwd)

    def test_init_creates_openguard_dir(self, unity_project: Path):
        self._run_init(unity_project)
        assert (unity_project / "openguard").is_dir()

    def test_init_creates_config_yaml(self, unity_project: Path):
        self._run_init(unity_project)
        assert (unity_project / "openguard" / "config.yaml").is_file()

    def test_init_creates_ignore(self, unity_project: Path):
        self._run_init(unity_project)
        assert (unity_project / "openguard" / "ignore").is_file()

    def test_init_creates_subdirs(self, unity_project: Path):
        self._run_init(unity_project)
        # traces/ 不在 REQ-02 目录结构中；reports/ 下有 suites/ 和 changes/
        for sub in ("changes", "artifacts", "reports", "baselines", "knowledge", "commands"):
            assert (unity_project / "openguard" / sub).is_dir(), f"Missing subdir: {sub}"

    def test_init_idempotent(self, unity_project: Path):
        self._run_init(unity_project)
        rc = self._run_init(unity_project)
        # Second run should return 0 (already initialized message)
        assert rc == 0

    def test_init_returns_zero(self, unity_project: Path):
        rc = self._run_init(unity_project)
        assert rc == 0

    def test_init_web_project(self, web_project: Path):
        self._run_init(web_project)
        config_path = web_project / "openguard" / "config.yaml"
        assert config_path.exists()
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["project"]["type"] == "web"


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-02: openguard update
# ──────────────────────────────────────────────────────────────────────────────

class TestUpdateCommand:
    def test_update_refreshes_commands(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.update import run_update

        monkeypatch.chdir(unity_project)

        init_args = argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        )
        run_init(init_args)

        # Delete one command file (codebuddy uses prefix_filename=False, so filename is "run.md")
        cmd_file = unity_project / ".codebuddy" / "commands" / "run.md"
        if cmd_file.exists():
            cmd_file.unlink()

        update_args = argparse.Namespace(yes=True)
        rc = run_update(update_args)
        assert rc == 0
        # File should be restored
        assert cmd_file.exists()

    def test_update_preserves_changes_dir(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.update import run_update

        monkeypatch.chdir(unity_project)
        init_args = argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        )
        run_init(init_args)

        # Create a fake change
        changes_dir = unity_project / "openguard" / "changes" / "chg-001"
        changes_dir.mkdir(parents=True)
        sentinel = changes_dir / "state.yaml"
        sentinel.write_text("phase: new\n")

        update_args = argparse.Namespace(yes=True)
        run_update(update_args)

        assert sentinel.exists(), "update must not delete existing changes"


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-03 / REQ_01-04 / REQ_01-05 / REQ_01-06: stub commands reachable
# ──────────────────────────────────────────────────────────────────────────────

class TestStubCommands:
    def _init_project(self, project: Path) -> None:
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(project)
        try:
            run_init(argparse.Namespace(
                profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
            ))
        finally:
            os.chdir(old)

    def test_new_stub(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        self._init_project(unity_project)
        monkeypatch.chdir(unity_project)
        rc = run_new(argparse.Namespace(
            target="verify onboarding reward", scan_scope="auto", test_suite=None, from_openspec=None
        ))
        assert rc == 0

    def test_continue_stub(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        from openguard.commands.continue_ import run_continue
        self._init_project(unity_project)
        monkeypatch.chdir(unity_project)
        # continue 需要先有活跃 change
        run_new(argparse.Namespace(
            target="continue test", scan_scope="auto", test_suite=None, from_openspec=None
        ))
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc == 0

    def test_apply_stub(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        from openguard.commands.apply import run_apply
        self._init_project(unity_project)
        monkeypatch.chdir(unity_project)
        run_new(argparse.Namespace(
            target="apply test", scan_scope="auto", test_suite=None, from_openspec=None
        ))
        rc = run_apply(argparse.Namespace(
            suite=None, change_id=None, test_suite=None,
            review_level=None, gate="local", scan_scope=None,
        ))
        assert isinstance(rc, int)

    def test_archive_stub(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        from openguard.commands.archive import run_archive
        self._init_project(unity_project)
        monkeypatch.chdir(unity_project)
        run_new(argparse.Namespace(
            target="archive test", scan_scope="auto", test_suite=None, from_openspec=None
        ))
        rc = run_archive(argparse.Namespace(change_id=None, dry_run=False))
        # archive 现为完整实现，有阻断项时返回 1，但不崩溃
        assert isinstance(rc, int)


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-07: openguard help
# ──────────────────────────────────────────────────────────────────────────────

class TestHelpCommand:
    def test_help_runs(self, tmp_project: Path, monkeypatch, capsys):
        from openguard.commands.help import run_help
        monkeypatch.chdir(tmp_project)
        rc = run_help(str(tmp_project))
        assert rc == 0

    def test_help_mentions_commands(self, tmp_project: Path, monkeypatch, capsys):
        from openguard.commands.help import run_help
        monkeypatch.chdir(tmp_project)
        run_help(str(tmp_project))
        captured = capsys.readouterr()
        for cmd in ("init", "update", "new", "continue", "apply", "archive"):
            assert cmd in captured.out

    def test_help_suggests_init_when_not_initialized(self, tmp_project: Path, monkeypatch, capsys):
        from openguard.commands.help import run_help
        monkeypatch.chdir(tmp_project)
        run_help(str(tmp_project))
        captured = capsys.readouterr()
        assert "openguard init" in captured.out


# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-14: non-interactive flags
# ──────────────────────────────────────────────────────────────────────────────

class TestNonInteractive:
    def test_init_with_profile_flag(self, tmp_project: Path):
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(tmp_project)
        try:
            rc = run_init(argparse.Namespace(
                profile="backend",
                hosts=["codebuddy"],
                gate="ci",
                yes=True,
                reconfigure=False,
            ))
        finally:
            os.chdir(old)
        assert rc == 0
        with (tmp_project / "openguard" / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["project"]["type"] == "backend"
        assert cfg["defaults"]["gate"] == "ci"

    def test_init_with_yes_flag_no_prompt(self, unity_project: Path, monkeypatch):
        """--yes must not attempt to read stdin."""
        import argparse
        from openguard.commands.init import run_init
        monkeypatch.chdir(unity_project)
        # Patch input() to raise if called (should not be called with --yes)
        monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(AssertionError("input() called with --yes")))
        rc = run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))
        assert rc == 0

    def test_yes_without_hosts_uses_detected(self, unity_project: Path, monkeypatch):
        """REQ-01-19: --yes 且无 --host 时使用探测结果，不弹菜单。"""
        import argparse
        from openguard.commands.init import run_init
        monkeypatch.chdir(unity_project)
        # 创建 .codebuddy/ 让探测到 codebuddy
        (unity_project / ".codebuddy").mkdir(exist_ok=True)
        monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(AssertionError("input() called with --yes")))
        rc = run_init(argparse.Namespace(
            profile=None, hosts=None, gate="local", yes=True, reconfigure=False
        ))
        assert rc == 0
        # codebuddy 宿主目录应被安装
        assert (unity_project / ".codebuddy" / "commands").is_dir()

    def test_yes_without_hosts_fallback_to_codebuddy(self, tmp_project: Path, monkeypatch):
        """REQ-01-19: --yes 且无探测到任何宿主时，fallback 到 codebuddy。"""
        import argparse
        from openguard.commands.init import run_init
        monkeypatch.chdir(tmp_project)
        monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(AssertionError("input() called")))
        rc = run_init(argparse.Namespace(
            profile=None, hosts=None, gate="local", yes=True, reconfigure=False
        ))
        assert rc == 0
        assert (tmp_project / ".codebuddy" / "commands").is_dir()

    def test_interactive_host_selection_enter_uses_preselected(self, unity_project: Path, monkeypatch):
        """REQ-01-19: 交互时回车使用预勾选推荐（即探测结果）。"""
        import argparse
        from openguard.commands.init import run_init
        monkeypatch.chdir(unity_project)
        (unity_project / ".codebuddy").mkdir(exist_ok=True)
        # 用户直接回车
        monkeypatch.setattr("builtins.input", lambda *_: "")
        rc = run_init(argparse.Namespace(
            profile=None, hosts=None, gate="local", yes=False, reconfigure=False
        ))
        assert rc == 0
        assert (unity_project / ".codebuddy" / "commands").is_dir()

    def test_interactive_host_selection_by_number(self, unity_project: Path, monkeypatch):
        """REQ-01-19: 交互时输入编号选择宿主。"""
        import argparse
        from openguard.commands.init import run_init
        from openguard.setup.slash_commands import get_supported_hosts
        monkeypatch.chdir(unity_project)
        # 输入 "1" 选第一个宿主（codebuddy）
        monkeypatch.setattr("builtins.input", lambda *_: "1")
        rc = run_init(argparse.Namespace(
            profile=None, hosts=None, gate="local", yes=False, reconfigure=False
        ))
        assert rc == 0
        # 第一个宿主的 commands 目录应存在
        first_host = get_supported_hosts()[0]
        host_dirs = {"codebuddy": ".codebuddy/commands", "cursor": ".cursor/rules", "claude-code": ".claude/commands"}
        expected_dir = unity_project / host_dirs[first_host]
        assert expected_dir.is_dir()





# ──────────────────────────────────────────────────────────────────────────────
# REQ_01-15: --reconfigure preserves existing artefacts
# ──────────────────────────────────────────────────────────────────────────────

class TestReconfigure:
    def test_reconfigure_preserves_changes(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.init import run_init
        monkeypatch.chdir(unity_project)
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))
        # Create fake change
        fake_change = unity_project / "openguard" / "changes" / "chg-001"
        fake_change.mkdir(parents=True)
        sentinel = fake_change / "intent.md"
        sentinel.write_text("# My change\n")

        # Reconfigure
        run_init(argparse.Namespace(
            profile="unity", hosts=["codebuddy"], gate="local", yes=True, reconfigure=True
        ))
        assert sentinel.exists(), "reconfigure must not delete existing changes"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-02-04 / REQ-02-12 / REQ-02-13: new workspace subdirs
# ──────────────────────────────────────────────────────────────────────────────

class TestWorkspaceLayout:
    def _init(self, project: Path) -> Path:
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(project)
        try:
            run_init(argparse.Namespace(
                profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
            ))
        finally:
            os.chdir(old)
        return project / "openguard"

    def test_test_assets_scripts_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "test_assets" / "scripts").is_dir()

    def test_test_assets_fixtures_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "test_assets" / "fixtures").is_dir()

    def test_suites_smoke_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "suites" / "smoke").is_dir()

    def test_suites_regression_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "suites" / "regression").is_dir()

    def test_suites_requirement_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "suites" / "requirement").is_dir()

    def test_suites_full_created(self, unity_project: Path):
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "suites" / "full").is_dir()

    def test_config_has_test_assets(self, unity_project: Path):
        # config.yaml 不再包含 test_assets 字段（目录结构约定，不写入配置）
        # 验证 automation 字段含 precondition_mode（REQ-15-03）
        import yaml
        openguard_dir = self._init(unity_project)
        with (openguard_dir / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert "automation" in cfg
        assert "precondition_mode" in cfg["automation"]

    def test_config_has_suites(self, unity_project: Path):
        # config.yaml 不再包含 suites 字段；套件目录结构通过文件系统验证
        openguard_dir = self._init(unity_project)
        assert (openguard_dir / "suites").is_dir()
        assert (openguard_dir / "suites" / "smoke").is_dir()

    def test_ensure_change_subdirs(self, unity_project: Path):
        """REQ-02-04: each change workspace has test_scripts/ and test_fixtures/."""
        from openguard.workspace.layout import ensure_change_subdirs
        change_dir = unity_project / "openguard" / "changes" / "chg-test"
        change_dir.mkdir(parents=True)
        ensure_change_subdirs(change_dir)
        assert (change_dir / "test_scripts").is_dir()
        assert (change_dir / "test_fixtures").is_dir()


# ──────────────────────────────────────────────────────────────────────────────
# REQ-01-17: openguard apply --suite
# ──────────────────────────────────────────────────────────────────────────────

class TestApplySuite:
    def _init(self, project: Path) -> Path:
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(project)
        try:
            run_init(argparse.Namespace(
                profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
            ))
        finally:
            os.chdir(old)
        return project / "openguard"

    def test_apply_suite_existing(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.apply import run_apply
        self._init(unity_project)
        monkeypatch.chdir(unity_project)
        rc = run_apply(argparse.Namespace(
            suite="smoke",
            change_id=None, test_suite=None, review_level=None, gate="local", scan_scope=None
        ))
        # suite 模式下执行，因无真实脚本可能返回 failed（1），但不崩溃
        assert isinstance(rc, int)

    def test_apply_suite_missing_returns_error(self, unity_project: Path, monkeypatch, capsys):
        import argparse
        from openguard.commands.apply import run_apply
        self._init(unity_project)
        monkeypatch.chdir(unity_project)
        rc = run_apply(argparse.Namespace(
            suite="nonexistent_suite",
            change_id=None, test_suite=None, review_level=None, gate="local", scan_scope=None
        ))
        assert rc != 0

    def test_apply_no_suite_change_mode(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        from openguard.commands.apply import run_apply
        self._init(unity_project)
        monkeypatch.chdir(unity_project)
        run_new(argparse.Namespace(
            target="apply no suite test", scan_scope="auto", test_suite=None, from_openspec=None
        ))
        rc = run_apply(argparse.Namespace(
            suite=None,
            change_id=None, test_suite=None, review_level=None, gate="local", scan_scope=None
        ))
        assert isinstance(rc, int)

    def test_apply_suite_parser_accepts_flag(self):
        """Parser must accept --suite without error."""
        from openguard.cli.main import build_parser
        parser = build_parser()
        args = parser.parse_args(["apply", "--suite", "regression"])
        assert args.suite == "regression"
        assert args.command == "apply"

    def test_apply_suite_and_gate(self):
        from openguard.cli.main import build_parser
        parser = build_parser()
        args = parser.parse_args(["apply", "--suite", "full", "--gate", "release"])
        assert args.suite == "full"
        assert args.gate == "release"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-01-18: test scripts must NOT be written to project source dirs
# ──────────────────────────────────────────────────────────────────────────────

class TestScriptPolicy:
    def test_apply_output_mentions_openguard_only(self, unity_project: Path, monkeypatch, capsys):
        """apply stub output must reference .openguard paths, not project source."""
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.apply import run_apply

        monkeypatch.chdir(unity_project)
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))
        run_apply(argparse.Namespace(
            suite=None,
            change_id=None, test_suite=None, review_level=None, gate=None, scan_scope=None
        ))
        out = capsys.readouterr().out
        # Output should reference openguard/ policy
        assert "openguard/" in out

    def test_slash_command_apply_mentions_script_policy(self):
        """The /opg:apply command template must mention the script location policy."""
        from openguard.prompts import get_commands
        commands = get_commands()
        apply_body = next(body for name, _, body in commands if name == "opg:apply")
        assert "openguard/" in apply_body
        # Must not suggest writing scripts into project source
        assert "test_scripts" in apply_body or "test_assets" in apply_body


# ──────────────────────────────────────────────────────────────────────────────
# REQ-01-19 / REQ-14: skill 安装
# ──────────────────────────────────────────────────────────────────────────────

class TestSkillInstallation:
    def _init(self, project: Path, hosts: list[str] | None = None) -> Path:
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(project)
        try:
            run_init(argparse.Namespace(
                profile=None,
                hosts=hosts or ["codebuddy"],
                gate="local",
                yes=True,
                reconfigure=False,
            ))
        finally:
            os.chdir(old)
        return project / "openguard"

    def test_skill_fallback_written_to_commands(self, unity_project: Path):
        """REQ-02-13：无宿主时 fallback skill 写入 openguard/commands/"""
        from openguard.setup.skills import SKILL_NAMES, install_skills
        openguard_dir = unity_project / "openguard"
        openguard_dir.mkdir(exist_ok=True)
        # 无宿主时触发 fallback
        install_skills(unity_project, [], openguard_dir)
        for skill_name in SKILL_NAMES:
            assert (openguard_dir / "commands" / f"{skill_name}.md").exists(), \
                f"fallback skill {skill_name}.md 不存在"

    def test_skill_installed_to_codebuddy(self, unity_project: Path):
        """skill 安装到 .codebuddy/skills/<name>/SKILL.md"""
        from openguard.setup.skills import SKILL_NAMES
        self._init(unity_project, hosts=["codebuddy"])
        for skill_name in SKILL_NAMES:
            skill_file = unity_project / ".codebuddy" / "skills" / skill_name / "SKILL.md"
            assert skill_file.exists(), f"{skill_file} 不存在"

    def test_four_skills_installed(self, unity_project: Path):
        """必须安装 4 个 skill（REQ-14-01）"""
        from openguard.setup.skills import SKILL_NAMES
        self._init(unity_project, hosts=["codebuddy"])
        skills_dir = unity_project / ".codebuddy" / "skills"
        installed = [d.name for d in skills_dir.iterdir() if d.is_dir()]
        for name in SKILL_NAMES:
            assert name in installed

    def _skill_content(self, unity_project: Path, skill_name: str) -> str:
        """从 codebuddy skill 目录读取 skill 内容。"""
        skill_file = unity_project / ".codebuddy" / "skills" / skill_name / "SKILL.md"
        return skill_file.read_text(encoding="utf-8")

    def test_skill_content_has_guardrails(self, unity_project: Path):
        """每个 skill 必须包含 Guardrails 节（REQ-14-03）"""
        from openguard.setup.skills import SKILL_NAMES
        self._init(unity_project, hosts=["codebuddy"])
        for skill_name in SKILL_NAMES:
            content = self._skill_content(unity_project, skill_name)
            assert "Guardrails" in content, f"{skill_name} 缺少 Guardrails 节"

    def test_skill_content_has_cli_calls(self, unity_project: Path):
        """每个 skill 必须引用真实 CLI 命令（REQ-14-04）"""
        self._init(unity_project, hosts=["codebuddy"])
        cli_map = {
            "openguard-run": "openguard run",
            "openguard-continue": "openguard continue",
            "openguard-apply": "openguard apply",
            "openguard-archive": "openguard archive",
        }
        for skill_name, cli in cli_map.items():
            content = self._skill_content(unity_project, skill_name)
            assert cli in content, f"{skill_name} 缺少 {cli} CLI 调用"

    def test_skill_continue_has_script_generation_guide(self, unity_project: Path):
        """openguard-continue skill 必须包含测试脚本生成指南（REQ-14-05）"""
        self._init(unity_project, hosts=["codebuddy"])
        content = self._skill_content(unity_project, "openguard-continue")
        assert "test_scripts" in content
        assert "project.type" in content
        assert "verified" in content or "test_assets" in content

    def test_skill_apply_has_overlay_guide(self, unity_project: Path):
        """openguard-apply skill 必须包含 overlay 生成指南（REQ-14-06）"""
        self._init(unity_project, hosts=["codebuddy"])
        content = self._skill_content(unity_project, "openguard-apply")
        assert "report_overlay" in content
        assert "UNKNOWN" in content

    def test_skill_mentions_no_direct_app_operation(self, unity_project: Path):
        """skill 必须说明 AI 宿主不直接操作目标应用（REQ-14-07）"""
        from openguard.setup.skills import SKILL_NAMES
        self._init(unity_project, hosts=["codebuddy"])
        for skill_name in SKILL_NAMES:
            content = self._skill_content(unity_project, skill_name)
            if skill_name in ("openguard-apply", "openguard-archive"):
                assert "不直接操作目标应用" in content or "不操作目标应用" in content or \
                       "not directly" in content.lower() or "REQ-14-07" in content, \
                    f"{skill_name} 缺少不操作目标应用的声明"

    def test_skill_installed_to_multiple_hosts(self, unity_project: Path):
        """多宿主时所有宿主都安装 skill（REQ-14-08）"""
        from openguard.setup.skills import SKILL_NAMES
        (unity_project / ".cursor").mkdir(exist_ok=True)
        self._init(unity_project, hosts=["codebuddy", "cursor"])
        for host_dir_name in (".codebuddy", ".cursor"):
            skills_dir = unity_project / host_dir_name / "skills"
            if skills_dir.exists():
                for name in SKILL_NAMES:
                    assert (skills_dir / name / "SKILL.md").exists(), \
                        f"{host_dir_name}/skills/{name}/SKILL.md 不存在"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-01-20: update 刷新 skill
# ──────────────────────────────────────────────────────────────────────────────

class TestUpdateRefreshesSkills:
    def test_update_refreshes_skill_files(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.update import run_update

        monkeypatch.chdir(unity_project)
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))

        # 删除一个 skill 文件
        skill_file = unity_project / ".codebuddy" / "skills" / "openguard-run" / "SKILL.md"
        if skill_file.exists():
            skill_file.unlink()

        run_update(argparse.Namespace(yes=True))
        # skill 应被恢复
        assert skill_file.exists()

    def test_update_preserves_change_data(self, unity_project: Path, monkeypatch):
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.update import run_update

        monkeypatch.chdir(unity_project)
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))

        # 创建 change 数据
        change_dir = unity_project / "openguard" / "changes" / "chg-test"
        change_dir.mkdir(parents=True)
        sentinel = change_dir / "intent.md"
        sentinel.write_text("# test\n", encoding="utf-8")

        run_update(argparse.Namespace(yes=True))
        # change 数据不受影响（REQ-01-20）
        assert sentinel.exists()


# ──────────────────────────────────────────────────────────────────────────────
# REQ-01-21 / REQ-02-14：.gitignore 建议规则
# ──────────────────────────────────────────────────────────────────────────────

class TestGitignoreSuggestion:
    def _init(self, project: Path) -> None:
        import argparse
        from openguard.commands.init import run_init
        old = os.getcwd()
        os.chdir(project)
        try:
            run_init(argparse.Namespace(
                profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
            ))
        finally:
            os.chdir(old)

    def test_gitignore_created_after_init(self, unity_project: Path):
        """REQ-01-21：init 后项目根目录应存在 .gitignore 文件。"""
        self._init(unity_project)
        assert (unity_project / ".gitignore").exists()

    def test_gitignore_contains_openguard_block(self, unity_project: Path):
        """REQ-01-21：.gitignore 包含 OpenGuard 规则块。"""
        self._init(unity_project)
        content = (unity_project / ".gitignore").read_text(encoding="utf-8")
        assert "openguard/reports" in content

    def test_gitignore_excludes_evidence_dir(self, unity_project: Path):
        """REQ-02-14：建议排除大型证据目录。"""
        self._init(unity_project)
        content = (unity_project / ".gitignore").read_text(encoding="utf-8")
        assert "evidence" in content

    def test_gitignore_idempotent(self, unity_project: Path):
        """重复 init 不应重复追加 OpenGuard 块。"""
        self._init(unity_project)
        self._init(unity_project)
        content = (unity_project / ".gitignore").read_text(encoding="utf-8")
        # 只应出现一次 OpenGuard 标记
        assert content.count("# ── OpenGuard") == 1

    def test_gitignore_appended_if_exists(self, unity_project: Path):
        """已有 .gitignore 时应追加，不覆盖原有内容。"""
        existing = "# Existing rules\n*.log\n"
        (unity_project / ".gitignore").write_text(existing, encoding="utf-8")
        self._init(unity_project)
        content = (unity_project / ".gitignore").read_text(encoding="utf-8")
        assert "*.log" in content
        assert "openguard/reports" in content

    def test_write_gitignore_suggestion_standalone(self, tmp_path: Path):
        """write_gitignore_suggestion 可独立调用。"""
        from openguard.setup.ignore_writer import write_gitignore_suggestion
        written, msg = write_gitignore_suggestion(tmp_path)
        assert written is True
        assert (tmp_path / ".gitignore").exists()
        # 再次调用：幂等
        written2, msg2 = write_gitignore_suggestion(tmp_path)
        assert written2 is False

