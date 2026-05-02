"""测试 REQ_03：Change 状态机。"""
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
def openguard_dir(tmp_path: Path) -> Path:
    """返回已初始化的 openguard/ 目录。"""
    import argparse
    from openguard.commands.init import run_init
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        run_init(argparse.Namespace(
            profile="backend", hosts=["codebuddy"],
            gate="local", yes=True, reconfigure=False,
        ))
    finally:
        os.chdir(old)
    return tmp_path / "openguard"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-03-01 / REQ-03-02：openguard new — change 工作区创建
# ──────────────────────────────────────────────────────────────────────────────

class TestChangeCreation:
    def test_change_dir_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        change_id, change_dir = create_change(openguard_dir, "验证新手引导奖励")
        assert change_dir.is_dir()

    def test_change_id_format(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        change_id, _ = create_change(openguard_dir, "test feature")
        assert change_id.startswith("chg-")

    def test_intent_md_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证登录流程")
        assert (change_dir / "intent.md").exists()

    def test_intent_md_has_front_matter(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证登录流程")
        content = (change_dir / "intent.md").read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "change_id" in content
        assert "target" in content

    def test_requirements_md_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证支付流程")
        assert (change_dir / "requirements.md").exists()

    def test_requirements_md_has_ears_template(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证支付流程")
        content = (change_dir / "requirements.md").read_text(encoding="utf-8")
        assert "WHEN" in content or "EARS" in content

    def test_state_yaml_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "新功能测试")
        assert (change_dir / "state.yaml").exists()

    def test_state_yaml_phase_is_new(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "新功能测试")
        with (change_dir / "state.yaml").open(encoding="utf-8") as f:
            state = yaml.safe_load(f)
        assert state["phase"] == "preparing"

    def test_state_yaml_next_step_is_continue(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "新功能测试")
        with (change_dir / "state.yaml").open(encoding="utf-8") as f:
            state = yaml.safe_load(f)
        assert "_advance" in state["next_cli"]

    def test_snapshot_json_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试新功能")
        assert (change_dir / "snapshot.json").exists()

    def test_snapshot_json_status_pending(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试新功能")
        data = json.loads((change_dir / "snapshot.json").read_text(encoding="utf-8"))
        assert data["status"] == "pending"

    def test_delta_json_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试新功能")
        assert (change_dir / "delta.json").exists()

    def test_artifact_index_yaml_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试新功能")
        assert (change_dir / "artifact_index.yaml").exists()

    def test_artifact_index_lists_all_required(self, openguard_dir: Path):
        from openguard.workspace.change import create_change, REQUIRED_ARTIFACTS
        _, change_dir = create_change(openguard_dir, "测试新功能")
        with (change_dir / "artifact_index.yaml").open(encoding="utf-8") as f:
            index = yaml.safe_load(f)
        listed = {a["name"] for a in index["artifacts"]}
        for req in REQUIRED_ARTIFACTS:
            assert req in listed, f"artifact_index 缺少 {req}"

    def test_unknowns_md_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        assert (change_dir / "unknowns.md").exists()

    def test_test_scripts_dir_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        assert (change_dir / "test_scripts").is_dir()

    def test_test_fixtures_dir_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        assert (change_dir / "test_fixtures").is_dir()

    def test_operation_log_created(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        assert (change_dir / "operation_log.jsonl").exists()

    def test_operation_log_has_valid_json_lines(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        lines = (change_dir / "operation_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        event = json.loads(lines[0])
        assert "event_id" in event
        assert "change_id" in event
        assert "phase" in event
        assert "status" in event

    def test_from_openspec_creates_link_yaml(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证功能", from_openspec="opsx-chg-001")
        assert (change_dir / "openspec_link.yaml").exists()

    def test_from_openspec_records_id_in_state(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "验证功能", from_openspec="opsx-chg-001")
        with (change_dir / "openspec_link.yaml").open(encoding="utf-8") as f:
            link = yaml.safe_load(f)
        assert link["openspec_change_id"] == "opsx-chg-001"

    def test_two_changes_get_different_ids(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        id1, _ = create_change(openguard_dir, "功能 A")
        id2, _ = create_change(openguard_dir, "功能 B")
        assert id1 != id2

    def test_change_id_slug_reflects_target(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        change_id, _ = create_change(openguard_dir, "login feature test")
        assert "login" in change_id or "feature" in change_id

    def test_same_target_creates_unique_id(self, openguard_dir: Path):
        """同一目标重复创建时不会冲突（REQ-03-01）。"""
        from openguard.workspace.change import create_change
        id1, _ = create_change(openguard_dir, "重复目标")
        id2, _ = create_change(openguard_dir, "重复目标")
        assert id1 != id2


# ──────────────────────────────────────────────────────────────────────────────
# REQ-03-02：change 记录目标、来源需求、当前状态
# ──────────────────────────────────────────────────────────────────────────────

class TestChangeRecordsInfo:
    def test_intent_records_target(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        target = "验证新手引导流程"
        _, change_dir = create_change(openguard_dir, target)
        content = (change_dir / "intent.md").read_text(encoding="utf-8")
        assert target in content

    def test_state_records_scan_scope(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试", scan_scope="full")
        with (change_dir / "state.yaml").open(encoding="utf-8") as f:
            state = yaml.safe_load(f)
        assert state["scan_scope"] == "full"

    def test_state_has_schema_version(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        with (change_dir / "state.yaml").open(encoding="utf-8") as f:
            state = yaml.safe_load(f)
        assert state["schema_version"].startswith("openguard/state/")

    def test_artifact_index_has_schema_version(self, openguard_dir: Path):
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, "测试")
        with (change_dir / "artifact_index.yaml").open(encoding="utf-8") as f:
            index = yaml.safe_load(f)
        assert index["schema_version"].startswith("openguard/artifact_index/")


# ──────────────────────────────────────────────────────────────────────────────
# REQ-03-03：openguard continue — 状态机推进
# ──────────────────────────────────────────────────────────────────────────────

class TestContinueStateMachine:
    def _new_change(self, openguard_dir: Path, target: str = "测试功能") -> Path:
        from openguard.workspace.change import create_change
        _, change_dir = create_change(openguard_dir, target)
        return change_dir

    def test_continue_identifies_missing_snapshot(self, openguard_dir: Path, monkeypatch, capsys):
        import argparse
        from openguard.commands.continue_ import run_continue
        change_dir = self._new_change(openguard_dir)
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc == 0
        out = capsys.readouterr().out
        # snapshot 处于 pending 状态，应提示扫描
        assert "snapshot" in out.lower() or "快照" in out

    def test_continue_updates_state_phase(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        from openguard.workspace.change import load_state
        change_dir = self._new_change(openguard_dir)
        monkeypatch.chdir(openguard_dir.parent)
        run_continue(argparse.Namespace(change_id=None))
        state = load_state(change_dir)
        assert state["phase"] == "preparing"

    def test_continue_appends_operation_log(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        change_dir = self._new_change(openguard_dir)
        monkeypatch.chdir(openguard_dir.parent)
        before = (change_dir / "operation_log.jsonl").read_text(encoding="utf-8").count("\n")
        run_continue(argparse.Namespace(change_id=None))
        after = (change_dir / "operation_log.jsonl").read_text(encoding="utf-8").count("\n")
        assert after > before

    def test_continue_ready_when_all_artifacts_present(self, openguard_dir: Path, monkeypatch):
        """所有必要产物就绪时，continue 应推进到 ready_for_apply 阶段。"""
        import argparse
        from openguard.commands.continue_ import run_continue
        from openguard.commands.advance import _STEPS
        from openguard.workspace.change import create_change, load_state, _write_json
        import json

        _, change_dir = create_change(openguard_dir, "完整功能")

        # 模拟所有产物就绪
        for artifact, _, _, _ in _STEPS:
            path = change_dir / artifact
            if artifact.endswith(".json"):
                data = {"status": "complete", "schema_version": "test"}
                path.write_text(json.dumps(data), encoding="utf-8")
            elif not path.exists():
                path.write_text(f"# {artifact}\n<!-- filled -->\n", encoding="utf-8")

        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc == 0
        state = load_state(change_dir)
        assert state["phase"] == "ready_for_apply"
        assert state.get("next_cli") is None  # wait_user 状态，不需要 CLI

    def test_continue_with_explicit_change_id(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        change_dir = self._new_change(openguard_dir, "指定 ID 测试")
        change_id = change_dir.name
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id=change_id))
        assert rc == 0

    def test_continue_fails_for_unknown_change_id(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id="nonexistent-change"))
        assert rc != 0

    def test_continue_without_active_change_fails(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc != 0


# ──────────────────────────────────────────────────────────────────────────────
# REQ-03-06：未解决 unknowns 不得静默跳过
# ──────────────────────────────────────────────────────────────────────────────

class TestUnknownsBlocking:
    def test_unknowns_with_data_rows_blocks_apply(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.continue_ import run_continue
        from openguard.commands.advance import _STEPS
        from openguard.workspace.change import create_change, load_state
        import json

        _, change_dir = create_change(openguard_dir, "含 unknowns 的功能")

        # 模拟所有产物就绪
        for artifact, _, _, _ in _STEPS:
            path = change_dir / artifact
            if artifact.endswith(".json"):
                path.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
            elif not path.exists():
                path.write_text(f"# {artifact}\n", encoding="utf-8")

        # 写入一条真实的 unknown 条目
        unknowns_content = (
            "# Unknowns\n\n"
            "| 编号 | 问题 | 影响阶段 | 状态 |\n"
            "| --- | --- | --- | --- |\n"
            "| U-001 | 登录账号配置未知 | apply | open |\n"
        )
        (change_dir / "unknowns.md").write_text(unknowns_content, encoding="utf-8")

        monkeypatch.chdir(openguard_dir.parent)
        rc = run_continue(argparse.Namespace(change_id=None))
        assert rc == 0
        state = load_state(change_dir)
        # 有 unknowns 时不应推进到 apply
        assert state["phase"] != "apply"
        assert "unresolved_unknowns" in state.get("blockers", [])


# ──────────────────────────────────────────────────────────────────────────────
# openguard new 命令端到端
# ──────────────────────────────────────────────────────────────────────────────

class TestNewCommand:
    def test_new_command_returns_zero(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_new(argparse.Namespace(
            target="验证新手引导",
            scan_scope="auto",
            test_suite=None,
            from_openspec=None,
        ))
        assert rc == 0

    def test_new_command_creates_change_dir(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        monkeypatch.chdir(openguard_dir.parent)
        run_new(argparse.Namespace(
            target="验证奖励发放",
            scan_scope="auto",
            test_suite=None,
            from_openspec=None,
        ))
        changes = list((openguard_dir / "changes").iterdir())
        assert len(changes) == 1

    def test_new_command_with_openspec(self, openguard_dir: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        monkeypatch.chdir(openguard_dir.parent)
        rc = run_new(argparse.Namespace(
            target="验证任务系统",
            scan_scope="full",
            test_suite="requirement-full",
            from_openspec="opsx-20260501-task-system",
        ))
        assert rc == 0
        changes_dir = openguard_dir / "changes"
        change_dirs = list(changes_dir.iterdir())
        assert len(change_dirs) == 1
        assert (change_dirs[0] / "openspec_link.yaml").exists()

    def test_new_command_without_init_fails(self, tmp_path: Path, monkeypatch):
        import argparse
        from openguard.commands.new import run_new
        monkeypatch.chdir(tmp_path)
        rc = run_new(argparse.Namespace(
            target="无工作区",
            scan_scope="auto",
            test_suite=None,
            from_openspec=None,
        ))
        assert rc != 0


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

class TestChangeHelpers:
    def test_list_active_changes(self, openguard_dir: Path):
        from openguard.workspace.change import create_change, list_active_changes
        create_change(openguard_dir, "功能 A")
        create_change(openguard_dir, "功能 B")
        active = list_active_changes(openguard_dir)
        assert len(active) == 2

    def test_latest_change_returns_last(self, openguard_dir: Path):
        from openguard.workspace.change import create_change, latest_change
        create_change(openguard_dir, "功能 A")
        _, last = create_change(openguard_dir, "功能 B")
        assert latest_change(openguard_dir) == last

    def test_latest_change_none_when_empty(self, openguard_dir: Path):
        from openguard.workspace.change import latest_change
        result = latest_change(openguard_dir)
        assert result is None

    def test_update_artifact_index(self, openguard_dir: Path):
        from openguard.workspace.change import create_change, update_artifact_index
        _, change_dir = create_change(openguard_dir, "测试")
        update_artifact_index(change_dir, "snapshot.json", status="generated")
        with (change_dir / "artifact_index.yaml").open(encoding="utf-8") as f:
            index = yaml.safe_load(f)
        snap = next(a for a in index["artifacts"] if a["name"] == "snapshot.json")
        assert snap["status"] == "generated"

    def test_make_change_id_format(self):
        from openguard.workspace.change import make_change_id
        cid = make_change_id("验证登录流程")
        assert cid.startswith("chg-")
        parts = cid.split("-")
        assert len(parts) >= 3
        assert len(parts[1]) == 8  # YYYYMMDD
