"""测试 REQ_06：代码 Review 计划、SARIF findings、报告生成。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def change_with_impact(tmp_path: Path):
    """已有 impact_graph.json 的 change。"""
    import argparse
    from openguard.commands.init import run_init
    from openguard.workspace.change import create_change
    from openguard.scan.scanner import execute_scan
    from openguard.scan.impact import run_impact_analysis
    from openguard.setup.config_writer import load_config

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login(u, p): pass\n", encoding="utf-8")
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
    config = load_config(openguard_dir)
    _, change_dir = create_change(openguard_dir, "验证认证逻辑")
    execute_scan(change_dir, openguard_dir, config, "full")
    run_impact_analysis(change_dir, openguard_dir, config)
    return tmp_path, openguard_dir, change_dir, config


class TestReviewPlan:
    def test_review_plan_created(self, change_with_impact):
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config)
        assert path.exists()

    def test_review_plan_has_front_matter(self, change_with_impact):
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config)
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "review_level" in content

    def test_review_plan_has_check_items(self, change_with_impact):
        """REQ-06-03：必须包含 8 个检查维度。"""
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config)
        content = path.read_text(encoding="utf-8")
        for dim in ("需求一致性", "边界条件", "异常处理", "安全"):
            assert dim in content

    def test_review_plan_has_blocking_policy(self, change_with_impact):
        """REQ-06-05：必须说明阻断策略。"""
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config)
        content = path.read_text(encoding="utf-8")
        assert "blocking" in content.lower() or "阻断" in content

    def test_review_plan_no_code_modification_allowed(self, change_with_impact):
        """REQ-06-07：不得直接修改产品代码。"""
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config)
        content = path.read_text(encoding="utf-8")
        assert "不直接修改产品代码" in content or "REQ-06-07" in content

    def test_review_level_off_returns_empty_scope(self, change_with_impact):
        from openguard.review.planner import generate_review_plan
        _, openguard_dir, change_dir, config = change_with_impact
        path = generate_review_plan(change_dir, openguard_dir, config, review_level="off")
        content = path.read_text(encoding="utf-8")
        # YAML 可能序列化为 'off' 或 off（带引号），检查两种形式
        assert "review_level: off" in content or "review_level: 'off'" in content


class TestSarifFindings:
    def test_sarif_skeleton_created(self, change_with_impact):
        """REQ-06-02：apply 时生成 review_findings.sarif.json。"""
        from openguard.review.findings import build_sarif_skeleton, write_sarif
        _, openguard_dir, change_dir, config = change_with_impact
        sarif = build_sarif_skeleton(change_dir, config)
        path = write_sarif(change_dir, sarif)
        assert path.exists()

    def test_sarif_is_valid_schema(self, change_with_impact):
        from openguard.review.findings import build_sarif_skeleton
        _, openguard_dir, change_dir, config = change_with_impact
        sarif = build_sarif_skeleton(change_dir, config)
        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert "runs" in sarif

    def test_sarif_has_rules(self, change_with_impact):
        """SARIF 必须包含 8 条规则（REQ-06-04）。"""
        from openguard.review.findings import build_sarif_skeleton
        _, openguard_dir, change_dir, config = change_with_impact
        sarif = build_sarif_skeleton(change_dir, config)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 8

    def test_make_finding_has_required_fields(self):
        """REQ-06-04：finding 必须包含所有必要字段。"""
        from openguard.review.findings import make_finding
        f = make_finding(
            "OPG006", "error", "src/auth.py", 10,
            "密码未加密存储",
            evidence="auth.py:10 明文存储密码",
            suggestion="使用 bcrypt 或 argon2",
            ears_requirement_id="REQ-001-AC-001",
            is_blocking=True,
        )
        assert f["ruleId"] == "OPG006"
        assert f["level"] == "error"
        assert f["properties"]["is_blocking"] is True
        assert f["properties"]["ears_requirement_id"] == "REQ-001-AC-001"
        assert "artifactLocation" in f["locations"][0]["physicalLocation"]

    def test_blocking_finding_detected(self, change_with_impact):
        """REQ-06-05：has_blocking_findings 正确检测 blocking。"""
        from openguard.review.findings import build_sarif_skeleton, write_sarif, make_finding, has_blocking_findings
        _, openguard_dir, change_dir, config = change_with_impact

        blocking = make_finding("OPG006", "error", "src/auth.py", 1,
                                "安全问题", is_blocking=True)
        sarif = build_sarif_skeleton(change_dir, config, findings=[blocking])
        write_sarif(change_dir, sarif)

        has_blocking, count = has_blocking_findings(change_dir)
        assert has_blocking is True
        assert count == 1

    def test_no_blocking_finding(self, change_with_impact):
        from openguard.review.findings import build_sarif_skeleton, write_sarif, has_blocking_findings
        _, openguard_dir, change_dir, config = change_with_impact
        sarif = build_sarif_skeleton(change_dir, config, findings=[])
        write_sarif(change_dir, sarif)
        has_blocking, count = has_blocking_findings(change_dir)
        assert has_blocking is False
        assert count == 0


class TestReviewReport:
    def test_review_report_created(self, change_with_impact):
        from openguard.review.findings import run_review_generation
        _, openguard_dir, change_dir, config = change_with_impact
        sarif_path, report_path = run_review_generation(change_dir, openguard_dir, config)
        assert report_path.exists()

    def test_review_report_mentions_no_code_change(self, change_with_impact):
        """REQ-06-07：报告必须说明不修改产品代码。"""
        from openguard.review.findings import run_review_generation
        _, openguard_dir, change_dir, config = change_with_impact
        _, report_path = run_review_generation(change_dir, openguard_dir, config)
        content = report_path.read_text(encoding="utf-8")
        assert "REQ-06-07" in content or "不直接修改" in content

    def test_review_report_blocking_summary(self, change_with_impact):
        from openguard.review.findings import run_review_generation, make_finding
        _, openguard_dir, change_dir, config = change_with_impact
        findings = [make_finding("OPG006", "error", "src/auth.py", 1, "安全", is_blocking=True)]
        _, report_path = run_review_generation(change_dir, openguard_dir, config, findings)
        content = report_path.read_text(encoding="utf-8")
        assert "blocking" in content.lower() or "阻断" in content
