"""工作区目录辅助函数：定位 openqa/、创建子目录、检测初始化状态。"""
from __future__ import annotations

import os
from pathlib import Path


OPENQA_DIR = "openqa"


def find_openqa_dir(start: str | Path | None = None) -> Path | None:
    """从 *start*（默认 cwd）向上查找 openqa/ 目录。

    找到则返回绝对路径，否则返回 None。
    """
    current = Path(start).resolve() if start else Path.cwd().resolve()
    for directory in [current, *current.parents]:
        candidate = directory / OPENQA_DIR
        if candidate.is_dir():
            return candidate
    return None


def require_openqa_dir(start: str | Path | None = None) -> Path:
    """同 find_openqa_dir，但找不到时抛出 RuntimeError。"""
    result = find_openqa_dir(start)
    if result is None:
        raise RuntimeError(
            "未找到 openqa/ 目录，请先运行 `openqa init`。"
        )
    return result


def get_openqa_dir(project_root: str | Path) -> Path:
    """返回 *project_root* 下的 openqa/ 路径（目录不一定已存在）。"""
    return Path(project_root).resolve() / OPENQA_DIR


def ensure_subdirs(openqa_dir: Path) -> None:
    """在 openqa/ 下创建所有标准子目录（如已存在则跳过）。

    目录结构（REQ-02-02 / REQ-02-03 / REQ-02-04 / REQ-02-05 / REQ-02-06）：
      openqa/
        commands/           – /oqa:* slash command fallback 目录（AI 宿主未检测到时使用）
        changes/            – 每个 QA change 的工作区
        artifacts/          – 工具生成的索引、delta、矩阵、overlay（REQ-02-03）
        reports/            – 执行报告，按执行来源分层（REQ-02-04）
          suites/           –   套件执行：suites/<name>/<run-id>/
          changes/          –   change 执行：changes/<change-id>/<run-id>/
        baselines/          – 截图 / 状态 / 性能基线（REQ-02-05）
        knowledge/          – 长期可复用项目知识（REQ-02-06）
        test_assets/        – 跨 change 稳定复用的测试脚本和数据（REQ-02-10）
          scripts/          –   已验证脚本（含 .meta.yaml 锚点）
          setup_paths/      –   已验证的前置路径脚本（REQ-15-01）
          fixtures/         –   通用测试数据
        suites/             – 全局可复用测试套件定义（REQ-02-11）
          smoke/
          regression/
          requirement/
          full/
    """
    # 顶层标准子目录
    top_level = (
        "commands",
        "changes",
        "artifacts",
        "baselines",
        "knowledge",
    )
    for sub in top_level:
        (openqa_dir / sub).mkdir(parents=True, exist_ok=True)

    # reports/ 分层结构（REQ-02-06）
    for sub in ("reports/suites", "reports/changes"):
        (openqa_dir / sub).mkdir(parents=True, exist_ok=True)

    # test_assets/ 子目录（REQ-02-12 / REQ-13-27）
    for sub in ("test_assets/scripts", "test_assets/fixtures", "test_assets/setup_paths"):
        (openqa_dir / sub).mkdir(parents=True, exist_ok=True)

    # suites/ 标准套件目录（REQ-02-13）
    for suite in ("smoke", "regression", "requirement", "full"):
        (openqa_dir / "suites" / suite).mkdir(parents=True, exist_ok=True)


def ensure_run_dir(
    openqa_dir: Path,
    run_id: str,
    *,
    change_id: str | None = None,
    suite_name: str | None = None,
) -> Path:
    """创建并返回一次执行的独立报告目录（REQ-02-06）。

    - suite 执行：openqa/reports/suites/<suite_name>/<run_id>/
    - change 执行：openqa/reports/changes/<change_id>/<run_id>/
    每次执行独立存储，不覆盖历史记录。
    """
    if suite_name:
        run_dir = openqa_dir / "reports" / "suites" / suite_name / run_id
    elif change_id:
        run_dir = openqa_dir / "reports" / "changes" / change_id / run_id
    else:
        raise ValueError("ensure_run_dir 需要 change_id 或 suite_name 之一")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def ensure_change_subdirs(change_dir: Path) -> None:
    """在 change 工作区下创建标准子目录（REQ-02-04）。

    每个 change 工作区包含：
      test_scripts/    – 本次 change 生成的测试脚本草稿
      test_fixtures/   – 本次 change 专用的测试数据和前置状态
    """
    for sub in ("test_scripts", "test_fixtures"):
        (change_dir / sub).mkdir(parents=True, exist_ok=True)


def is_initialized(project_root: str | Path) -> bool:
    """若 *project_root* 下存在 openqa/config.yaml 则返回 True。"""
    config = Path(project_root).resolve() / OPENQA_DIR / "config.yaml"
    return config.is_file()
