"""Unity Editor 探测工具（REQ-15-06 / REQ-15-07 / REQ-15-09）。"""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

from openguard.tools.registry import tool


@tool(
    name="runtime.find_unity_editors",
    description=(
        "Find Unity Editor executables on this machine. "
        "Searches: env var UNITY_EDITOR_PATH → sibling dirs of project (depth≤2) → Hub installation. "
        "Returns list sorted by priority: compiled/custom first, then Hub versions."
    ),
    input_schema={
        "project_root": {"type": "string", "description": "Unity project root directory"},
        "unity_version": {
            "type": ["string", "null"],
            "default": None,
            "description": "Expected Unity version string (e.g. '2019.4.41f1') for priority matching",
        },
    },
    output_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to Unity.exe / Unity binary"},
                "label": {"type": "string", "description": "Human-readable display label"},
                "source": {"type": "string", "enum": ["env", "compiled", "hub"]},
            },
        },
    },
    tags=["runtime", "unity", "search"],
    timeout_seconds=5,
)
@functools.lru_cache(maxsize=16)
def find_unity_editors(
    project_root: str,
    unity_version: str | None = None,
) -> list[dict[str, str]]:
    """按优先级搜索 Unity Editor（REQ-15-06/07/09）。

    搜索顺序（优先级递减）：
    1. 环境变量 UNITY_EDITOR_PATH（最快，零 IO）
    2. 项目同级目录（枚举，深度 ≤ 2，不递归）
    3. Unity Hub 官方安装目录（枚举版本子目录，不递归）

    进程内缓存：相同参数的第二次调用直接返回缓存结果（elapsed_ms ≈ 0）。
    """
    root = Path(project_root).resolve()
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(exe: Path, label: str, source: str) -> None:
        key = str(exe).lower()
        if key not in seen and exe.exists():
            seen.add(key)
            found.append({"path": str(exe), "label": label, "source": source})

    # 1. 环境变量（零 IO）
    env_path = os.environ.get("UNITY_EDITOR_PATH", "")
    if env_path:
        _add(Path(env_path), "[env] UNITY_EDITOR_PATH", "env")

    # 2. 项目同级目录（枚举，深度 ≤ 2）
    #    覆盖 ../UnityEditorWin/WindowsEditor/Unity.exe 这类自建引擎结构
    exe_candidates = [
        "Unity.exe",                        # Windows 直接在目录根
        "WindowsEditor/Unity.exe",          # Windows 编译版常见结构
        "Editor/Unity.exe",                 # Hub 风格
        "Unity.app/Contents/MacOS/Unity",   # macOS
    ]
    sibling_root = root.parent
    if sibling_root.exists():
        try:
            for sibling in sorted(sibling_root.iterdir()):
                if sibling.resolve() == root:
                    continue
                if not sibling.is_dir():
                    continue
                # 深度 1
                for cand in exe_candidates:
                    exe = sibling / cand
                    try:
                        rel = str(exe.relative_to(sibling_root)).replace("\\", "/")
                    except ValueError:
                        rel = str(exe)
                    _add(exe, f"[compiled] {rel}", "compiled")
                # 深度 2
                try:
                    for sub in sorted(sibling.iterdir()):
                        if not sub.is_dir():
                            continue
                        for cand in exe_candidates:
                            exe = sub / cand
                            try:
                                rel = str(exe.relative_to(sibling_root)).replace("\\", "/")
                            except ValueError:
                                rel = str(exe)
                            _add(exe, f"[compiled] {rel}", "compiled")
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass

    # 3. Unity Hub 官方安装目录（枚举 1 层版本子目录）
    hub_roots: list[Path] = []
    if sys.platform == "win32":
        hub_roots = [
            Path("C:/Program Files/Unity/Hub/Editor"),
            Path("C:/Program Files (x86)/Unity/Hub/Editor"),
        ]
    elif sys.platform == "darwin":
        hub_roots = [Path("/Applications/Unity/Hub/Editor")]
    else:
        hub_roots = [Path(os.path.expanduser("~/Unity/Hub/Editor"))]

    for hub_root in hub_roots:
        if not hub_root.exists():
            continue
        try:
            for ver_dir in sorted(hub_root.iterdir(), reverse=True):
                if not ver_dir.is_dir():
                    continue
                ver = ver_dir.name
                priority_mark = "  ← matches project version" if ver == unity_version else ""
                for exe_rel in ("Editor/Unity.exe", "Unity.app/Contents/MacOS/Unity", "Editor/Unity"):
                    _add(ver_dir / exe_rel, f"[hub] Unity {ver}{priority_mark}", "hub")
        except (PermissionError, OSError):
            pass

    return found
