"""Run ID 生成与报告目录管理（REQ-07-14 / REQ-07-15）。

每次执行有唯一 Run ID：run-<ISO8601时间戳>
报告存入独立目录，历史执行记录不覆盖。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from openqa.utils import now_iso as _now_iso


def make_run_id() -> str:
    """生成唯一 Run ID：run-<ISO8601时间戳>（REQ-07-14）。"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return f"run-{ts}"


def get_run_dir(
    openqa_dir: Path,
    run_id: str,
    *,
    change_id: str | None = None,
    suite_name: str | None = None,
) -> Path:
    """返回本次执行的报告目录路径（不创建）。"""
    if suite_name:
        return openqa_dir / "reports" / "suites" / suite_name / run_id
    elif change_id:
        return openqa_dir / "reports" / "changes" / change_id / run_id
    else:
        raise ValueError("get_run_dir 需要 change_id 或 suite_name 之一")


def ensure_run_dir(
    openqa_dir: Path,
    run_id: str,
    *,
    change_id: str | None = None,
    suite_name: str | None = None,
) -> Path:
    """创建并返回本次执行的报告目录（REQ-07-14）。"""
    run_dir = get_run_dir(openqa_dir, run_id, change_id=change_id, suite_name=suite_name)
    (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
    return run_dir


def update_suite_index(
    openqa_dir: Path,
    suite_name: str,
    run_id: str,
    result: str,
    script_count: int,
    code_version: str,
    gate: str,
) -> Path:
    """更新 suite_index.yaml（REQ-07-15）。"""
    suite_dir = openqa_dir / "reports" / "suites" / suite_name
    suite_dir.mkdir(parents=True, exist_ok=True)
    index_path = suite_dir / "suite_index.yaml"

    index: dict[str, Any] = {}
    if index_path.exists():
        with index_path.open(encoding="utf-8") as f:
            index = yaml.safe_load(f) or {}

    runs: list[dict[str, Any]] = index.get("runs", [])
    runs.append({
        "id": run_id,
        "timestamp": _now_iso(),
        "result": result,
        "script_count": script_count,
        "code_version": code_version,
        "gate": gate,
    })

    # 应用保留策略（REQ-07-16）
    max_runs = index.get("retention", {}).get("max_runs", 30)
    if len(runs) > max_runs:
        runs = runs[-max_runs:]

    index["suite"] = suite_name
    index["runs"] = runs
    index["latest_run_id"] = run_id
    index.setdefault("retention", {"max_runs": max_runs})

    index_path.write_text(
        yaml.dump(index, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return index_path


def update_change_run_index(
    openqa_dir: Path,
    change_id: str,
    run_id: str,
    result: str,
    script_count: int,
    code_version: str,
    gate: str,
) -> Path:
    """更新 change_run_index.yaml（REQ-07-15）。"""
    change_report_dir = openqa_dir / "reports" / "changes" / change_id
    change_report_dir.mkdir(parents=True, exist_ok=True)
    index_path = change_report_dir / "change_run_index.yaml"

    index: dict[str, Any] = {}
    if index_path.exists():
        with index_path.open(encoding="utf-8") as f:
            index = yaml.safe_load(f) or {}

    runs: list[dict[str, Any]] = index.get("runs", [])
    runs.append({
        "id": run_id,
        "timestamp": _now_iso(),
        "result": result,
        "script_count": script_count,
        "code_version": code_version,
        "gate": gate,
    })

    index["change_id"] = change_id
    index["runs"] = runs
    index["latest_run_id"] = run_id
    # change 维度不受 suite 保留策略影响（REQ-07-16）

    index_path.write_text(
        yaml.dump(index, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return index_path
