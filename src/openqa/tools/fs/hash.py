"""文件哈希工具（REQ-15-10）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from openqa.tools.registry import tool


@tool(
    name="fs.file_hash",
    description="Compute SHA-256 hash of a file, returning first `length` hex chars. Returns 'error' on IO failure.",
    input_schema={
        "path": {"type": "string"},
        "length": {"type": "integer", "default": 32},
    },
    output_schema={"type": "string", "description": "Hex digest (truncated) or 'error'"},
    tags=["fs", "hash"],
)
def file_hash(path: str | Path, length: int = 32) -> str:
    """计算文件 SHA-256 哈希，返回前 length 位 hex；IO 失败返回 'error'。"""
    h = hashlib.sha256()
    try:
        h.update(Path(path).read_bytes())
    except Exception:
        return "error"
    return h.hexdigest()[:length]


@tool(
    name="fs.content_hash",
    description="Compute SHA-256 hash of a string content.",
    input_schema={
        "content": {"type": "string"},
        "length": {"type": "integer", "default": 16},
    },
    output_schema={"type": "string"},
    tags=["fs", "hash"],
)
def content_hash(content: str, length: int = 16) -> str:
    """计算字符串内容的 SHA-256 哈希，返回前 length 位 hex。"""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:length]
