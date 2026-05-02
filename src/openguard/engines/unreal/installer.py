"""OpenGuard Unreal Engine 适配层（占位，待实现）。"""
from __future__ import annotations
from pathlib import Path


class UnrealInstaller:
    """Unreal Engine 安装器（待实现）。"""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def install(self):
        raise NotImplementedError("Unreal Engine 支持尚未实现")

    def is_installed(self) -> bool:
        return False
