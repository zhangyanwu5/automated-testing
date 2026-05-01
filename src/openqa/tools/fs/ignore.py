"""忽略规则工具（REQ-15-10）。"""
from __future__ import annotations

import fnmatch
from pathlib import Path

from openqa.tools.registry import tool


@tool(
    name="fs.load_ignore",
    description="Read openqa/ignore file and return a list of glob patterns.",
    input_schema={"openqa_dir": {"type": "string"}},
    output_schema={"type": "array", "items": {"type": "string"}},
    tags=["fs", "ignore"],
)
def load_ignore(openqa_dir: str | Path) -> list[str]:
    """读取 openqa/ignore 文件，返回 glob 模式列表（过滤注释和空行）。"""
    ignore_file = Path(openqa_dir) / "ignore"
    if not ignore_file.exists():
        return []
    patterns: list[str] = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


@tool(
    name="fs.is_ignored",
    description="Check whether a path matches any gitignore-style ignore pattern.",
    input_schema={
        "path": {"type": "string"},
        "root": {"type": "string"},
        "patterns": {"type": "array", "items": {"type": "string"}},
    },
    output_schema={"type": "boolean"},
    tags=["fs", "ignore"],
)
def is_ignored(path: str | Path, root: str | Path, patterns: list[str]) -> bool:
    """判断 path 是否匹配任意忽略模式（gitignore 风格）。"""
    rel = str(Path(path).relative_to(Path(root))).replace("\\", "/")
    for pat in patterns:
        if pat.endswith("/"):
            if rel.startswith(pat) or ("/" + pat) in ("/" + rel + "/"):
                return True
            for part in Path(rel).parts:
                if fnmatch.fnmatch(part + "/", pat):
                    return True
        else:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat):
                return True
            if any(fnmatch.fnmatch(p, pat.rstrip("/")) for p in Path(rel).parts):
                return True
    return False
