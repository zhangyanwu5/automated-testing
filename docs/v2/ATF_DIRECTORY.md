# `.atf/` 目录约定（M0）

对齐 [ATF_PIPELINE_AND_SCAN_SPEC.md](./ATF_PIPELINE_AND_SCAN_SPEC.md) §3.4–3.6 与 [ROADMAP.md](./ROADMAP.md#6-风险与缓解) §6。

## 建议子结构

| 路径 | 用途 |
| --- | --- |
| `.atf/scan_index.json` | 扫描索引（字段契约见仓库内 `schemas/scan_index.v1.json` 与 `core/atf_scan_index`） |
| `.atf/artifacts/` | 分析片段、中间 JSON（可选）；**自动化知识包**建议文件名 `automation_knowledge.v1.json`（或带时间戳变体），契约见 [AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md) |
| `.atf/reports/` | 运行报告、卡点分析等（可选） |
| `.atf/baselines/` | 回归索引与快照、可选 `approved/` 参考帧策略（[BASELINE_STRATEGY.md](./BASELINE_STRATEGY.md)） |

根目录名 **`.atf/`** 为规格固定契约；其下文件名可由实现细化，但 **`scan_index.json`** 为本文档与 schema 的默认约定名。

## 与 Git / `.gitignore` 的推荐策略

与 [ROADMAP §6](./ROADMAP.md#6-风险与缓解) 一致：

- **默认建议将 `.atf/` 整体加入 `.gitignore`**（或至少忽略 `artifacts/`、`reports/`），避免本机路径、缓存体积与 CI 噪声进入版本库。
- 若团队希望**共享扫描索引**以加速 CI，可仅跟踪 `scan_index.json`，仍忽略 `artifacts/` 与 `reports/`；需在文档中明确谁负责刷新索引与 `rule_version` 一致性。
- **基线截图 / 回归素材**是否入库由项目策略单独决定（见 Roadmap M12）；不要与「默认忽略 `.atf/`」混为一谈。

## 机器可读 Schema

- JSON Schema：`schemas/scan_index.v1.json`
- Python 校验与迁移：`core.atf_scan_index`

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-04-30 | M0.1：初版目录说明与 `.gitignore` 建议。 |
| 2026-04-30 | `artifacts/` 行补充 AKP 默认文件名与《自动化知识包》链接；文首节号对齐《流水线规格》§3.4–3.6。 |
