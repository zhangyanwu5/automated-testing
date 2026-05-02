"""OpenGuard 引擎适配层。

每个子模块对应一种游戏引擎，提供：
- installer.py  : ``openguard init`` 阶段在被测项目中安装必要文件
- assets/       : 需要部署到被测项目的模板文件（C#、蓝图等）

使用方式::

    from openguard.engines import get_installer
    installer = get_installer("unity")       # → UnityInstaller
    installer.install(project_root)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_installer(engine: str, project_root: Path):
    """根据引擎类型返回对应的 Installer 实例。

    支持的 engine 值：
    - ``"unity"``   → UnityInstaller
    - ``"unreal"``  → UnrealInstaller（待实现）
    """
    if engine == "unity":
        from openguard.engines.unity.installer import UnityInstaller
        return UnityInstaller(project_root)
    if engine == "unreal":
        from openguard.engines.unreal.installer import UnrealInstaller
        return UnrealInstaller(project_root)
    return None
