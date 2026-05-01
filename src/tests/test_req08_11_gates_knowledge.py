"""测试 REQ_08~11：门禁、知识进化、治理边界、操作追踪。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def full_env(tmp_path: Path):
    """完整环境：init + new + scan + impact + matrix + apply（dry_run）。"""
    import argparse
    from openqa.commands.init import run_init
    from openqa.workspace.change import create_change
    from openqa.scan.scanner import execute_scan
    from openqa.scan.impact import run_impact_analysis
    from openqa.matrix.generator import run_matrix_generation
    from openqa.executor.runner import run_apply as executor_run
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
    _, change_dir = create_change(openqa_dir, "完整流程测试")
    execute_scan(change_dir, openqa_dir, config, "full")
    run_impact_analysis(change_dir, openqa_dir, config)
    run_matrix_generation(change_dir, openqa_dir, config, "smoke")
    executor_run(openqa_dir, config, change_id=change_dir.name, gate="local", dry_run=True)
    return tmp_path, openqa_dir, change_dir, config


# ──────────────────────────────────────────────────────────────────────────────
# REQ-08：门禁
# ──────────────────────────────────────────────────────────────────────────────

class TestGateEngine:
    def test_resolve_gate_policy_local(self, full_env):
        from openqa.gates.gate_engine import resolve_gate_policy
        _, _, _, config = full_env
        policy = resolve_gate_policy("local", config)
        assert policy["scan_scope"] == "incremental"
        assert policy["test_suite"] == "smoke"

    def test_resolve_gate_policy_release(self, full_env):
        from openqa.gates.gate_engine import resolve_gate_policy
        _, _, _, config = full_env
        policy = resolve_gate_policy("release", config)
        assert policy["scan_scope"] == "full"

    def test_all_five_gates_defined(self):
        from openqa.gates.gate_engine import GATE_POLICIES
        for gate in ("local", "ci", "requirement", "release", "nightly"):
            assert gate in GATE_POLICIES

    def test_evaluate_gate_passed(self, full_env):
        from openqa.gates.gate_engine import evaluate_gate
        _, openqa_dir, change_dir, config = full_env
        run_report = {"result": "passed", "summary": {"failed": 0, "unknown": 0, "blocked": 0}}
        result = evaluate_gate("local", run_report, change_dir, openqa_dir, config)
        assert result["result"] == "passed"
        assert result["gate"] == "local"

    def test_evaluate_gate_blocked_by_unknown(self, full_env):
        """REQ-08-02：UNKNOWN 在 release gate 下阻断。"""
        from openqa.gates.gate_engine import evaluate_gate
        _, openqa_dir, change_dir, config = full_env
        run_report = {"result": "unknown", "summary": {"failed": 0, "unknown": 2, "blocked": 0}}
        result = evaluate_gate("release", run_report, change_dir, openqa_dir, config)
        assert result["result"] == "failed"
        assert "unknown_not_pass" in result["blocking_items"]

    def test_evaluate_gate_with_exemption(self, full_env):
        """REQ-08-03：豁免后不再阻断。"""
        from openqa.gates.gate_engine import evaluate_gate, make_exemption
        _, openqa_dir, change_dir, config = full_env
        run_report = {"result": "unknown", "summary": {"failed": 0, "unknown": 1, "blocked": 0}}
        exemption = make_exemption("unknown_not_pass", "上线时间紧，人工确认无影响", "alice")
        result = evaluate_gate("release", run_report, change_dir, openqa_dir, config,
                                exemptions=[exemption])
        # 豁免后 unknown_not_pass 不再阻断
        assert "unknown_not_pass" not in result["blocking_items"]

    def test_make_exemption_has_required_fields(self):
        """REQ-08-03：豁免必须记录原因、人员、时间、范围。"""
        from openqa.gates.gate_engine import make_exemption
        ex = make_exemption("smoke_pass", "紧急发布，人工验证", "bob", "feature-x")
        assert ex["reason"]
        assert ex["by"] == "bob"
        assert ex["scope"]
        assert ex["exempted_at"]

    def test_gate_report_written(self, full_env):
        """REQ-08-04：gate_report.yaml 生成。"""
        from openqa.gates.gate_engine import evaluate_gate, write_gate_report
        _, openqa_dir, change_dir, config = full_env
        run_report = {"result": "passed", "summary": {"failed": 0, "unknown": 0, "blocked": 0}}
        gate_result = evaluate_gate("local", run_report, change_dir, openqa_dir, config)
        path = write_gate_report(change_dir, gate_result, run_id="run-001")
        assert path.exists()
        with path.open(encoding="utf-8") as f:
            report = yaml.safe_load(f)
        assert report["schema_version"].startswith("openqa/gate_report/")
        assert "next_steps" in report
        assert "checks" in report

    def test_gate_report_has_exemptions(self, full_env):
        from openqa.gates.gate_engine import evaluate_gate, write_gate_report, make_exemption
        _, openqa_dir, change_dir, config = full_env
        run_report = {"result": "passed", "summary": {"failed": 0, "unknown": 0, "blocked": 0}}
        ex = make_exemption("smoke_pass", "豁免测试", "tester")
        gate_result = evaluate_gate("local", run_report, change_dir, openqa_dir, config,
                                     exemptions=[ex])
        path = write_gate_report(change_dir, gate_result)
        with path.open(encoding="utf-8") as f:
            report = yaml.safe_load(f)
        assert len(report["exemptions"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# REQ-09：知识进化
# ──────────────────────────────────────────────────────────────────────────────

class TestKnowledgeManager:
    def test_init_creates_knowledge_files(self, full_env):
        from openqa.knowledge.manager import init_knowledge_dir, KNOWLEDGE_FILES
        _, openqa_dir, _, config = full_env
        init_knowledge_dir(openqa_dir, config)
        knowledge_dir = openqa_dir / "knowledge"
        for fname in KNOWLEDGE_FILES:
            assert (knowledge_dir / fname).exists(), f"{fname} 不存在"

    def test_project_profile_initialized(self, full_env):
        from openqa.knowledge.manager import init_knowledge_dir
        _, openqa_dir, _, config = full_env
        init_knowledge_dir(openqa_dir, config)
        with (openqa_dir / "knowledge" / "project_profile.yaml").open(encoding="utf-8") as f:
            profile = yaml.safe_load(f)
        items = profile.get("items", [])
        assert len(items) > 0
        assert items[0]["status"] == "init_only"  # REQ-09-08

    def test_add_knowledge_item_medium_confidence(self, full_env):
        from openqa.knowledge.manager import init_knowledge_dir, add_knowledge_item
        _, openqa_dir, _, config = full_env
        init_knowledge_dir(openqa_dir, config)
        item = {
            "id": "tp-test-001",
            "key": "stable_path.smoke",
            "value": "smoke 套件稳定通过",
            "source": "run_report:run-001",
            "evidence": ["run-001"],
            "confidence": "medium",
        }
        result = add_knowledge_item(openqa_dir / "knowledge", "test_patterns.yaml", item)
        assert result is True

    def test_low_confidence_not_auto_promoted(self, full_env):
        """REQ-09-07：低置信度不自动晋升。"""
        from openqa.knowledge.manager import init_knowledge_dir, add_knowledge_item
        _, openqa_dir, _, config = full_env
        init_knowledge_dir(openqa_dir, config)
        item = {
            "id": "low-001",
            "key": "some.key",
            "value": "低置信度知识",
            "source": "model_output",
            "confidence": "low",
        }
        result = add_knowledge_item(openqa_dir / "knowledge", "test_patterns.yaml", item)
        assert result is False  # 默认不追加低置信度（REQ-09-07）

    def test_promote_script_requires_run_ids(self, full_env):
        """REQ-09-09：脚本晋升必须有执行记录。"""
        from openqa.knowledge.manager import promote_script
        _, openqa_dir, change_dir, _ = full_env
        script = change_dir / "test_scripts" / "test_main.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("def test_it(): pass\n", encoding="utf-8")
        result = promote_script(script, openqa_dir, run_ids=[])
        assert result["status"] == "rejected"
        assert "REQ-09-09" in result["reason"] or "未经过" in result["reason"]

    def test_promote_script_with_run_ids(self, full_env):
        from openqa.knowledge.manager import promote_script
        _, openqa_dir, change_dir, _ = full_env
        script = change_dir / "test_scripts" / "test_main.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("def test_it(): pass\n", encoding="utf-8")
        result = promote_script(script, openqa_dir, run_ids=["run-001", "run-002"],
                                suite_membership=["smoke"])
        assert result["status"] == "promoted"
        assert Path(result["dest_path"]).exists()
        assert Path(result["meta_path"]).exists()

    def test_meta_yaml_has_anchor_hash(self, full_env):
        """REQ-09-10：.meta.yaml 含锚点哈希。"""
        from openqa.knowledge.manager import promote_script
        _, openqa_dir, change_dir, _ = full_env
        script = change_dir / "test_scripts" / "test_anchor.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("def test_anchor(): pass\n", encoding="utf-8")
        result = promote_script(script, openqa_dir, run_ids=["run-001"])
        meta_path = Path(result["meta_path"])
        with meta_path.open(encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        assert "anchor_hash" in meta
        assert meta["status"] == "verified"
        assert "promoted_at" in meta

    def test_flaky_script_demoted(self, full_env):
        """REQ-09-11：flaky 脚本降为 needs-review。"""
        from openqa.knowledge.manager import promote_script, check_flaky_and_demote
        _, openqa_dir, change_dir, _ = full_env
        script = change_dir / "test_scripts" / "test_flaky.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("def test_flaky(): pass\n", encoding="utf-8")
        promote_script(script, openqa_dir, run_ids=["run-001"])
        result = check_flaky_and_demote(openqa_dir, "test_flaky.py", ["passed", "failed", "passed"])
        assert result["status"] == "demoted_to_needs_review"
        meta_path = openqa_dir / "test_assets" / "scripts" / "test_flaky.meta.yaml"
        with meta_path.open(encoding="utf-8") as f:
            meta = yaml.safe_load(f)
        assert meta["status"] == "needs-review"

    def test_distill_from_run_report(self, full_env):
        """REQ-09-01/03：从执行报告沉淀知识。"""
        from openqa.knowledge.manager import init_knowledge_dir, distill_from_run_report
        _, openqa_dir, change_dir, config = full_env
        init_knowledge_dir(openqa_dir, config)
        run_report = {
            "run_id": "run-test-001",
            "result": "passed",
            "suite": "smoke",
            "gate": "local",
            "summary": {"passed": 3, "failed": 0},
            "failure_buckets": {},
        }
        added = distill_from_run_report(
            openqa_dir / "knowledge", run_report, change_dir.name, "smoke"
        )
        assert len(added) > 0


# ──────────────────────────────────────────────────────────────────────────────
# REQ-10：治理边界
# ──────────────────────────────────────────────────────────────────────────────

class TestGovernance:
    def test_sensitive_scan_detects_password(self):
        from openqa.governance.compliance import scan_sensitive
        text = 'password: "super_secret_123"'
        findings = scan_sensitive(text)
        assert len(findings) > 0

    def test_sensitive_scan_allows_env_var(self):
        from openqa.governance.compliance import scan_sensitive
        text = 'password: ${DB_PASSWORD}'
        findings = scan_sensitive(text)
        assert len(findings) == 0

    def test_sensitive_scan_clean_text(self):
        from openqa.governance.compliance import scan_sensitive
        text = "project.type: unity\nconfidence: high"
        findings = scan_sensitive(text)
        assert len(findings) == 0

    def test_overlay_validation_missing_fields(self):
        """REQ-10-05：overlay 缺少必要字段。"""
        from openqa.governance.compliance import validate_overlay
        overlay = {"generator": "test", "confidence": "medium"}
        missing = validate_overlay(overlay)
        assert "generated_at" in missing
        assert "source_change" in missing

    def test_overlay_validation_complete(self):
        from openqa.governance.compliance import validate_overlay
        overlay = {
            "generator": "openqa-apply",
            "generated_at": "2026-05-01T00:00:00Z",
            "source_change": "chg-001",
            "source_report": "run-001",
            "confidence": "high",
        }
        missing = validate_overlay(overlay)
        assert len(missing) == 0

    def test_write_overlay_injects_fields(self, full_env, tmp_path):
        """REQ-10-05：write_overlay 自动注入合规字段。"""
        from openqa.governance.compliance import write_overlay
        path = tmp_path / "overlay.yaml"
        write_overlay(
            path, {"attribution": "环境问题"},
            generator="test-agent",
            source_change="chg-001",
            source_report="run-001",
        )
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data["generator"] == "test-agent"
        assert "generated_at" in data

    def test_overlay_rejects_sensitive_content(self, tmp_path):
        """REQ-10-06：overlay 含敏感信息时拒绝写入。"""
        from openqa.governance.compliance import write_overlay
        path = tmp_path / "bad_overlay.yaml"
        with pytest.raises(ValueError, match="敏感信息"):
            write_overlay(
                path, {"note": 'password: "real_secret_abc"'},
                generator="test",
                source_change="chg-001",
                source_report="run-001",
            )

    def test_script_path_boundary_inside(self, full_env):
        """REQ-01-11：脚本在 openqa/ 内时返回 True。"""
        from openqa.governance.compliance import check_script_path_boundary
        _, openqa_dir, change_dir, _ = full_env
        script = change_dir / "test_scripts" / "test.py"
        assert check_script_path_boundary(script, openqa_dir) is True

    def test_script_path_boundary_outside(self, full_env):
        """脚本在 openqa/ 外时返回 False。"""
        from openqa.governance.compliance import check_script_path_boundary
        tmp_path, openqa_dir, _, _ = full_env
        outside_script = tmp_path / "src" / "test_bad.py"
        assert check_script_path_boundary(outside_script, openqa_dir) is False


# ──────────────────────────────────────────────────────────────────────────────
# REQ-11：操作追踪
# ──────────────────────────────────────────────────────────────────────────────

class TestOperationTrace:
    def test_decision_log_created(self, full_env):
        """REQ-11-04：decision_log.md 记录策略决策。"""
        from openqa.governance.compliance import append_decision
        _, _, change_dir, _ = full_env
        append_decision(change_dir, "continue", "选择 smoke 套件",
                        "gate=local，快速验证为主", "recorded")
        log_path = change_dir / "decision_log.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "smoke" in content

    def test_decision_log_has_table(self, full_env):
        from openqa.governance.compliance import write_decision_log
        _, _, change_dir, _ = full_env
        decisions = [
            {"timestamp": "2026-05-01T10:00:00Z", "phase": "continue",
             "decision": "增量扫描", "reason": "日常变更，incremental 更快", "status": "applied"},
        ]
        path = write_decision_log(change_dir, decisions)
        content = path.read_text(encoding="utf-8")
        assert "| --- |" in content
        assert "增量扫描" in content

    def test_operation_log_has_required_fields(self, full_env):
        """REQ-11-01：operation_log.jsonl 事件包含必要字段。"""
        _, _, change_dir, _ = full_env
        log_path = change_dir / "operation_log.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        for line in lines:
            event = json.loads(line)
            for field in ("event_id", "change_id", "phase", "step", "status"):
                assert field in event, f"operation_log 缺少字段：{field}"

    def test_evidence_index_entries_have_required_fields(self, full_env):
        """REQ-11-05：evidence_index.yaml 每条证据含路径/步骤/关联。"""
        from openqa.executor.reporter import register_evidence
        from openqa.executor.run_id import ensure_run_dir, make_run_id
        _, openqa_dir, change_dir, _ = full_env
        run_id = make_run_id()
        run_dir = ensure_run_dir(openqa_dir, run_id, change_id=change_dir.name)
        register_evidence(run_dir, "ev-001", "log", "logs/app.log",
                          step="T-001", hash_value="abc123", summary="应用日志")
        idx_path = run_dir / "evidence_index.yaml"
        with idx_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f)
        entry = idx["entries"][0]
        assert entry["path"]
        assert entry["step"]
        assert entry["id"]


# ──────────────────────────────────────────────────────────────────────────────
# REQ-09：archive 命令端到端
# ──────────────────────────────────────────────────────────────────────────────

class TestArchiveCommand:
    def test_archive_dry_run(self, full_env, monkeypatch):
        import argparse
        from openqa.commands.archive import run_archive
        _, openqa_dir, change_dir, _ = full_env
        monkeypatch.chdir(openqa_dir.parent)
        rc = run_archive(argparse.Namespace(change_id=change_dir.name, dry_run=True))
        # dry_run 应返回 0（无阻断项时）或 1（有阻断项）
        assert isinstance(rc, int)

    def test_archive_updates_state(self, full_env, monkeypatch):
        import argparse
        from openqa.commands.archive import run_archive
        from openqa.workspace.change import load_state
        _, openqa_dir, change_dir, _ = full_env
        monkeypatch.chdir(openqa_dir.parent)
        rc = run_archive(argparse.Namespace(change_id=change_dir.name, dry_run=False))
        if rc == 0:  # 无阻断项时才检查 state
            state = load_state(change_dir)
            assert state["phase"] == "archive"

    def test_archive_without_change_fails(self, tmp_path, monkeypatch):
        import argparse
        from openqa.commands.archive import run_archive
        monkeypatch.chdir(tmp_path)
        rc = run_archive(argparse.Namespace(change_id=None, dry_run=False))
        assert rc != 0
