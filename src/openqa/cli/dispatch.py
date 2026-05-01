"""将解析后的 CLI 参数路由到对应命令处理器。"""
from __future__ import annotations

import argparse
import sys


def dispatch(args: argparse.Namespace) -> int:
    """根据 args.command 调用对应处理函数，返回退出码。"""
    cmd = args.command

    if cmd == "init":
        from openqa.commands.init import run_init
        return run_init(args)

    if cmd == "update":
        from openqa.commands.update import run_update
        return run_update(args)

    if cmd == "run":
        from openqa.commands.run import run_run
        return run_run(args)

    # _advance：内部状态机推进命令（AI 调用）
    if cmd == "_advance":
        from openqa.commands.advance import run_advance
        return run_advance(args)

    # continue：手动恢复别名，映射到 _advance 逻辑
    if cmd == "continue":
        from openqa.commands.advance import run_advance
        return run_advance(args)

    # new：向后兼容别名，映射到 run
    if cmd == "new":
        from openqa.commands.run import run_run
        return run_run(args)

    if cmd == "apply":
        from openqa.commands.apply import run_apply
        return run_apply(args)

    if cmd == "archive":
        from openqa.commands.archive import run_archive
        return run_archive(args)

    if cmd == "help":
        from openqa.commands.help import run_help
        return run_help(project_dir=".")

    print(f"openqa: unknown command '{cmd}'. Run `openqa help` for usage.", file=sys.stderr)
    return 1
