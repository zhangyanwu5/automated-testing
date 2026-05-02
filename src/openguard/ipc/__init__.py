"""OpenGuard IPC 客户端（Python 侧）。

任何引擎适配层（Unity、Unreal 等）都通过 ``IPCClient`` 与被测项目中的
Bridge 脚本通信，无需关心底层文件操作细节。

用法
----
::

    from openguard.ipc import IPCClient
    from openguard.ipc.protocol import Cmd

    client = IPCClient(project_root / "openguard" / "runtime")

    # 发送命令并等待响应（同步，内置超时）
    resp = client.send(Cmd.ENTER_PLAYMODE, timeout=15.0)
    if resp.ok:
        print(resp.data)   # {"state": "entering"}
    else:
        print(resp.error)

    # 带参数
    resp = client.send(Cmd.OPEN_SCENE,
                       args={"scene": "Assets/Scenes/Login.unity"},
                       timeout=30.0)

    # 健康检查
    resp = client.send(Cmd.PING, timeout=3.0)
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from openguard.ipc.protocol import (
    REQUEST_FILE,
    RESPONSE_FILE,
    Cmd,
    Request,
    Response,
)

__all__ = ["IPCClient"]


class IPCClient:
    """文件 IPC 客户端。

    与引擎无关，只负责将 Request 写入 ``request.json`` 并
    轮询 ``response.json`` 直到收到对应响应或超时。

    Args:
        runtime_dir: 被测项目中的 ``openguard/runtime/`` 目录路径。
        poll_interval: 轮询间隔（秒），默认 0.1s（100ms）。
    """

    def __init__(self, runtime_dir: Path, *, poll_interval: float = 0.1):
        self.runtime_dir   = Path(runtime_dir)
        self.poll_interval = poll_interval

    # ── 主接口 ────────────────────────────────────────────────────────────────

    def send(
        self,
        cmd: str,
        args: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> Response:
        """发送命令并同步等待响应。

        Args:
            cmd:     命令名，使用 ``Cmd.*`` 常量。
            args:    命令参数（可选）。
            timeout: 等待响应的最长秒数。

        Returns:
            ``Response`` 对象，包含 ``ok``, ``data``, ``error``。
        """
        if not self.runtime_dir.exists():
            return Response(
                id="",
                ok=False,
                error=(
                    f"IPC runtime 目录不存在：{self.runtime_dir}。"
                    "请先运行 openguard init 完成初始化。"
                ),
            )

        req_path  = self.runtime_dir / REQUEST_FILE
        resp_path = self.runtime_dir / RESPONSE_FILE
        req_id    = uuid.uuid4().hex[:8]

        # 清理上次可能残留的文件
        self._try_unlink(req_path)
        self._try_unlink(resp_path)

        # 写请求
        request = Request(id=req_id, cmd=cmd, args=args or {})
        try:
            req_path.write_text(
                json.dumps(request.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            return Response(id=req_id, ok=False,
                            error=f"写 {REQUEST_FILE} 失败：{e}")

        # 轮询响应
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if resp_path.exists():
                resp = self._read_response(resp_path, req_id)
                if resp is not None:
                    return resp
            time.sleep(self.poll_interval)

        # 超时：清理请求文件，返回超时错误
        self._try_unlink(req_path)
        return Response(
            id=req_id,
            ok=False,
            error=(
                f"等待 Bridge 响应超时（>{timeout:.1f}s）[cmd={cmd}]。"
                "可能原因：Bridge 脚本未编译、引擎未运行或已崩溃。"
            ),
        )

    def cleanup(self) -> None:
        """清理 runtime/ 下的通信文件（stop 时调用）。"""
        for name in (REQUEST_FILE, RESPONSE_FILE):
            self._try_unlink(self.runtime_dir / name)

    def is_ready(self, *, ping_timeout: float = 2.0) -> bool:
        """向 Bridge 发送 ping，检查 Bridge 是否就绪。"""
        resp = self.send(Cmd.PING, timeout=ping_timeout)
        return resp.ok

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    def _read_response(self, path: Path, expected_id: str) -> Response | None:
        """尝试读取并验证 response.json，成功则删除文件。"""
        try:
            raw = path.read_text(encoding="utf-8")
            self._try_unlink(path)
            d = json.loads(raw)
            resp = Response.from_dict(d)
            # ID 校验：防止读到上次残留的响应
            if resp.id == expected_id:
                return resp
            # ID 不匹配（残留）：忽略，继续等
        except Exception:
            pass
        return None

    @staticmethod
    def _try_unlink(path: Path) -> None:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
