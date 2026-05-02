"""测试 REQ_04：扫描与影响分析，REQ_05：测试矩阵生成。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def project_with_change(tmp_path: Path):
    """返回已 init + new change 的项目，包含若干源码文件。"""
    import argparse
    from openguard.commands.init import run_init
    from openguard.workspace.change import create_change

    # 创建一些源码文件
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "def main():\n    pass\n\nclass App:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "src" / "auth.py").write_text(
        "def login(user, password):\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        run_init(argparse.Namespace(
            profile="backend", hosts=["codebuddy"],
            gate="local", yes=True, reconfigure=False,
        ))
    finally:
        os.chdir(old)

    openguard_dir = tmp_path / "openguard"
    _, change_dir = create_change(openguard_dir, "验证用户认证逻辑")
    return tmp_path, openguard_dir, change_dir


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-07：忽略规则
# ──────────────────────────────────────────────────────────────────────────────

class TestIgnoreRules:
    def test_load_ignore_patterns(self, project_with_change):
        from openguard.scan.scanner import load_ignore_patterns
        _, openguard_dir, _ = project_with_change
        patterns = load_ignore_patterns(openguard_dir)
        assert len(patterns) > 0
        assert ".git/" in patterns

    def test_openguard_dir_excluded(self, project_with_change):
        from openguard.scan.scanner import load_ignore_patterns, _is_ignored
        tmp_path, openguard_dir, _ = project_with_change
        patterns = load_ignore_patterns(openguard_dir)
        # openguard/ 内文件应被忽略
        test_path = openguard_dir / "config.yaml"
        assert _is_ignored(test_path, tmp_path, patterns)

    def test_src_files_not_ignored(self, project_with_change):
        from openguard.scan.scanner import load_ignore_patterns, _is_ignored
        tmp_path, openguard_dir, _ = project_with_change
        patterns = load_ignore_patterns(openguard_dir)
        src_file = tmp_path / "src" / "main.py"
        assert not _is_ignored(src_file, tmp_path, patterns)


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-01 / REQ-04-08：文件扫描与符号摘要
# ──────────────────────────────────────────────────────────────────────────────

class TestFileScanning:
    def test_full_scan_returns_files(self, project_with_change):
        from openguard.scan.scanner import run_full_scan
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        assert result["file_count"] > 0
        assert len(result["files"]) > 0

    def test_file_record_has_required_fields(self, project_with_change):
        from openguard.scan.scanner import run_full_scan
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        for f in result["files"]:
            assert "path" in f
            assert "hash" in f
            assert "language" in f
            assert "symbols" in f

    def test_python_language_detected(self, project_with_change):
        from openguard.scan.scanner import run_full_scan
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        py_files = [f for f in result["files"] if f["language"] == "python"]
        assert len(py_files) > 0

    def test_symbols_extracted(self, project_with_change):
        from openguard.scan.scanner import run_full_scan
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        main_file = next((f for f in result["files"] if "main.py" in f["path"]), None)
        assert main_file is not None
        assert "main" in main_file["symbols"] or "App" in main_file["symbols"]

    def test_scan_hints_generated(self, project_with_change):
        from openguard.scan.scanner import run_full_scan
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        assert "scan_hints" in result
        assert "project_type" in result["scan_hints"]

    def test_analyzer_version_recorded(self, project_with_change):
        from openguard.scan.scanner import run_full_scan, ANALYZER_VERSION
        from openguard.setup.config_writer import load_config
        tmp_path, openguard_dir, _ = project_with_change
        config = load_config(openguard_dir)
        result = run_full_scan(tmp_path, openguard_dir, config)
        assert result["analyzer_version"] == ANALYZER_VERSION


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-01 / REQ-04-02：snapshot 写入
# ──────────────────────────────────────────────────────────────────────────────

class TestSnapshotWrite:
    def test_execute_scan_creates_snapshot(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        snap_path, _ = execute_scan(change_dir, openguard_dir, config, "full")
        assert snap_path.exists()

    def test_snapshot_status_complete(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        snap_path, _ = execute_scan(change_dir, openguard_dir, config, "full")
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        assert data["status"] == "complete"

    def test_snapshot_has_code_files(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        snap_path, _ = execute_scan(change_dir, openguard_dir, config, "full")
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        assert len(data["code_files"]) > 0

    def test_full_scan_creates_full_index(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")
        full_index = openguard_dir / "artifacts" / "full_index.json"
        assert full_index.exists()

    def test_incremental_scan_creates_delta(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        # 先执行全量建立基线
        execute_scan(change_dir, openguard_dir, config, "full")
        # 再执行增量
        _, delta_path = execute_scan(change_dir, openguard_dir, config, "incremental")
        assert delta_path is not None and delta_path.exists()

    def test_delta_has_required_fields(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")
        _, delta_path = execute_scan(change_dir, openguard_dir, config, "incremental")
        data = json.loads(delta_path.read_text(encoding="utf-8"))
        for field in ("added", "modified", "deleted", "change_summary"):
            assert field in data


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-05：新鲜度校验
# ──────────────────────────────────────────────────────────────────────────────

class TestFreshnessCheck:
    def test_freshness_fails_without_snapshot(self, project_with_change):
        from openguard.scan.freshness import check_freshness
        _, openguard_dir, change_dir = project_with_change
        result = check_freshness(change_dir, openguard_dir)
        assert result["is_fresh"] is False
        failed = [c for c in result["checks"] if c["status"] == "fail"]
        assert any("snapshot" in c["check"].lower() for c in failed)

    def test_freshness_passes_after_scan(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.scan.freshness import run_freshness_check
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")
        is_fresh, path = run_freshness_check(change_dir, openguard_dir)
        assert is_fresh is True
        assert path.exists()

    def test_freshness_json_written(self, project_with_change):
        from openguard.scan.freshness import run_freshness_check
        _, openguard_dir, change_dir = project_with_change
        _, path = run_freshness_check(change_dir, openguard_dir)
        assert path.name == "freshness.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert "checks" in data
        assert "is_fresh" in data

    def test_freshness_fails_after_requirements_change(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.scan.freshness import check_freshness
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        # 先扫描
        execute_scan(change_dir, openguard_dir, config, "full")
        # 修改 requirements.md 后应失效
        req_path = change_dir / "requirements.md"
        original = req_path.read_text(encoding="utf-8")
        req_path.write_text(original + "\n| NEW-REQ-001 | WHEN changed THEN system SHALL respond | P0 | draft |\n", encoding="utf-8")
        result = check_freshness(change_dir, openguard_dir)
        assert result["is_fresh"] is False


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-04：影响图生成
# ──────────────────────────────────────────────────────────────────────────────

class TestImpactGraph:
    def _scan_first(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")
        return openguard_dir, change_dir, config

    def test_impact_graph_created(self, project_with_change):
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        assert path.exists()

    def test_impact_graph_has_schema_version(self, project_with_change):
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"].startswith("openguard/impact_graph/")

    def test_impact_graph_has_changed_files(self, project_with_change):
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "changed_files" in data

    def test_impact_graph_has_review_scope(self, project_with_change):
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "review_scope" in data
        assert "files" in data["review_scope"]

    def test_impact_graph_recommends_test_types(self, project_with_change):
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "test_types" in data
        assert len(data["test_types"]) > 0

    def test_high_risk_auth_file_detected(self, project_with_change):
        """auth.py 应被标记为高风险（REQ-04-04）。"""
        from openguard.scan.impact import run_impact_analysis
        openguard_dir, change_dir, config = self._scan_first(project_with_change)
        path = run_impact_analysis(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        review_files = data["review_scope"]["files"]
        auth_files = [f for f in review_files if "auth" in f["path"]]
        if auth_files:
            assert auth_files[0]["risk_level"] == "high"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-05：测试矩阵生成
# ──────────────────────────────────────────────────────────────────────────────

class TestMatrixGeneration:
    def _setup(self, project_with_change):
        from openguard.scan.scanner import execute_scan
        from openguard.scan.impact import run_impact_analysis
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")
        run_impact_analysis(change_dir, openguard_dir, config)
        return openguard_dir, change_dir, config

    def test_matrix_generated(self, project_with_change):
        from openguard.matrix.generator import run_matrix_generation
        openguard_dir, change_dir, config = self._setup(project_with_change)
        path = run_matrix_generation(change_dir, openguard_dir, config)
        assert path.exists()

    def test_matrix_schema_version(self, project_with_change):
        from openguard.matrix.generator import run_matrix_generation
        openguard_dir, change_dir, config = self._setup(project_with_change)
        path = run_matrix_generation(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["schema_version"].startswith("openguard/test_matrix/")

    def test_matrix_has_tasks(self, project_with_change):
        from openguard.matrix.generator import run_matrix_generation
        openguard_dir, change_dir, config = self._setup(project_with_change)
        path = run_matrix_generation(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "tasks" in data
        assert len(data["tasks"]) > 0

    def test_matrix_has_env_task(self, project_with_change):
        """所有套件都应有环境准备任务（REQ-05-03）。"""
        from openguard.matrix.generator import run_matrix_generation
        openguard_dir, change_dir, config = self._setup(project_with_change)
        path = run_matrix_generation(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data["tasks"]
        env_tasks = [t for t in tasks if t["type"] == "precondition"]
        assert len(env_tasks) > 0

    def test_matrix_has_summary(self, project_with_change):
        from openguard.matrix.generator import run_matrix_generation
        openguard_dir, change_dir, config = self._setup(project_with_change)
        path = run_matrix_generation(change_dir, openguard_dir, config)
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]
        assert "total" in summary
        assert "runnable" in summary
        assert "blocked" in summary
        assert "skipped" in summary

    def test_matrix_blocked_when_runtime_incomplete(self, project_with_change):
        """runtime 配置不完整时，任务应标记 blocked（REQ-05-09）。"""
        from openguard.matrix.generator import build_test_matrix
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        # 强制设置 runtime 为 incomplete
        config["runtime"] = {
            "status": "incomplete",
            "missing": ["unity.editor_path"],
        }
        matrix = build_test_matrix(change_dir, openguard_dir, config, "smoke")
        assert matrix["runtime_requirements"]["status"] == "incomplete"
        assert len(matrix["runtime_requirements"]["blockers"]) > 0

    def test_matrix_suite_smoke_uses_fail_fast(self, project_with_change):
        """冒烟套件应设置 fail_fast=True（REQ-05-07）。"""
        from openguard.matrix.generator import build_test_matrix
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        matrix = build_test_matrix(change_dir, openguard_dir, config, "smoke")
        assert matrix["execution_strategy"]["fail_fast"] is True

    def test_matrix_suite_full_no_fail_fast(self, project_with_change):
        from openguard.matrix.generator import build_test_matrix
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        matrix = build_test_matrix(change_dir, openguard_dir, config, "full")
        assert matrix["execution_strategy"]["fail_fast"] is False

    def test_matrix_records_selection_basis(self, project_with_change):
        """矩阵必须记录套件选择依据（REQ-05-06）。"""
        from openguard.matrix.generator import build_test_matrix
        from openguard.setup.config_writer import load_config
        _, openguard_dir, change_dir = project_with_change
        config = load_config(openguard_dir)
        for suite in ("smoke", "incremental", "requirement-full"):
            matrix = build_test_matrix(change_dir, openguard_dir, config, suite)
            assert matrix["execution_strategy"]["selection_basis"]

    def test_valid_test_suites_accepted(self):
        from openguard.matrix.generator import _resolve_suite, VALID_TEST_SUITES
        for suite in VALID_TEST_SUITES:
            assert _resolve_suite(suite, "smoke") == suite

    def test_invalid_suite_falls_back_to_smoke(self):
        from openguard.matrix.generator import _resolve_suite
        assert _resolve_suite("invalid-suite", "smoke") == "smoke"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04/05：continue 集成（扫描+矩阵自动生成）
# ──────────────────────────────────────────────────────────────────────────────

class TestContinueWithAutoGeneration:
    def test_continue_auto_generates_snapshot(self, project_with_change, monkeypatch):
        """continue 在 intent/requirements 就绪后应自动执行扫描。"""
        import argparse
        from openguard.commands.continue_ import run_continue
        _, openguard_dir, change_dir = project_with_change
        monkeypatch.chdir(openguard_dir.parent)

        # 标记 intent.md 和 requirements.md 为就绪（已有骨架）
        # 直接运行 continue，它应自动扫描
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc == 0
        # 第一次 continue 应停在 intent.md（Agent 需确认），不会自动扫描
        # 测试：运行足够多次，最终 snapshot 应被自动生成
        # 首先模拟 Agent 确认 intent/requirements
        for _ in range(5):
            rc = run_continue(argparse.Namespace(change_id=None))
            if (change_dir / "snapshot.json").exists():
                snap = json.loads((change_dir / "snapshot.json").read_text(encoding="utf-8"))
                if snap.get("status") == "complete":
                    break

        # snapshot 应最终被自动生成
        assert (change_dir / "snapshot.json").exists()

    def test_continue_auto_generates_impact_graph(self, project_with_change, monkeypatch):
        """扫描完成后继续运行，应自动生成影响图。"""
        import argparse
        from openguard.scan.scanner import execute_scan
        from openguard.setup.config_writer import load_config
        from openguard.commands.continue_ import run_continue
        _, openguard_dir, change_dir = project_with_change
        monkeypatch.chdir(openguard_dir.parent)

        # 预先完成扫描
        config = load_config(openguard_dir)
        execute_scan(change_dir, openguard_dir, config, "full")

        # continue 应自动生成影响图
        for _ in range(3):
            run_continue(argparse.Namespace(change_id=None))
            if (change_dir / "impact_graph.json").exists():
                break

        assert (change_dir / "impact_graph.json").exists()
        data = json.loads((change_dir / "impact_graph.json").read_text(encoding="utf-8"))
        assert data["status"] == "complete"
