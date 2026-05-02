"""公共工具函数。"""
from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串，精确到秒。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
