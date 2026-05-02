"""文件读取工具（REQ-15-10）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from openguard.tools.registry import tool


@tool(
    name="fs.read_text",
    description="Safely read a text file, returning None on any error instead of raising.",
    input_schema={"path": {"type": "string", "description": "Absolute or relative file path"}},
    output_schema={"type": ["string", "null"]},
    tags=["fs", "read"],
)
def read_text(path: str | Path) -> str | None:
    """安全读取文本文件，任何异常返回 None。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


@tool(
    name="fs.read_yaml",
    description="Safely read and parse a YAML file, returning None on any error.",
    input_schema={"path": {"type": "string"}},
    output_schema={"type": ["object", "null"]},
    tags=["fs", "read"],
)
def read_yaml(path: str | Path) -> dict[str, Any] | None:
    """安全读取 YAML 文件。"""
    import yaml
    text = read_text(path)
    if text is None:
        return None
    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return None


@tool(
    name="fs.read_json",
    description="Safely read and parse a JSON file, returning None on any error.",
    input_schema={"path": {"type": "string"}},
    output_schema={"type": ["object", "null"]},
    tags=["fs", "read"],
)
def read_json(path: str | Path) -> dict[str, Any] | None:
    """安全读取 JSON 文件。"""
    import json
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None
