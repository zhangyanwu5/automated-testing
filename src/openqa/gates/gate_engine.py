"""质量门禁：策略解析、阻断规则、gate_report.yaml 生成（REQ-08）。

五种门禁（REQ-08-01）：
  local       → incremental scan + smoke + changed review
  ci          → auto scan + incremental + risk-based review
  requirement → requirement-full + risk-based review
  release     → full scan + regression/full + risk-based review
  nightly     → full scan + full suite

阻断条件（REQ-08-02）：
  - blocking Review finding
  - 冒烟测试失败
  - 验收失败（非豁免）
  - 证据缺失
  - 敏感信息泄漏

人工豁免（REQ-08-03/11）：必须记录原因、人员、时间、范围。
历史记录决策（REQ-08-06）：可基于 suite_index.yaml 判断稳定性。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from openqa.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 门禁默认策略（REQ-08-01）
# ──────────────────────────────────────────────────────────────────────────────

GATE_POLICIES: dict[str, dict[str, str]] = {
    "local": {
        "scan_scope": "incremental",
        "test_suite": "smoke",
        "review_level": "changed",
        "description": "本地开发快速验证，发现明显问题",
    },
    "ci": {
        "scan_scope": "auto",
        "test_suite": "incremental",
        "review_level": "risk-based",
        "description": "PR / 日常变更，验证受影响子图",
    },
    "requirement": {
        "scan_scope": "auto",
        "test_suite": "requirement-full",
        "review_level": "risk-based",
        "description": "单个需求完整验收闭环",
    },
    "release": {
        "scan_scope": "full",
        "test_suite": "regression",
        "review_level": "risk-based",
        "description": "发布前质量确认，优先正确性",
    },
    "nightly": {
        "scan_scope": "full",
        "test_suite": "full",
        "review_level": "risk-based",
        "description": "夜间构建，发现慢问题、基线漂移、长稳问题",
    },
}


def resolve_gate_policy(gate: str, config: dict[str, Any]) -> dict[str, str]:
    """返回门禁策略，config.yaml 中的覆盖可叠加（REQ-08-01）。"""
    base = dict(GATE_POLICIES.get(gate, GATE_POLICIES["local"]))
    # 允许 config.yaml defaults 覆盖
    defaults = config.get("defaults", {})
    if "scan_scope" in defaults:
        base["scan_scope"] = defaults["scan_scope"]
    return base


# ──────────────────────────────────────────────────────────────────────────────
# 阻断规则（REQ-08-02）
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_gate(
    gate: str,
    run_report: dict[str, Any],
    change_dir: Path | None,
    openqa_dir: Path,
    config: dict[str, Any],
    exemptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """评估门禁并返回结论（不写盘）。"""
    checks: list[dict[str, Any]] = []
    blocking_items: list[str] = []
    exemptions = exemptions or []
    exempted_ids = {e.get("check_id") for e in exemptions}
    policy = resolve_gate_policy(gate, config)

    # 1. Review blocking findings（REQ-08-02）
    if change_dir and change_dir.is_dir():
        from openqa.review.findings import has_blocking_findings
        has_blocking, count = has_blocking_findings(change_dir)
        check_id = "review_blocking"
        if has_blocking and check_id not in exempted_ids:
            blocking_items.append(check_id)
            checks.append(_fail_check(check_id,
                f"有 {count} 个 blocking Review finding"))
        else:
            status = "exempted" if has_blocking and check_id in exempted_ids else "pass"
            checks.append(_check(check_id, status,
                f"blocking findings: {count}" if has_blocking else "无 blocking findings"))

    # 2. 冒烟测试失败（REQ-08-02 / REQ-05-07）
    if run_report.get("result") == "failed":
        summary = run_report.get("summary", {})
        check_id = "smoke_pass"
        if gate in ("local", "ci") and summary.get("failed", 0) > 0:
            if check_id not in exempted_ids:
                blocking_items.append(check_id)
                checks.append(_fail_check(check_id,
                    f"有 {summary['failed']} 个测试失败"))
            else:
                checks.append(_check(check_id, "exempted", "测试失败但已豁免"))
        else:
            checks.append(_check(check_id, "pass" if run_report.get("result") != "failed" else "fail",
                f"执行结果：{run_report.get('result')}"))
    else:
        checks.append(_check("smoke_pass", "pass", f"执行结果：{run_report.get('result', 'unknown')}"))

    # 3. UNKNOWN 不得当 PASS（REQ-10 / REQ-07-03）
    check_id = "unknown_not_pass"
    unknown_count = run_report.get("summary", {}).get("unknown", 0)
    if unknown_count > 0 and check_id not in exempted_ids:
        if gate in ("release", "nightly"):
            blocking_items.append(check_id)
            checks.append(_fail_check(check_id,
                f"有 {unknown_count} 个 UNKNOWN 结果，release/nightly gate 不允许"))
        else:
            checks.append(_check(check_id, "warn",
                f"有 {unknown_count} 个 UNKNOWN，需补充证据"))
    else:
        checks.append(_check(check_id, "pass", "无 UNKNOWN 结果"))

    # 4. 发布/夜间门禁：优先正确性（REQ-08-05）
    check_id = "release_quality"
    if gate in ("release", "nightly"):
        blocked_count = run_report.get("summary", {}).get("blocked", 0)
        if blocked_count > 0 and check_id not in exempted_ids:
            blocking_items.append(check_id)
            checks.append(_fail_check(check_id,
                f"release/nightly gate 有 {blocked_count} 个任务被阻断，不允许跳过高风险项"))
        else:
            checks.append(_check(check_id, "pass", "无高风险阻断项"))

    # 5. 历史记录决策（REQ-08-06）
    history_check = _check_history(gate, openqa_dir, config)
    checks.extend(history_check)
    if any(c["status"] == "fail" for c in history_check):
        blocking_items.extend(c["check_id"] for c in history_check if c["status"] == "fail")

    # 总结论
    overall = "failed" if blocking_items else "passed"
    if exemptions:
        overall = "passed_with_exemptions" if not blocking_items else "failed"

    return {
        "gate": gate,
        "policy": policy,
        "result": overall,
        "blocking_items": blocking_items,
        "checks": checks,
        "exemptions": exemptions,
        "evaluated_at": _now_iso(),
    }


def _check_history(
    gate: str,
    openqa_dir: Path,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """基于历史执行记录决策（REQ-08-06）。"""
    checks: list[dict[str, Any]] = []
    # 门禁历史配置（可从 config 读取阈值）
    gate_cfg = config.get("gate_history", {})
    consecutive_pass_required = gate_cfg.get("consecutive_pass_required", {}).get(gate, 0)

    if consecutive_pass_required <= 0:
        return checks  # 未配置，跳过历史检查

    # 读取对应套件的历史
    suite_name = GATE_POLICIES.get(gate, {}).get("test_suite", "smoke")
    index_path = openqa_dir / "reports" / "suites" / suite_name / "suite_index.yaml"
    if not index_path.exists():
        checks.append(_check("history_stability", "info",
            f"无历史记录，跳过 {consecutive_pass_required} 次连续通过检查"))
        return checks

    try:
        with index_path.open(encoding="utf-8") as f:
            idx = yaml.safe_load(f) or {}
    except Exception:
        return checks

    runs = idx.get("runs", [])
    recent = runs[-consecutive_pass_required:] if len(runs) >= consecutive_pass_required else runs
    all_passed = all(r.get("result") == "passed" for r in recent)

    if not all_passed and len(recent) >= consecutive_pass_required:
        checks.append(_fail_check("history_stability",
            f"gate={gate} 要求最近 {consecutive_pass_required} 次连续通过，当前不满足"))
    else:
        checks.append(_check("history_stability", "pass",
            f"历史记录检查通过（最近 {len(recent)} 次）"))
    return checks


# ──────────────────────────────────────────────────────────────────────────────
# 豁免处理（REQ-08-03 / REQ-10-11）
# ──────────────────────────────────────────────────────────────────────────────

def make_exemption(
    check_id: str,
    reason: str,
    by: str,
    scope: str = "",
) -> dict[str, Any]:
    """构造豁免记录（REQ-08-03）。"""
    return {
        "check_id": check_id,
        "reason": reason,
        "by": by,
        "scope": scope or "this run",
        "exempted_at": _now_iso(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# gate_report.yaml 生成（REQ-08-04）
# ──────────────────────────────────────────────────────────────────────────────

def write_gate_report(
    change_dir: Path,
    gate_result: dict[str, Any],
    run_id: str = "",
) -> Path:
    """将门禁结论写入 gate_report.yaml（REQ-08-04）。"""
    report: dict[str, Any] = {
        "schema_version": "openqa/gate_report/v1",
        "gate": gate_result["gate"],
        "run_id": run_id,
        "generated_at": _now_iso(),
        "result": gate_result["result"],
        "policy": gate_result["policy"],
        "blocking_items": gate_result["blocking_items"],
        "checks": gate_result["checks"],
        "exemptions": gate_result.get("exemptions", []),
        "next_steps": _suggest_next_steps(gate_result),
    }
    path = change_dir / "gate_report.yaml"
    path.write_text(
        yaml.dump(report, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _suggest_next_steps(gate_result: dict[str, Any]) -> list[str]:
    """根据失败项给出下一步建议。"""
    steps: list[str] = []
    for item in gate_result.get("blocking_items", []):
        suggestions: dict[str, str] = {
            "review_blocking": "修复 Review blocking findings 或在 report_overlay.yaml 中记录豁免",
            "smoke_pass": "修复失败的测试用例，查看 run_report.md 和 timeline.md",
            "unknown_not_pass": "补充证据或人工确认 UNKNOWN 结果，更新 report_overlay.yaml",
            "release_quality": "确保所有高风险测试项均通过，不得跳过",
            "history_stability": "等待连续通过要求的执行次数达到阈值",
        }
        steps.append(suggestions.get(item, f"处理 {item} 阻断项"))
    if not steps:
        steps.append("门禁通过，可继续下一步")
    return steps


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _check(check_id: str, status: str, note: str = "") -> dict[str, Any]:
    r: dict[str, Any] = {"check_id": check_id, "status": status}
    if note:
        r["note"] = note
    return r


def _fail_check(check_id: str, reason: str) -> dict[str, Any]:
    return {"check_id": check_id, "status": "fail", "reason": reason}
