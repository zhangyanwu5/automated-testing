"""敏感信息扫描与 overlay 合规（REQ-10-02/05/06/07）。

敏感信息扫描：
  - 拒绝在报告、overlay、知识库中写入密钥、口令、私钥、token
  - 操作日志过滤敏感字段

Overlay 合规（REQ-10-05）：
  - 每个 overlay 必须包含 generator/generated_at/source_change/source_report/confidence

设计边界（REQ-10）：
  - OpenQA 工具进程不调用大模型
  - 测试脚本只写入 openqa/ 目录
  - 默认只读 OpenSpec，不修改
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from openqa.utils import now_iso as _now_iso


# ──────────────────────────────────────────────────────────────────────────────
# 敏感信息检测（REQ-10-06）
# ──────────────────────────────────────────────────────────────────────────────

# 常见敏感信息模式（简化实现）
_SENSITIVE_PATTERNS = [
    # API keys / tokens
    re.compile(r'(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*["\']?[\w\-/+]{8,}', re.I),
    # Private keys
    re.compile(r'-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----'),
    # Bearer tokens
    re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]{20,}'),
    # AWS-style keys
    re.compile(r'(?i)AKIA[0-9A-Z]{16}'),
    # GitHub tokens
    re.compile(r'gh[pousr]_[A-Za-z0-9]{36}'),
]

# 允许的占位符形式（环境变量引用不算敏感）
_ALLOWED_PATTERNS = [
    re.compile(r'\$\{?\w+\}?'),          # ${ENV_VAR} 或 $ENV_VAR
    re.compile(r'<\w+>'),                # <placeholder>
    re.compile(r'\*{3,}'),               # *** 掩码
    re.compile(r'ENV:[\w_]+'),           # ENV:VAR_NAME
]


def scan_sensitive(text: str) -> list[str]:
    """扫描文本中的敏感信息，返回发现列表（REQ-10-06）。"""
    findings: list[str] = []
    for pattern in _SENSITIVE_PATTERNS:
        for m in pattern.finditer(text):
            matched = m.group(0)
            # 检查是否是允许的占位符形式
            if not any(allowed.search(matched) for allowed in _ALLOWED_PATTERNS):
                findings.append(f"疑似敏感信息：{matched[:30]}…")
    return findings


def assert_no_sensitive(text: str, context: str = "") -> None:
    """若发现敏感信息则抛出 ValueError（REQ-10-06）。"""
    findings = scan_sensitive(text)
    if findings:
        raise ValueError(
            f"敏感信息扫描失败{(' (' + context + ')') if context else ''}，"
            f"拒绝写入：{findings[0]}"
        )


def redact_sensitive(text: str) -> str:
    """将文本中的敏感信息替换为 *** （REQ-10-07）。"""
    result = text
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Overlay 合规（REQ-10-05）
# ──────────────────────────────────────────────────────────────────────────────

OVERLAY_REQUIRED_FIELDS = {
    "generator", "generated_at", "source_change", "source_report", "confidence"
}


def validate_overlay(overlay: dict[str, Any]) -> list[str]:
    """校验 overlay 格式，返回缺失字段列表（REQ-10-05）。"""
    missing = [f for f in OVERLAY_REQUIRED_FIELDS if f not in overlay]
    return missing


def write_overlay(
    path: Path,
    overlay_data: dict[str, Any],
    *,
    generator: str,
    source_change: str,
    source_report: str,
    confidence: str = "medium",
) -> Path:
    """写入 report_overlay.yaml，自动注入合规字段（REQ-10-05）。"""
    overlay_data["generator"] = generator
    overlay_data["generated_at"] = _now_iso()
    overlay_data["source_change"] = source_change
    overlay_data["source_report"] = source_report
    overlay_data["confidence"] = confidence

    # 敏感信息过滤
    content = yaml.dump(overlay_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    assert_no_sensitive(content, context="overlay")

    path.write_text(content, encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Decision Log（REQ-11-04）
# ──────────────────────────────────────────────────────────────────────────────

def write_decision_log(
    change_dir: Path,
    decisions: list[dict[str, Any]],
) -> Path:
    """写入 decision_log.md（REQ-11-04）。

    记录：为什么选择这个测试套件、为什么跳过/阻断某项、豁免原因。
    """
    lines: list[str] = [
        f"# Decision Log — {change_dir.name}\n",
        "> 记录策略选择、跳过、阻断、豁免及原因（REQ-11-04）。\n",
        "| 时间 | 阶段 | 决策 | 原因 | 状态 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in decisions:
        ts = d.get("timestamp", _now_iso())[:19].replace("T", " ")
        phase = d.get("phase", "")
        decision = d.get("decision", "")
        reason = d.get("reason", "")
        status = d.get("status", "")
        lines.append(f"| {ts} | {phase} | {decision[:40]} | {reason[:60]} | {status} |")

    path = change_dir / "decision_log.md"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        # 如果已存在，追加新条目到表格末尾
        lines_to_append = lines[4:]  # 只追加数据行
        existing_lines = existing.rstrip().splitlines()
        existing_lines.extend(lines_to_append)
        path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
        return path

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def append_decision(
    change_dir: Path,
    phase: str,
    decision: str,
    reason: str,
    status: str = "recorded",
) -> None:
    """向 decision_log.md 追加一条决策记录。"""
    write_decision_log(change_dir, [{
        "timestamp": _now_iso(),
        "phase": phase,
        "decision": decision,
        "reason": reason,
        "status": status,
    }])


# ──────────────────────────────────────────────────────────────────────────────
# 设计边界检查（REQ-10）
# ──────────────────────────────────────────────────────────────────────────────

def check_script_path_boundary(script_path: str | Path, openqa_dir: Path) -> bool:
    """检查脚本路径是否在 openqa/ 内（REQ-01-11 / REQ-10）。"""
    script = Path(script_path).resolve()
    openqa = openqa_dir.resolve()
    return str(script).startswith(str(openqa))
