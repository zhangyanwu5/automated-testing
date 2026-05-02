"""执行前校验（REQ-07-01 / REQ-07-12 / REQ-07-13 / REQ-13-06~09）。

校验顺序：
1. 新鲜度校验（代码哈希、需求指纹、矩阵版本）
2. 脚本状态校验（broken/stale 不得执行）
3. Review blocking 检查（有 blocking findings 且无豁免时阻断）
4. Runtime/Automation 配置完整性（缺失关键配置阻断）
5. 侵入策略合规校验（REQ-13-06~09）
6. OpenSpec 变化检测（REQ-12-07）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from openguard.utils import now_iso as _now_iso


def pre_apply_check(
    change_dir: Path | None,
    openguard_dir: Path,
    config: dict[str, Any],
    suite_name: str | None = None,
    gate: str = "local",
) -> dict[str, Any]:
    """执行前综合校验，返回校验报告。"""
    checks: list[dict[str, Any]] = []
    is_blocked = False
    blockers: list[str] = []

    # 1. 新鲜度校验（REQ-07-01）
    if change_dir and change_dir.is_dir():
        from openguard.scan.freshness import check_freshness
        freshness = check_freshness(change_dir, openguard_dir)
        if not freshness["is_fresh"]:
            failed = [c["check"] for c in freshness["checks"] if c["status"] == "fail"]
            checks.append(_fail("freshness", f"新鲜度校验失败：{', '.join(failed)}"))
            is_blocked = True
            blockers.append("freshness_stale")
        else:
            checks.append(_pass("freshness"))

    # 2. 脚本状态校验（REQ-07-13 / REQ-13-15）
    script_check = _check_scripts(change_dir, openguard_dir, suite_name, gate)
    checks.extend(script_check["checks"])
    if script_check["blocked"]:
        is_blocked = True
        blockers.append("broken_scripts")

    # 3. Review blocking 检查（REQ-06-05）
    if change_dir and change_dir.is_dir():
        from openguard.review.findings import has_blocking_findings
        has_blocking, count = has_blocking_findings(change_dir)
        sarif_exists = (change_dir / "review_findings.sarif.json").exists()
        if sarif_exists and has_blocking:
            checks.append(_fail(
                "review_blocking",
                f"有 {count} 个 blocking Review finding，需修复或显式豁免（REQ-06-05）",
            ))
            is_blocked = True
            blockers.append("blocking_review_findings")
        else:
            checks.append(_pass("review_blocking"))

    # 4. Runtime 配置校验（REQ-07-12）
    rt_check = _check_runtime(config, gate)
    checks.extend(rt_check["checks"])
    if rt_check["blocked"]:
        is_blocked = True
        blockers.append("incomplete_runtime")

    # 5. 侵入策略合规校验（REQ-13-06~09）
    intrusion_check = _check_intrusion(config, openguard_dir)
    checks.extend(intrusion_check["checks"])
    if intrusion_check["blocked"]:
        is_blocked = True
        blockers.append("intrusion_strategy_violation")

    # 6. OpenSpec 变化检测（REQ-12-07）
    if change_dir and change_dir.is_dir():
        openspec_check = _check_openspec_changes(change_dir, openguard_dir)
        checks.extend(openspec_check["checks"])
        # OpenSpec 变化仅警告，不阻断（除非 release/nightly）
        if openspec_check["changed"] and gate in ("release", "nightly"):
            is_blocked = True
            blockers.append("openspec_changed_without_rescan")

    return {
        "schema_version": "openguard/pre_apply_check/v1",
        "checked_at": _now_iso(),
        "is_blocked": is_blocked,
        "blockers": blockers,
        "checks": checks,
    }


def _check_scripts(
    change_dir: Path | None,
    openguard_dir: Path,
    suite_name: str | None,
    gate: str,
) -> dict[str, Any]:
    """校验矩阵引用脚本状态（REQ-07-13 / REQ-13-15~19）。"""
    checks: list[dict[str, Any]] = []
    blocked = False

    # suite 模式：从 suite_manifest 获取脚本状态（REQ-13-25）
    if suite_name:
        from openguard.workspace.asset_lifecycle import list_suite_scripts
        scripts = list_suite_scripts(openguard_dir, suite_name, gate)
        broken = [s["path"] for s in scripts if s["status"] in ("broken", "stale")]
        blocked_by_gate = [s["path"] for s in scripts if s["skipped"] and s["status"] == "needs-review"]
        if broken:
            checks.append(_fail("script_status", f"suite 中有 {len(broken)} 个 broken/stale 脚本：{broken[:3]}"))
            blocked = True
        elif blocked_by_gate:
            checks.append(_fail("script_needs_review",
                f"gate={gate} 下 {len(blocked_by_gate)} 个 needs-review 脚本不得执行"))
            blocked = True
        else:
            checks.append(_pass("script_status", note=f"suite={suite_name} 脚本状态校验通过"))
        return {"checks": checks, "blocked": blocked}

    # change 模式：从 test_matrix.json 获取脚本引用
    matrix_path = change_dir / "test_matrix.json" if change_dir else None
    if matrix_path and matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        except Exception:
            matrix = {}

        broken_scripts: list[str] = []
        needs_review_blocked: list[str] = []

        for task in matrix.get("tasks", []):
            for ref in task.get("script_refs", []):
                status = ref.get("anchor_status", "verified")
                script_path = ref.get("script_path", "")

                if status in ("broken", "stale"):
                    broken_scripts.append(script_path)
                elif status == "needs-review" and gate in ("release", "nightly"):
                    needs_review_blocked.append(script_path)

        if broken_scripts:
            checks.append(_fail(
                "script_status",
                f"有 {len(broken_scripts)} 个 broken/stale 脚本不得参与执行：{broken_scripts[:3]}",
            ))
            blocked = True
        elif needs_review_blocked:
            checks.append(_fail(
                "script_needs_review",
                f"gate={gate} 下 {len(needs_review_blocked)} 个 needs-review 脚本不得执行",
            ))
            blocked = True
        else:
            checks.append(_pass("script_status"))
    else:
        checks.append(_pass("script_status", note="无矩阵脚本引用，跳过脚本状态校验"))

    return {"checks": checks, "blocked": blocked}


def _check_runtime(config: dict[str, Any], gate: str) -> dict[str, Any]:
    """校验 runtime 和 automation 配置（REQ-07-12）。"""
    checks: list[dict[str, Any]] = []
    blocked = False

    runtime = config.get("runtime", {})

    # release/nightly gate 对 runtime 要求更严格
    if gate in ("release", "nightly") and runtime.get("status") == "incomplete":
        missing = runtime.get("missing", [])
        checks.append(_fail(
            "runtime_config",
            f"gate={gate} 要求 runtime 配置完整，但 missing: {missing}",
        ))
        blocked = True
    elif runtime.get("status") == "incomplete":
        missing = runtime.get("missing", [])
        checks.append(_warn(
            "runtime_config",
            f"runtime 配置未完整（missing: {missing}），真实执行可能失败",
        ))
    else:
        checks.append(_pass("runtime_config"))

    return {"checks": checks, "blocked": blocked}


def _check_intrusion(config: dict[str, Any], openguard_dir: Path) -> dict[str, Any]:
    """校验侵入策略合规性（REQ-13-06~09）。"""
    checks: list[dict[str, Any]] = []
    blocked = False

    from openguard.workspace.asset_lifecycle import check_intrusion_strategy, check_intrusion_strategy_changed
    intrusion = check_intrusion_strategy(config)

    if not intrusion["ok"]:
        for blocker in intrusion["blockers"]:
            checks.append(_fail("intrusion_strategy", blocker))
        blocked = True
    else:
        checks.append(_pass("intrusion_strategy", note=f"侵入策略：{intrusion['strategy']}"))

    for warning in intrusion.get("warnings", []):
        checks.append(_warn("intrusion_strategy_warning", warning))

    # 检查策略是否变化（需触发全量扫描，REQ-13-09）
    if check_intrusion_strategy_changed(openguard_dir, config):
        checks.append(_warn(
            "intrusion_strategy_changed",
            "侵入策略已变化，建议执行全量扫描和矩阵重建（REQ-13-09）",
        ))

    return {"checks": checks, "blocked": blocked}


def _check_openspec_changes(change_dir: Path, openguard_dir: Path) -> dict[str, Any]:
    """通过插件系统检测规格产物变化（REQ-12-07）。"""
    checks: list[dict[str, Any]] = []
    changed = False

    project_root = openguard_dir.parent
    try:
        from openguard.integrations import get_registry
        provider = get_registry().get_spec_provider()
        result = provider.check_changed(change_dir, project_root)
        if result.get("changed"):
            changed = True
            changed_artifacts = result.get("changed_artifacts", [])
            checks.append(_warn(
                "spec_changed",
                f"{provider.display_name} 产物已变化（{changed_artifacts}），"
                "需重新计算需求指纹、影响图和测试矩阵（REQ-12-07）",
            ))
        else:
            checks.append(_pass("spec_changed", note=f"{provider.display_name} 产物无变化"))
    except Exception:
        checks.append(_pass("spec_changed", note="未检测到规格工具，跳过变化检测"))

    return {"checks": checks, "changed": changed}


def _pass(name: str, note: str = "") -> dict[str, Any]:
    r: dict[str, Any] = {"check": name, "status": "pass"}
    if note:
        r["note"] = note
    return r


def _fail(name: str, reason: str) -> dict[str, Any]:
    return {"check": name, "status": "fail", "reason": reason}


def _warn(name: str, reason: str) -> dict[str, Any]:
    return {"check": name, "status": "warn", "reason": reason}


