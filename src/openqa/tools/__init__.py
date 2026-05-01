"""工具模块公开 API（REQ-15）。

用法：
  # 1. 直接导入调用（CLI 内部，零额外开销）
  from openqa.tools.fs.hash import file_hash
  h = file_hash("/path/to/file.py")

  # 2. 动态调用（Agent / MCP）
  from openqa.tools import call_tool, list_tools
  result = call_tool("fs.file_hash", {"path": "/path/to/file.py"})
  if result.ok:
      print(result.data)          # "a3f9..."
  else:
      print(result.error)

  # 3. 列出可用工具
  tools = list_tools(tags=["fs"])
"""
from openqa.tools.registry import (
    ToolResult,
    ToolMeta,
    tool,
    call_tool,
    list_tools,
    get_registry,
)

__all__ = [
    "ToolResult",
    "ToolMeta",
    "tool",
    "call_tool",
    "list_tools",
    "get_registry",
]
