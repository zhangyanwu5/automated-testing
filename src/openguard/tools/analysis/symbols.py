"""符号抽取与语言探测工具（REQ-15-10）。"""
from __future__ import annotations

import re
from pathlib import Path

from openguard.tools.registry import tool


# 扩展名 → 语言标准化名
_EXT_LANG: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript",
    ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp", ".h": "cpp",
    ".go": "go", ".java": "java", ".kt": "kotlin",
    ".rs": "rust", ".rb": "ruby", ".swift": "swift",
    ".unity": "unity-scene", ".asset": "unity-asset",
    ".uasset": "unreal-asset", ".umap": "unreal-map",
    ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".xml": "xml", ".toml": "toml",
    ".proto": "protobuf", ".graphql": "graphql",
}

# 每种语言的顶层符号抽取正则（列表，按优先级）
_SYMBOL_PATTERNS: dict[str, list[str]] = {
    "python": [r"^(?:class|def|async def)\s+(\w+)"],
    "javascript": [
        r"^(?:export\s+)?(?:class|function(?:\s*\*)?\s+)(\w+)",
        r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(",
    ],
    "typescript": [
        r"^(?:export\s+)?(?:class|interface|function(?:\s*\*)?\s+|type\s+)(\w+)",
        r"^(?:export\s+)?const\s+(\w+)\s*(?::\s*\w+)?\s*=\s*(?:async\s*)?\(",
    ],
    "csharp": [
        r"^\s*(?:public|private|protected|internal|static|abstract|sealed|partial).*?(?:class|interface|struct|enum|void|Task)\s+(\w+)",
    ],
    "cpp": [
        r"^\s*(?:class|struct|enum(?:\s+class)?)\s+(\w+)",
        r"^\w[\w\s*&<>]+\s+(\w+)\s*\(",
    ],
    "go": [
        r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
        r"^type\s+(\w+)\s+",
    ],
    "java": [
        r"^\s*(?:public|private|protected|static|final|abstract).*?(?:class|interface|enum|void)\s+(\w+)",
    ],
}


@tool(
    name="analysis.detect_language",
    description="Detect programming language from file extension.",
    input_schema={"path": {"type": "string"}},
    output_schema={"type": "string", "description": "Normalized language name, e.g. 'python', 'csharp', 'unknown'"},
    tags=["analysis", "language"],
)
def detect_language(path: str | Path) -> str:
    """按扩展名推断编程语言，返回标准化语言名。"""
    return _EXT_LANG.get(Path(path).suffix.lower(), "unknown")


@tool(
    name="analysis.extract_symbols",
    description=(
        "Extract top-level symbol names (classes, functions, interfaces) from a source file "
        "using lightweight regex. Supports python/js/ts/csharp/cpp/go/java."
    ),
    input_schema={
        "path": {"type": "string"},
        "language": {
            "type": "string",
            "description": "Language name (auto-detected if omitted)",
            "default": "",
        },
        "max_symbols": {"type": "integer", "default": 50},
    },
    output_schema={"type": "array", "items": {"type": "string"}},
    tags=["analysis", "symbols"],
)
def extract_symbols(
    path: str | Path,
    language: str = "",
    max_symbols: int = 50,
) -> list[str]:
    """从源文件中正则抽取顶层符号名，最多返回 max_symbols 个，去重保序。"""
    lang = language or detect_language(path)
    patterns = _SYMBOL_PATTERNS.get(lang, [])
    if not patterns:
        return []

    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    symbols: list[str] = []
    for line in content.splitlines()[:500]:  # 只扫前 500 行
        for pat in patterns:
            m = re.match(pat, line)
            if m:
                symbols.append(m.group(1))

    # 去重保序，截断
    seen: set[str] = set()
    result: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            result.append(s)
            if len(result) >= max_symbols:
                break
    return result
