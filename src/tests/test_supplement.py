"""补充测试：update 兼容性报告 / 日志采集 / flaky 治理。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def initialized_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """返回 (project_root, openqa_dir)，含最小 config.yaml。"""
    project_root = tmp_path
    openqa_dir = project_root / "openqa"
    from openqa.workspace.layout import ensure_subdirs
    ensure_subdirs(openqa_dir)
    config = {
        "schema_version": "openqa/config/v1",
        "project": {"type": "unity"},
        "ai_hosts": ["codebuddy"],
        "runtime": {"status": "incomplete", "missing": [], "intrusion_strategy": "external-only"},
        "defaults": {"gate": "local"},
    }
    (openqa_dir / "config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return project_root, openqa_dir


@pytest.fixture
def promoted_script(initialized_workspace, tmp_path):
    """在 test_assets/scripts/ 中放置已晋升的脚本 + meta.yaml。"""
    _, openqa_dir = initialized_workspace
    scripts_dir = openqa_dir / "test_assets" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script = scripts_dir / "login_test.py"
    script.write_text("# login test\n", encoding="utf-8")

    meta = {
        "schema_version": "openqa/script_meta/v2",
        "script": "test_assets/scripts/login_test.py",
        "script_path": "test_assets/scripts/login_test.py",
        "status": "verified",
        "anchor_hash": "abc123",
        "run_ids": ["run-001", "run-002"],
        "suite_membership": ["smoke"],
        "flaky_history": [],
    }
    (scripts_dir / "login_test.meta.yaml").write_text(
        yaml.dump(meta, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return openqa_dir, script


# ──────────────────────────────────────────────────────────────────────────────
# update 命令：兼容性报告
# ──────────────────────────────────────────────────────────────────────────────

class TestUpdateCompatReport:
    def test_compat_report_no_migrate_when_fresh(self, initialized_workspace, monkeypatch):
        """新初始化的工作区不应有需迁移产物。"""
        import argparse
        project_root, _ = initialized_workspace
        monkeypatch.chdir(project_root)
        from openqa.commands.update import run_update
        rc = run_update(argparse.Namespace(yes=True))
        assert rc == 0

    def test_compat_report_detect_old_schema(self, initialized_workspace, monkeypatch, capsys):
        """存在旧 schema_version 的产物时，兼容性报告应标出需迁移项。"""
        project_root, openqa_dir = initialized_workspace
        # 写入旧版 snapshot（假设旧版本号）
        (openqa_dir / "config.yaml").write_text(
            yaml.dump({
                "schema_version": "openqa/config/v0",  # 旧版本
                "project": {"type": "unity"},
                "ai_hosts": ["codebuddy"],
                "runtime": {"status": "incomplete"},
                "defaults": {"gate": "local"},
            }, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        from openqa.commands.update import _build_compat_report
        report = _build_compat_report(openqa_dir)
        assert len(report["migrate"]) > 0
        assert any("config.yaml" in m for m in report["migrate"])

    def test_compat_report_warns_on_old_meta_yaml(self, initialized_workspace):
        """test_assets/ 中旧版 meta.yaml 触发警告但不阻断。"""
        _, openqa_dir = initialized_workspace
        scripts_dir = openqa_dir / "test_assets" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        # 写入旧版 v1 meta
        (scripts_dir / "old_test.meta.yaml").write_text(
            yaml.dump({"schema_version": "openqa/script_meta/v1", "status": "verified"}),
            encoding="utf-8",
        )
        from openqa.commands.update import _build_compat_report
        report = _build_compat_report(openqa_dir)
        # 旧 v1 meta 应触发 warn 而非 migrate
        assert len(report["warn"]) > 0

    def test_update_preserves_changes(self, initialized_workspace, monkeypatch):
        """update 不删除 changes/ 中的已有数据。"""
        import argparse
        project_root, openqa_dir = initialized_workspace
        sentinel = openqa_dir / "changes" / "chg-test" / "intent.md"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("# test\n", encoding="utf-8")
        monkeypatch.chdir(project_root)
        from openqa.commands.update import run_update
        run_update(argparse.Namespace(yes=True))
        assert sentinel.exists()


# ──────────────────────────────────────────────────────────────────────────────
# 日志采集：三层策略
# ──────────────────────────────────────────────────────────────────────────────

class TestLogCollector:
    def test_collect_plaintext_log(self, tmp_path):
        """REQ-13-10：采集已有日志，过滤关键行。"""
        log_file = tmp_path / "game.log"
        log_file.write_text(
            "INFO: Game started\n"
            "ERROR: Login failed: timeout\n"
            "INFO: Frame 100\n"
            "WARN: Low memory\n",
            encoding="utf-8",
        )
        config = {
            "evidence": {
                "log_sources": [{"path": "game.log", "format": "plaintext"}]
            }
        }
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()

        from openqa.log.log_collector import LogCollector
        collector = LogCollector(config, run_dir)
        events = collector.collect(tmp_path)

        # 只保留 ERROR/WARN 相关行
        assert any(e["level"] == "error" for e in events), "应采集到 ERROR 行"
        assert any(e["level"] == "warn" for e in events), "应采集到 WARN 行"
        # 普通 INFO 行应被过滤
        assert not any("Frame 100" in e.get("message", "") for e in events)

    def test_collect_missing_log_produces_warn_event(self, tmp_path):
        """日志文件不存在时产生 warn 事件（不崩溃）。"""
        config = {
            "evidence": {"log_sources": [{"path": "nonexistent.log", "format": "plaintext"}]}
        }
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()
        from openqa.log.log_collector import LogCollector
        collector = LogCollector(config, run_dir)
        events = collector.collect(tmp_path)
        assert any(e["level"] == "warn" for e in events)

    def test_collect_writes_events_jsonl(self, tmp_path):
        """采集结果应写入 events.jsonl。"""
        log_file = tmp_path / "error.log"
        log_file.write_text("ERROR: crash at line 42\n", encoding="utf-8")
        config = {"evidence": {"log_sources": [{"path": "error.log", "format": "plaintext"}]}}
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()
        from openqa.log.log_collector import LogCollector
        collector = LogCollector(config, run_dir)
        events = collector.collect(tmp_path)
        events_path = collector.write_events(events)
        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) > 0
        # 每行是有效 JSON
        for line in lines:
            data = json.loads(line)
            assert "event_type" in data

    def test_log_enhancement_suggestion_not_modify_project(self, tmp_path):
        """REQ-13-11：日志增强建议不修改项目代码，write_to_project=False。"""
        change_dir = tmp_path / "change"
        change_dir.mkdir()
        from openqa.log.log_collector import generate_log_enhancement_suggestions
        result = generate_log_enhancement_suggestions(
            assertion_gaps=["登录成功状态", "金币变化"],
            project_type="unity",
            change_dir=change_dir,
        )
        assert result["write_to_project"] is False
        assert result["suggestion_count"] == 2
        # 建议文件已生成
        assert Path(result["suggestions_path"]).exists()

    def test_debug_build_config_isolated_from_project(self, tmp_path):
        """REQ-13-12：debug build 配置存放在 openqa/ 内，不修改项目代码。"""
        openqa_dir = tmp_path / "openqa"
        openqa_dir.mkdir()
        (openqa_dir / "artifacts").mkdir()
        from openqa.log.log_collector import generate_debug_build_config
        result = generate_debug_build_config("unity", openqa_dir)
        assert result["write_to_project"] is False
        assert result["isolation"] == "debug_build_only"
        config_path = Path(result["config_path"])
        assert "openqa" in str(config_path)
        assert config_path.exists()

    def test_debug_build_config_has_project_type_settings(self, tmp_path):
        """debug build 配置包含项目类型特定设置。"""
        openqa_dir = tmp_path / "openqa"
        openqa_dir.mkdir()
        (openqa_dir / "artifacts").mkdir()
        from openqa.log.log_collector import generate_debug_build_config
        result = generate_debug_build_config("web", openqa_dir)
        config = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
        assert "web_debug_settings" in config

    def test_json_log_parsing(self, tmp_path):
        """JSON 格式日志能被正确解析。"""
        log_file = tmp_path / "app.log"
        log_file.write_text(
            '{"level": "error", "message": "DB connection failed", "timestamp": "2026-05-01T10:00:00Z"}\n'
            '{"level": "info", "message": "Server started"}\n',
            encoding="utf-8",
        )
        config = {"evidence": {"log_sources": [{"path": "app.log", "format": "json"}]}}
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        from openqa.log.log_collector import LogCollector
        collector = LogCollector(config, run_dir)
        events = collector.collect(tmp_path)
        error_events = [e for e in events if e["level"] == "error"]
        assert len(error_events) >= 1
        assert "DB connection failed" in error_events[0]["message"]


# ──────────────────────────────────────────────────────────────────────────────
# flaky 治理
# ──────────────────────────────────────────────────────────────────────────────

class TestFlakyGovernance:
    def test_flaky_detected_when_mixed_results(self, promoted_script):
        """REQ-09-11：有通过有失败时检测为 flaky，降为 needs-review。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import check_flaky_and_demote
        result = check_flaky_and_demote(
            openqa_dir, "login_test.py",
            run_results=["passed", "failed", "passed"]
        )
        assert result["status"] == "demoted_to_needs_review"

    def test_stable_script_not_demoted(self, promoted_script):
        """全部通过时不降级。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import check_flaky_and_demote
        result = check_flaky_and_demote(
            openqa_dir, "login_test.py",
            run_results=["passed", "passed", "passed"]
        )
        assert result["status"] == "stable"

    def test_flaky_written_to_knowledge_dir(self, promoted_script):
        """REQ-09-11：flaky 检测结果写入 knowledge/flaky_rules.yaml。"""
        openqa_dir, _ = promoted_script
        knowledge_dir = openqa_dir / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        # 初始化 flaky_rules.yaml
        (knowledge_dir / "flaky_rules.yaml").write_text(
            yaml.dump({"schema_version": "openqa/knowledge/v1", "items": []}),
            encoding="utf-8",
        )
        from openqa.knowledge.manager import check_flaky_and_demote
        check_flaky_and_demote(
            openqa_dir, "login_test.py",
            run_results=["passed", "failed"]
        )
        data = yaml.safe_load(
            (knowledge_dir / "flaky_rules.yaml").read_text(encoding="utf-8")
        )
        items = data.get("items", [])
        assert len(items) > 0
        assert any("flaky" in str(item.get("key", "")) for item in items)

    def test_flaky_history_accumulated(self, promoted_script):
        """多次 flaky 检测时历史记录累积。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import check_flaky_and_demote, get_flaky_history
        check_flaky_and_demote(openqa_dir, "login_test.py", ["passed", "failed"])
        # 修复状态后再次 flaky
        scripts_dir = openqa_dir / "test_assets" / "scripts"
        meta_path = scripts_dir / "login_test.meta.yaml"
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "verified"
        meta_path.write_text(yaml.dump(meta, default_flow_style=False, allow_unicode=True), encoding="utf-8")
        check_flaky_and_demote(openqa_dir, "login_test.py", ["passed", "failed"])
        history = get_flaky_history(openqa_dir, "login_test.py")
        assert len(history) >= 2

    def test_should_not_promote_flaky_script(self, promoted_script):
        """REQ-13-22：有 flaky 历史的脚本不得晋升。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import check_flaky_and_demote, should_promote_script
        check_flaky_and_demote(openqa_dir, "login_test.py", ["passed", "failed"])
        result = should_promote_script(openqa_dir, "login_test.py", run_ids=["r1", "r2"])
        assert result["eligible"] is False
        assert "flaky" in result["reason"]

    def test_should_not_promote_without_run_ids(self, promoted_script):
        """REQ-13-23：无真实执行记录不得晋升。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import should_promote_script
        result = should_promote_script(openqa_dir, "login_test.py", run_ids=[])
        assert result["eligible"] is False
        assert "执行记录" in result["reason"] or "REQ-13-23" in result["reason"]

    def test_eligible_to_promote_with_clean_history(self, promoted_script):
        """满足条件（多次通过，无 flaky）时判定可晋升。"""
        openqa_dir, _ = promoted_script
        from openqa.knowledge.manager import should_promote_script
        result = should_promote_script(openqa_dir, "login_test.py", run_ids=["r1", "r2"])
        assert result["eligible"] is True


# ──────────────────────────────────────────────────────────────────────────────
# freshness: test_assets 锚点联动
# ──────────────────────────────────────────────────────────────────────────────

class TestFreshnessAnchorLinkage:
    def _make_snapshot(self, change_dir: Path, symbols: list[dict]) -> None:
        """写入带符号哈希的 snapshot.json。"""
        import json as _json
        snapshot = {
            "schema_version": "openqa/snapshot/v1",
            "status": "complete",
            "analyzer_version": "openqa-scanner/v1",
            "code_files": [
                {
                    "path": "Assets/Login.cs",
                    "hash": "file_hash",
                    "symbols": symbols,
                }
            ],
            "requirements": {},
        }
        (change_dir / "snapshot.json").write_text(
            _json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )

    def test_freshness_detects_anchor_change(self, initialized_workspace):
        """新鲜度校验中的锚点检查能检测到符号哈希变化。"""
        project_root, openqa_dir = initialized_workspace

        # 在 test_assets 中放置 verified 脚本，绑定符号 oldHash
        scripts_dir = openqa_dir / "test_assets" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "schema_version": "openqa/script_meta/v2",
            "script_path": "test_assets/scripts/t.py",
            "status": "verified",
            "anchor_hash": "x",
            "bound_to": [{"type": "code_symbol", "path": "Assets/Login.cs",
                           "symbol": "Login.Handle", "hash": "oldHash"}],
        }
        (scripts_dir / "t.meta.yaml").write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True), encoding="utf-8"
        )

        # change_dir 写入 snapshot（符号 newHash）
        change_dir = openqa_dir / "changes" / "chg-test"
        change_dir.mkdir(parents=True)
        self._make_snapshot(change_dir, [{"name": "Login.Handle", "hash": "newHash"}])

        from openqa.scan.freshness import check_freshness
        result = check_freshness(change_dir, openqa_dir)

        # 应有 anchor_reports 且含 needs-review 变化
        reports = result.get("anchor_reports", [])
        assert any(r["new_status"] == "needs-review" for r in reports)

    def test_freshness_passes_when_anchors_unchanged(self, initialized_workspace):
        """符号哈希未变时不产生 anchor 变化报告。"""
        _, openqa_dir = initialized_workspace

        scripts_dir = openqa_dir / "test_assets" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "schema_version": "openqa/script_meta/v2",
            "script_path": "test_assets/scripts/t.py",
            "status": "verified",
            "anchor_hash": "x",
            "bound_to": [{"type": "code_symbol", "path": "A.cs",
                           "symbol": "A.Do", "hash": "sameHash"}],
        }
        (scripts_dir / "t.meta.yaml").write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True), encoding="utf-8"
        )

        change_dir = openqa_dir / "changes" / "chg-test"
        change_dir.mkdir(parents=True)
        self._make_snapshot(change_dir, [{"name": "A.Do", "hash": "sameHash"}])

        from openqa.scan.freshness import check_freshness
        result = check_freshness(change_dir, openqa_dir)
        reports = result.get("anchor_reports", [])
        assert reports == []
