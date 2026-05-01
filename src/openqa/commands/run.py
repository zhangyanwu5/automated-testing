"""``openqa run <target>`` — 开始一次 QA 测试任务（REQ-03-01）。

取代原 `openqa new`，合并了创建 change 工作区和触发 AI 驱动循环的职责。

执行步骤：
1. 校验工作区已初始化。
2. 生成 change-id 并创建 openqa/changes/<change-id>/ 目录，写入骨架产物。
3. 若 --from-openspec 则写入 openspec_link.yaml 并做有效性校验。
4. 执行 knowledge-scan（REQ-03-09）。
5. 查询 preconditions.yaml（REQ-03-10）。
6. 将 state.yaml 的 agent_action 设为 run_cli、next_cli 设为 openqa _advance，
   触发 AI 驱动循环自主推进准备阶段。
7. 打印摘要，告知 AI 进入驱动循环。
"""
from __future__ import annotations

import argparse
import sys

from openqa.workspace.layout import require_openqa_dir
from openqa.workspace.change import (
    create_change,
    load_state,
    AGENT_ACTION_RUN_CLI,
    NEXT_CLI_ADVANCE,
)
from openqa.init.config_writer import load_config


def run_run(args: argparse.Namespace) -> int:
    from openqa.cli.spinner import step, ok, set_plain_mode

    try:
        openqa_dir = require_openqa_dir()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    target: str = args.target
    scan_scope: str = getattr(args, "scan_scope", "auto") or "auto"
    test_suite: str | None = getattr(args, "test_suite", None)
    from_openspec: str | None = getattr(args, "from_openspec", None)
    yes: bool = getattr(args, "yes", False)

    if yes:
        set_plain_mode(True)

    print(f"openqa run: '{target}'")
    print(f"  workspace  : {openqa_dir}")

    # 自动注册已安装的规格插件（OpenSpec 等）
    try:
        from openqa.plugins import get_registry
        get_registry().auto_register(openqa_dir.parent)
    except Exception:
        pass

    # 创建 change 工作区
    try:
        with step("Creating change workspace", cmd="run") as s:
            change_id, change_dir = create_change(
                openqa_dir,
                target,
                from_openspec=from_openspec,
                scan_scope=scan_scope,
                test_suite=test_suite,
            )
            s.set_label(f"Created change {change_id}")
    except Exception as exc:
        print(f"Error: change 创建失败 — {exc}", file=sys.stderr)
        return 1

    state = load_state(change_dir)

    print()
    print(f"  change_id  : {change_id}")
    print(f"  change_dir : {change_dir}")
    print(f"  scan_scope : {scan_scope}")
    if test_suite:
        print(f"  test_suite : {test_suite}")
    if from_openspec:
        print(f"  from_openspec : {from_openspec}")
    print()

    # OpenSpec 有效性校验
    if from_openspec:
        with step("Validating OpenSpec consistency", cmd="run") as s:
            _run_openspec_validation(change_dir, openqa_dir, s)

    # knowledge-scan
    with step("Running knowledge-scan", cmd="run") as s:
        _run_knowledge_scan(openqa_dir, target, s)

    # preconditions 查询（仅当 test_knowledge.md 已存在时有效，run 阶段通常跳过）
    _query_preconditions(change_dir, openqa_dir)

    # 打印骨架产物
    print("Generated artifacts:")
    for art in state.get("missing", []):
        print(f"  [pending] {art}")
    for fname in ("intent.md", "requirements.md", "state.yaml",
                  "unknowns.md", "snapshot.json", "delta.json", "artifact_index.yaml"):
        if (change_dir / fname).exists():
            print(f"  [ok] {fname}")
    if from_openspec and (change_dir / "openspec_link.yaml").exists():
        print(f"  [ok] openspec_link.yaml")

    print()
    # 告知 AI 进入驱动循环
    print(f"agent_action : {state.get('agent_action', AGENT_ACTION_RUN_CLI)}")
    print(f"next_cli     : {state.get('next_cli', NEXT_CLI_ADVANCE)}")
    print()
    print("AI: enter drive loop → call next_cli, keep looping until agent_action=wait_user")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# OpenSpec 有效性校验（REQ-03-11 / REQ-12-08~10）
# ──────────────────────────────────────────────────────────────────────────────

def _run_openspec_validation(change_dir, openqa_dir, s=None) -> None:
    """通过插件系统做规格有效性校验（REQ-03-11 / REQ-12-08~10）。"""
    try:
        from openqa.plugins import get_registry
        provider = get_registry().get_spec_provider()
        link = provider.read_link(change_dir)
        if not link:
            if s:
                s.set_label("OpenSpec validation — no link found, skipped")
            return

        spec_change_id = link.get("openspec_change_id") or link.get("spec_change_id", "")
        if not spec_change_id:
            if s:
                s.set_label("OpenSpec validation — no spec change ID, skipped")
            return

        project_root = openqa_dir.parent
        result = provider.validate_consistency(change_dir, spec_change_id, project_root)

        checks = result.get("checks", [])
        stale_count = sum(1 for c in checks if c.get("status") == "stale")
        not_impl_count = sum(1 for c in checks if c.get("status") == "not_implemented")

        label = (
            f"OpenSpec validation — {len(checks)} checks, "
            f"{stale_count} stale, {not_impl_count} not implemented"
        )
        if s:
            s.set_label(label)
            if stale_count or not_impl_count:
                s.fail(f"{stale_count + not_impl_count} issues written to unknowns.md")
    except Exception as e:
        if s:
            s.set_label(f"OpenSpec validation — skipped ({e})")


def _run_knowledge_scan(openqa_dir, target: str, s=None) -> None:
    """执行 knowledge-scan，提取游戏接口知识（REQ-03-09）。"""
    try:
        config = load_config(openqa_dir)
        project_root = openqa_dir.parent

        knowledge_dir = openqa_dir / "knowledge"
        event_catalog = knowledge_dir / "event_catalog.yaml"
        if event_catalog.exists():
            import yaml
            with event_catalog.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if data.get("scan_status") == "complete" and len(data.get("items", [])) > 0:
                if s:
                    s.set_label(f"Knowledge-scan — reusing {len(data['items'])} cached items")
                return

        from openqa.scan.scanner import run_knowledge_scan
        result = run_knowledge_scan(project_root, openqa_dir, config, target)
        total = sum(result.get("extracted_counts", {}).values())
        if s:
            if total > 0:
                s.set_label(f"Knowledge-scan — extracted {total} interface items")
            else:
                proj_type = config.get("project", {}).get("type", "unknown")
                s.set_label(f"Knowledge-scan — no items found (project type: {proj_type})")
    except Exception as e:
        if s:
            s.set_label(f"Knowledge-scan — skipped ({e})")


# ──────────────────────────────────────────────────────────────────────────────
# preconditions 查询（REQ-03-10）
# ──────────────────────────────────────────────────────────────────────────────

def _query_preconditions(change_dir, openqa_dir) -> None:
    """查询 AI 在 test_knowledge.md 中标注的外部前置需求（REQ-03-10）。

    前置标签由 AI 在 test_knowledge.md 的 external_preconditions 字段中填写，
    CLI 不做关键词推断。run 阶段 test_knowledge.md 通常尚未生成，直接跳过。
    """
    try:
        from openqa.knowledge.preconditions import query_preconditions_for_change

        knowledge_dir = openqa_dir / "knowledge"
        external_tags = _read_external_precondition_tags(change_dir)
        if not external_tags:
            return

        result = query_preconditions_for_change(knowledge_dir, external_tags)
        if result["found"]:
            matches = result["matches"]
            print(f"  [preconditions] 找到 {len(matches)} 条匹配前置路径（REQ-03-10）")
        else:
            unknown_entry = result.get("unknown_entry")
            if unknown_entry:
                _append_unknown(change_dir, unknown_entry)
                print(f"  [preconditions] 无匹配外部前置路径，已写入 unknowns.md（REQ-03-10）")
    except Exception:
        pass


def _read_external_precondition_tags(change_dir) -> list[str]:
    """从 test_knowledge.md 的 external_preconditions 字段读取外部前置标签。"""
    import yaml as _yaml
    tk_path = change_dir / "test_knowledge.md"
    if not tk_path.exists():
        return []

    content = tk_path.read_text(encoding="utf-8")

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            try:
                fm = _yaml.safe_load(content[3:end]) or {}
                tags = fm.get("external_preconditions", [])
                if isinstance(tags, list):
                    return [str(t) for t in tags]
            except Exception:
                pass

    import re
    section = re.search(
        r"##\s*[Ee]xternal[_ ][Pp]reconditions\s*\n((?:[^\n]*\n)*?)(?:##|$)",
        content,
    )
    if section:
        tags = re.findall(r"[-*]\s+`?(\w+)`?", section.group(1))
        if tags:
            return tags

    return []


def _append_unknown(change_dir, entry: str) -> None:
    """向 unknowns.md 追加一条未知项。"""
    unknowns_path = change_dir / "unknowns.md"
    if unknowns_path.exists():
        current = unknowns_path.read_text(encoding="utf-8")
    else:
        current = "# Unknowns\n\n<!-- 待确认项，由 openqa run/_advance 自动填充。 -->\n\n"

    current += f"\n## 前置路径缺失\n\n{entry}\n"
    unknowns_path.write_text(current, encoding="utf-8")
