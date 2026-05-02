"""层二诊断日志：记录 _advance 每次推进的决策链和产物变化（per-change）。

日志文件：<change_dir>/agent_trace.jsonl
- 每条记录对应 _advance 的一个操作步骤
- 追加写入，不覆盖

每条记录结构：
{
  "ts": "ISO时间",
  "invocation_id": "本次 _advance 调用的唯一 ID（同一次调用的所有步骤共享）",
  "step": "步骤名",       // check_artifacts / auto_scan / auto_impact / auto_matrix / etc.
  "status": "ok|skip|fail",
  "phase_before": "preparing",
  "phase_after": "ready_for_apply",
  "artifact": "test_matrix.json",     // 涉及的产物（可选）
  "decision": "描述本步骤做了什么决策",
  "outputs": ["文件名"],
  "elapsed_ms": 123,
  "error": "错误信息（仅 fail 时）"
}
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


class TraceWriter:
    """_advance 推进轨迹记录器（层二）。

    用法：
        writer = get_trace_writer(change_dir)
        inv_id = writer.begin_invocation(state)
        with writer.step(inv_id, "auto_scan", artifact="snapshot.json") as s:
            # 执行操作
            s["decision"] = "scan_scope=auto"
            s["outputs"] = ["snapshot.json"]
        writer.end_invocation(inv_id, state_after)
    """

    def __init__(self, change_dir: Path):
        self._path = change_dir / "agent_trace.jsonl"

    def begin_invocation(self, state: dict[str, Any]) -> str:
        """开始一次 _advance 调用，返回 invocation_id。"""
        inv_id = uuid.uuid4().hex[:12]
        self._append({
            "invocation_id": inv_id,
            "step": "_advance:begin",
            "status": "ok",
            "phase": state.get("phase", ""),
            "agent_action": state.get("agent_action", ""),
            "missing": state.get("missing", []),
            "change_id": state.get("change_id", ""),
        })
        return inv_id

    def end_invocation(self, inv_id: str, state_after: dict[str, Any], exit_code: int = 0) -> None:
        """结束一次 _advance 调用，记录最终状态。"""
        self._append({
            "invocation_id": inv_id,
            "step": "_advance:end",
            "status": "ok" if exit_code == 0 else "fail",
            "exit_code": exit_code,
            "phase": state_after.get("phase", ""),
            "agent_action": state_after.get("agent_action", ""),
            "next_cli": state_after.get("next_cli", ""),
            "missing": state_after.get("missing", []),
        })

    def record_step(
        self,
        inv_id: str,
        step: str,
        *,
        status: str = "ok",
        artifact: str = "",
        decision: str = "",
        outputs: list[str] | None = None,
        elapsed_ms: int = 0,
        error: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录单个步骤。"""
        record: dict[str, Any] = {
            "invocation_id": inv_id,
            "step": step,
            "status": status,
            "elapsed_ms": elapsed_ms,
        }
        if artifact:
            record["artifact"] = artifact
        if decision:
            record["decision"] = decision
        if outputs:
            record["outputs"] = outputs
        if error:
            record["error"] = error
        if extra:
            record.update(extra)
        self._append(record)

    def record_auto_generate(
        self,
        inv_id: str,
        artifact: str,
        *,
        ok: bool,
        msg: str,
        elapsed_ms: int = 0,
    ) -> None:
        """记录自动生成产物的结果。"""
        self.record_step(
            inv_id,
            f"auto_generate:{artifact}",
            status="ok" if ok else "fail",
            artifact=artifact,
            decision=msg,
            elapsed_ms=elapsed_ms,
            error="" if ok else msg,
        )

    def record_artifact_check(
        self,
        inv_id: str,
        artifact: str,
        *,
        ready: bool,
    ) -> None:
        """记录产物就绪状态检查。"""
        self.record_step(
            inv_id,
            "check_artifact",
            status="ok" if ready else "skip",
            artifact=artifact,
            decision="ready" if ready else "missing or skeleton",
        )

    def _append(self, data: dict[str, Any]) -> None:
        """追加一条记录，失败静默处理。"""
        try:
            data.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 诊断日志写入失败绝不影响主流程


def get_trace_writer(change_dir: Path) -> TraceWriter:
    """获取指定 change 的轨迹写入器。"""
    return TraceWriter(change_dir)
