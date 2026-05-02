"""运行时启动器工厂（REQ-16-01）。

根据 config.yaml 的 runtime.mode 选择并返回对应的启动器实例。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_launcher(
    project_root: Path,
    config: dict[str, Any],
    test_knowledge: dict[str, Any] | None = None,
    *,
    event_sink=None,
):
    """根据 runtime.mode 返回对应的启动器实例。

    返回值实现了 start() / stop() 和 context manager 协议。
    若 auto_start=False 且应用不需要启动，返回 NullLauncher（空操作）。
    """
    runtime = config.get("runtime", {})
    mode = runtime.get("mode", "")
    auto_start = runtime.get("auto_start", True)

    if not auto_start:
        return NullLauncher(reason="auto_start=false，跳过应用启动")

    if mode == "editor-playmode":
        from openguard.launcher.unity import UnityLauncher
        return UnityLauncher(
            project_root, config,
            test_knowledge or {},
            event_sink=event_sink,
        )

    if mode in ("playwright", "http-api", "http", "playwright+js-bridge"):
        from openguard.launcher.web import WebLauncher
        return WebLauncher(project_root, config, event_sink=event_sink)

    # 未知 mode：空操作（不阻断执行）
    return NullLauncher(reason=f"未知 runtime.mode={mode!r}，跳过自动启动")


def check_launcher_config(config: dict[str, Any]) -> dict[str, Any]:
    """校验启动器所需配置，返回 {"ok": bool, "missing": list, "warnings": list}。"""
    runtime = config.get("runtime", {})
    mode = runtime.get("mode", "")

    if mode == "editor-playmode":
        from openguard.launcher.unity import check_unity_config
        result = check_unity_config(config)
        return {
            "ok": result["ok"],
            "missing": result["missing"],
            "warnings": [],
        }

    if mode in ("playwright", "http-api", "http", "playwright+js-bridge"):
        from openguard.launcher.web import check_web_config
        result = check_web_config(config)
        return {
            "ok": result["ok"],
            "missing": result["missing"],
            "warnings": [],
        }

    return {"ok": True, "missing": [], "warnings": [f"runtime.mode={mode!r} 无已知启动器，将跳过自动启动"]}


class NullLauncher:
    """空操作启动器，用于 auto_start=false 或未知 mode。"""

    def __init__(self, reason: str = ""):
        self.reason = reason

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def start(self) -> dict[str, Any]:
        return {"ok": True, "reused": False, "reason": self.reason}

    def stop(self) -> None:
        pass
