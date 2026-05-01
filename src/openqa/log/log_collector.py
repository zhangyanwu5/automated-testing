"""日志采集策略（REQ-13-10 / REQ-13-11 / REQ-13-12）。

三层策略：
  第一层：已有日志采集 — 采集目标应用正常输出的日志，不修改项目代码（REQ-13-10）。
  第二层：协商增强建议 — 当已有日志不足时，输出日志增强建议，不自动修改代码（REQ-13-11）。
  第三层：debug build 配置 — 生成带额外日志开关的 debug 构建配置，与生产配置隔离（REQ-13-12）。

OpenQA 只做：
- 采集已有日志输出到 events.jsonl
- 生成建议文件，不写入目标项目代码
- debug 配置与主分支隔离，测试后无需手动还原
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from openqa.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 第一层：已有日志采集（REQ-13-10）
# ──────────────────────────────────────────────────────────────────────────────

class LogCollector:
    """采集目标应用日志，过滤并摘要后写入 events.jsonl（REQ-13-10）。

    不修改目标项目代码。只读取 config.yaml 中配置的日志路径和格式。
    """

    def __init__(self, config: dict[str, Any], run_dir: Path):
        self.config = config
        self.run_dir = run_dir
        self._log_sources: list[dict[str, Any]] = (
            config.get("evidence", {}).get("log_sources", [])
        )

    def collect(self, project_root: Path) -> list[dict[str, Any]]:
        """采集所有配置的日志源，返回事件列表。"""
        events: list[dict[str, Any]] = []

        for source in self._log_sources:
            log_path = project_root / source.get("path", "")
            if not log_path.exists():
                events.append(_make_event(
                    "log_source_missing",
                    f"日志文件不存在：{log_path}",
                    level="warn",
                    source=str(log_path),
                ))
                continue

            fmt = source.get("format", "plaintext")
            filter_patterns = source.get("filter_patterns", [])

            try:
                raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as e:
                events.append(_make_event("log_read_error", str(e), level="error",
                                         source=str(log_path)))
                continue

            # 过滤 + 摘要
            collected = _filter_log_lines(raw_lines, filter_patterns, fmt)
            for entry in collected:
                events.append(_make_event(
                    "log_line",
                    entry["message"],
                    level=entry.get("level", "info"),
                    source=str(log_path),
                    raw=entry.get("raw", ""),
                    timestamp=entry.get("timestamp", ""),
                ))

        return events

    def write_events(self, events: list[dict[str, Any]]) -> Path:
        """将事件追加到 run_dir/events.jsonl（REQ-13-10）。"""
        events_path = self.run_dir / "events.jsonl"
        with events_path.open("a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return events_path


def _filter_log_lines(
    lines: list[str],
    filter_patterns: list[str],
    fmt: str,
) -> list[dict[str, Any]]:
    """过滤日志行，提取有意义的内容。

    fmt: 'plaintext' / 'json' / 'unity' / 'unreal'
    filter_patterns: 正则表达式列表，匹配的行被保留
    """
    if not lines:
        return []

    result: list[dict[str, Any]] = []
    compiled = [re.compile(p, re.IGNORECASE) for p in filter_patterns] if filter_patterns else []

    # 默认：保留 ERROR / WARN / ASSERT / Exception / [Test] 等关键行
    default_patterns = [
        re.compile(r"(error|exception|assert|warn|fail|crash|unity.*test|unreal.*spec)", re.IGNORECASE),
    ]

    for line in lines:
        if not line.strip():
            continue

        # 应用用户过滤模式
        if compiled:
            if not any(p.search(line) for p in compiled):
                continue
        else:
            # 默认过滤：仅保留关键行
            if not any(p.search(line) for p in default_patterns):
                continue

        entry: dict[str, Any] = {"raw": line, "message": line.strip()}

        # 格式特定解析
        if fmt == "json":
            try:
                data = json.loads(line)
                entry["message"] = data.get("message") or data.get("msg") or line.strip()
                entry["level"] = data.get("level") or data.get("severity") or "info"
                entry["timestamp"] = data.get("timestamp") or data.get("time") or ""
            except Exception:
                pass
        elif fmt == "unity":
            # Unity 格式：[时间戳] 级别: 消息
            m = re.match(r"\[([^\]]+)\]\s*(ERROR|WARN|INFO|DEBUG|ASSERT)?:?\s*(.*)", line, re.IGNORECASE)
            if m:
                entry["timestamp"] = m.group(1)
                entry["level"] = (m.group(2) or "info").lower()
                entry["message"] = m.group(3)
        elif fmt == "unreal":
            # Unreal 格式：[时间戳][frame] LogCategory: Verbosity: 消息
            m = re.match(r"\[.*?\]\s*\[.*?\]\s*\w+:\s*(Error|Warning|Display|Log|Verbose)?:?\s*(.*)", line, re.IGNORECASE)
            if m:
                lvl = (m.group(1) or "info").lower()
                entry["level"] = "error" if lvl == "error" else ("warn" if lvl == "warning" else "info")
                entry["message"] = m.group(2)

        # 推断级别
        if "level" not in entry:
            low = line.lower()
            if any(k in low for k in ("error", "exception", "crash", "assert fail")):
                entry["level"] = "error"
            elif any(k in low for k in ("warn", "warning")):
                entry["level"] = "warn"
            else:
                entry["level"] = "info"

        result.append(entry)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 第二层：日志增强建议（REQ-13-11）
# ──────────────────────────────────────────────────────────────────────────────

def generate_log_enhancement_suggestions(
    assertion_gaps: list[str],
    project_type: str,
    change_dir: Path,
) -> dict[str, Any]:
    """当已有日志不足以支撑特定断言分析时，生成日志增强建议（REQ-13-11）。

    不修改目标项目代码。建议写入 log_enhancement_suggestions.md，
    由开发者决定是否采纳。
    """
    suggestions: list[dict[str, Any]] = []

    for gap in assertion_gaps:
        suggestion: dict[str, Any] = {
            "gap": gap,
            "suggestion_type": "协商增强",  # 不自动执行
            "write_to_project": False,      # 不修改项目代码（REQ-13-11）
        }

        # 根据项目类型给出针对性建议
        if project_type == "unity":
            suggestion["suggestions"] = [
                f"在相关脚本中添加 Debug.Log(\"{gap}: \" + state) 日志",
                "开启 Unity Test Framework 的 verbose 模式",
                "在 config.yaml 的 evidence.log_sources 中配置 Unity 日志路径",
            ]
            suggestion["where"] = "开发者在相关 Unity 脚本中手动添加"
        elif project_type in ("unreal", "unreal-game"):
            suggestion["suggestions"] = [
                f"使用 UE_LOG(LogGame, Display, TEXT(\"{gap}: %s\"), *StateStr)",
                "在 config.yaml 中配置 Unreal 日志路径（Saved/Logs/）",
            ]
            suggestion["where"] = "开发者在相关 UE 模块中手动添加"
        elif project_type in ("web", "webgl", "web-game"):
            suggestion["suggestions"] = [
                f"在关键操作处添加 console.log(\"{gap}:\", state)",
                "在 Playwright 脚本中捕获 page.on('console') 事件",
                "在 config.yaml 中设置 automation.capture_console_logs: true",
            ]
            suggestion["where"] = "开发者在相关 JS/TS 模块中手动添加，或在测试脚本中捕获"
        else:
            suggestion["suggestions"] = [
                f"在需要断言的位置添加日志输出：{gap}",
                "更新 config.yaml 的 evidence.log_sources 配置",
            ]
            suggestion["where"] = "开发者根据具体项目结构决定"

        suggestions.append(suggestion)

    # 写入建议文件
    md_lines = [
        "# 日志增强建议",
        "",
        "<!-- 由 OpenQA 自动生成，由开发者决定是否采纳。OpenQA 不会自动修改项目代码（REQ-13-11）。 -->",
        "",
    ]
    for i, s in enumerate(suggestions, 1):
        md_lines += [
            f"## 建议 {i}：{s['gap']}",
            "",
            f"**类型**：{s['suggestion_type']}",
            f"**建议执行人**：{s['where']}",
            "",
            "**具体操作**：",
        ]
        for sug in s.get("suggestions", []):
            md_lines.append(f"- {sug}")
        md_lines.append("")

    suggestion_path = change_dir / "log_enhancement_suggestions.md"
    suggestion_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "suggestion_count": len(suggestions),
        "suggestions_path": str(suggestion_path),
        "write_to_project": False,
        "suggestions": suggestions,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 第三层：debug build 配置（REQ-13-12）
# ──────────────────────────────────────────────────────────────────────────────

def generate_debug_build_config(
    project_type: str,
    openqa_dir: Path,
    extra_log_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """生成 debug build 额外日志配置（REQ-13-12）。

    不修改主分支代码；debug 配置存放在 openqa/artifacts/debug_build_config/，
    与生产配置隔离，测试完成后不需要手动还原（因为主分支未被修改）。
    """
    debug_dir = openqa_dir / "artifacts" / "debug_build_config"
    debug_dir.mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "schema_version": "openqa/debug_build_config/v1",
        "generated_at": _now_iso(),
        "project_type": project_type,
        "isolation_note": (
            "此配置仅用于 debug build，与生产配置隔离。"
            "主分支代码未被修改。测试完成后无需手动还原（REQ-13-12）。"
        ),
        "extra_log_symbols": extra_log_symbols or [],
    }

    # 项目类型特定的 debug 配置
    if project_type == "unity":
        config["unity_debug_settings"] = {
            "enable_unity_test_verbose": True,
            "log_level": "Debug",
            "additional_log_filter": extra_log_symbols or [],
            "build_target": "debug",
            "define_symbols": ["OPENQA_DEBUG", "QA_VERBOSE_LOGGING"],
        }
    elif project_type in ("unreal", "unreal-game"):
        config["unreal_debug_settings"] = {
            "log_verbosity": "Verbose",
            "log_categories": extra_log_symbols or ["LogGame"],
            "build_configuration": "Debug",
            "ini_overrides": {
                "Engine.ini": "[Core.Log]\nLogGame=Verbose",
            },
        }
    elif project_type in ("web", "webgl", "web-game"):
        config["web_debug_settings"] = {
            "capture_console": True,
            "capture_network": True,
            "verbose_websocket": True,
            "extra_log_points": extra_log_symbols or [],
        }
    elif project_type in ("backend", "api"):
        config["backend_debug_settings"] = {
            "log_level": "DEBUG",
            "structured_logging": True,
            "extra_log_modules": extra_log_symbols or [],
        }

    config_path = debug_dir / f"debug_config_{project_type}.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "config_path": str(config_path),
        "project_type": project_type,
        "write_to_project": False,  # 不修改项目代码
        "isolation": "debug_build_only",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _make_event(
    event_type: str,
    message: str,
    level: str = "info",
    source: str = "",
    raw: str = "",
    timestamp: str = "",
) -> dict[str, Any]:
    """创建标准化事件字典。"""
    ev: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": timestamp or _now_iso(),
        "level": level,
        "message": message,
    }
    if source:
        ev["source"] = source
    if raw and raw != message:
        ev["raw"] = raw
    return ev
