# TODO — 待办事项

> 本文件记录尚未实现或需要进一步讨论的事项。持续补充。

---

## T-001 测试脚本超时状态上报协议（批次 C）

**背景**
`executor/runner.py` 超时后目前只能报"脚本超时"，无法区分：
- 脚本本身死循环/逻辑错误（`script_timeout`）
- 测试目标响应太慢，脚本在等待中被 kill（`target_timeout`）

Runner 侧的读取逻辑已实现（读 `run_dir/waiting_for.json`），待定的是**脚本侧协议**。

**待决策**

1. **写入责任方**：测试脚本自己写/删文件（方向 A），还是提供 `openguard.sdk.wait_for()` 封装（方向 B）？
   - 方向 A：改动小，但 AI 生成脚本时需在 prompt 里加约定说明，容易漏
   - 方向 B：脚本干净，需新建 `openguard/sdk/` 模块（~100 行）

2. **`run_dir` 路径传递**：倾向环境变量 `OPENGUARD_RUN_DIR`，runner 启动脚本时注入，改动量最小

3. **协议范围**：本次只覆盖"等待测试目标"这一场景即可

**文件格式约定（已确定）**
```json
// run_dir/waiting_for.json
{
  "waiting_for": "scene_loaded",
  "since": "2026-05-02T21:00:00Z",
  "detail": "MainScene"
}
```
脚本等待结束后删除该文件。Runner 超时后若文件存在 → `target_timeout`；不存在 → `script_timeout`。

**涉及文件**
- `src/openguard/executor/runner.py`（runner 侧已改，待补传参）
- `src/openguard/executor/reporter.py`（已加 `script_timeout` / `target_timeout` 分桶）
- `src/openguard/sdk/`（若选方向 B，需新建）
- `src/openguard/prompts/`（若选方向 A，需更新脚本生成 prompt 中的约定说明）

---
