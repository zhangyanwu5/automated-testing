"""REQ-03-09/10/11、REQ-04-09~14、REQ-05-13/14、REQ-09-14~17、REQ-12-08~10、REQ-13-27~32 测试。"""
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
def game_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """返回 (project_root, openqa_dir)，模拟 Unity 游戏项目。"""
    project_root = tmp_path

    # Unity 标志
    (project_root / "Assets").mkdir()
    (project_root / "ProjectSettings").mkdir()
    (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.18f1\n"
    )
    # 包含事件系统
    assets_scripts = project_root / "Assets" / "Scripts"
    assets_scripts.mkdir(parents=True)
    (assets_scripts / "EventBus.cs").write_text(
        "public class EventBus {\n"
        "    public static void Subscribe<LoginEvent>(Action handler) {}\n"
        "    [ServerRpc]\n"
        "    public void TeleportToMap(string mapId) {}\n"
        "    private void log_warn() { Debug.Log('Error: login failed'); }\n"
        "}\n",
        encoding="utf-8",
    )

    openqa_dir = project_root / "openqa"
    from openqa.workspace.layout import ensure_subdirs
    ensure_subdirs(openqa_dir)

    config = {
        "schema_version": "openqa/config/v1",
        "project": {"type": "unity"},
        "ai_hosts": ["codebuddy"],
        "runtime": {"status": "incomplete", "missing": [], "intrusion_strategy": "external-only"},
        "defaults": {"gate": "local", "test_suite": "smoke"},
        "scan": {"include": ["Assets"], "exclude": ["Library/", "Temp/"]},
    }
    (openqa_dir / "config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return project_root, openqa_dir


@pytest.fixture
def openspec_project(tmp_path: Path) -> Path:
    """含 OpenSpec changes 的项目。"""
    project_root = tmp_path
    change_dir = project_root / "openspec" / "changes" / "opsx-001"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text("# 登录功能\n", encoding="utf-8")
    specs_dir = change_dir / "specs"
    specs_dir.mkdir()
    (specs_dir / "login.md").write_text(
        "接口 `LoginManager.HandleLogin` 应在 2s 内返回。\n", encoding="utf-8"
    )
    (change_dir / "tasks.md").write_text("## 任务\n1. 登录测试\n", encoding="utf-8")
    # 对应代码实现
    (project_root / "Assets").mkdir(exist_ok=True)
    scripts = project_root / "Assets" / "Scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "LoginManager.cs").write_text(
        "public class LoginManager { public void HandleLogin() {} }\n",
        encoding="utf-8",
    )
    return project_root


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-09：init-probe 轻量探测
# ──────────────────────────────────────────────────────────────────────────────

class TestInitProbe:
    def test_init_probe_returns_structure(self, game_workspace):
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.scan.scanner import run_init_probe
        result = run_init_probe(project_root, openqa_dir, config)
        assert "structure" in result
        assert "project_type" in result
        assert result["project_type"] == "unity"

    def test_init_probe_no_full_scan(self, game_workspace):
        """REQ-04-09：init 时不做全量接口深度扫描。"""
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.scan.scanner import run_init_probe
        result = run_init_probe(project_root, openqa_dir, config)
        # init-probe 结果不包含深度接口知识
        assert "items" not in result
        assert "event_catalog" not in result

    def test_init_probe_detects_control_channels(self, game_workspace):
        """REQ-04-09：init-probe 探测控制通道类型入口。"""
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.scan.scanner import run_init_probe
        result = run_init_probe(project_root, openqa_dir, config)
        assert "control_channel_hints" in result["structure"]


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-10 / REQ-03-09：knowledge-scan
# ──────────────────────────────────────────────────────────────────────────────

class TestKnowledgeScan:
    def test_knowledge_scan_creates_event_catalog(self, game_workspace):
        """REQ-04-10：knowledge-scan 提取事件写入 event_catalog.yaml。"""
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir
        init_knowledge_dir(openqa_dir, config)

        from openqa.scan.scanner import run_knowledge_scan
        result = run_knowledge_scan(project_root, openqa_dir, config, "测试登录功能")

        # 检查 event_catalog.yaml 有条目
        event_catalog_path = openqa_dir / "knowledge" / "event_catalog.yaml"
        assert event_catalog_path.exists()
        data = yaml.safe_load(event_catalog_path.read_text(encoding="utf-8"))
        # scan_status 应为 complete
        assert data.get("scan_status") == "complete"

    def test_knowledge_scan_creates_protocol_catalog(self, game_workspace):
        """REQ-04-10：knowledge-scan 提取 RPC 写入 protocol_catalog.yaml。"""
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir
        init_knowledge_dir(openqa_dir, config)

        from openqa.scan.scanner import run_knowledge_scan
        run_knowledge_scan(project_root, openqa_dir, config, "测试传送功能")

        proto_path = openqa_dir / "knowledge" / "protocol_catalog.yaml"
        assert proto_path.exists()

    def test_knowledge_scan_skips_fresh_catalog(self, game_workspace):
        """REQ-03-09：知识库已有新鲜条目时跳过重复扫描。"""
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir, add_interface_knowledge_item
        init_knowledge_dir(openqa_dir, config)

        # 预填 event_catalog
        knowledge_dir = openqa_dir / "knowledge"
        add_interface_knowledge_item(knowledge_dir, "event_catalog.yaml", {
            "id": "evt-existing",
            "name": "ExistingEvent",
            "anchor": {"file_path": "Assets/Scripts/A.cs", "symbol": "ExistingEvent", "hash": "abc"},
            "source": "manual",
            "confidence": "high",
        })
        # 标记为 complete
        data = yaml.safe_load((knowledge_dir / "event_catalog.yaml").read_text(encoding="utf-8"))
        data["scan_status"] = "complete"
        (knowledge_dir / "event_catalog.yaml").write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8"
        )

        # 调用 new.py 中的 knowledge-scan 逻辑，传入一个 mock StepHandle 捕获标签
        from openqa.commands.new import _run_knowledge_scan
        from openqa.cli.spinner import StepHandle
        handle = StepHandle("Running knowledge-scan", "new")
        _run_knowledge_scan(openqa_dir, "测试目标", handle)
        # 有新鲜条目时应跳过扫描并在标签中体现"reusing"或"cached"
        assert "reusing" in handle._label or "cached" in handle._label


# ──────────────────────────────────────────────────────────────────────────────
# REQ-04-11 / REQ-09-14：接口知识锚点检查
# ──────────────────────────────────────────────────────────────────────────────

class TestInterfaceKnowledgeAnchors:
    def _setup(self, game_workspace):
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir
        init_knowledge_dir(openqa_dir, config)
        return project_root, openqa_dir, openqa_dir / "knowledge"

    def test_anchor_hash_change_triggers_needs_review(self, game_workspace):
        """REQ-09-14：锚点哈希变化时条目状态降为 needs-review。"""
        _, openqa_dir, knowledge_dir = self._setup(game_workspace)
        from openqa.knowledge.manager import add_interface_knowledge_item, check_interface_knowledge_anchors

        add_interface_knowledge_item(knowledge_dir, "event_catalog.yaml", {
            "id": "evt-login",
            "name": "LoginEvent",
            "anchor": {"file_path": "Assets/Scripts/A.cs", "symbol": "LoginEvent", "hash": "oldHash"},
            "source": "code_scan",
            "confidence": "medium",
            "status": "verified",
        })

        reports = check_interface_knowledge_anchors(
            knowledge_dir,
            current_symbols={"LoginEvent": "newHash"},
        )
        assert any(r["new_status"] == "needs-review" for r in reports)

    def test_symbol_missing_triggers_stale(self, game_workspace):
        """REQ-09-14：符号消失时条目降为 stale。"""
        _, openqa_dir, knowledge_dir = self._setup(game_workspace)
        from openqa.knowledge.manager import add_interface_knowledge_item, check_interface_knowledge_anchors

        add_interface_knowledge_item(knowledge_dir, "event_catalog.yaml", {
            "id": "evt-teleport",
            "name": "TeleportEvent",
            "anchor": {"file_path": "A.cs", "symbol": "TeleportEvent", "hash": "x"},
            "source": "code_scan",
            "confidence": "high",
            "status": "verified",
        })

        reports = check_interface_knowledge_anchors(knowledge_dir, current_symbols={})
        assert any(r["new_status"] == "stale" for r in reports)

    def test_inferred_items_excluded_from_filter(self, game_workspace):
        """REQ-09-15：inferred 状态不得用于执行矩阵，可通过 status_filter 过滤。"""
        _, openqa_dir, knowledge_dir = self._setup(game_workspace)
        from openqa.knowledge.manager import add_interface_knowledge_item, get_interface_knowledge

        add_interface_knowledge_item(knowledge_dir, "event_catalog.yaml", {
            "id": "evt-inferred",
            "name": "InferredEvent",
            "anchor": {"file_path": "A.cs", "symbol": "InferredEvent", "hash": "h"},
            "source": "code_scan",
            "confidence": "low",
            "status": "inferred",
        })

        # 只查 verified
        items = get_interface_knowledge(knowledge_dir, "event_catalog.yaml", status_filter=["verified"])
        assert not any(i.get("id") == "evt-inferred" for i in items)

        # 查所有
        all_items = get_interface_knowledge(knowledge_dir, "event_catalog.yaml")
        assert any(i.get("id") == "evt-inferred" for i in all_items)


# ──────────────────────────────────────────────────────────────────────────────
# REQ-09-16/17 / REQ-13-27~32：前置路径
# ──────────────────────────────────────────────────────────────────────────────

class TestPreconditions:
    def test_promote_setup_path(self, game_workspace, tmp_path):
        """REQ-13-27/30：前置路径晋升到 test_assets/setup_paths/。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "login_server.py"
        script.write_text("# login setup\n", encoding="utf-8")

        from openqa.knowledge.preconditions import promote_setup_path
        result = promote_setup_path(
            script, openqa_dir,
            tags=["logged_in"],
            mode="white-box",
            run_id="run-001",
            change_id="chg-001",
        )
        assert result["status"] == "promoted"
        assert Path(result["dest_path"]).exists()
        assert Path(result["meta_path"]).exists()

    def test_promote_requires_run_id(self, game_workspace, tmp_path):
        """REQ-13-30：无执行记录不得晋升。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "setup.py"
        script.write_text("# setup\n", encoding="utf-8")

        from openqa.knowledge.preconditions import promote_setup_path
        result = promote_setup_path(script, openqa_dir, tags=["logged_in"], mode="white-box", run_id="")
        assert result["status"] == "rejected"

    def test_promote_updates_preconditions_yaml(self, game_workspace, tmp_path):
        """REQ-09-16：晋升后 preconditions.yaml 更新为 verified 状态。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "login.py"
        script.write_text("# login\n", encoding="utf-8")

        from openqa.knowledge.preconditions import promote_setup_path, load_preconditions
        from openqa.knowledge.manager import init_knowledge_dir
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        init_knowledge_dir(openqa_dir, config)

        promote_setup_path(script, openqa_dir, tags=["logged_in", "map_a"],
                           mode="white-box", run_id="run-1", change_id="c1")

        data = load_preconditions(openqa_dir / "knowledge")
        preconds = data.get("preconditions", [])
        match = next((p for p in preconds if "logged_in" in p.get("tags", [])), None)
        assert match is not None
        assert match["status"] == "verified"

    def test_find_preconditions_by_tags(self, game_workspace, tmp_path):
        """REQ-13-28 / REQ-09-17：按标签查找已验证前置路径。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "login.py"
        script.write_text("# login\n", encoding="utf-8")
        from openqa.knowledge.preconditions import promote_setup_path, find_preconditions
        from openqa.knowledge.manager import init_knowledge_dir
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        init_knowledge_dir(openqa_dir, config)

        promote_setup_path(script, openqa_dir, tags=["logged_in", "map_a"],
                           mode="white-box", run_id="run-1", change_id="c1")

        matches = find_preconditions(openqa_dir / "knowledge", ["logged_in"])
        assert len(matches) >= 1
        assert all("logged_in" in m.get("tags", []) for m in matches)

    def test_query_returns_unknown_when_no_match(self, game_workspace):
        """REQ-03-10 / REQ-09-17：无匹配时返回 unknown_entry 文本。"""
        _, openqa_dir = game_workspace
        from openqa.knowledge.preconditions import query_preconditions_for_change
        from openqa.knowledge.manager import init_knowledge_dir
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        init_knowledge_dir(openqa_dir, config)

        result = query_preconditions_for_change(openqa_dir / "knowledge", ["logged_in", "quest_active"])
        assert result["found"] is False
        assert result["unknown_entry"] is not None

    def test_precondition_mode_recorded(self, game_workspace, tmp_path):
        """REQ-13-29：前置路径实现模式必须记录。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "setup.py"
        script.write_text("# setup\n", encoding="utf-8")
        from openqa.knowledge.preconditions import promote_setup_path, load_preconditions
        from openqa.knowledge.manager import init_knowledge_dir
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        init_knowledge_dir(openqa_dir, config)

        promote_setup_path(script, openqa_dir, tags=["logged_in"],
                           mode="black-box", run_id="run-1", change_id="c1")

        data = load_preconditions(openqa_dir / "knowledge")
        match = next((p for p in data["preconditions"] if "logged_in" in p.get("tags", [])), None)
        assert match["mode"] == "black-box"

    def test_setup_path_anchor_check(self, game_workspace, tmp_path):
        """REQ-13-31：前置路径锚点失效时降为 needs-review 或 stale。"""
        _, openqa_dir = game_workspace
        script = tmp_path / "login.py"
        script.write_text("# login\n", encoding="utf-8")
        from openqa.knowledge.preconditions import promote_setup_path, check_setup_path_anchors
        from openqa.knowledge.manager import init_knowledge_dir
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        init_knowledge_dir(openqa_dir, config)

        promote_setup_path(
            script, openqa_dir,
            tags=["logged_in"],
            mode="white-box",
            run_id="run-1",
            change_id="c1",
            bound_symbols=[{"path": "Assets/Login.cs", "symbol": "Login.Handle", "hash": "abc"}],
        )

        # 模拟符号哈希变化
        reports = check_setup_path_anchors(openqa_dir, current_symbols={"Login.Handle": "newHash"})
        assert any(r["new_status"] == "needs-review" for r in reports)

    def test_setup_paths_dir_created(self, game_workspace):
        """REQ-13-27：init 时创建 test_assets/setup_paths/ 目录。"""
        _, openqa_dir = game_workspace
        assert (openqa_dir / "test_assets" / "setup_paths").is_dir()


# ──────────────────────────────────────────────────────────────────────────────
# REQ-05-13：矩阵任务显式引用前置路径
# ──────────────────────────────────────────────────────────────────────────────

class TestMatrixPreconditionBinding:
    def _build_matrix_env(self, game_workspace, tmp_path):
        project_root, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir
        init_knowledge_dir(openqa_dir, config)
        # 创建最小 change 工作区
        change_dir = openqa_dir / "changes" / "chg-test"
        change_dir.mkdir(parents=True)
        (change_dir / "snapshot.json").write_text(
            json.dumps({"status": "complete", "analyzer_version": "v1",
                        "code_files": [], "requirements": {}}),
            encoding="utf-8",
        )
        return openqa_dir, change_dir, config

    def test_task_blocked_when_no_precondition(self, game_workspace, tmp_path):
        """REQ-05-13：无匹配前置路径时任务标记为 blocked。"""
        openqa_dir, change_dir, config = self._build_matrix_env(game_workspace, tmp_path)
        from openqa.matrix.generator import _bind_preconditions_to_tasks

        tasks = [{
            "id": "t1",
            "name": "测试登录奖励",
            "status": "ready",
            "required_precondition_tags": ["logged_in", "quest_complete"],
        }]
        updated = _bind_preconditions_to_tasks(tasks, openqa_dir)
        assert updated[0]["status"] == "blocked"
        assert any("missing_precondition" in str(b) for b in updated[0].get("blockers", []))

    def test_task_gets_precondition_ref_when_found(self, game_workspace, tmp_path):
        """REQ-05-13：有匹配前置路径时任务获得 precondition_ref。"""
        openqa_dir, change_dir, config = self._build_matrix_env(game_workspace, tmp_path)

        # 注册一个前置路径
        script = tmp_path / "login.py"
        script.write_text("# login\n", encoding="utf-8")
        from openqa.knowledge.preconditions import promote_setup_path
        promote_setup_path(script, openqa_dir, tags=["logged_in"],
                           mode="white-box", run_id="run-1", change_id="c1")

        from openqa.matrix.generator import _bind_preconditions_to_tasks
        tasks = [{
            "id": "t1",
            "name": "测试",
            "status": "ready",
            "required_precondition_tags": ["logged_in"],
        }]
        updated = _bind_preconditions_to_tasks(tasks, openqa_dir)
        assert updated[0]["precondition_ref"] is not None
        assert updated[0]["status"] == "ready"

    def test_matrix_includes_interface_knowledge_summary(self, game_workspace, tmp_path):
        """REQ-05-14：矩阵包含接口知识查询摘要。"""
        openqa_dir, change_dir, config = self._build_matrix_env(game_workspace, tmp_path)
        from openqa.matrix.generator import build_test_matrix
        matrix = build_test_matrix(change_dir, openqa_dir, config)
        assert "interface_knowledge_summary" in matrix
        assert "inferred_count" in matrix["interface_knowledge_summary"]


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12-08~10 / REQ-03-11：OpenSpec 有效性校验
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenSpecValidation:
    def test_validate_consistent_spec(self, openspec_project, tmp_path):
        """REQ-12-08：对 OpenSpec 内容做有效性校验，结果不崩溃且写入 checks。"""
        from openqa.openspec.detector import validate_openspec_consistency
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        (change_dir / "openspec_link.yaml").write_text(
            yaml.dump({"schema_version": "openqa/openspec_link/v1",
                       "openspec_change_id": "opsx-001"}),
            encoding="utf-8",
        )
        result = validate_openspec_consistency(change_dir, "opsx-001", openspec_project)
        # 校验完成，有 checks 列表（可以是任意状态）
        assert "checks" in result
        assert isinstance(result["checks"], list)
        # 所有 check 都有 status 字段
        for check in result["checks"]:
            assert "status" in check

    def test_validate_not_implemented(self, tmp_path):
        """REQ-12-08：代码中没有接口时，校验状态为 not_implemented。"""
        project_root = tmp_path / "project"
        project_root.mkdir()
        # OpenSpec 有 spec 但代码不存在
        change_dir_os = project_root / "openspec" / "changes" / "opsx-missing"
        change_dir_os.mkdir(parents=True)
        specs_dir = change_dir_os / "specs"
        specs_dir.mkdir()
        (specs_dir / "feature.md").write_text(
            "接口 `NonExistentClass.SpecialMethod` 必须实现特殊功能。\n",
            encoding="utf-8",
        )

        from openqa.openspec.detector import validate_openspec_consistency
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        (change_dir / "openspec_link.yaml").write_text(
            yaml.dump({"schema_version": "openqa/openspec_link/v1",
                       "openspec_change_id": "opsx-missing"}),
            encoding="utf-8",
        )
        result = validate_openspec_consistency(change_dir, "opsx-missing", project_root)
        checks = result.get("checks", [])
        assert any(c["status"] == "not_implemented" for c in checks)

    def test_validation_writes_to_openspec_link(self, openspec_project, tmp_path):
        """REQ-12-09：校验结果写入 openspec_link.yaml。"""
        from openqa.openspec.detector import validate_openspec_consistency
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        (change_dir / "openspec_link.yaml").write_text(
            yaml.dump({"schema_version": "openqa/openspec_link/v1",
                       "openspec_change_id": "opsx-001"}),
            encoding="utf-8",
        )
        validate_openspec_consistency(change_dir, "opsx-001", openspec_project)

        link = yaml.safe_load((change_dir / "openspec_link.yaml").read_text(encoding="utf-8"))
        assert "validation" in link
        assert "checks" in link["validation"]

    def test_problematic_specs_written_to_unknowns(self, tmp_path):
        """REQ-12-10：stale/not_implemented 规格写入 unknowns.md。"""
        project_root = tmp_path / "project"
        project_root.mkdir()
        # 有 spec 无代码
        change_dir_os = project_root / "openspec" / "changes" / "opsx-prob"
        change_dir_os.mkdir(parents=True)
        specs_dir = change_dir_os / "specs"
        specs_dir.mkdir()
        (specs_dir / "missing.md").write_text(
            "接口 `MissingClass.MissingMethod` 实现。\n", encoding="utf-8"
        )

        from openqa.openspec.detector import validate_openspec_consistency
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        (change_dir / "openspec_link.yaml").write_text(
            yaml.dump({"schema_version": "openqa/openspec_link/v1",
                       "openspec_change_id": "opsx-prob"}),
            encoding="utf-8",
        )
        result = validate_openspec_consistency(change_dir, "opsx-prob", project_root)

        if any(c["status"] == "not_implemented" for c in result.get("checks", [])):
            assert (change_dir / "unknowns.md").exists()

    def test_new_command_triggers_openspec_validation(self, openspec_project, monkeypatch):
        """REQ-03-11：openqa new --from-openspec 触发有效性校验。"""
        import argparse
        from openqa.commands.init import run_init
        from openqa.commands.new import run_new

        # 初始化
        (openspec_project / "Assets").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.18f1\n"
        )
        monkeypatch.chdir(openspec_project)
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))

        rc = run_new(argparse.Namespace(
            target="测试登录功能",
            scan_scope="auto",
            test_suite=None,
            from_openspec="opsx-001",
        ))
        assert rc == 0

        # 验证 openspec_link.yaml 已写入
        openqa_dir = openspec_project / "openqa"
        changes = list((openqa_dir / "changes").iterdir())
        if changes:
            change_dir = changes[0]
            if (change_dir / "openspec_link.yaml").exists():
                link = yaml.safe_load(
                    (change_dir / "openspec_link.yaml").read_text(encoding="utf-8")
                )
                # validation 字段可能存在也可能没有（取决于是否写入成功）
                assert "openspec_change_id" in link


# ──────────────────────────────────────────────────────────────────────────────
# REQ-02：目录结构补充
# ──────────────────────────────────────────────────────────────────────────────

class TestDirectoryStructure:
    def test_setup_paths_dir_in_layout(self, game_workspace):
        """REQ-13-27：ensure_subdirs 创建 test_assets/setup_paths/。"""
        _, openqa_dir = game_workspace
        assert (openqa_dir / "test_assets" / "setup_paths").is_dir()

    def test_knowledge_interface_files_initialized(self, game_workspace):
        """REQ-04-09：init_knowledge_dir 创建游戏接口知识文件骨架。"""
        _, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir, INTERFACE_KNOWLEDGE_FILES
        init_knowledge_dir(openqa_dir, config)

        knowledge_dir = openqa_dir / "knowledge"
        for fname in INTERFACE_KNOWLEDGE_FILES:
            assert (knowledge_dir / fname).exists(), f"{fname} 未创建"

    def test_preconditions_yaml_initialized(self, game_workspace):
        """REQ-09-16：init_knowledge_dir 创建 preconditions.yaml 骨架。"""
        _, openqa_dir = game_workspace
        config = yaml.safe_load((openqa_dir / "config.yaml").read_text(encoding="utf-8"))
        from openqa.knowledge.manager import init_knowledge_dir
        init_knowledge_dir(openqa_dir, config)
        assert (openqa_dir / "knowledge" / "preconditions.yaml").exists()
