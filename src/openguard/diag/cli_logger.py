"""层一诊断日志：记录每次 CLI 调用的完整上下文。

日志文件：<openguard_dir>/logs/cli-YYYYMMDD.log
- 每天一个文件，自动滚动
- 保留最近 30 天（超出自动清理）
- 每条记录包含：时间戳、命令、argv、cwd、退出码、stdout、stderr、耗时

设计原则：
- 写入失败绝不影响主流程（所有写入均 try/except 静默处理）
- 不记录敏感信息（密码、token 等）
- 文件体积：单条最大 64KB（stdout/stderr 各截断 32KB）
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# 单条记录中 stdout/stderr 的最大字节数
_MAX_OUTPUT_BYTES = 32 * 1024  # 32KB each


class CliLogger:
    """CLI 调用日志记录器（层一）。

    用法（在 main() 里）：
        logger = get_cli_logger(openguard_dir)
        with logger.record(argv):
            exit_code = dispatch(args)
        sys.exit(exit_code)
    """

    def __init__(self, log_dir: Path):
        self._log_dir = log_dir

    def _log_path(self) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        return self._log_dir / f"cli-{today}.log"

    @contextmanager
    def record(self, argv: list[str]):
        """上下文管理器：捕获 stdout/stderr，退出时写入日志。"""
        t0 = time.monotonic()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        exit_code = 0

        # 同时写到原始 stdout/stderr（用户仍能看到输出）
        tee_out = _TeeWriter(sys.stdout, stdout_buf)
        tee_err = _TeeWriter(sys.stderr, stderr_buf)

        try:
            with redirect_stdout(tee_out), redirect_stderr(tee_err):
                yield
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
            raise
        except Exception:
            exit_code = 1
            raise
        finally:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            self._write(argv, exit_code, stdout_buf.getvalue(), stderr_buf.getvalue(), elapsed_ms)

    def _write(
        self,
        argv: list[str],
        exit_code: int,
        stdout: str,
        stderr: str,
        elapsed_ms: int,
    ) -> None:
        """写入单条日志记录，失败静默处理。"""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            record: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "argv": argv,
                "cwd": os.getcwd(),
                "exit_code": exit_code,
                "elapsed_ms": elapsed_ms,
                "stdout": _truncate(stdout, _MAX_OUTPUT_BYTES),
                "stderr": _truncate(stderr, _MAX_OUTPUT_BYTES),
            }
            line = json.dumps(record, ensure_ascii=False)
            with self._log_path().open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._cleanup_old_logs()
        except Exception:
            pass  # 诊断日志写入失败绝不影响主流程

    def _cleanup_old_logs(self, keep_days: int = 30) -> None:
        """清理超过保留天数的日志文件。"""
        try:
            cutoff = time.time() - keep_days * 86400
            for p in self._log_dir.glob("cli-*.log"):
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
        except Exception:
            pass


class _TeeWriter:
    """同时写入两个输出流（原始流 + 缓冲流）。"""

    def __init__(self, primary: Any, secondary: io.StringIO):
        self._primary = primary
        self._secondary = secondary

    def write(self, data: str) -> int:
        try:
            self._secondary.write(data)
        except Exception:
            pass
        return self._primary.write(data)

    def flush(self) -> None:
        self._primary.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)


def _truncate(text: str, max_bytes: int) -> str:
    """按字节截断字符串，超出时加省略标注。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    return truncated + f"\n... [truncated, total {len(encoded)} bytes]"


def get_cli_logger(openguard_dir: Path | None) -> CliLogger | None:
    """获取 CLI 日志记录器。openguard_dir 为 None 时（工作区未初始化）返回 None。"""
    if openguard_dir is None:
        return None
    return CliLogger(openguard_dir / "logs")
