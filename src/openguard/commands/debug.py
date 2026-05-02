"""``openguard debug`` — 开发者调试工具，单点触发内部步骤，无需走完整流程。

子命令：
  launcher        启动目标应用（Unity/Web）并等待就绪，然后保持或退出
  launcher-stop   停止当前运行的目标应用
  scan            执行代码/需求扫描
  impact          执行影响分析
  matrix          生成测试矩阵
  preflight       执行 apply 前校验
  detect          执行项目类型探测（等同于 init 的探测阶段）

用法示例：
  openguard debug launcher                  # 启动 Unity/Web，成功后保持进程（Ctrl+C 退出）
  openguard debug launcher --stop-after 0   # 启动后立即停止（验证启动流程）
  openguard debug scan                      # 对当前 change 执行扫描
  openguard debug scan --scope full         # 强制全量扫描
  openguard debug impact                    # 执行影响分析
  openguard debug matrix                    # 生成测试矩阵
  openguard debug preflight                 # 执行 preflight 校验
  openguard debug detect                    # 探测项目类型
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# 公共辅助
# ──────────────────────────────────────────────────────────────────────────────

def _require_workspace() -> tuple[Path, dict[str, Any]]:
    """确保工作区已初始化，返回 (openguard_dir, config)。"""
    from openguard.workspace.layout import require_openguard_dir
    from openguard.setup.config_writer import load_config
    openguard_dir = require_openguard_dir()
    config = load_config(openguard_dir)
    return openguard_dir, config


def _require_change(openguard_dir: Path, change_id: str | None) -> Path:
    """返回 change_dir，未指定时取最近活跃 change。"""
    from openguard.workspace.change import latest_change
    if change_id:
        cd = openguard_dir / "changes" / change_id
        if not cd.is_dir():
            print(f"Error: change '{change_id}' not found.", file=sys.stderr, flush=True)
            sys.exit(1)
        return cd
    cd = latest_change(openguard_dir)
    if cd is None:
        print("Error: no active change found. Run `openguard run <goal>` first.", file=sys.stderr, flush=True)
        sys.exit(1)
    return cd


def _make_temp_run_dir(openguard_dir: Path) -> Path:
    """为 debug 创建一个临时 run 目录（不写入正式报告索引）。"""
    from openguard.executor.run_id import make_run_id
    run_id = f"debug-{make_run_id()}"
    run_dir = openguard_dir / "logs" / "debug_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _print_event(step: str, status: str, message: str) -> None:
    """终端直接打印 launcher emit 的事件，颜色区分状态。"""
    icons = {
        "running": "…",
        "passed":  "✓",
        "failed":  "✗",
        "warn":    "!",
        "info":    "·",
        "blocked": "⛔",
    }
    icon = icons.get(status, "·")
    print(f"  [{icon}] {step}: {message}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# debug launcher
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_launcher(args: argparse.Namespace) -> int:
    """启动目标应用并等待就绪，然后根据 --stop-after 决定是否保持。"""
    try:
        openguard_dir, config = _require_workspace()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        return 1

    stop_after: int = getattr(args, "stop_after", -1)   # -1 = 持续保持，0 = 立即停止，N = 保持 N 秒
    change_id: str | None = getattr(args, "change_id", None)
    run_dir = _make_temp_run_dir(openguard_dir)

    # 尝试读取 test_knowledge（可选）
    test_knowledge: dict[str, Any] = {}
    try:
        change_dir = _require_change(openguard_dir, change_id)
        tk_path = change_dir / "test_knowledge.md"
        if tk_path.exists():
            from openguard.executor.runner import _load_test_knowledge
            test_knowledge = _load_test_knowledge(tk_path)
    except SystemExit:
        pass  # 没有 change 也能调试 launcher

    from openguard.launcher import get_launcher

    mode = config.get("runtime", {}).get("mode", "unknown")
    print(f"debug launcher  mode={mode}", flush=True)
    print(f"  run_dir: {run_dir}", flush=True)
    print(flush=True)

    launcher = get_launcher(
        openguard_dir.parent, config, test_knowledge,
        event_sink=_print_event,
    )

    print("启动中…", flush=True)
    result = launcher.start()

    print(flush=True)
    if not result["ok"]:
        print(f"✗ 启动失败：{result.get('error', '未知错误')}", flush=True)
        return 1

    state = result.get("state", "")
    reused = result.get("reused", False)
    print(f"✓ 启动成功  state={state}  reused={reused}", flush=True)

    if stop_after == 0:
        print("  --stop-after 0，立即停止应用…", flush=True)
        launcher.stop()
        print("✓ 已停止", flush=True)
        return 0

    if stop_after > 0:
        print(f"  保持 {stop_after}s 后自动停止…", flush=True)
        try:
            time.sleep(stop_after)
        except KeyboardInterrupt:
            print("\n  收到 Ctrl+C，提前停止…", flush=True)
        launcher.stop()
        print("✓ 已停止", flush=True)
        return 0

    # stop_after == -1：持续保持，等用户 Ctrl+C
    print("  应用保持运行中，按 Ctrl+C 停止…", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  收到 Ctrl+C，停止应用…", flush=True)
        launcher.stop()
        print("✓ 已停止", flush=True)

    return 0


# ──────────────────────────────────────────────────────────────────────────────
# debug scan
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_scan(args: argparse.Namespace) -> int:
    """对当前/指定 change 执行代码扫描。"""
    try:
        openguard_dir, config = _require_workspace()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        return 1

    scope: str = getattr(args, "scope", "auto") or "auto"
    change_id: str | None = getattr(args, "change_id", None)
    change_dir = _require_change(openguard_dir, change_id)

    print(f"debug scan  scope={scope}  change={change_dir.name}", flush=True)
    print(flush=True)

    from openguard.scan.scanner import execute_scan
    t0 = time.monotonic()
    try:
        snap_path, delta_path = execute_scan(change_dir, openguard_dir, config, scope)
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"✓ snapshot  → {snap_path.name}", flush=True)
        if delta_path:
            print(f"✓ delta     → {delta_path.name}", flush=True)
        print(f"  ({elapsed}ms, flush=True)")
        return 0
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"✗ 扫描失败（{elapsed}ms）：{e}", flush=True)
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# debug impact
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_impact(args: argparse.Namespace) -> int:
    """执行影响分析，生成 impact_graph.json。"""
    try:
        openguard_dir, config = _require_workspace()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        return 1

    change_id: str | None = getattr(args, "change_id", None)
    change_dir = _require_change(openguard_dir, change_id)

    print(f"debug impact  change={change_dir.name}", flush=True)
    print(flush=True)

    from openguard.scan.impact import run_impact_analysis
    t0 = time.monotonic()
    try:
        path = run_impact_analysis(change_dir, openguard_dir, config)
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"✓ impact_graph → {path.name}  ({elapsed}ms, flush=True)")
        return 0
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"✗ 影响分析失败（{elapsed}ms）：{e}", flush=True)
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# debug matrix
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_matrix(args: argparse.Namespace) -> int:
    """生成测试矩阵（test_matrix.json）。"""
    try:
        openguard_dir, config = _require_workspace()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        return 1

    change_id: str | None = getattr(args, "change_id", None)
    suite: str | None = getattr(args, "suite", None)
    change_dir = _require_change(openguard_dir, change_id)

    print(f"debug matrix  change={change_dir.name}  suite={suite or 'from config'}", flush=True)
    print(flush=True)

    from openguard.matrix.generator import run_matrix_generation
    t0 = time.monotonic()
    try:
        path = run_matrix_generation(change_dir, openguard_dir, config, suite)
        elapsed = int((time.monotonic() - t0) * 1000)
        # 读取生成的矩阵，打印摘要
        import json as _json
        try:
            matrix = _json.loads(path.read_text(encoding="utf-8"))
            cases = matrix.get("cases", matrix.get("tasks", []))
            active = [c for c in cases if c.get("status") != "skipped"]
            print(f"✓ test_matrix → {path.name}  ({elapsed}ms, flush=True)")
            print(f"  cases: {len(active, flush=True)} active / {len(cases)} total")
        except Exception:
            print(f"✓ test_matrix → {path.name}  ({elapsed}ms, flush=True)")
        return 0
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"✗ 矩阵生成失败（{elapsed}ms）：{e}", flush=True)
        return 1


# ──────────────────────────────────────────────────────────────────────────────
# debug preflight
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_preflight(args: argparse.Namespace) -> int:
    """执行 apply 前校验，打印校验结果。"""
    try:
        openguard_dir, config = _require_workspace()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        return 1

    change_id: str | None = getattr(args, "change_id", None)
    gate: str = getattr(args, "gate", "local") or "local"
    suite: str | None = getattr(args, "suite", None)

    change_dir: Path | None = None
    try:
        change_dir = _require_change(openguard_dir, change_id)
    except SystemExit:
        pass  # preflight 可以在无 change 时也运行（只做 launcher 配置校验）

    print(f"debug preflight  gate={gate}  change={change_dir.name if change_dir else 'none'}", flush=True)
    print(flush=True)

    from openguard.executor.preflight import pre_apply_check
    run_dir = _make_temp_run_dir(openguard_dir)
    result = pre_apply_check(change_dir, openguard_dir, config, suite_name=suite, gate=gate)

    checks = result.get("checks", [])
    for check in checks:
        status = check.get("status", "?")
        name = check.get("check", "")
        reason = check.get("reason", "")
        icon = "✓" if status == "pass" else ("✗" if status == "fail" else "·")
        line = f"  [{icon}] {name}"
        if reason:
            line += f"  — {reason}"
        print(line, flush=True)

    print(flush=True)
    if result.get("is_blocked"):
        blockers = result.get("blockers", [])
        print(f"✗ 校验未通过，阻断项：{', '.join(blockers, flush=True)}")
        return 1
    else:
        print("✓ 校验通过，可以执行 apply", flush=True)
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# debug detect
# ──────────────────────────────────────────────────────────────────────────────

def _cmd_detect(args: argparse.Namespace) -> int:
    """执行项目类型探测，打印探测结果（等同于 init 的探测阶段）。"""
    project_root = Path(getattr(args, "path", None) or ".").resolve()

    print(f"debug detect  path={project_root}", flush=True)
    print(flush=True)

    from openguard.setup.detector import detect_project
    t0 = time.monotonic()
    try:
        result = detect_project(str(project_root))
        elapsed = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"✗ 探测失败：{e}", flush=True)
        return 1

    print(f"✓ 探测完成  ({elapsed}ms, flush=True)")
    print(f"  project_type  : {result.project_type}", flush=True)
    print(f"  confidence    : {result.confidence}", flush=True)
    print(f"  decided_by    : {result.decided_by}", flush=True)
    if result.evidence:
        print(f"  evidence      :", flush=True)
        for ev in result.evidence[:8]:
            print(f"    · {ev}", flush=True)
    if result.missing:
        print(f"  missing       :", flush=True)
        for m in result.missing:
            print(f"    ! {m}", flush=True)
    if result.detected_editors:
        print(f"  editors found :", flush=True)
        for ed in result.detected_editors:
            print(f"    · {ed.get('label', '', flush=True)}  →  {ed.get('path', '')}")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# 主入口（路由到子命令）
# ──────────────────────────────────────────────────────────────────────────────

_SUBCMDS = {
    "launcher": _cmd_launcher,
    "scan":     _cmd_scan,
    "impact":   _cmd_impact,
    "matrix":   _cmd_matrix,
    "preflight":_cmd_preflight,
    "detect":   _cmd_detect,
}


def run_debug(args: argparse.Namespace) -> int:
    subcmd: str | None = getattr(args, "debug_subcmd", None)
    if subcmd is None or subcmd not in _SUBCMDS:
        print("openguard debug: 可用子命令：", ", ".join(_SUBCMDS.keys()), flush=True)
        print("用法：openguard debug <子命令> [选项]", flush=True)
        print("示例：openguard debug launcher --stop-after 0", flush=True)
        return 1
    return _SUBCMDS[subcmd](args)
