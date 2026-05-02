"""生成 openguard/ignore 文件。

此文件告知 OpenGuard 扫描器哪些路径需要跳过。
有意与 .gitignore 分离，可随项目一同提交到版本控制，
且不会污染项目自身的忽略规则。

格式：每行一个 gitignore 兼容的 glob 模式，'#' 开头为注释。
"""
from __future__ import annotations

from pathlib import Path


_HEADER = """\
# openguard/ignore
# OpenGuard 扫描忽略规则。
# 格式：gitignore 兼容的 glob 模式（每行一条）。
# 可手动添加项目专属排除规则。
#
# 由 `openguard init` 自动生成，可安全手动编辑。
"""

_ALWAYS_EXCLUDE = [
    "# ── 版本控制 ─────────────────────────────────────────",
    ".git/",
    ".svn/",
    "",
    "# ── AI 工具 & IDE ───────────────────────────────────────────",
    "openguard/",
    ".cursor/",
    ".codebuddy/",
    ".claude/",
    ".vscode/",
    ".idea/",
    "",
    "# ── 包管理器 & 锁文件 ────────────────────────────────────────",
    "node_modules/",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "",
    "# ── 构建产物 & 缓存 ─────────────────────────────────────────",
    "dist/",
    "build/",
    "out/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "coverage/",
    ".coverage",
    "",
    "# ── 密钥 & 凭证 ────────────────────────────────────────",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "secrets/",
]

_TYPE_EXTRA: dict[str, list[str]] = {
    "unity": [
        "# ── Unity ───────────────────────────────────────────────────",
        "Library/",
        "Temp/",
        "Logs/",
        "obj/",
        "*.csproj",
        "*.sln",
        "UserSettings/",
    ],
    "unreal": [
        "# ── Unreal ───────────────────────────────────────────────────",
        "Binaries/",
        "Intermediate/",
        "Saved/",
        "DerivedDataCache/",
        ".vs/",
    ],
    "web": [
        "# ── Web ─────────────────────────────────────────────────────",
        ".next/",
        ".nuxt/",
        "*.min.js",
        "*.min.css",
        "storybook-static/",
    ],
    "backend": [
        "# ── Backend ─────────────────────────────────────────────────",
        ".venv/",
        "venv/",
        "env/",
        "target/",
        "bin/",
        "*.class",
        "*.jar",
    ],
    "api": [
        "# ── API ─────────────────────────────────────────────────────",
        ".venv/",
        "venv/",
        "env/",
    ],
    "web-game": [
        "# ── WebGame / WebGL ──────────────────────────────────────────",
        "Build/",
        "Temp/",
        "Library/",
        "*.wasm.gz",
    ],
    # mixed：各子项目重型目录的并集，子项目忽略规则可追加
    "mixed": [
        "# ── Mixed 项目 ───────────────────────────────────────────",
        "Library/",
        "Temp/",
        "Binaries/",
        "Intermediate/",
        "Saved/",
        ".venv/",
        "venv/",
        "target/",
    ],
}


def generate_ignore(project_type: str) -> str:
    """返回指定项目类型的 openguard/ignore 文件内容。"""
    lines: list[str] = [_HEADER]
    lines.extend(_ALWAYS_EXCLUDE)

    type_specific = _TYPE_EXTRA.get(project_type)
    if type_specific:
        lines.append("")
        lines.extend(type_specific)

    lines.append("")  # 末尾空行
    return "\n".join(lines)


def write_ignore(project_type: str, openguard_dir: Path) -> Path:
    """写入 ignore 文件并返回路径。"""
    openguard_dir.mkdir(parents=True, exist_ok=True)
    ignore_path = openguard_dir / "ignore"
    ignore_path.write_text(generate_ignore(project_type), encoding="utf-8")
    return ignore_path


# ──────────────────────────────────────────────────────────────────────────────
# .gitignore 建议规则（REQ-01-21 / REQ-02-14）
# ──────────────────────────────────────────────────────────────────────────────

_GITIGNORE_BLOCK = """\
# ── OpenGuard（由 `openguard init` 生成）────────────────────────────────────────
# 排除大型执行证据，保留团队共享的 changes、test_assets、suites、knowledge。
openguard/reports/*/evidence/
openguard/reports/*/*/evidence/
openguard/traces/
openguard/baselines/
# 如需排除所有报告（仅保留源码型产物），取消以下注释：
# openguard/reports/
"""


def generate_gitignore_block() -> str:
    """返回建议追加到 .gitignore 的 OpenGuard 规则块（REQ-01-21）。"""
    return _GITIGNORE_BLOCK


def write_gitignore_suggestion(project_root: Path) -> tuple[bool, str]:
    """在项目根目录 .gitignore 中追加 OpenGuard 建议规则（REQ-01-21 / REQ-02-14）。

    - 若 .gitignore 已包含 OpenGuard 块，则跳过（幂等）。
    - 若 .gitignore 不存在，则创建并写入建议规则。
    - 返回 (written: bool, message: str)。
    """
    gitignore_path = project_root / ".gitignore"
    block = generate_gitignore_block()
    marker = "# ── OpenGuard"

    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        if marker in existing:
            return False, ".gitignore 中已包含 OpenGuard 规则，跳过。"
        # 追加到末尾
        with gitignore_path.open("a", encoding="utf-8") as f:
            f.write("\n" + block)
        return True, f"已将 OpenGuard 规则追加到 {gitignore_path}"
    else:
        gitignore_path.write_text(block, encoding="utf-8")
        return True, f"已创建 {gitignore_path} 并写入 OpenGuard 规则"
