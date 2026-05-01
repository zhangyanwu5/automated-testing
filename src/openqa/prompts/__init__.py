"""prompts — 提示词与文本内容统一管理模块。

目录结构：
  prompts/
    en/   英文（默认语言，必须完整）
    zh/   中文（可选，缺失 key 自动 fallback 到 en）
    …     未来可按需添加其他语言子目录

用法：

  from openqa.prompts import get_prompt, list_languages, set_language

  # 全局设置语言（init 时调用一次）
  set_language("zh")

  # 按 key 获取文本（缺失时 fallback 到 en）
  welcome = get_prompt("cli_messages.WELCOME")
  steps   = get_prompt("agent_hints.CONTINUE_STEPS")

  # 获取函数类型的 prompt（artifact 骨架生成函数）
  fn = get_prompt("artifacts.intent_md")
  content = fn(change_id=..., target=..., ...)

  # 列出当前支持的语言
  langs = list_languages()   # → ['en', 'zh']

语言目录检测规则：
  - 目录存在（prompts/<lang>/）且包含 cli_messages.py 视为"已支持"
  - en 是默认语言，始终存在；缺失的 key 自动 fallback 到 en
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).parent
_DEFAULT_LANG = "en"
_current_lang = _DEFAULT_LANG


# ──────────────────────────────────────────────────────────────────────────────
# 语言管理
# ──────────────────────────────────────────────────────────────────────────────

def list_languages() -> list[str]:
    """返回所有支持的语言代码（按字母排序，en 始终在首位）。

    判定标准：prompts/<lang>/ 目录存在且含 cli_messages.py。
    """
    langs: list[str] = []
    for d in sorted(_PROMPTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            if (d / "cli_messages.py").exists():
                langs.append(d.name)
    # en 始终在首位
    if _DEFAULT_LANG in langs:
        langs.remove(_DEFAULT_LANG)
        langs.insert(0, _DEFAULT_LANG)
    return langs


def set_language(lang: str) -> None:
    """设置当前会话语言。不存在的语言 fallback 到 en。"""
    global _current_lang
    supported = list_languages()
    _current_lang = lang if lang in supported else _DEFAULT_LANG


def get_language() -> str:
    """返回当前语言代码。"""
    return _current_lang


# ──────────────────────────────────────────────────────────────────────────────
# 核心 get_prompt
# ──────────────────────────────────────────────────────────────────────────────

def get_prompt(key: str, lang: str | None = None) -> Any:
    """按 key 获取 prompt 值，缺失时自动 fallback 到 en。

    key 格式：`<module>.<attribute>`
    例：
      "cli_messages.WELCOME"
      "agent_hints.CONTINUE_STEPS"
      "artifacts.intent_md"         ← 函数类型
      "skills.get_skill_content"    ← 函数类型

    Args:
        key:  `module.attr` 格式的 prompt 键
        lang: 指定语言（None 时使用 set_language() 设置的当前语言）

    Returns:
        对应的字符串、列表、或可调用对象。
        若指定语言缺失该 key，返回 en 版本。
    """
    use_lang = lang or _current_lang
    module_name, attr = key.split(".", 1)

    value = _load_attr(use_lang, module_name, attr)
    if value is _MISSING and use_lang != _DEFAULT_LANG:
        value = _load_attr(_DEFAULT_LANG, module_name, attr)
    if value is _MISSING:
        raise KeyError(f"Prompt key not found: {key!r} (tried lang={use_lang!r} and {_DEFAULT_LANG!r})")
    return value


class _MissingType:
    """哨兵对象，标记 key 缺失。"""
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingType()


def _load_attr(lang: str, module_name: str, attr: str) -> Any:
    """加载 prompts/<lang>/<module>.attr，失败返回 _MISSING。"""
    pkg = f"openqa.prompts.{lang}.{module_name}"
    try:
        mod = importlib.import_module(pkg)
    except ImportError:
        return _MISSING
    return getattr(mod, attr, _MISSING)


# ──────────────────────────────────────────────────────────────────────────────
# 便捷函数（常用 key 的直接访问）
# ──────────────────────────────────────────────────────────────────────────────

def get_cli(attr: str, lang: str | None = None) -> Any:
    """获取 cli_messages.<attr>。"""
    return get_prompt(f"cli_messages.{attr}", lang)


def get_hint(attr: str, lang: str | None = None) -> Any:
    """获取 agent_hints.<attr>。"""
    return get_prompt(f"agent_hints.{attr}", lang)


def get_artifact_fn(fn_name: str, lang: str | None = None):
    """获取 artifacts.<fn_name> 函数。"""
    return get_prompt(f"artifacts.{fn_name}", lang)


def get_skill(skill_name: str, lang: str | None = None) -> str:
    """获取指定 skill 的 Markdown 内容。"""
    fn = get_prompt("skills.get_skill_content", lang)
    return fn(skill_name)


def get_commands(lang: str | None = None) -> list[tuple[str, str, str]]:
    """获取 slash command 列表。"""
    return get_prompt("slash_commands.COMMANDS", lang)
