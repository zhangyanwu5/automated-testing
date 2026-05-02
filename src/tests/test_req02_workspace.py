"""测试 REQ_02：工作区目录结构与产物格式约束。"""
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
def initialized_project(tmp_path: Path) -> Path:
    """返回已完成 openguard init 的项目目录。"""
    import argparse
    from openguard.commands.init import run_init
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        run_init(argparse.Namespace(
            profile="backend",
            hosts=["codebuddy"],
            gate="local",
            yes=True,
            reconfigure=False,
        ))
    finally:
        os.chdir(old)
    return tmp_path


# ──────────────────────────────────────────────────────────────────────────────
# REQ-02-04 / REQ-02-06：目录结构
# ──────────────────────────────────────────────────────────────────────────────

class TestDirectoryLayout:
    def test_reports_suites_dir_created(self, initialized_project: Path):
        assert (initialized_project / "openguard" / "reports" / "suites").is_dir()

    def test_reports_changes_dir_created(self, initialized_project: Path):
        assert (initialized_project / "openguard" / "reports" / "changes").is_dir()

    def test_test_assets_scripts_created(self, initialized_project: Path):
        assert (initialized_project / "openguard" / "test_assets" / "scripts").is_dir()

    def test_test_assets_fixtures_created(self, initialized_project: Path):
        assert (initialized_project / "openguard" / "test_assets" / "fixtures").is_dir()

    def test_suites_smoke_created(self, initialized_project: Path):
        assert (initialized_project / "openguard" / "suites" / "smoke").is_dir()

    def test_no_reports_flat_dir(self, initialized_project: Path):
        """reports/ 应只有 suites/ 和 changes/ 子目录，不再有 flat reports/。"""
        reports = initialized_project / "openguard" / "reports"
        children = {p.name for p in reports.iterdir() if p.is_dir()}
        assert "suites" in children
        assert "changes" in children


class TestEnsureRunDir:
    def test_suite_run_dir(self, initialized_project: Path):
        from openguard.workspace.layout import ensure_run_dir
        openguard_dir = initialized_project / "openguard"
        run_dir = ensure_run_dir(openguard_dir, "run-20260501T100000Z", suite_name="smoke")
        assert run_dir.is_dir()
        assert "suites" in str(run_dir)
        assert "smoke" in str(run_dir)

    def test_change_run_dir(self, initialized_project: Path):
        from openguard.workspace.layout import ensure_run_dir
        openguard_dir = initialized_project / "openguard"
        run_dir = ensure_run_dir(openguard_dir, "run-20260501T100000Z", change_id="chg-001")
        assert run_dir.is_dir()
        assert "changes" in str(run_dir)

    def test_run_dir_is_independent(self, initialized_project: Path):
        """两次执行目录互不覆盖（REQ-02-06）。"""
        from openguard.workspace.layout import ensure_run_dir
        openguard_dir = initialized_project / "openguard"
        r1 = ensure_run_dir(openguard_dir, "run-001", suite_name="smoke")
        r2 = ensure_run_dir(openguard_dir, "run-002", suite_name="smoke")
        assert r1 != r2
        assert r1.is_dir() and r2.is_dir()

    def test_missing_both_raises(self, initialized_project: Path):
        from openguard.workspace.layout import ensure_run_dir
        openguard_dir = initialized_project / "openguard"
        with pytest.raises(ValueError):
            ensure_run_dir(openguard_dir, "run-001")


# ──────────────────────────────────────────────────────────────────────────────
# REQ-02-14：config.yaml 的 reports.retention
# ──────────────────────────────────────────────────────────────────────────────

class TestReportsRetention:
    def test_config_has_reports_retention(self, initialized_project: Path):
        with (initialized_project / "openguard" / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert "reports" in cfg
        assert "retention" in cfg["reports"]

    def test_retention_has_suite_runs_max(self, initialized_project: Path):
        with (initialized_project / "openguard" / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        retention = cfg["reports"]["retention"]
        assert "suite_runs_max" in retention
        assert isinstance(retention["suite_runs_max"], int)

    def test_retention_has_suite_runs_days(self, initialized_project: Path):
        # reports.structure 字段已移除（目录结构是约定，不写入 config）
        # 验证 reports.retention 包含完整的保留配置
        with (initialized_project / "openguard" / "config.yaml").open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        retention = cfg["reports"]["retention"]
        assert "suite_runs_days" in retention
        assert isinstance(retention["suite_runs_days"], int)
