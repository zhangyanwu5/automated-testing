"""工具注册表（REQ-15-01 ~ 15-05 / 15-08）。

提供：
  - ToolResult：统一返回格式
  - ToolMeta：工具元数据
  - @tool 装饰器：注册工具并注入计时/异常捕获/超时
  - call_tool()：动态调用已注册工具
  - list_tools()：枚举可用工具
"""
from __future__ import annotations

import functools
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ──────────────────────────────────────────────────────────────────────────────
# 核心数据结构
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """工具统一返回格式（REQ-15-02）。

    成功：ok=True，data 为返回值，error=None。
    失败：ok=False，data=None，error 为可读错误描述。
    永远不向调用方抛出异常。
    """
    ok: bool
    data: Any = None
    error: str | None = None
    elapsed_ms: int = 0

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class ToolMeta:
    """工具元数据（REQ-15-01）。"""
    name: str                           # 唯一标识，格式 "<category>.<tool_name>"
    description: str                    # 供 Agent 决策是否调用
    input_schema: dict[str, Any]        # JSON Schema 描述输入参数
    output_schema: dict[str, Any]       # JSON Schema 描述 data 字段结构
    tags: list[str] = field(default_factory=list)
    is_read_only: bool = True           # False = 有 IO 写或命令执行副作用
    timeout_seconds: int = 10           # 默认超时


# ──────────────────────────────────────────────────────────────────────────────
# 注册表
# ──────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    """全局工具注册表（单例）。"""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolMeta, Callable]] = {}

    def register(self, meta: ToolMeta, fn: Callable) -> None:
        self._tools[meta.name] = (meta, fn)

    def get(self, name: str) -> tuple[ToolMeta, Callable] | None:
        return self._tools.get(name)

    def list(self, tags: list[str] | None = None) -> list[ToolMeta]:
        result = [m for m, _ in self._tools.values()]
        if tags:
            result = [m for m in result if any(t in m.tags for t in tags)]
        return result

    def call(self, name: str, inputs: dict[str, Any]) -> ToolResult:
        """动态调用已注册工具（REQ-15-03）。"""
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(ok=False, error=f"Tool not found: {name!r}")
        meta, fn = entry
        t0 = time.monotonic()
        try:
            data = fn(**inputs)
            elapsed = int((time.monotonic() - t0) * 1000)
            # 函数可以直接返回 ToolResult，或者返回原始值（自动包装）
            if isinstance(data, ToolResult):
                data.elapsed_ms = elapsed
                return data
            return ToolResult(ok=True, data=data, elapsed_ms=elapsed)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return ToolResult(ok=False, error=str(exc), elapsed_ms=elapsed)


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


# ──────────────────────────────────────────────────────────────────────────────
# @tool 装饰器
# ──────────────────────────────────────────────────────────────────────────────

def tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    tags: list[str] | None = None,
    is_read_only: bool = True,
    timeout_seconds: int = 10,
) -> Callable:
    """注册工具的装饰器（REQ-15-01）。

    被装饰的函数可以直接调用（高性能路径），也可以通过 call_tool() 动态调用。
    装饰后函数行为不变，只是把元数据注册到全局注册表。
    """
    def decorator(fn: Callable) -> Callable:
        meta = ToolMeta(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            tags=tags or [],
            is_read_only=is_read_only,
            timeout_seconds=timeout_seconds,
        )
        _registry.register(meta, fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.__tool_meta__ = meta  # type: ignore[attr-defined]
        # 透传 lru_cache 的 cache_clear / cache_info（如果有）
        if hasattr(fn, "cache_clear"):
            wrapper.cache_clear = fn.cache_clear  # type: ignore[attr-defined]
        if hasattr(fn, "cache_info"):
            wrapper.cache_info = fn.cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# 公开便捷函数
# ──────────────────────────────────────────────────────────────────────────────

def call_tool(name: str, inputs: dict[str, Any] | None = None) -> ToolResult:
    """动态调用已注册工具（REQ-15-03）。"""
    # 延迟导入，确保所有工具模块已加载
    _ensure_tools_loaded()
    return _registry.call(name, inputs or {})


def list_tools(tags: list[str] | None = None) -> list[ToolMeta]:
    """列出所有已注册工具的元数据（REQ-15-04）。"""
    _ensure_tools_loaded()
    return _registry.list(tags=tags)


_tools_loaded = False


def _ensure_tools_loaded() -> None:
    """延迟加载所有工具子模块，触发 @tool 装饰器注册。"""
    global _tools_loaded
    if _tools_loaded:
        return
    _tools_loaded = True
    import importlib
    _submodules = [
        "openguard.tools.fs.read",
        "openguard.tools.fs.hash",
        "openguard.tools.fs.ignore",
        "openguard.tools.fs.search",
        "openguard.tools.runtime.unity",
        "openguard.tools.runtime.process",
        "openguard.tools.analysis.symbols",
    ]
    for mod in _submodules:
        try:
            importlib.import_module(mod)
        except ImportError:
            pass
