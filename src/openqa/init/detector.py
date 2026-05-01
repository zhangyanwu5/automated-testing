"""项目类型探测器。

扫描当前工作目录中的标志性文件/目录，生成 DetectionResult，
记录项目类型、置信度、证据，以及无法可靠推断的 unknowns。

设计原则：
- 纯确定性逻辑，不调用大模型。
- 只返回结构化数据，由调用方决定如何展示或追问。
- 每个探测字段记录 detected_from（证据路径列表）和 confidence（high/medium/low）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openqa.tools.fs.read import read_text as _read_text_tool
from openqa.tools.fs.search import find_files as _find_files_tool
from openqa.tools.runtime.unity import find_unity_editors as _find_unity_editors_tool


CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

PROJECT_TYPE_WEB = "web"
PROJECT_TYPE_WEBGL = "webgl"
PROJECT_TYPE_WEB_GAME = "web-game"
PROJECT_TYPE_UNITY = "unity"
PROJECT_TYPE_UNREAL = "unreal"
PROJECT_TYPE_BACKEND = "backend"
PROJECT_TYPE_API = "api"
PROJECT_TYPE_MIXED = "mixed"
PROJECT_TYPE_UNKNOWN = "unknown"


@dataclass
class FieldEvidence:
    value: Any
    confidence: str
    detected_from: list[str] = field(default_factory=list)
    decided_by: str = "auto"


@dataclass
class RuntimeProfile:
    status: str = "incomplete"           # incomplete | complete
    mode: str | None = None              # editor-playmode | standalone | browser | cli | …
    confidence: str = CONFIDENCE_LOW
    decided_by: str = "auto"
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    startup_timeout_seconds: int = 60
    # 探测到的 editor/runtime 候选路径列表（供 init 多选）
    detected_editors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AutomationProfile:
    control_channel_type: str | None = None
    url_env: str | None = None
    confidence: str = CONFIDENCE_LOW
    fallback: str = "manual-or-blackbox"
    missing: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    """单次项目根目录探测的完整结果。"""

    project_type: FieldEvidence
    languages: list[str]
    frameworks: list[str]
    runtime: RuntimeProfile
    automation: AutomationProfile
    evidence_collect: list[str]
    log_paths: list[str]
    unknowns: list[str] = field(default_factory=list)

    # 类型特定的附加字段，以自由字典形式存储（如 unity_version、sub_projects）
    extra: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _exists(*parts: str, root: Path) -> bool:
    return (root / Path(*parts)).exists()


def _find_first(patterns: list[str], root: Path) -> list[str]:
    """返回匹配任意 pattern 的已存在相对路径列表（委托给 tools）。"""
    return _find_files_tool(root=root, patterns=patterns)


def _read_text_safe(path: Path) -> str:
    """以文本模式读取文件，出错时返回空字符串（委托给 tools）。"""
    return _read_text_tool(path) or ""


# ──────────────────────────────────────────────────────────────────────────────
# 各项目类型探测器
# ──────────────────────────────────────────────────────────────────────────────


def _find_unity_editors(project_root: Path, unity_version: str | None) -> list[dict[str, str]]:
    """搜索本机 Unity Editor（委托给 tools.runtime.unity）。"""
    return _find_unity_editors_tool(str(project_root), unity_version)


def _detect_unity(root: Path) -> DetectionResult | None:
    has_assets = _exists("Assets", root=root)
    has_project_settings = _exists("ProjectSettings", root=root)
    if not (has_assets and has_project_settings):
        return None

    evidence: list[str] = ["Assets/", "ProjectSettings/"]
    version: str | None = None
    version_file = root / "ProjectSettings" / "ProjectVersion.txt"
    if version_file.exists():
        evidence.append("ProjectSettings/ProjectVersion.txt")
        for line in _read_text_safe(version_file).splitlines():
            m = re.match(r"m_EditorVersion:\s*(.+)", line)
            if m:
                version = m.group(1).strip()
                break

    # 检测测试框架
    manifest = root / "Packages" / "manifest.json"
    has_utf = False
    if manifest.exists():
        evidence.append("Packages/manifest.json")
        content = _read_text_safe(manifest)
        if "com.unity.test-framework" in content:
            has_utf = True

    # 检测 PlayMode / EditMode 测试
    play_mode_tests = _find_first(["Assets/**/*Tests*", "Assets/**/*Test*"], root=root)
    tests_detected = []
    if play_mode_tests:
        tests_detected.append("PlayMode")

    # 检测场景文件
    scenes = _find_first(["Assets/**/*.unity"], root=root)

    # 搜索本机 Unity Editor（含编译版）
    detected_editors = _find_unity_editors(root, version)

    extra: dict[str, Any] = {
        "unity_version": version,
        "test_framework": "Unity Test Framework" if has_utf else None,
        "tests_detected": tests_detected,
        "scenes_detected": len(scenes),
    }
    if detected_editors:
        extra["detected_editors"] = detected_editors

    # 如果探测到唯一编辑器，运行时状态可视为 complete（仍需用户确认）
    runtime_missing: list[str] = []
    if not detected_editors:
        runtime_missing = ["unity.editor_path"]

    runtime = RuntimeProfile(
        status="incomplete",
        mode="editor-playmode",
        confidence=CONFIDENCE_MEDIUM,
        decided_by="auto",
        evidence=[
            "Packages/manifest.json contains com.unity.test-framework",
            "PlayMode tests detected",
        ] if has_utf else ["Assets/ and ProjectSettings/ present"],
        missing=runtime_missing,
        detected_editors=detected_editors,
    )

    automation = AutomationProfile(
        control_channel_type="editor-playmode",
        confidence=CONFIDENCE_HIGH,
        missing=[],
    )

    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_UNITY,
            confidence=CONFIDENCE_HIGH,
            detected_from=evidence,
        ),
        languages=["csharp"],
        frameworks=["unity"],
        runtime=runtime,
        automation=automation,
        evidence_collect=["logs", "screenshots", "video", "state_snapshot"],
        log_paths=["Logs/"],
        extra=extra,
    )


def _detect_unreal(root: Path) -> DetectionResult | None:
    uproject_files = list(root.glob("*.uproject"))
    if not uproject_files:
        return None

    evidence = [uproject_files[0].name]
    has_source = _exists("Source", root=root)
    has_config = _exists("Config", root=root)
    if has_source:
        evidence.append("Source/")
    if has_config:
        evidence.append("Config/")

    runtime = RuntimeProfile(
        status="incomplete",
        mode="editor-automation",
        confidence=CONFIDENCE_MEDIUM,
        decided_by="auto",
        evidence=evidence,
        missing=["unreal.editor_path"],
    )
    automation = AutomationProfile(
        control_channel_type="console-command",
        confidence=CONFIDENCE_LOW,
        missing=["automation_spec_path"],
    )
    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_UNREAL,
            confidence=CONFIDENCE_HIGH,
            detected_from=evidence,
        ),
        languages=["cpp", "blueprints"],
        frameworks=["unreal"],
        runtime=runtime,
        automation=automation,
        evidence_collect=["logs", "screenshots", "state_snapshot"],
        log_paths=["Saved/Logs/"],
    )


def _detect_webgl(root: Path) -> DetectionResult | None:
    """检测 WebGL 游戏构建或项目。"""
    webgl_build_dirs = _find_first(
        ["Build/WebGL", "WebGL", "webgl", "dist/webgl", "build/webgl"],
        root=root,
    )
    # 同时检测 .wasm 文件
    wasm_files = _find_first(["**/*.wasm"], root=root)
    if not (webgl_build_dirs or wasm_files):
        return None

    evidence = webgl_build_dirs + wasm_files[:2]
    runtime = RuntimeProfile(
        status="incomplete",
        mode="browser-webgl",
        confidence=CONFIDENCE_MEDIUM,
        decided_by="auto",
        evidence=evidence,
        missing=["browser_entry_url"],
        startup_timeout_seconds=60,
    )
    automation = AutomationProfile(
        control_channel_type="playwright+js-bridge",
        url_env="OPENQA_WEBGL_URL",
        confidence=CONFIDENCE_LOW,
        missing=["webgl_entry_url", "js_bridge_endpoint"],
    )
    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_WEBGL,
            confidence=CONFIDENCE_MEDIUM,
            detected_from=evidence,
        ),
        languages=[],
        frameworks=[],
        runtime=runtime,
        automation=automation,
        evidence_collect=["logs", "screenshots", "video", "network"],
        log_paths=[],
    )


def _detect_web(root: Path) -> DetectionResult | None:
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return None

    evidence = ["package.json"]
    content = _read_text_safe(pkg_json)
    frameworks: list[str] = []
    languages: list[str] = []
    start_script: str | None = None

    # 从 package.json 内容检测前端框架
    for fw in ("react", "vue", "angular", "svelte", "next", "nuxt", "vite"):
        if f'"{fw}"' in content or f'"@{fw}/' in content:
            frameworks.append(fw)
    for lang_marker, lang in [("typescript", "typescript"), ('"ts"', "typescript")]:
        if lang_marker in content and lang not in languages:
            languages.append(lang)
    if not languages:
        languages.append("javascript")

    # 检测 Playwright / Cypress
    automation_type = "playwright"
    if "playwright" in content:
        evidence.append("package.json contains playwright")
    elif "cypress" in content:
        automation_type = "cypress"
        evidence.append("package.json contains cypress")

    # 尝试提取 start 脚本
    m = re.search(r'"start"\s*:\s*"([^"]+)"', content)
    if m:
        start_script = m.group(1)

    runtime = RuntimeProfile(
        status="incomplete" if not start_script else "complete",
        mode="browser",
        confidence=CONFIDENCE_MEDIUM,
        decided_by="auto",
        evidence=evidence,
        missing=[] if start_script else ["app_start_url"],
        startup_timeout_seconds=30,
    )
    automation = AutomationProfile(
        control_channel_type=automation_type,
        url_env="OPENQA_APP_URL",
        confidence=CONFIDENCE_MEDIUM,
        missing=[] if start_script else ["app_start_url"],
    )
    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_WEB,
            confidence=CONFIDENCE_HIGH,
            detected_from=evidence,
        ),
        languages=languages,
        frameworks=frameworks,
        runtime=runtime,
        automation=automation,
        evidence_collect=["logs", "screenshots", "network"],
        log_paths=[],
        extra={"start_script": start_script},
    )


def _detect_backend(root: Path) -> DetectionResult | None:
    """检测后端 / API 项目。"""
    indicators: list[str] = []

    # Python
    for f in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"):
        if _exists(f, root=root):
            indicators.append(f)

    # Go
    if _exists("go.mod", root=root):
        indicators.append("go.mod")

    # Java / Kotlin
    for f in ("pom.xml", "build.gradle", "build.gradle.kts"):
        if _exists(f, root=root):
            indicators.append(f)

    # Node 项目已由 _detect_web 处理，此处不重复
    if not indicators:
        return None

    evidence = indicators[:3]
    # 检测 OpenAPI / gRPC 定义
    openapi = _find_first(
        ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json", "**/*.proto"],
        root=root,
    )
    if openapi:
        evidence += openapi[:2]

    runtime = RuntimeProfile(
        status="incomplete",
        mode="cli",
        confidence=CONFIDENCE_MEDIUM,
        decided_by="auto",
        evidence=evidence,
        missing=["service_start_command", "health_check_url"],
    )
    automation = AutomationProfile(
        control_channel_type="http-api",
        url_env="OPENQA_API_BASE_URL",
        confidence=CONFIDENCE_LOW,
        missing=["api_base_url"],
    )
    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_BACKEND,
            confidence=CONFIDENCE_MEDIUM,
            detected_from=evidence,
        ),
        languages=[],
        frameworks=[],
        runtime=runtime,
        automation=automation,
        evidence_collect=["logs", "network"],
        log_paths=[],
    )


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

# 探测器优先级：越具体的越靠前
_DETECTORS = [
    _detect_unity,
    _detect_unreal,
    _detect_webgl,
    _detect_web,
    _detect_backend,
]


def detect_project(project_root: str | Path) -> DetectionResult:
    """依次运行所有探测器，返回最佳匹配结果。

    - 无匹配：返回 unknown 类型。
    - 单一匹配：直接返回。
    - 多重匹配：调用 _build_mixed_result 生成 mixed 类型画像（REQ-01-12）。
    """
    root = Path(project_root).resolve()
    results: list[DetectionResult] = []

    for detector in _DETECTORS:
        result = detector(root)
        if result is not None:
            results.append(result)

    if not results:
        # 未识别项目，收集顶层文件名作为证据
        unknown_evidence = [
            str(p.name) for p in sorted(root.iterdir())[:10]
            if not p.name.startswith(".")
        ]
        return DetectionResult(
            project_type=FieldEvidence(
                value=PROJECT_TYPE_UNKNOWN,
                confidence=CONFIDENCE_LOW,
                detected_from=unknown_evidence,
            ),
            languages=[],
            frameworks=[],
            runtime=RuntimeProfile(
                status="incomplete",
                missing=["project_type", "runtime_mode"],
            ),
            automation=AutomationProfile(missing=["control_channel_type"]),
            evidence_collect=["logs"],
            log_paths=[],
            unknowns=[
                "project.type",
                "runtime.mode",
                "automation.control_channel",
            ],
        )

    if len(results) > 1:
        # 多类型并存 → 构建 mixed 画像（REQ-01-12）
        return _build_mixed_result(results)

    return results[0]


# ──────────────────────────────────────────────────────────────────────────────
# Mixed 项目画像构建
# ──────────────────────────────────────────────────────────────────────────────

def _build_mixed_result(results: list[DetectionResult]) -> DetectionResult:
    """将多个单类型探测结果合并为 MIXED DetectionResult。

    记录内容（REQ-01-12）：
    - 子项目列表（类型、置信度、证据、执行顺序建议）
    - 合并后的语言/框架列表
    - 候选执行顺序（置信度高者优先）
    - unknowns：跨项目端到端环境、执行优先级
    """
    # 置信度由高到低排序，决定建议执行顺序
    conf_order = [CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW]
    results_sorted = sorted(
        results,
        key=lambda r: conf_order.index(r.project_type.confidence),
    )

    sub_projects: list[dict[str, Any]] = []
    all_evidence: list[str] = []
    all_languages: list[str] = []
    all_frameworks: list[str] = []
    all_evidence_collect: list[str] = []

    for i, r in enumerate(results_sorted):
        sub_projects.append({
            "type": r.project_type.value,
            "confidence": r.project_type.confidence,
            "detected_from": r.project_type.detected_from,
            "execution_order": i + 1,  # 建议顺序，非强制
        })
        all_evidence.extend(r.project_type.detected_from)
        for lang in r.languages:
            if lang not in all_languages:
                all_languages.append(lang)
        for fw in r.frameworks:
            if fw not in all_frameworks:
                all_frameworks.append(fw)
        for ev in r.evidence_collect:
            if ev not in all_evidence_collect:
                all_evidence_collect.append(ev)

    sub_types = [s["type"] for s in sub_projects]

    # 以置信度最高的子项目 runtime 作为主 runtime
    primary_runtime = results_sorted[0].runtime
    primary_automation = results_sorted[0].automation

    unknowns = [
        "mixed.default_change_entry: which sub-project is the primary change entry?",
        "mixed.e2e_environment: cross-project end-to-end environment configuration details",
        f"mixed.execution_priority: confirm or adjust suggested execution order {sub_types}",
    ]

    return DetectionResult(
        project_type=FieldEvidence(
            value=PROJECT_TYPE_MIXED,
            confidence=CONFIDENCE_MEDIUM,
            detected_from=list(dict.fromkeys(all_evidence))[:6],  # 去重并限制数量
            decided_by="auto",
        ),
        languages=all_languages,
        frameworks=all_frameworks,
        runtime=primary_runtime,
        automation=primary_automation,
        evidence_collect=all_evidence_collect,
        log_paths=[],
        unknowns=unknowns,
        extra={
            "sub_projects": sub_projects,
            "execution_order_candidate": sub_types,
        },
    )
