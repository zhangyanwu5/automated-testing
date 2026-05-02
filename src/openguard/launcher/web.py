"""Web / H5 / HTTP API 启动器（REQ-16-07）。

支持：
- Playwright 浏览器（web / h5 / webgl 项目）
- HTTP 健康检查（backend / api 项目）
- 静态端口可达检查（通用 fallback）
"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Any


class WebLauncher:
    """Web / HTTP 服务启动器。

    对于 web/h5：启动服务进程（若配置了 start_command），等待 HTTP 健康检查通过。
    对于 backend/api：同上。
    对于 webgl：等待静态服务就绪。
    """

    def __init__(
        self,
        project_root: Path,
        config: dict[str, Any],
        *,
        event_sink=None,
    ):
        self.project_root = project_root
        self.config = config
        self.event_sink = event_sink or (lambda step, status, msg: None)

        runtime = config.get("runtime", {})
        self.start_command: str | None = runtime.get("start_command")
        self.base_url: str | None = runtime.get("base_url")
        self.auto_start: bool = runtime.get("auto_start", True)
        self.auto_close: bool = runtime.get("auto_close", True)
        self.startup_timeout: float = float(runtime.get("startup_timeout_seconds", 60))

        hc = runtime.get("health_check", {})
        self.hc_url: str | None = hc.get("url") or self.base_url
        self.hc_type: str = hc.get("type", "http")  # http | port
        self.hc_timeout: float = float(hc.get("timeout_seconds", self.startup_timeout))

        self._proc: subprocess.Popen | None = None
        self._we_started = False

    def __enter__(self):
        result = self.start()
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return self

    def __exit__(self, *_):
        self.stop()

    def start(self) -> dict[str, Any]:
        """启动服务并等待就绪。"""
        if self.start_command and self.auto_start:
            result = self._launch_service()
            if not result["ok"]:
                return result

        if self.hc_url:
            return self._wait_http_ready()
        elif self.base_url:
            return self._wait_port_ready()
        else:
            self._emit("web_launcher", "warn", "未配置 health_check.url 或 base_url，跳过就绪等待")
            return {"ok": True}

    def stop(self) -> None:
        if not self._we_started or not self.auto_close:
            return
        if self._proc is not None and self._proc.poll() is None:
            self._emit("web_launcher", "running", "关闭服务进程…")
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _launch_service(self) -> dict[str, Any]:
        self._emit("web_launcher", "running", f"启动服务：{self.start_command}")
        try:
            self._proc = subprocess.Popen(
                self.start_command,
                shell=True,
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._we_started = True
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"服务启动失败：{e}"}

    def _wait_http_ready(self) -> dict[str, Any]:
        """轮询 HTTP 健康检查 URL 直到返回 2xx、进程退出或超时。"""
        import urllib.request

        self._emit("web_launcher", "running", f"等待 HTTP 就绪：{self.hc_url}（最长 {self.hc_timeout:.0f}s）…")
        deadline = time.monotonic() + self.hc_timeout

        while time.monotonic() < deadline:
            # 优先检查进程是否已退出——进程死了不可能就绪，立即报错
            if self._proc is not None and self._proc.poll() is not None:
                returncode = self._proc.returncode
                return {
                    "ok": False,
                    "error": f"服务进程已意外退出（exit code {returncode}），健康检查终止：{self.hc_url}",
                }
            try:
                with urllib.request.urlopen(self.hc_url, timeout=3) as resp:
                    if 200 <= resp.status < 300:
                        self._emit("web_launcher", "passed", f"服务就绪：HTTP {resp.status}")
                        return {"ok": True}
            except Exception:
                pass
            time.sleep(1)

        # 超时：区分进程存活与进程死亡
        if self._proc is not None and self._proc.poll() is not None:
            return {
                "ok": False,
                "error": f"服务进程已退出（exit code {self._proc.returncode}），且未通过健康检查：{self.hc_url}",
            }
        return {
            "ok": False,
            "error": (
                f"HTTP 健康检查超时（>{self.hc_timeout:.0f}s）：{self.hc_url}。"
                f"服务进程仍在运行，但未返回 2xx 响应——可能正在初始化或启动耗时过长。"
            ),
        }

    def _wait_port_ready(self) -> dict[str, Any]:
        """等待 base_url 中的端口可达、进程退出或超时。"""
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        self._emit("web_launcher", "running", f"等待端口就绪：{host}:{port}（最长 {self.startup_timeout:.0f}s）…")
        deadline = time.monotonic() + self.startup_timeout

        while time.monotonic() < deadline:
            # 优先检查进程是否已退出
            if self._proc is not None and self._proc.poll() is not None:
                returncode = self._proc.returncode
                return {
                    "ok": False,
                    "error": f"服务进程已意外退出（exit code {returncode}），端口等待终止：{host}:{port}",
                }
            try:
                with socket.create_connection((host, port), timeout=2):
                    self._emit("web_launcher", "passed", f"端口 {host}:{port} 可达")
                    return {"ok": True}
            except Exception:
                pass
            time.sleep(1)

        if self._proc is not None and self._proc.poll() is not None:
            return {
                "ok": False,
                "error": f"服务进程已退出（exit code {self._proc.returncode}），且端口未就绪：{host}:{port}",
            }
        return {
            "ok": False,
            "error": (
                f"端口连接超时（>{self.startup_timeout:.0f}s）：{host}:{port}。"
                f"服务进程仍在运行，但端口未监听——可能正在初始化。"
            ),
        }

    def _emit(self, step: str, status: str, message: str) -> None:
        try:
            self.event_sink(step, status, message)
        except Exception:
            pass


def check_web_config(config: dict[str, Any]) -> dict[str, Any]:
    """校验 Web 启动器所需配置，返回 {"ok": bool, "missing": [...]}。"""
    runtime = config.get("runtime", {})
    missing = []
    if not runtime.get("base_url") and not runtime.get("health_check", {}).get("url"):
        missing.append("runtime.base_url 或 runtime.health_check.url")
    return {"ok": len(missing) == 0, "missing": missing}
