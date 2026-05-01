"""OpenQA CLI 入口。

提供 `openqa` 命令及以下子命令：

用户指令（文档可见）：
  init, update, run, apply, archive, help

内部命令（AI 调用，不出现在 help 中）：
  _advance, continue（手动恢复别名）
"""
from __future__ import annotations

import sys
import argparse

from openqa.cli.dispatch import dispatch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openqa",
        description="OpenQA – 面向 AI 编码宿主的自动化测试与代码质量框架",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="显示帮助信息并退出。"
    )
    parser.add_argument(
        "--version", action="store_true", help="显示版本号并退出。"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── init ──────────────────────────────────────────────────────────────────
    p_init = sub.add_parser("init", help="在当前项目初始化 openqa/ 工作区。")
    p_init.add_argument(
        "--profile",
        metavar="TYPE",
        help="强制指定项目类型（web / web-game / webgl / unity / unreal / backend / api / mixed / unknown）。",
    )
    p_init.add_argument(
        "--host",
        metavar="AI_HOST",
        action="append",
        dest="hosts",
        help="安装 /oqa:* 指令的 AI 宿主，可重复使用。例如：codebuddy、cursor。",
    )
    p_init.add_argument(
        "--gate",
        metavar="GATE",
        default="local",
        help="默认质量门禁（local / ci / release），默认值：local。",
    )
    p_init.add_argument(
        "--yes", "-y",
        action="store_true",
        help="非交互模式：接受所有自动探测的默认值，不进行提示。",
    )
    p_init.add_argument(
        "--lang",
        metavar="LANG",
        help="指定界面语言（zh / en），跳过交互式语言选择步骤。",
    )
    p_init.add_argument(
        "--reconfigure",
        action="store_true",
        help="重新运行探测并覆写项目画像，同时保留已有 changes/reports/knowledge。",
    )

    # ── update ────────────────────────────────────────────────────────────────
    p_update = sub.add_parser("update", help="刷新 /oqa:* slash commands、schema 和模板。")
    p_update.add_argument(
        "--yes", "-y",
        action="store_true",
        help="非交互模式。",
    )

    # ── run（用户指令：开始一次测试任务）─────────────────────────────────────
    p_run = sub.add_parser("run", help="开始一次测试任务，AI 自主推进准备，完成后等用户确认执行。")
    p_run.add_argument("target", help="本次测试任务的目标描述。")
    p_run.add_argument(
        "--from-openspec",
        metavar="CHANGE_ID",
        dest="from_openspec",
        help="将此测试任务关联到指定的 OpenSpec change。",
    )
    p_run.add_argument(
        "--scan-scope",
        metavar="SCOPE",
        dest="scan_scope",
        default="auto",
        help="扫描范围：auto / full / incremental，默认值：auto。",
    )
    p_run.add_argument(
        "--test-suite",
        metavar="SUITE",
        dest="test_suite",
        help="测试套件：smoke / incremental / requirement-full / regression / full。",
    )

    # ── _advance（内部命令：AI 驱动循环调用，不出现在 help 中）────────────────
    p_advance = sub.add_parser(
        "_advance",
        help=argparse.SUPPRESS,  # 不在 help 中显示
    )
    p_advance.add_argument(
        "--change",
        metavar="CHANGE_ID",
        dest="change_id",
        help="指定 change ID（默认使用最近一个活跃 change）。",
    )

    # ── continue（手动恢复别名，映射到 _advance 逻辑）────────────────────────
    p_continue = sub.add_parser(
        "continue",
        help="手动恢复：AI 中断后从当前状态继续驱动循环。正常流程无需手动触发。",
    )
    p_continue.add_argument(
        "--change",
        metavar="CHANGE_ID",
        dest="change_id",
        help="指定 change ID（默认使用最近一个活跃 change）。",
    )

    # ── apply ─────────────────────────────────────────────────────────────────
    p_apply = sub.add_parser(
        "apply",
        help="执行代码 Review 与测试矩阵，采集证据，生成报告。",
    )
    p_apply.add_argument(
        "--change",
        metavar="CHANGE_ID",
        dest="change_id",
        help="指定目标 change ID。",
    )
    p_apply.add_argument(
        "--suite",
        metavar="NAME",
        dest="suite",
        help="无 change 上下文时直接执行 openqa/suites/<name>/ 中定义的全局测试套件。",
    )
    p_apply.add_argument(
        "--scan-scope",
        metavar="SCOPE",
        dest="scan_scope",
        help="覆盖新鲜度校验所用的扫描范围。",
    )
    p_apply.add_argument(
        "--test-suite",
        metavar="SUITE",
        dest="test_suite",
        help="覆盖本次运行使用的测试套件。",
    )
    p_apply.add_argument(
        "--review-level",
        metavar="LEVEL",
        dest="review_level",
        help="覆盖 Review 级别：off / changed / risk-based / full。",
    )
    p_apply.add_argument(
        "--gate",
        metavar="GATE",
        help="覆盖质量门禁：local / ci / release。",
    )

    # ── archive ───────────────────────────────────────────────────────────────
    p_archive = sub.add_parser(
        "archive",
        help="归档已完成 change，沉淀稳定知识。",
    )
    p_archive.add_argument(
        "--change",
        metavar="CHANGE_ID",
        dest="change_id",
        help="指定目标 change ID。",
    )

    # ── help ──────────────────────────────────────────────────────────────────
    sub.add_parser("help", help="显示详细帮助和下一步建议。")

    return parser


def main(argv: list[str] | None = None) -> int:
    # 在最开始设置 UTF-8 输出，避免 Windows GBK 终端的 UnicodeEncodeError
    from openqa.cli.output import setup_utf8_stdout
    setup_utf8_stdout()

    parser = build_parser()
    args = parser.parse_args(argv)

    # REQ-01-27：非 TTY 环境全局启用纯文本模式
    import sys as _sys
    if not (_sys.stdout.isatty() and _sys.stdin.isatty()):
        from openqa.cli.spinner import set_plain_mode
        set_plain_mode(True)

    if args.version:
        from openqa import __version__
        print(f"openqa {__version__}")
        return 0

    if args.command is None or args.help:
        from openqa.commands.help import run_help
        run_help(project_dir=".")
        return 0

    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
