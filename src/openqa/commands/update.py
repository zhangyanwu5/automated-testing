"""``openqa update`` — 刷新 /oqa:* slash commands、skill、schema 和模板（REQ-01-02 / REQ-01-20）。

不修改已有 changes/、reports/、knowledge/。
输出兼容性报告：哪些旧产物可继续使用，哪些需要迁移（PRODUCT.md 3.2 节）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from openqa.init.config_writer import load_config
from openqa.init.slash_commands import install_commands
from openqa.init.skills import install_skills
from openqa.workspace.layout import require_openqa_dir

# 当前工具各产物的最新 schema 版本
CURRENT_SCHEMA_VERSIONS: dict[str, str] = {
    "config.yaml":           "openqa/config/v1",
    "snapshot.json":         "openqa/snapshot/v1",
    "delta.json":            "openqa/delta/v1",
    "impact_graph.json":     "openqa/impact_graph/v1",
    "test_matrix.json":      "openqa/test_matrix/v1",
    "freshness.json":        "openqa/freshness/v1",
    "gate_report.yaml":      "openqa/gate_report/v1",
    "openspec_link.yaml":    "openqa/openspec_link/v1",
    "artifact_index.yaml":   "openqa/artifact_index/v1",
    "state.yaml":            "openqa/state/v1",
    "review_findings.sarif.json": "2.1.0",  # SARIF 标准版本
}


def run_update(args: argparse.Namespace) -> int:
    from openqa.cli.spinner import step, ok, set_plain_mode

    yes: bool = getattr(args, "yes", False)
    if yes:
        set_plain_mode(True)

    try:
        openqa_dir = require_openqa_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    project_root = openqa_dir.parent
    print("Updating OpenQA templates, slash commands and skills…")

    try:
        config = load_config(openqa_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    ai_hosts: list[str] = config.get("ai_hosts", ["codebuddy"])

    # 刷新 slash commands
    with step("Refreshing /oqa:* commands", cmd="update") as s:
        written_map = install_commands(project_root, ai_hosts, openqa_dir)
        total = sum(len(p) for p in written_map.values())
        hosts_str = ", ".join(written_map.keys()) if written_map else "fallback"
        s.set_label(f"Refreshed /oqa:* commands ({hosts_str}, {total} files)")

    # 刷新 skill 文件（REQ-01-20 / REQ-14-02）
    with step("Refreshing openqa-* skills", cmd="update") as s:
        skill_map = install_skills(project_root, ai_hosts, openqa_dir)
        if skill_map:
            total = sum(len(p) for p in skill_map.values())
            hosts_str = ", ".join(skill_map.keys())
            s.set_label(f"Refreshed openqa-* skills ({hosts_str}, {total} files)")
        else:
            install_skills(project_root, [], openqa_dir)
            s.set_label("Refreshed openqa-* skills (fallback: openqa/commands/)")

    print()

    # 兼容性报告
    compat_report = _build_compat_report(openqa_dir)
    _print_compat_report(compat_report)

    print("Update complete.")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# 兼容性报告
# ──────────────────────────────────────────────────────────────────────────────

def _build_compat_report(openqa_dir: Path) -> dict[str, Any]:
    """扫描 openqa/ 下所有产物，检测 schema_version 兼容性。

    返回：{ok: [], warn: [], migrate: []}
    """
    ok: list[str] = []
    warn: list[str] = []
    migrate: list[str] = []

    # 检查顶层配置和产物
    for fname, expected_ver in CURRENT_SCHEMA_VERSIONS.items():
        fpath = openqa_dir / fname
        if fpath.exists():
            ver = _read_schema_version(fpath)
            if ver == expected_ver:
                ok.append(fname)
            elif ver and ver != expected_ver:
                migrate.append(f"{fname} (current {ver}, expected {expected_ver})")
            else:
                ok.append(fname)  # 无版本字段，视为兼容

    # 扫描所有 changes/ 下的产物
    changes_dir = openqa_dir / "changes"
    if changes_dir.exists():
        stale_changes: list[str] = []
        for change_dir in changes_dir.iterdir():
            if not change_dir.is_dir():
                continue
            state_path = change_dir / "state.yaml"
            if state_path.exists():
                ver = _read_schema_version(state_path)
                current = CURRENT_SCHEMA_VERSIONS["state.yaml"]
                if ver and ver != current:
                    stale_changes.append(f"changes/{change_dir.name}/state.yaml ({ver})")
        if stale_changes:
            warn.extend(stale_changes[:5])  # show at most 5
            if len(stale_changes) > 5:
                warn.append(f"  … and {len(stale_changes) - 5} more stale change state.yaml")

    # 检查 test_assets/scripts/ 下的 .meta.yaml
    scripts_dir = openqa_dir / "test_assets" / "scripts"
    if scripts_dir.exists():
        old_metas: list[str] = []
        for meta_path in scripts_dir.glob("*.meta.yaml"):
            ver = _read_schema_version(meta_path)
            if ver and "v1" in ver and "v2" not in ver:
                old_metas.append(meta_path.name)
        if old_metas:
            warn.append(
                f"test_assets/scripts/: {len(old_metas)} meta.yaml file(s) use old v1 format"
                " (still usable, recommend upgrading to v2 on next promotion)"
            )

    return {"ok": ok, "warn": warn, "migrate": migrate}


def _read_schema_version(path: Path) -> str:
    """读取文件中的 schema_version 字段。"""
    try:
        content = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            data = json.loads(content)
            return str(data.get("schema_version", ""))
        else:
            # YAML 简单提取，避免 import yaml 循环
            for line in content.splitlines():
                if "schema_version" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _print_compat_report(report: dict[str, Any]) -> None:
    """Print compatibility report."""
    migrate = report.get("migrate", [])
    warn = report.get("warn", [])
    ok = report.get("ok", [])

    print("Compatibility report:")

    if not migrate and not warn:
        print(f"  ✓ All {len(ok)} detected artifact(s) are compatible with the current version, no migration needed.")
    else:
        if ok:
            print(f"  ✓ Compatible artifacts: {len(ok)}")
        if warn:
            print(f"  ⚠  Warnings (still usable):")
            for w in warn:
                print(f"    - {w}")
        if migrate:
            print(f"  ✗ Migration required (incompatible format):")
            for m in migrate:
                print(f"    - {m}")
            print("    Suggestion: re-run `openqa init --reconfigure` to update affected artifacts.")

    print(f"  • changes/, reports/, knowledge/ artifacts are not affected.")
    print(f"  • config.yaml is not affected. To update the project profile, run `openqa init --reconfigure`.")
    print()
