"""从 DetectionResult 生成 openguard/config.yaml。

config.yaml 是后续 new、continue、apply 步骤统一消费的项目测试画像。
所有自动推断字段必须记录 confidence、detected_from、decided_by，
以便 Agent 和用户审计或覆盖各项决策。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from openguard.setup.detector import DetectionResult, CONFIDENCE_HIGH, CONFIDENCE_MEDIUM


# ──────────────────────────────────────────────────────────────────────────────
# YAML 序列化辅助
# ──────────────────────────────────────────────────────────────────────────────

def _represent_str_literal(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """多行字符串使用 literal block 样式（|）。"""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _OpenGuardDumper(yaml.Dumper):
    pass


_OpenGuardDumper.add_representer(str, _represent_str_literal)


def _dump(data: Any) -> str:
    return yaml.dump(
        data,
        Dumper=_OpenGuardDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def build_config(
    result: DetectionResult,
    ai_hosts: list[str],
    gate: str = "local",
    user_inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """将 DetectionResult 转换为 config.yaml 数据结构。

    user_inputs: init 时用户交互式填写的 missing 字段答案，
                 key 为 missing 名称（如 "unity.editor_path"），value 为用户输入。
    """
    user_inputs = user_inputs or {}
    pt = result.project_type
    rt = result.runtime
    auto = result.automation

    # ── project ───────────────────────────────────────────────────────────────
    project: dict[str, Any] = {
        "type": pt.value,
        "confidence": pt.confidence,
        "detected_from": pt.detected_from,
        "root": ".",
        "languages": result.languages,
        "frameworks": result.frameworks,
    }

    # 类型特定附加字段（如 unity_version、mixed 的 sub_projects）
    for k, v in result.extra.items():
        if v is not None:
            project[k] = v

    # ── scan ──────────────────────────────────────────────────────────────────
    scan_include, scan_exclude = _scan_paths_for_type(pt.value)
    scan: dict[str, Any] = {
        "scope": "auto",
        "include": scan_include,
        "exclude": scan_exclude,
    }

    # ── runtime ───────────────────────────────────────────────────────────────
    runtime: dict[str, Any] = {
        "status": rt.status,
        "mode": rt.mode,
        "confidence": rt.confidence,
        "decided_by": rt.decided_by,
        "evidence": rt.evidence,
        "startup_timeout_seconds": rt.startup_timeout_seconds,
    }
    if rt.missing:
        runtime["missing"] = rt.missing
    runtime["health_check"] = {"type": "log-pattern", "pattern": None}

    # 将 init 时用户填入的字段直接写进 runtime（去除 missing 状态）
    # key 格式如 "unity.editor_path" → runtime["unity_editor_path"]
    # 以及 control_channel 相关字段
    still_missing: list[str] = list(rt.missing)
    for raw_key, value in user_inputs.items():
        if not value:
            continue
        # unity.editor_path → unity_editor_path
        config_key = raw_key.replace(".", "_")
        runtime[config_key] = value
        # 从 missing 中移除已填写的项
        if raw_key in still_missing:
            still_missing.remove(raw_key)
    if still_missing:
        runtime["missing"] = still_missing
    elif "missing" in runtime:
        del runtime["missing"]
    if not still_missing:
        runtime["status"] = "complete"

    # ── automation ────────────────────────────────────────────────────────────
    automation: dict[str, Any] = {
        "control_channel": {
            "type": auto.control_channel_type,
            "confidence": auto.confidence,
        },
        "fallback": auto.fallback,
        # REQ-15-03：前置路径实现模式（white-box 优先）
        "precondition_mode": "white-box",
    }
    if auto.url_env:
        automation["control_channel"]["url_env"] = auto.url_env

    auto_still_missing: list[str] = list(auto.missing)
    for raw_key, value in user_inputs.items():
        if not value:
            continue
        if raw_key in auto_still_missing:
            config_key = raw_key.replace(".", "_")
            automation["control_channel"][config_key] = value
            auto_still_missing.remove(raw_key)
    if auto_still_missing:
        automation["missing"] = auto_still_missing

    # ── evidence ──────────────────────────────────────────────────────────────
    evidence: dict[str, Any] = {
        "collect": result.evidence_collect,
        "decided_by": "auto",
    }
    if result.log_paths:
        evidence["log_paths"] = result.log_paths

    # ── defaults ──────────────────────────────────────────────────────────────
    test_suite_default = _default_test_suite(pt.confidence)
    defaults: dict[str, Any] = {
        "gate": gate,
        "test_suite": test_suite_default,
        "review_level": "changed",
        "timeout_seconds": 300,
        "max_parallel": 2,
    }

    # ── reports.retention（REQ-02-12）──────────────────────────────────────────
    # suite 执行保留策略；change 执行记录跟随 change 归档，不受此配置影响。
    reports: dict[str, Any] = {
        "retention": {
            "suite_runs_max": 20,       # 每个套件最多保留的历史执行次数
            "suite_runs_days": 90,      # 超过此天数的套件执行可被清理（0 = 不按天清理）
        },
    }

    # ── unknowns ──────────────────────────────────────────────────────────────
    config: dict[str, Any] = {
        "schema_version": "openguard/config/v1",
        "project": project,
        "ai_hosts": ai_hosts or ["codebuddy"],
        "scan": scan,
        "runtime": runtime,
        "automation": automation,
        "evidence": evidence,
        "defaults": defaults,
        "reports": reports,
    }
    if result.unknowns:
        config["unknowns"] = result.unknowns

    return config


def write_config(config: dict[str, Any], openguard_dir: Path) -> Path:
    """将 config.yaml 写入 *openguard_dir*，返回写入路径。"""
    openguard_dir.mkdir(parents=True, exist_ok=True)
    config_path = openguard_dir / "config.yaml"
    config_path.write_text(_dump(config), encoding="utf-8")
    return config_path


def load_config(openguard_dir: Path) -> dict[str, Any]:
    """加载并返回 config.yaml 字典，文件不存在时抛出 FileNotFoundError。"""
    config_path = openguard_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"未找到 openguard/config.yaml：{config_path}。请先运行 `openguard init`。"
        )
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _scan_paths_for_type(project_type: str) -> tuple[list[str], list[str]]:
    """根据项目类型返回（include, exclude）路径列表。"""
    excludes_common = [
        "node_modules/", ".git/", "openguard/", "openspec/",
        "*.lock", "*.log",
    ]
    mapping: dict[str, tuple[list[str], list[str]]] = {
        "unity": (
            ["Assets/", "Packages/", "ProjectSettings/"],
            excludes_common + ["Library/", "Temp/", "Logs/", "obj/"],
        ),
        "unreal": (
            ["Source/", "Config/", "Content/"],
            excludes_common + ["Binaries/", "Intermediate/", "Saved/", "DerivedDataCache/"],
        ),
        "web": (
            ["src/", "app/", "pages/", "components/"],
            excludes_common + ["dist/", "build/", ".next/", "coverage/"],
        ),
        "webgl": (
            ["src/", "Assets/"],
            excludes_common + ["Build/", "Temp/", "Library/"],
        ),
        "backend": (
            ["."],
            excludes_common + ["__pycache__/", "*.pyc", ".venv/", "venv/", "target/", "bin/", "obj/"],
        ),
        "api": (
            ["."],
            excludes_common + ["__pycache__/", ".venv/", "venv/"],
        ),
        "web-game": (
            ["src/", "Assets/"],
            excludes_common + ["Build/", "Temp/", "Library/"],
        ),
        # mixed：扫描全部，子项目探测器负责细化
        "mixed": (
            ["."],
            excludes_common + ["Library/", "Temp/", "Binaries/", "Intermediate/",
                                "__pycache__/", ".venv/", "venv/", "node_modules/"],
        ),
    }
    return mapping.get(project_type, (["."], excludes_common))


def _default_test_suite(confidence: str) -> str:
    # 默认使用最保守的 smoke 套件
    return "smoke"
