"""REQ-12 + REQ-13 测试：测试资产生命周期 & OpenSpec 联动。"""
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
def qa_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """返回 (project_root, openguard_dir)，已初始化好目录结构。"""
    project_root = tmp_path
    # 创建最基本的 Unity 标志
    (project_root / "Assets").mkdir()
    (project_root / "ProjectSettings").mkdir()
    (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2022.3.18f1\n"
    )

    openguard_dir = project_root / "openguard"
    from openguard.workspace.layout import ensure_subdirs
    ensure_subdirs(openguard_dir)

    # 写入最小 config.yaml
    config = {
        "schema_version": "openguard/config/v1",
        "project": {"type": "unity"},
        "runtime": {"status": "incomplete", "missing": ["unity_path"],
                    "intrusion_strategy": "external-only"},
        "defaults": {"gate": "local", "test_suite": "smoke"},
    }
    (openguard_dir / "config.yaml").write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return project_root, openguard_dir


@pytest.fixture
def openspec_project(tmp_path: Path) -> Path:
    """返回含 OpenSpec changes 的项目根目录。"""
    project_root = tmp_path
    changes_dir = project_root / "openspec" / "changes" / "opsx-001"
    changes_dir.mkdir(parents=True)
    (changes_dir / "proposal.md").write_text("# 登录功能改进\n目标：提升登录稳定性。\n", encoding="utf-8")
    specs_dir = changes_dir / "specs"
    specs_dir.mkdir()
    (specs_dir / "login.md").write_text("WHEN 用户输入正确凭据 THE 系统 SHALL 在 2s 内完成登录\n", encoding="utf-8")
    (changes_dir / "tasks.md").write_text("## 任务\n1. 登录流程单元测试\n2. E2E 验证\n", encoding="utf-8")
    return project_root


# ──────────────────────────────────────────────────────────────────────────────
# REQ-13：脚本锚点状态机
# ──────────────────────────────────────────────────────────────────────────────

class TestAnchorStateMachine:
    def _make_meta(self, openguard_dir: Path, script_name: str, status: str = "verified",
                   symbols: list[dict] | None = None, reqs: list[dict] | None = None) -> Path:
        """在 test_assets/scripts/ 写入 .meta.yaml。"""
        scripts_dir = openguard_dir / "test_assets" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        bound_to = []
        for sym in (symbols or []):
            bound_to.append({"type": "code_symbol", **sym})
        for req in (reqs or []):
            bound_to.append({"type": "requirement", **req})
        meta = {
            "schema_version": "openguard/script_meta/v2",
            "script": f"test_assets/scripts/{script_name}",
            "script_path": f"test_assets/scripts/{script_name}",
            "status": status,
            "anchor_hash": "abc123",
            "bound_to": bound_to,
        }
        meta_path = scripts_dir / f"{Path(script_name).stem}.meta.yaml"
        meta_path.write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        return meta_path

    def test_symbol_hash_change_triggers_needs_review(self, qa_workspace):
        """REQ-13-16：符号哈希变化时降为 needs-review。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="verified",
                        symbols=[{"path": "Assets/Login.cs", "symbol": "Login.Handle", "hash": "oldHash"}])

        from openguard.workspace.asset_lifecycle import check_anchor_freshness
        reports = check_anchor_freshness(
            openguard_dir,
            current_symbols={"Login.Handle": "newHash"},  # 哈希变化
        )
        assert len(reports) == 1
        assert reports[0]["new_status"] == "needs-review"
        assert reports[0]["old_status"] == "verified"

    def test_symbol_missing_triggers_stale(self, qa_workspace):
        """REQ-13-17：绑定符号消失时降为 stale。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="verified",
                        symbols=[{"path": "Assets/Login.cs", "symbol": "Login.Handle", "hash": "abc"}])

        from openguard.workspace.asset_lifecycle import check_anchor_freshness
        # 不传入该符号 → 视为消失
        reports = check_anchor_freshness(openguard_dir, current_symbols={})
        assert any(r["new_status"] == "stale" for r in reports)

    def test_stale_symbol_missing_triggers_broken(self, qa_workspace):
        """REQ-13-18：stale 状态下符号消失升级为 broken。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="stale",
                        symbols=[{"path": "A.cs", "symbol": "A.Do", "hash": "x"}])

        from openguard.workspace.asset_lifecycle import check_anchor_freshness
        reports = check_anchor_freshness(openguard_dir, current_symbols={})
        assert any(r["new_status"] == "broken" for r in reports)

    def test_req_fingerprint_change_triggers_stale(self, qa_workspace):
        """REQ-13-17：需求指纹变化时降为 stale。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="verified",
                        reqs=[{"id": "REQ-001", "fingerprint": "fp1"}])

        from openguard.workspace.asset_lifecycle import check_anchor_freshness
        reports = check_anchor_freshness(
            openguard_dir,
            current_req_fingerprints={"REQ-001": "fp2"},
        )
        assert any(r["new_status"] == "stale" for r in reports)

    def test_no_change_no_report(self, qa_workspace):
        """符号哈希未变化时不产生报告。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="verified",
                        symbols=[{"path": "A.cs", "symbol": "A.Do", "hash": "sameHash"}])

        from openguard.workspace.asset_lifecycle import check_anchor_freshness
        reports = check_anchor_freshness(
            openguard_dir,
            current_symbols={"A.Do": "sameHash"},  # 哈希未变
        )
        assert reports == []

    def test_verified_script_allowed_in_all_gates(self, qa_workspace):
        """REQ-13-19：verified 脚本在所有 gate 下均可执行。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="verified")
        # 手动写 suite.yaml
        suite_dir = openguard_dir / "suites" / "smoke"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "suite.yaml").write_text(
            yaml.dump({"name": "smoke", "scripts": [{"path": "test_assets/scripts/login.py"}]}),
            encoding="utf-8",
        )
        from openguard.workspace.asset_lifecycle import list_suite_scripts
        for gate in ("local", "ci", "release", "nightly"):
            scripts = list_suite_scripts(openguard_dir, "smoke", gate)
            assert not any(s["skipped"] for s in scripts), f"gate={gate} 不应跳过 verified 脚本"

    def test_needs_review_blocked_in_release_gate(self, qa_workspace):
        """REQ-13-19：needs-review 脚本在 release gate 下被跳过。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="needs-review")
        suite_dir = openguard_dir / "suites" / "smoke"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "suite.yaml").write_text(
            yaml.dump({"name": "smoke", "scripts": [{"path": "test_assets/scripts/login.py"}]}),
            encoding="utf-8",
        )
        from openguard.workspace.asset_lifecycle import list_suite_scripts
        scripts = list_suite_scripts(openguard_dir, "smoke", "release")
        assert scripts[0]["skipped"]
        assert "needs-review" in scripts[0]["skip_reason"]

    def test_broken_script_skipped_in_all_gates(self, qa_workspace):
        """REQ-13-18：broken 脚本在任何 gate 下均被跳过。"""
        _, openguard_dir = qa_workspace
        self._make_meta(openguard_dir, "login.py", status="broken")
        suite_dir = openguard_dir / "suites" / "smoke"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "suite.yaml").write_text(
            yaml.dump({"name": "smoke", "scripts": [{"path": "test_assets/scripts/login.py"}]}),
            encoding="utf-8",
        )
        from openguard.workspace.asset_lifecycle import list_suite_scripts
        for gate in ("local", "ci", "release", "nightly"):
            scripts = list_suite_scripts(openguard_dir, "smoke", gate)
            assert scripts[0]["skipped"], f"gate={gate} 下 broken 脚本应被跳过"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-13：suite.yaml 管理
# ──────────────────────────────────────────────────────────────────────────────

class TestSuiteManagement:
    def test_add_script_to_suite(self, qa_workspace):
        """REQ-13-04：脚本可添加到 suite.yaml。"""
        _, openguard_dir = qa_workspace
        from openguard.workspace.asset_lifecycle import add_script_to_suite, load_suite
        result = add_script_to_suite(
            openguard_dir, "smoke", "test_assets/scripts/login.py"
        )
        assert result is True
        suite = load_suite(openguard_dir / "suites" / "smoke" / "suite.yaml")
        paths = [s["path"] for s in suite.get("scripts", [])]
        assert "test_assets/scripts/login.py" in paths

    def test_suite_rejects_change_dir_script(self, qa_workspace):
        """REQ-13-04：不允许 suite 引用 changes/ 工作区草稿。"""
        _, openguard_dir = qa_workspace
        from openguard.workspace.asset_lifecycle import add_script_to_suite
        result = add_script_to_suite(
            openguard_dir, "smoke", "openguard/changes/chg-001/test_scripts/login.py"
        )
        assert result is False

    def test_add_script_deduplication(self, qa_workspace):
        """重复添加同一脚本不产生重复条目。"""
        _, openguard_dir = qa_workspace
        from openguard.workspace.asset_lifecycle import add_script_to_suite, load_suite
        add_script_to_suite(openguard_dir, "smoke", "test_assets/scripts/login.py")
        add_script_to_suite(openguard_dir, "smoke", "test_assets/scripts/login.py")
        suite = load_suite(openguard_dir / "suites" / "smoke" / "suite.yaml")
        count = sum(1 for s in suite.get("scripts", []) if s["path"] == "test_assets/scripts/login.py")
        assert count == 1

    def test_requirement_suite_subpath(self, qa_workspace):
        """requirement/<req-id> 形式的套件支持子目录。"""
        _, openguard_dir = qa_workspace
        from openguard.workspace.asset_lifecycle import add_script_to_suite
        result = add_script_to_suite(
            openguard_dir, "requirement/REQ-001", "test_assets/scripts/req001.py"
        )
        assert result is True
        assert (openguard_dir / "suites" / "requirement" / "REQ-001" / "suite.yaml").exists()

    def test_suite_execution_manifest_has_anchor_hash(self, qa_workspace):
        """REQ-13-26：suite 执行清单包含锚点哈希。"""
        _, openguard_dir = qa_workspace
        scripts_dir = openguard_dir / "test_assets" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        meta = {"status": "verified", "anchor_hash": "deadbeef", "script_path": "test_assets/scripts/t.py"}
        (scripts_dir / "t.meta.yaml").write_text(
            yaml.dump(meta), encoding="utf-8"
        )
        suite_dir = openguard_dir / "suites" / "smoke"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "suite.yaml").write_text(
            yaml.dump({"name": "smoke", "scripts": [{"path": "test_assets/scripts/t.py"}]}),
            encoding="utf-8",
        )
        from openguard.workspace.asset_lifecycle import build_suite_execution_manifest
        manifest = build_suite_execution_manifest(openguard_dir, "smoke", "local", code_version="v1.2.3")
        assert manifest["code_version"] == "v1.2.3"
        assert manifest["scripts"][0]["anchor_hash"] == "deadbeef"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-13：脚本晋升（完整 meta.yaml）
# ──────────────────────────────────────────────────────────────────────────────

class TestScriptPromotion:
    def test_promote_creates_full_meta(self, qa_workspace, tmp_path):
        """REQ-13-13/14：晋升时生成完整 .meta.yaml。"""
        _, openguard_dir = qa_workspace
        # 创建草稿脚本
        draft = tmp_path / "login_test.py"
        draft.write_text("# login test\n", encoding="utf-8")

        from openguard.knowledge.manager import promote_script
        result = promote_script(
            draft, openguard_dir,
            change_id="chg-001",
            run_ids=["run-abc", "run-def"],
            bound_symbols=[{"path": "Assets/Login.cs", "symbol": "Login.Handle", "hash": "h1"}],
            bound_requirements=[{"id": "REQ-001", "fingerprint": "fp1"}],
            suite_membership=["smoke", "regression"],
        )
        assert result["status"] == "promoted"
        # 检查 meta.yaml 内容
        meta_path = Path(result["meta_path"])
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        bound = meta.get("bound_to", [])
        assert any(b.get("type") == "code_symbol" for b in bound)
        assert any(b.get("type") == "requirement" for b in bound)
        assert "smoke" in meta.get("suite_membership", [])
        assert "regression" in meta.get("suite_membership", [])

    def test_promote_rejects_without_run_ids(self, qa_workspace, tmp_path):
        """REQ-13-23：无真实执行记录不得晋升。"""
        _, openguard_dir = qa_workspace
        draft = tmp_path / "login_test.py"
        draft.write_text("# test\n", encoding="utf-8")
        from openguard.knowledge.manager import promote_script
        result = promote_script(draft, openguard_dir, run_ids=None)
        assert result["status"] == "rejected"

    def test_promote_adds_to_suite_yaml(self, qa_workspace, tmp_path):
        """晋升后自动更新 suite.yaml（REQ-13-04）。"""
        _, openguard_dir = qa_workspace
        draft = tmp_path / "smoke_test.py"
        draft.write_text("# smoke\n", encoding="utf-8")
        from openguard.knowledge.manager import promote_script
        from openguard.workspace.asset_lifecycle import load_suite
        promote_script(
            draft, openguard_dir,
            change_id="chg-001",
            run_ids=["run-1"],
            suite_membership=["smoke"],
        )
        suite = load_suite(openguard_dir / "suites" / "smoke" / "suite.yaml")
        paths = [s["path"] for s in suite.get("scripts", [])]
        assert any("smoke_test.py" in p for p in paths)

    def test_meta_file_same_stem_as_script(self, qa_workspace, tmp_path):
        """REQ-13-14：meta 文件与脚本同名（.meta.yaml 后缀）。"""
        _, openguard_dir = qa_workspace
        draft = tmp_path / "unique_test.py"
        draft.write_text("pass\n", encoding="utf-8")
        from openguard.knowledge.manager import promote_script
        result = promote_script(draft, openguard_dir, run_ids=["r1"], change_id="c1")
        assert Path(result["meta_path"]).name == "unique_test.meta.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# REQ-13：侵入策略
# ──────────────────────────────────────────────────────────────────────────────

class TestIntrusionStrategy:
    def test_external_only_always_ok(self):
        """REQ-13-06：external-only 是默认策略，不需要授权记录。"""
        from openguard.workspace.asset_lifecycle import check_intrusion_strategy
        result = check_intrusion_strategy({"runtime": {"intrusion_strategy": "external-only"}})
        assert result["ok"] is True

    def test_build_time_bridge_requires_authorization(self):
        """REQ-13-07：build-time-bridge 必须有授权记录。"""
        from openguard.workspace.asset_lifecycle import check_intrusion_strategy
        # 无授权 → 阻断
        result = check_intrusion_strategy({"runtime": {"intrusion_strategy": "build-time-bridge"}})
        assert result["ok"] is False
        assert any("intrusion_authorized_by" in b for b in result["blockers"])

    def test_build_time_bridge_with_auth_ok(self):
        """build-time-bridge 有授权时通过。"""
        from openguard.workspace.asset_lifecycle import check_intrusion_strategy
        result = check_intrusion_strategy({
            "runtime": {
                "intrusion_strategy": "build-time-bridge",
                "intrusion_authorized_by": "QA Lead",
                "bridge_source": "https://example.com/bridge",
            }
        })
        assert result["ok"] is True

    def test_runtime_patch_requires_restore_command(self):
        """REQ-13-08：runtime-patch 必须有还原命令。"""
        from openguard.workspace.asset_lifecycle import check_intrusion_strategy
        result = check_intrusion_strategy({
            "runtime": {
                "intrusion_strategy": "runtime-patch",
                "intrusion_authorized_by": "QA Lead",
                # 缺 restore_command
            }
        })
        assert result["ok"] is False
        assert any("restore_command" in b for b in result["blockers"])

    def test_intrusion_strategy_in_preflight(self, qa_workspace):
        """侵入策略校验集成到 pre_apply_check（REQ-13-06）。"""
        _, openguard_dir = qa_workspace
        # 写入 build-time-bridge 但无授权
        config = {
            "project": {"type": "unity"},
            "runtime": {"status": "incomplete", "missing": [],
                        "intrusion_strategy": "build-time-bridge"},
        }
        from openguard.executor.preflight import pre_apply_check
        result = pre_apply_check(None, openguard_dir, config, gate="local")
        assert result["is_blocked"] is True
        assert "intrusion_strategy_violation" in result["blockers"]

    def test_intrusion_strategy_changed_detected(self, qa_workspace):
        """REQ-13-09：侵入策略变化时能被检测到。"""
        _, openguard_dir = qa_workspace
        from openguard.workspace.asset_lifecycle import check_intrusion_strategy_changed
        config1 = {"runtime": {"intrusion_strategy": "external-only"}}
        config2 = {"runtime": {"intrusion_strategy": "build-time-bridge"}}
        # 首次记录
        check_intrusion_strategy_changed(openguard_dir, config1)
        # 变化
        changed = check_intrusion_strategy_changed(openguard_dir, config2)
        assert changed is True


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12：OpenSpec 检测
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenSpecDetection:
    def test_detect_openspec_installed(self, openspec_project):
        """REQ-12-01：有 openspec/changes/ 时检测为已安装。"""
        from openguard.integrations.openspec.detector import detect_openspec
        info = detect_openspec(openspec_project)
        assert info["installed"] is True
        assert len(info["detected_from"]) > 0

    def test_detect_openspec_not_installed(self, tmp_path):
        """REQ-12-01：没有 OpenSpec 标志时返回 installed=False。"""
        from openguard.integrations.openspec.detector import detect_openspec
        info = detect_openspec(tmp_path)
        assert info["installed"] is False

    def test_list_openspec_changes(self, openspec_project):
        """list_openspec_changes 返回已有 change 列表。"""
        from openguard.integrations.openspec.detector import list_openspec_changes
        changes = list_openspec_changes(openspec_project)
        assert "opsx-001" in changes

    def test_detect_no_openspec_no_effect_on_init(self, qa_workspace):
        """未安装 OpenSpec 时，OpenGuard init 工作流不受影响（REQ-12 验收）。"""
        project_root, _ = qa_workspace
        from openguard.integrations.openspec.detector import detect_openspec
        info = detect_openspec(project_root)
        assert info["installed"] is False


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12：openspec_link.yaml 写入
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenSpecLink:
    def test_write_openspec_link(self, openspec_project, tmp_path):
        """REQ-12-04：write_openspec_link 记录产物路径和哈希。"""
        from openguard.integrations.openspec.detector import write_openspec_link, read_openspec_link
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        link_path = write_openspec_link(change_dir, "opsx-001", openspec_project)
        assert link_path.exists()
        link = read_openspec_link(change_dir)
        assert link is not None
        assert link["openspec_change_id"] == "opsx-001"
        # 产物哈希已记录
        artifacts = link.get("artifacts", {})
        assert "proposal.md" in artifacts

    def test_openspec_link_has_hash(self, openspec_project, tmp_path):
        """REQ-12-04：产物哈希应为非空字符串。"""
        from openguard.integrations.openspec.detector import write_openspec_link, read_openspec_link
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        write_openspec_link(change_dir, "opsx-001", openspec_project)
        link = read_openspec_link(change_dir)
        proposal_info = link["artifacts"]["proposal.md"]
        assert proposal_info.get("hash", "") != ""


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12：需求提取
# ──────────────────────────────────────────────────────────────────────────────

class TestRequirementsExtraction:
    def test_extract_requirements_from_openspec(self, openspec_project):
        """REQ-12-03：从 OpenSpec specs 提取 EARS 模板。"""
        from openguard.integrations.openspec.detector import extract_requirements_from_openspec
        content = extract_requirements_from_openspec("opsx-001", openspec_project)
        # 应包含来自 proposal 的内容
        assert "登录功能" in content or "OpenSpec" in content
        # 应包含 EARS 提示
        assert "验收" in content or "specs" in content.lower()

    def test_extract_requirements_no_openspec_produces_template(self, tmp_path):
        """当 OpenSpec 产物不存在时，生成空白模板。"""
        from openguard.integrations.openspec.detector import extract_requirements_from_openspec
        content = extract_requirements_from_openspec("nonexistent-change", tmp_path)
        assert "REQ-001" in content or "验收" in content


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12：变化检测与门禁结论
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenSpecChangedAndClearance:
    def test_no_change_when_content_same(self, openspec_project, tmp_path):
        """REQ-12-07：内容未变化时 check_openspec_changed 返回 changed=False。"""
        from openguard.integrations.openspec.detector import write_openspec_link, check_openspec_changed
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        write_openspec_link(change_dir, "opsx-001", openspec_project)
        result = check_openspec_changed(change_dir, openspec_project)
        assert result["changed"] is False

    def test_change_detected_when_file_modified(self, openspec_project, tmp_path):
        """REQ-12-07：文件内容变化时 check_openspec_changed 返回 changed=True。"""
        from openguard.integrations.openspec.detector import write_openspec_link, check_openspec_changed
        change_dir = tmp_path / "chg-001"
        change_dir.mkdir()
        write_openspec_link(change_dir, "opsx-001", openspec_project)
        # 修改 proposal.md
        (openspec_project / "openspec" / "changes" / "opsx-001" / "proposal.md").write_text(
            "# 修改后的内容\n", encoding="utf-8"
        )
        result = check_openspec_changed(change_dir, openspec_project)
        assert result["changed"] is True

    def test_generate_archive_clearance_passed(self, tmp_path):
        """REQ-12-06：门禁通过后输出 cleared=True。"""
        from openguard.integrations.openspec.detector import generate_archive_clearance
        change_dir = tmp_path
        gate_report = {
            "result": "passed",
            "gate": "ci",
            "change_id": "chg-001",
        }
        clearance = generate_archive_clearance(change_dir, gate_report)
        assert clearance["cleared"] is True
        assert clearance["conclusion"] == "PASS"

    def test_generate_archive_clearance_failed(self, tmp_path):
        """REQ-12-06：门禁失败时 cleared=False。"""
        from openguard.integrations.openspec.detector import generate_archive_clearance
        gate_report = {"result": "failed", "gate": "ci", "change_id": "chg-001"}
        clearance = generate_archive_clearance(tmp_path, gate_report)
        assert clearance["cleared"] is False
        assert clearance["conclusion"] == "FAIL"

    def test_fix_suggestions_generated_on_gate_fail(self, tmp_path):
        """REQ-12-05：门禁失败时生成修复建议且不修改 OpenSpec。"""
        from openguard.integrations.openspec.detector import generate_fix_suggestions
        gate_report = {
            "result": "failed",
            "change_id": "chg-001",
            "blockers": [
                {"category": "test_failure", "message": "登录测试失败"},
                {"category": "blocking_review", "message": "安全漏洞"},
            ],
        }
        suggestions = generate_fix_suggestions(gate_report, tmp_path)
        assert len(suggestions) == 2
        # 所有建议默认不修改 OpenSpec 产物
        assert all(s["write_to_openspec"] is False for s in suggestions)


# ──────────────────────────────────────────────────────────────────────────────
# REQ-12：new 命令 --from-openspec 端到端
# ──────────────────────────────────────────────────────────────────────────────

class TestNewFromOpenSpec:
    def test_new_from_openspec_creates_link(self, openspec_project, monkeypatch):
        """REQ-12-02/04：openguard new --from-openspec 生成 openspec_link.yaml。"""
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.new import run_new

        # 初始化 QA 工作区
        monkeypatch.chdir(openspec_project)
        (openspec_project / "Assets").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.18f1\n"
        )
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))

        rc = run_new(argparse.Namespace(
            target="登录功能 QA",
            scan_scope="auto",
            test_suite=None,
            from_openspec="opsx-001",
        ))
        assert rc == 0

        # 找到 change 目录并检查 openspec_link.yaml
        openguard_dir = openspec_project / "openguard"
        changes = list((openguard_dir / "changes").iterdir())
        assert len(changes) >= 1
        change_dir = changes[0]
        assert (change_dir / "openspec_link.yaml").exists()

    def test_new_from_openspec_state_records_link(self, openspec_project, monkeypatch):
        """REQ-12-04：state.yaml 记录 openspec_change_id。"""
        import argparse
        from openguard.commands.init import run_init
        from openguard.commands.new import run_new

        monkeypatch.chdir(openspec_project)
        (openspec_project / "Assets").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings").mkdir(exist_ok=True)
        (openspec_project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2022.3.18f1\n"
        )
        run_init(argparse.Namespace(
            profile=None, hosts=["codebuddy"], gate="local", yes=True, reconfigure=False
        ))
        run_new(argparse.Namespace(
            target="登录功能 QA",
            scan_scope="auto",
            test_suite=None,
            from_openspec="opsx-001",
        ))

        openguard_dir = openspec_project / "openguard"
        change_dir = next((openguard_dir / "changes").iterdir())
        artifact_index = yaml.safe_load(
            (change_dir / "artifact_index.yaml").read_text(encoding="utf-8")
        )
        assert artifact_index.get("openspec_change_id") == "opsx-001"
