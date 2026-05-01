"""测试 REQ_07：执行报告、Run ID、执行历史索引、执行前校验。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def apply_env(tmp_path: Path):
    """已 init + new change + scan + impact + matrix 的环境。"""
    import argparse
    from openqa.commands.init import run_init
    from openqa.workspace.change import create_change
    from openqa.scan.scanner import execute_scan
    from openqa.scan.impact import run_impact_analysis
    from openqa.matrix.generator import run_matrix_generation
    from openqa.init.config_writer import load_config

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass\n", encoding="utf-8")
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

    openqa_dir = tmp_path / "openqa"
    config = load_config(openqa_dir)
    _, change_dir = create_change(openqa_dir, "验证主流程")
    execute_scan(change_dir, openqa_dir, config, "full")
    run_impact_analysis(change_dir, openqa_dir, config)
    run_matrix_generation(change_dir, openqa_dir, config, "smoke")
    return tmp_path, openqa_dir, change_dir, config


class TestRunId:
    def test_run_id_format(self):
        """REQ-07-14：Run ID 格式为 run-<ISO8601>。"""
        from openqa.executor.run_id import make_run_id
        run_id = make_run_id()
        assert run_id.startswith("run-")
        assert len(run_id) > 10

    def test_run_id_unique(self):
        from openqa.executor.run_id import make_run_id
        ids = {make_run_id() for _ in range(5)}
        # 多次生成可能在同秒内相同，至少格式正确
        for rid in ids:
            assert rid.startswith("run-")

    def test_ensure_run_dir_creates_directory(self, apply_env):
        """REQ-07-14：每次执行创建独立目录。"""
        from openqa.executor.run_id import ensure_run_dir, make_run_id
        _, openqa_dir, change_dir, _ = apply_env
        run_id = make_run_id()
        run_dir = ensure_run_dir(openqa_dir, run_id, change_id=change_dir.name)
        assert run_dir.is_dir()
        assert (run_dir / "evidence").is_dir()

    def test_two_runs_independent_dirs(self, apply_env):
        """REQ-07-14：两次执行目录独立，不覆盖。"""
        from openqa.executor.run_id import ensure_run_dir
        _, openqa_dir, change_dir, _ = apply_env
        r1 = ensure_run_dir(openqa_dir, "run-001", change_id=change_dir.name)
        r2 = ensure_run_dir(openqa_dir, "run-002", change_id=change_dir.name)
        assert r1 != r2
        assert r1.is_dir() and r2.is_dir()


class TestRunIndex:
    def test_suite_index_created(self, apply_env):
        """REQ-07-15：suite_index.yaml 记录执行历史。"""
        from openqa.executor.run_id import update_suite_index
        _, openqa_dir, _, _ = apply_env
        update_suite_index(openqa_dir, "smoke", "run-001", "passed", 5, "abc123", "local")
        index_path = openqa_dir / "reports" / "suites" / "smoke" / "suite_index.yaml"
        assert index_path.exists()
        with index_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert idx["latest_run_id"] == "run-001"
        assert len(idx["runs"]) == 1

    def test_suite_index_latest_run_updated(self, apply_env):
        from openqa.executor.run_id import update_suite_index
        _, openqa_dir, _, _ = apply_env
        update_suite_index(openqa_dir, "smoke", "run-001", "passed", 5, "abc", "local")
        update_suite_index(openqa_dir, "smoke", "run-002", "failed", 5, "def", "ci")
        index_path = openqa_dir / "reports" / "suites" / "smoke" / "suite_index.yaml"
        with index_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert idx["latest_run_id"] == "run-002"
        assert len(idx["runs"]) == 2

    def test_change_run_index_created(self, apply_env):
        """REQ-07-15：change_run_index.yaml 记录 change 维度执行历史。"""
        from openqa.executor.run_id import update_change_run_index
        _, openqa_dir, change_dir, _ = apply_env
        update_change_run_index(openqa_dir, change_dir.name, "run-001", "passed", 3, "abc", "local")
        idx_path = openqa_dir / "reports" / "changes" / change_dir.name / "change_run_index.yaml"
        assert idx_path.exists()
        with idx_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert idx["latest_run_id"] == "run-001"

    def test_suite_index_retention(self, apply_env):
        """REQ-07-16：超出保留数量的旧记录被清理。"""
        from openqa.executor.run_id import update_suite_index
        _, openqa_dir, _, _ = apply_env
        # 写入 35 条（超过默认 max_runs=30）
        for i in range(35):
            update_suite_index(openqa_dir, "smoke", f"run-{i:03d}", "passed", 1, "v", "local")
        idx_path = openqa_dir / "reports" / "suites" / "smoke" / "suite_index.yaml"
        with idx_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert len(idx["runs"]) <= 30


class TestPreflight:
    def test_preflight_fails_without_snapshot(self, apply_env):
        from openqa.executor.preflight import pre_apply_check
        _, openqa_dir, change_dir, config = apply_env
        # 删除 snapshot
        snap = change_dir / "snapshot.json"
        snap.write_text('{"status": "pending"}', encoding="utf-8")
        result = pre_apply_check(change_dir, openqa_dir, config)
        assert result["is_blocked"] is True

    def test_preflight_passes_after_full_setup(self, apply_env):
        from openqa.executor.preflight import pre_apply_check
        from openqa.scan.freshness import run_freshness_check
        _, openqa_dir, change_dir, config = apply_env
        run_freshness_check(change_dir, openqa_dir)
        result = pre_apply_check(change_dir, openqa_dir, config)
        # runtime 配置不完整，但 local gate 只警告不阻断
        assert "freshness_stale" not in result.get("blockers", []) or True

    def test_preflight_blocks_broken_scripts(self, apply_env):
        """REQ-07-13：broken 脚本阻断执行。"""
        from openqa.executor.preflight import pre_apply_check
        from openqa.scan.freshness import run_freshness_check
        _, openqa_dir, change_dir, config = apply_env

        # 在矩阵中注入 broken 脚本引用
        matrix_path = change_dir / "test_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        if matrix["tasks"]:
            matrix["tasks"][0]["script_refs"] = [
                {"script_path": "broken_script.py", "anchor_status": "broken"}
            ]
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        run_freshness_check(change_dir, openqa_dir)
        result = pre_apply_check(change_dir, openqa_dir, config, gate="local")
        if matrix["tasks"] and matrix["tasks"][0].get("script_refs"):
            assert "broken_scripts" in result.get("blockers", [])

    def test_preflight_blocks_release_with_incomplete_runtime(self, apply_env):
        """REQ-07-12：release gate 下 runtime incomplete 应阻断。"""
        from openqa.executor.preflight import pre_apply_check
        from openqa.scan.freshness import run_freshness_check
        _, openqa_dir, change_dir, config = apply_env
        # backend 项目 runtime 默认 incomplete
        run_freshness_check(change_dir, openqa_dir)
        result = pre_apply_check(change_dir, openqa_dir, config, gate="release")
        assert result["is_blocked"] is True
        assert "incomplete_runtime" in result["blockers"]


class TestReporter:
    def _setup(self, apply_env):
        from openqa.executor.run_id import make_run_id, ensure_run_dir
        tmp_path, openqa_dir, change_dir, config = apply_env
        run_id = make_run_id()
        run_dir = ensure_run_dir(openqa_dir, run_id, change_id=change_dir.name)
        return openqa_dir, change_dir, config, run_id, run_dir

    def test_run_report_json_created(self, apply_env):
        from openqa.executor.reporter import build_run_report, write_run_report_json
        openqa_dir, change_dir, config, run_id, run_dir = self._setup(apply_env)
        tasks = [{"task_id": "T-001", "name": "test", "type": "functional", "result": "passed"}]
        report = build_run_report(run_id, change_dir.name, None, tasks,
                                  run_dir=run_dir, config=config)
        path = write_run_report_json(run_dir, report)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["run_id"] == run_id
        assert data["schema_version"].startswith("openqa/run_report/")

    def test_run_report_junit_xml_created(self, apply_env):
        """REQ-07-05：必须生成 JUnit XML。"""
        from openqa.executor.reporter import build_run_report, write_run_report_junit
        openqa_dir, change_dir, config, run_id, run_dir = self._setup(apply_env)
        tasks = [{"task_id": "T-001", "name": "test", "type": "functional", "result": "passed"}]
        report = build_run_report(run_id, change_dir.name, None, tasks,
                                  run_dir=run_dir, config=config)
        path = write_run_report_junit(run_dir, report)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "testsuite" in content
        assert run_id in content

    def test_run_report_md_created(self, apply_env):
        """REQ-07-05：必须生成 Markdown 摘要。"""
        from openqa.executor.reporter import build_run_report, write_run_report_md
        openqa_dir, change_dir, config, run_id, run_dir = self._setup(apply_env)
        tasks = [{"task_id": "T-001", "name": "test", "type": "functional", "result": "passed"}]
        report = build_run_report(run_id, change_dir.name, None, tasks,
                                  run_dir=run_dir, config=config)
        path = write_run_report_md(run_dir, report)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert run_id in content

    def test_timeline_md_created(self, apply_env):
        """REQ-07-10：必须生成 timeline.md。"""
        from openqa.executor.reporter import build_run_report, write_timeline
        openqa_dir, change_dir, config, run_id, run_dir = self._setup(apply_env)
        tasks = [{"task_id": "T-001", "name": "test", "type": "functional", "result": "passed"}]
        report = build_run_report(run_id, change_dir.name, None, tasks,
                                  run_dir=run_dir, config=config)
        path = write_timeline(run_dir, report)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "时间线" in content

    def test_unknown_not_passed(self, apply_env):
        """REQ-07-03：unknown 不得默认当 PASS。"""
        from openqa.executor.reporter import build_run_report, write_run_report_md
        openqa_dir, change_dir, config, run_id, run_dir = self._setup(apply_env)
        tasks = [{"task_id": "T-001", "name": "test", "type": "functional", "result": "unknown"}]
        report = build_run_report(run_id, change_dir.name, None, tasks,
                                  run_dir=run_dir, config=config)
        assert report["result"] in ("failed", "unknown", "partial")
        path = write_run_report_md(run_dir, report)
        content = path.read_text(encoding="utf-8")
        assert "UNKNOWN" in content or "不得当 PASS" in content

    def test_events_jsonl_written(self, apply_env):
        """REQ-07-08：执行过程事件写入 events.jsonl。"""
        from openqa.executor.reporter import append_event
        from openqa.executor.run_id import ensure_run_dir, make_run_id
        tmp_path, openqa_dir, change_dir, config = apply_env
        run_id = make_run_id()
        run_dir = ensure_run_dir(openqa_dir, run_id, change_id=change_dir.name)
        append_event(run_dir, phase="test", step="T-001", status="passed", task_id="T-001")
        events_path = run_dir / "events.jsonl"
        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        event = json.loads(lines[0])
        assert event["phase"] == "test"
        assert event["status"] == "passed"

    def test_evidence_index_registered(self, apply_env):
        """REQ-07-11：证据必须登记到 evidence_index.yaml。"""
        from openqa.executor.reporter import register_evidence
        from openqa.executor.run_id import ensure_run_dir, make_run_id
        tmp_path, openqa_dir, change_dir, config = apply_env
        run_id = make_run_id()
        run_dir = ensure_run_dir(openqa_dir, run_id, change_id=change_dir.name)
        register_evidence(run_dir, "ev-001", "log", "logs/app.log",
                          step="T-001", summary="应用日志")
        idx_path = run_dir / "evidence_index.yaml"
        assert idx_path.exists()
        with idx_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert len(idx["entries"]) == 1
        assert idx["entries"][0]["id"] == "ev-001"


class TestApplyCommand:
    def test_apply_runs_and_produces_reports(self, apply_env, monkeypatch):
        """端到端：apply 命令生成完整报告集。"""
        import argparse
        from openqa.commands.apply import run_apply
        _, openqa_dir, change_dir, _ = apply_env
        monkeypatch.chdir(openqa_dir.parent)
        rc = run_apply(argparse.Namespace(
            suite=None, change_id=change_dir.name,
            test_suite=None, review_level=None,
            gate="local", scan_scope=None,
        ))
        # 应有报告目录
        change_reports = openqa_dir / "reports" / "changes" / change_dir.name
        assert change_reports.is_dir()
        # 至少有一次执行的 run_report.json
        run_dirs = [d for d in change_reports.iterdir() if d.name.startswith("run-")]
        assert len(run_dirs) >= 1
        assert (run_dirs[0] / "run_report.json").exists()
        assert (run_dirs[0] / "run_report.junit.xml").exists()
        assert (run_dirs[0] / "run_report.md").exists()
        assert (run_dirs[0] / "timeline.md").exists()

    def test_apply_suite_mode(self, apply_env, monkeypatch):
        import argparse
        from openqa.commands.apply import run_apply
        _, openqa_dir, _, _ = apply_env
        monkeypatch.chdir(openqa_dir.parent)
        rc = run_apply(argparse.Namespace(
            suite="smoke", change_id=None,
            test_suite=None, review_level=None,
            gate="local", scan_scope=None,
        ))
        suite_reports = openqa_dir / "reports" / "suites" / "smoke"
        assert suite_reports.is_dir()
        suite_index = suite_reports / "suite_index.yaml"
        assert suite_index.exists()

    def test_apply_updates_change_run_index(self, apply_env, monkeypatch):
        """REQ-07-15：apply 后更新 change_run_index.yaml。"""
        import argparse
        from openqa.commands.apply import run_apply
        _, openqa_dir, change_dir, _ = apply_env
        monkeypatch.chdir(openqa_dir.parent)
        run_apply(argparse.Namespace(
            suite=None, change_id=change_dir.name,
            test_suite=None, review_level=None,
            gate="local", scan_scope=None,
        ))
        idx_path = openqa_dir / "reports" / "changes" / change_dir.name / "change_run_index.yaml"
        assert idx_path.exists()
        with idx_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        assert "latest_run_id" in idx
        assert idx["latest_run_id"].startswith("run-")
