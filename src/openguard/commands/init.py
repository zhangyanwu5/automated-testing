"""``openguard init`` 命令处理器。

执行流程：
1. 项目类型探测。
2. 必要时对低置信度字段进行交互式追问。
3. 生成 config.yaml。
4. 生成 openguard/ignore。
5. 创建工作区目录结构。
6. 安装 /opg:* slash commands。
7. 检测 OpenSpec 并给出联动提示。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from openguard.setup.detector import (
    detect_project,
    DetectionResult,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    PROJECT_TYPE_UNKNOWN,
)
from openguard.setup.config_writer import build_config, write_config
from openguard.setup.ignore_writer import write_ignore, write_gitignore_suggestion
from openguard.setup.slash_commands import (
    install_commands,
    detect_installed_hosts,
    get_supported_hosts,
)
from openguard.setup.skills import install_skills
from openguard.workspace.layout import get_openguard_dir, ensure_subdirs, is_initialized


# ──────────────────────────────────────────────────────────────────────────────
# 展示辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _print_welcome() -> None:
    from openguard.prompts import get_cli
    print()
    print(get_cli("WELCOME"))


def _select_language(yes: bool, forced_lang: str | None) -> str:
    """第一步：语言选择（REQ-01-22）。

    - `--lang` 明确指定时直接使用。
    - `--yes` 时默认英文（en）。
    - 交互模式：TUI 单选菜单。

    返回语言代码（如 "zh" 或 "en"）。
    """
    from openguard.prompts import list_languages

    if forced_lang:
        return forced_lang

    available = list_languages()

    if yes:
        return "en"

    from openguard.cli.prompt import singleselect

    _lang_labels = {"zh": "中文", "en": "English"}
    # 菜单选项：优先展示中文在前
    ordered = sorted(available, key=lambda x: 0 if x == "zh" else 1)
    options = [_lang_labels.get(lang, lang) for lang in ordered]

    # 双语提示（选语言时尚未选择，故使用双语）
    chosen_label = singleselect(
        title="? Select language / 选择语言:",
        options=options,
        default=options[0],
    )
    # 从 label 反查 code
    for code, label in _lang_labels.items():
        if label == chosen_label:
            return code
    return chosen_label  # fallback：直接返回选中的文本


def _print_detection(result: DetectionResult) -> None:
    from openguard.prompts import get_cli
    pt = result.project_type
    if pt.value != PROJECT_TYPE_UNKNOWN:
        label = get_cli("DETECTED_PROJECT").format(type=pt.value)
    else:
        label = get_cli("NO_DETECT_PROJECT")
    print(label)
    print(f"  project.type: {pt.value:<24} confidence: {pt.confidence}")
    if pt.detected_from:
        print(f"  detected_from: {', '.join(pt.detected_from[:3])}")

    extra = result.extra
    if pt.value == "unity":
        if extra.get("unity_version"):
            print(f"  unity.version: {extra['unity_version']}")
        if extra.get("test_framework"):
            print(f"  test.framework: {extra['test_framework']}")
        if extra.get("tests_detected"):
            print(f"  tests.detected: {', '.join(extra['tests_detected'])}")
        scenes = extra.get("scenes_detected", 0)
        if scenes:
            print(f"  scenes.detected: {scenes}")
        editors = extra.get("detected_editors", [])
        if editors:
            print(f"  editors.found: {len(editors)}")
            for e in editors[:3]:
                print(f"    {e['source']:12} {e['path']}")

    print()
    print(get_cli("RECOMMENDED"))
    rt = result.runtime
    if rt.mode:
        print(f"  runtime.mode: {rt.mode:<22} decided_by: {rt.decided_by}")
    if result.evidence_collect:
        print(f"  evidence: {' + '.join(result.evidence_collect)}")
    print()


def _collect_missing(result: DetectionResult, yes: bool) -> dict[str, str]:
    """展示并收集 missing 字段的用户输入（REQ-01-15）。

    对于 Unity editor_path：
    - 探测到多个候选 → TUI 单选菜单（--yes 时选第一个）
    - 探测到唯一一个 → 自动选用，提示用户确认
    - 未探测到 → 手动输入

    对于其他 missing 字段：
    - 非 --yes：交互式追问
    - --yes：仅打印提示
    """
    from openguard.prompts import get_cli
    answers: dict[str, str] = {}

    # ── 处理 Unity Editor 路径（特殊逻辑）────────────────────────────────────
    detected_editors: list[dict[str, str]] = result.runtime.detected_editors
    missing_items = list(result.runtime.missing) + list(result.automation.missing)

    if "unity.editor_path" in missing_items and not detected_editors:
        # 无候选，降级为手动输入
        pass
    elif detected_editors:
        # 有候选，从 missing 中移除（将由下面逻辑处理）
        missing_items = [m for m in missing_items if m != "unity.editor_path"]

        if len(detected_editors) == 1:
            # 唯一候选：自动选用，告知用户
            editor = detected_editors[0]
            print(get_cli("UNITY_EDITOR_DETECTED").format(source=editor["source"]))
            print(f"    {editor['path']}")
            if not yes:
                try:
                    confirm = input(get_cli("USE_EDITOR_PROMPT")).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    confirm = "y"
                if confirm in ("n", "no"):
                    try:
                        custom = input(get_cli("ENTER_EDITOR_PATH")).strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        custom = editor["path"]
                    answers["unity.editor_path"] = custom or editor["path"]
                else:
                    answers["unity.editor_path"] = editor["path"]
            else:
                answers["unity.editor_path"] = editor["path"]
            print()

        else:
            # 多个候选：单选菜单
            from openguard.cli.prompt import singleselect
            options = [e["path"] for e in detected_editors]
            labels = [f"{e['source']:12} {e['path']}" for e in detected_editors]

            print()
            if yes:
                # --yes 模式：优先选编译版（source=compiled），其次第一个
                compiled = [e for e in detected_editors if e["source"] == "compiled"]
                chosen = compiled[0]["path"] if compiled else detected_editors[0]["path"]
                print(get_cli("AUTO_SELECT_EDITOR").format(path=chosen))
            else:
                chosen_label = singleselect(
                    title=get_cli("SELECT_UNITY_EDITOR"),
                    options=labels,
                    default=labels[0],
                )
                # 从 label 反查 path
                idx = labels.index(chosen_label) if chosen_label in labels else 0
                chosen = options[idx]
            answers["unity.editor_path"] = chosen
            print()

    # ── 处理其余 missing 字段 ─────────────────────────────────────────────────
    # 去重保序
    seen: set[str] = set()
    unique_missing: list[str] = []
    for item in missing_items:
        if item not in seen:
            seen.add(item)
            unique_missing.append(item)

    if unique_missing:
        print(get_cli("REQUIRED_INPUT_HEADER"))
        for item in unique_missing:
            if yes:
                print(get_cli("SKIPPED_FILL_LATER").format(item=item))
            else:
                try:
                    answer = input(f"  ? {item}: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    answer = ""
                if answer:
                    answers[item] = answer
                else:
                    print(get_cli("SKIPPED_FILL_LATER_INLINE"))
        print()

    return answers


def _print_quick_start() -> None:
    from openguard.prompts import get_cli
    print(get_cli("QUICK_START"))


def _print_openspec_hint(project_root: Path) -> None:
    """通过插件系统检测规格工具并给出联动提示（REQ-12-01）。"""
    try:
        from openguard.integrations import get_registry
        registry = get_registry()
        registry.auto_register(project_root)
        for provider in registry.get_all_spec_providers():
            if hasattr(provider, "detect_hint_for_init"):
                hint = provider.detect_hint_for_init(project_root)
                if hint:
                    print(hint)
            else:
                info = provider.detect(project_root)
                if info.get("installed"):
                    print(f"{provider.display_name} detected.")
                    print(f"  Use `openguard new --from-{provider.name} <change-id>` to link QA changes.")
        print()
    except Exception:
        pass


def _resolve_hosts(args_hosts: list[str] | None, project_root: Path, yes: bool) -> list[str]:
    """确定要安装命令的 AI 宿主列表（REQ-01-19）。

    - `--host` 明确指定：直接使用，不弹菜单。
    - `--yes`：使用探测结果；未探测到任何宿主时 fallback 到 codebuddy。
    - 交互模式：TUI 多选菜单，探测到的宿主预勾选（Space 切换，Enter 确认）。
    """
    if args_hosts:
        return args_hosts

    auto_detected = detect_installed_hosts(project_root)

    if yes:
        # 非交互：探测到就用探测结果，否则 fallback
        return auto_detected if auto_detected else ["codebuddy"]

    # 交互：TUI 多选菜单（REQ-01-19）
    from openguard.cli.prompt import multiselect
    from openguard.prompts import get_cli

    all_supported = get_supported_hosts()

    # 构建探测提示
    _host_dirs = {
        "codebuddy":  ".codebuddy/",
        "workbuddy":  ".workbuddy/",
        "cursor":     ".cursor/",
        "claude-code": ".claude/",
        "windsurf":   ".windsurf/",
        "gemini":     ".gemini/",
        "codex":      ".codex/",
    }
    hint_map = {
        host: f"[detected {_host_dirs[host]}]"
        for host in auto_detected
        if host in _host_dirs
    }

    selected = multiselect(
        title=get_cli("SELECT_AI_TOOLS"),
        options=all_supported,
        preselected=auto_detected,
        hint_map=hint_map,
    )
    return selected


def _resolve_project_type(
    result: DetectionResult,
    forced_profile: str | None,
    yes: bool,
) -> str:
    """确定最终项目类型，必要时交互式确认（TUI 单选）。"""
    if forced_profile:
        return forced_profile

    pt = result.project_type
    if pt.confidence == CONFIDENCE_HIGH:
        return pt.value

    if yes:
        return pt.value

    from openguard.cli.prompt import singleselect

    valid_types = [
        "web", "web-game", "webgl", "unity", "unreal",
        "backend", "api", "mixed", "unknown",
    ]
    chosen = singleselect(
        title=f"? Confirm project type (detected: {pt.value}, confidence: {pt.confidence}):",
        options=valid_types,
        default=pt.value,
    )
    result.project_type.value = chosen  # type: ignore[attr-defined]
    return chosen


# ──────────────────────────────────────────────────────────────────────────────
# 主处理函数
# ──────────────────────────────────────────────────────────────────────────────

def run_init(args: argparse.Namespace) -> int:
    from openguard.cli.spinner import step, ok, warn, set_plain_mode
    from openguard.prompts import get_cli

    project_root = Path.cwd()
    openguard_dir = get_openguard_dir(project_root)
    yes: bool = getattr(args, "yes", False)

    # REQ-01-27：--yes 或非 TTY 时强制纯文本模式
    if yes:
        set_plain_mode(True)

    # 已初始化且未指定 --reconfigure 时直接返回
    if is_initialized(project_root) and not getattr(args, "reconfigure", False):
        # 语言尚未选择，先读取 --lang 参数或默认英文
        _early_lang = getattr(args, "lang", None) or "en"
        from openguard import prompts as _prompts_mod
        _prompts_mod.set_language(_early_lang)
        print(get_cli("ALREADY_INIT_MSG").format(openguard_dir=openguard_dir))
        return 0

    # 第 0 步：Welcome（双语，语言选择前）
    _print_welcome()

    # 第 1 步：语言选择（REQ-01-22）
    lang = _select_language(
        yes=yes,
        forced_lang=getattr(args, "lang", None),
    )
    # 将语言切换应用到 prompts 模块，后续所有输出均使用所选语言
    from openguard import prompts as _prompts_mod
    _prompts_mod.set_language(lang)

    # 第 2 步：探测项目（有 IO，加 spinner）
    with step(get_cli("SCANNING_PROJECT"), cmd="init") as s:
        result = detect_project(project_root)
        s.set_label(get_cli("SCANNING_DETECTED").format(type=result.project_type.value))

    _print_detection(result)

    # 第 3 步：确定项目类型（低置信度时追问，交互步骤不加 spinner）
    project_type = _resolve_project_type(
        result,
        forced_profile=getattr(args, "profile", None),
        yes=yes,
    )
    result.project_type.value = project_type  # type: ignore[attr-defined]

    # 第 4 步：确定 AI 宿主（交互，不加 spinner）
    ai_hosts = _resolve_hosts(
        args_hosts=getattr(args, "hosts", None),
        project_root=project_root,
        yes=yes,
    )

    # 第 5 步：收集仍需用户补充的必要信息（有答案则写入 config）
    user_inputs = _collect_missing(result, yes=yes)

    # 第 6 步：创建工作区目录（瞬时，用 ok()）
    ensure_subdirs(openguard_dir)
    ok(get_cli("CREATED_WORKSPACE").format(path=openguard_dir), cmd="init")

    # 第 7 步：写入 config.yaml
    with step(get_cli("WRITING_CONFIG"), cmd="init"):
        gate = getattr(args, "gate", "local") or "local"
        config = build_config(result, ai_hosts=ai_hosts, gate=gate, user_inputs=user_inputs)
        write_config(config, openguard_dir)

    # 第 8 步：写入 ignore 文件（瞬时）
    ignore_path = write_ignore(project_type, openguard_dir)
    ok(get_cli("WRITTEN_FILE").format(path=ignore_path.relative_to(project_root)), cmd="init")

    # 第 9 步：安装 slash commands
    if ai_hosts:
        with step(get_cli("INSTALLING_COMMANDS"), cmd="init") as s:
            written_map = install_commands(project_root, ai_hosts, openguard_dir)
            total = sum(len(p) for p in written_map.values())
            hosts_str = ", ".join(written_map.keys())
            s.set_label(get_cli("INSTALLED_COMMANDS").format(hosts=hosts_str, total=total))
    else:
        warn(get_cli("NO_HOST_SKIP_COMMANDS"), cmd="init")
        warn(get_cli("NO_HOST_RUN_UPDATE"), cmd="init")

    # 第 10 步：安装 skill 文件（REQ-01-19 / REQ-14-01 / REQ-02-13）
    with step(get_cli("INSTALLING_SKILLS"), cmd="init") as s:
        if ai_hosts:
            skill_map = install_skills(project_root, ai_hosts, openguard_dir)
            if skill_map:
                total = sum(len(p) for p in skill_map.values())
                hosts_str = ", ".join(skill_map.keys())
                s.set_label(get_cli("INSTALLED_SKILLS").format(hosts=hosts_str, total=total))
            else:
                install_skills(project_root, [], openguard_dir)
                s.set_label(get_cli("INSTALLED_SKILLS_FALLBACK"))
        else:
            install_skills(project_root, [], openguard_dir)
            s.set_label(get_cli("INSTALLED_SKILLS_FALLBACK"))

    # 第 11 步：生成 .gitignore 建议规则（REQ-01-21 / REQ-02-14）
    written, gi_msg = write_gitignore_suggestion(project_root)
    if written:
        ok(gi_msg, cmd="init")

    # 第 11-A 步：引擎适配层安装（Unity / Unreal 等）
    _install_engine_runtime(project_root, project_type)

    # 第 12 步：OpenSpec 联动提示
    _print_openspec_hint(project_root)

    # 第 13 步：快速开始提示
    _print_quick_start()

    print(get_cli("INIT_COMPLETE"))
    return 0


def _install_engine_runtime(project_root: Path, project_type: str) -> None:
    """调用引擎适配层，在被测项目中安装运行时文件。

    - Unity  → engines.unity.UnityInstaller
    - Unreal → engines.unreal.UnrealInstaller（待实现）
    - 其他   → 无操作
    """
    from openguard.engines import get_installer
    from openguard.cli.spinner import ok, warn

    installer = get_installer(project_type, project_root)
    if installer is None:
        return  # 非引擎项目，无需安装

    try:
        result = installer.install()
        result.print_to_cli(cmd="init")
    except NotImplementedError:
        warn(f"{project_type} 引擎适配层尚未实现", cmd="init")
    except Exception as e:
        warn(f"引擎运行时安装失败：{e}", cmd="init")
