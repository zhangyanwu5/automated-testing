"""文件搜索工具（REQ-15-06 / REQ-15-10）。"""
from __future__ import annotations

from pathlib import Path

from openqa.tools.registry import tool
from openqa.tools.fs.ignore import is_ignored


@tool(
    name="fs.find_files",
    description="Batch glob with optional ignore rules and depth limit. Returns relative paths.",
    input_schema={
        "root": {"type": "string"},
        "patterns": {"type": "array", "items": {"type": "string"}},
        "ignore": {"type": "array", "items": {"type": "string"}, "default": []},
        "max_depth": {"type": "integer", "default": -1, "description": "-1 = unlimited"},
    },
    output_schema={"type": "array", "items": {"type": "string"}},
    tags=["fs", "search"],
)
def find_files(
    root: str | Path,
    patterns: list[str],
    ignore: list[str] | None = None,
    max_depth: int = -1,
) -> list[str]:
    """批量 glob 匹配，支持忽略规则和深度限制，返回相对路径（/ 分隔符）。"""
    root = Path(root).resolve()
    ignore = ignore or []
    found: list[str] = []
    seen: set[str] = set()

    for pat in patterns:
        try:
            for p in sorted(root.glob(pat)):
                if not p.is_file():
                    continue
                if ignore and is_ignored(p, root, ignore):
                    continue
                if max_depth >= 0:
                    depth = len(p.relative_to(root).parts) - 1
                    if depth > max_depth:
                        continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
        except (PermissionError, OSError):
            pass
    return found


@tool(
    name="fs.find_executables",
    description=(
        "Search for executables by name under a root directory with limited depth. "
        "Returns list of {path, label, source} dicts. "
        "This is the generic engine; use runtime.find_unity_editors for Unity-specific search."
    ),
    input_schema={
        "root": {"type": "string", "description": "Directory to search under"},
        "exe_names": {"type": "array", "items": {"type": "string"},
                      "description": "Relative path patterns like 'Unity.exe' or 'Editor/Unity.exe'"},
        "max_depth": {"type": "integer", "default": 2},
        "source_label": {"type": "string", "default": "found"},
    },
    output_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "label": {"type": "string"},
                "source": {"type": "string"},
            },
        },
    },
    tags=["fs", "search", "executable"],
)
def find_executables(
    root: str | Path,
    exe_names: list[str],
    max_depth: int = 2,
    source_label: str = "found",
) -> list[dict[str, str]]:
    """在 root 下（有限深度）查找可执行文件，返回 [{path, label, source}]。

    遍历策略：枚举 root 的直接子目录，每个子目录再枚举 max_depth 层，
    对每层检查 exe_names 列表中的候选路径。
    不使用 glob("**") 避免大目录遍历耗时。
    """
    root = Path(root).resolve()
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def _check(directory: Path, depth: int) -> None:
        for exe_rel in exe_names:
            exe = directory / exe_rel
            key = str(exe).lower()
            if key not in seen and exe.exists():
                seen.add(key)
                try:
                    rel = str(exe.relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel = str(exe)
                found.append({"path": str(exe), "label": f"[{source_label}] {rel}", "source": source_label})

        if depth >= max_depth:
            return
        try:
            for child in sorted(directory.iterdir()):
                if child.is_dir():
                    _check(child, depth + 1)
        except (PermissionError, OSError):
            pass

    if root.exists():
        _check(root, 0)
    return found
