# 截图与回归基线策略（M12.3）

对齐 [TODO.md](./TODO.md) M12、[ATF_DIRECTORY.md](./ATF_DIRECTORY.md) 与《体系说明》Phase 3 运营语义。

## `.atf/baselines/` 机器可读内容

| 路径 | 用途 |
| --- | --- |
| `runs_index.json` | 历史 run 索引：`run_id`、报告相对路径、`acceptance_digest`、日志摘要指纹、证据路径指纹 |
| `state_snapshot.json` | 最近一次运行的摘要快照（供趋势与外部看板） |
| `approved/` | **人工审批**后的参考帧 / 截图元数据（可选入库；默认不入库） |
| `product_fix_audit.jsonl` | M14 产品修复草案与策略相关审计行（JSONL） |

## 截图 / 像素基线入库范围

- **默认**：运行产生的截图、帧缓冲导出留在本机或 CI 产物，**不**强制进入 Git。
- **Approved 参考帧**：仅当版本管理员在 MR 中明确批准，并将元数据（路径、`rule_version`、关联 `type_id`）登记到 `approved/` 或团队约定仓库后，才视为回归对比的黄金源。
- **像素指纹**：实现侧对 `run_report.evidence_paths` 列表做稳定哈希（见 `regression_baseline.evidence_pixel_fingerprint`）；像素 buffer 本体由宿主管线提供路径，索引中不存大图二进制。

## 人工审批门槛（项目模板）

1. **谁可批**：测试负责人 + 对应功能开发 owner 双签（可按项目缩减为单签）。
2. **批什么**：视觉用例的「预期通过」帧；须附 `run_id`、宿主版本、分辨率、渲染特性开关说明。
3. **何时更新**：产品有意变更 UI/特效导致像素 diff 时，走新基线审批，旧基线标记废弃（可在 `approved/manifest.json` 自建，本仓库初版不强制 schema）。

## 与 `.gitignore` 的关系

若 `.atf/` 整体被忽略，基线索引仍可在 CI 中生成；团队若需**共享**基线，可仅跟踪 `baselines/runs_index.json` 与 `approved/manifest.json`，仍忽略体积大的 `reports/` 与原始截图目录。

## 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-04-30 | M12.3：初版策略与目录约定。 |
