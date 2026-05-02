"""OpenGuard IPC 协议定义。

所有引擎（Unity、Unreal 等）共享同一套 JSON 文件通信协议。
通信文件位于被测项目的 ``openguard/runtime/`` 目录下：

- ``request.json``  Python(Client) 写 → Bridge 脚本(Server) 读后删除
- ``response.json`` Bridge 脚本(Server) 写 → Python(Client) 读后删除

Request 格式
------------
::

    {
        "id":   "a1b2c3d4",     // 唯一请求 ID（8位随机十六进制）
        "cmd":  "enter_playmode",
        "args": {}              // 命令参数，可为空对象
    }

Response 格式
-------------
::

    {
        "id":    "a1b2c3d4",    // 对应请求的 ID（用于校验）
        "ok":    true,
        "data":  { ... },       // 命令返回数据，可为 null
        "error": null           // 错误描述，ok=false 时非 null
    }

支持的命令（cmd）
----------------
通用命令（所有引擎必须实现）：

- ``ping``             健康检查，返回 ``{"pong": true}``
- ``get_status``       返回当前运行时状态

引擎专用命令：

- ``enter_playmode``   [Unity/Unreal] 进入 PlayMode / PIE
- ``exit_playmode``    [Unity/Unreal] 退出 PlayMode / PIE
- ``open_scene``       [Unity/Unreal] 打开指定场景，args: ``{"scene": "path/to/scene"}``
- ``capture_screenshot`` [Unity/Unreal] 截图，args: ``{"path": "output/path.png"}``（预留）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── 通信文件名 ────────────────────────────────────────────────────────────────

REQUEST_FILE  = "request.json"
RESPONSE_FILE = "response.json"
STATUS_FILE   = "status.json"   # Bridge 主动写入，Python 只读

# runtime/ 目录名（相对于被测项目根目录 openguard/）
RUNTIME_DIR = "runtime"


# ── 命令常量 ──────────────────────────────────────────────────────────────────

class Cmd:
    """支持的命令名称常量。"""
    # 通用
    PING             = "ping"
    GET_STATUS       = "get_status"
    # 引擎 PlayMode / PIE
    ENTER_PLAYMODE   = "enter_playmode"
    EXIT_PLAYMODE    = "exit_playmode"
    # 场景
    OPEN_SCENE       = "open_scene"
    # 截图（预留）
    CAPTURE_SCREENSHOT = "capture_screenshot"


# ── 数据类 ────────────────────────────────────────────────────────────────────

@dataclass
class Request:
    """IPC 请求。"""
    id:   str
    cmd:  str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "cmd": self.cmd, "args": self.args}


@dataclass
class Response:
    """IPC 响应。"""
    id:    str
    ok:    bool
    data:  Any   = None
    error: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Response":
        return cls(
            id    = d.get("id", ""),
            ok    = bool(d.get("ok", False)),
            data  = d.get("data"),
            error = d.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":    self.id,
            "ok":    self.ok,
            "data":  self.data,
            "error": self.error,
        }

    # 方便在 Python 代码里解包
    def as_result(self) -> dict[str, Any]:
        """转为 launcher 通用的 {"ok", "data", "error"} 字典。"""
        return {"ok": self.ok, "data": self.data, "error": self.error}
