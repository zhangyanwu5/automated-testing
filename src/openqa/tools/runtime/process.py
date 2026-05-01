"""进程/命令执行工具（REQ-15-05）。"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from openqa.tools.registry import ToolResult, tool


@tool(
    name="runtime.check_executable",
    description="Check if a file exists and is executable.",
    input_schema={"path": {"type": "string"}},
    output_schema={"type": "boolean"},
    tags=["runtime", "process"],
)
def check_executable(path: str | Path) -> bool:
    """检测文件是否存在且可执行。"""
    p = Path(path)
    return p.exists() and os.access(p, os.X_OK)


@tool(
    name="runtime.run_command",
    description=(
        "Run a shell command safely, capturing stdout/stderr. "
        "Returns {returncode, stdout, stderr, elapsed_ms}."
    ),
    input_schema={
        "cmd": {"type": "array", "items": {"type": "string"}},
        "cwd": {"type": ["string", "null"], "default": None},
        "timeout": {"type": "integer", "default": 30},
    },
    output_schema={
        "type": "object",
        "properties": {
            "returncode": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "elapsed_ms": {"type": "integer"},
        },
    },
    tags=["runtime", "process"],
    is_read_only=False,
    timeout_seconds=60,
)
def run_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 30,
) -> ToolResult:
    """安全执行命令，捕获 stdout/stderr，不向调用方抛出异常。"""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        return ToolResult(
            ok=proc.returncode == 0,
            data={
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "elapsed_ms": elapsed,
            },
            elapsed_ms=elapsed,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - t0) * 1000)
        return ToolResult(ok=False, error=f"Command timed out after {timeout}s", elapsed_ms=elapsed)
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return ToolResult(ok=False, error=str(exc), elapsed_ms=elapsed)


@tool(
    name="runtime.get_env",
    description="Read an environment variable, with optional fallback.",
    input_schema={
        "key": {"type": "string"},
        "fallback": {"type": "string", "default": ""},
    },
    output_schema={"type": "string"},
    tags=["runtime", "env"],
)
def get_env(key: str, fallback: str = "") -> str:
    """读取环境变量，不存在时返回 fallback。"""
    return os.environ.get(key, fallback)
