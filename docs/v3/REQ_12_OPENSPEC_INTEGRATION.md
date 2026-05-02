# REQ_12_OPENSPEC_INTEGRATION：OpenSpec 联动

## 目标

当项目安装 OpenSpec 时，OpenGuard 应能读取 OpenSpec 的需求、设计和任务产物，结合自身测试、Review、执行和报告能力，形成"开发 + 测试 + 归档"的闭环。

## 联动原则

| 原则 | 要求 |
| --- | --- |
| 不替代 | OpenSpec 负责规格驱动开发，OpenGuard 负责质量验证。 |
| 不强依赖 | 未安装 OpenSpec 时，OpenGuard 必须独立可用。 |
| 默认只读 | OpenGuard 默认只读取 OpenSpec 产物，不修改 OpenSpec，除非显式授权。 |
| 可追溯 | OpenGuard change 必须能记录来源 OpenSpec change、proposal、specs、tasks。 |
| 闭环门禁 | OpenSpec apply 后，OpenGuard 可作为 archive 前质量门禁。 |

## 关联关系

| OpenSpec | OpenGuard |
| --- | --- |
| `openspec/changes/<id>/proposal.md` | `openguard/changes/<id>/intent.md` 输入来源。 |
| `openspec/changes/<id>/specs/` | `openguard/changes/<id>/requirements.md` 的需求来源。 |
| `openspec/changes/<id>/design.md` | Review 与影响分析输入。 |

| `openspec/changes/<id>/tasks.md` | 测试范围、执行顺序、验收阶段输入。 |
| `/opsx:apply` | 开发实现。 |
| `/opg:apply` | Review、测试、门禁报告。 |
| `/opsx:archive` | 应在 OpenGuard 门禁通过或人工豁免后执行。 |

## 工作流

```text
/opsx:new 或 /opsx:propose
→ OpenSpec 生成 proposal/specs/design/tasks
→ /opsx:apply 实现代码
→ /opg:new --from-openspec <change-id>
→ /opg:continue 生成需求验收、Review 计划、测试矩阵
→ /opg:apply 生成 Review/测试/门禁报告
→ 通过后 /opg:archive
→ 再由用户或 Agent 执行 /opsx:archive
```

## 功能需求

| 编号 | 需求 |
| --- | --- |
| REQ-12-01 | `openguard init` 必须检测项目中是否存在 OpenSpec 配置或 `openspec/changes/`。 |
| REQ-12-02 | `openguard new` 应支持从 OpenSpec change 创建 QA change。 |
| REQ-12-03 | OpenGuard 必须把 OpenSpec proposal/specs/tasks 转换或引用到 `requirements.md`，验收句可使用 EARS 表达。 |
| REQ-12-04 | OpenGuard 必须在 `artifact_index.yaml` 和 `state.yaml` 中记录 OpenSpec 来源引用。 |
| REQ-12-05 | OpenGuard 门禁失败时，必须输出可回写给开发 Agent 的修复建议，但默认不修改 OpenSpec 产物。 |
| REQ-12-06 | OpenGuard 门禁通过后，应输出"可归档"结论，供 OpenSpec archive 使用。 |
| REQ-12-07 | OpenSpec 变更后，OpenGuard 必须重新计算需求指纹、影响图和测试矩阵。 |
| REQ-12-08 | `openguard new --from-openspec` 时必须对 OpenSpec 内容做有效性校验：比对规格描述的接口与当前代码实现，判断一致性并给出置信度。 |
| REQ-12-09 | OpenSpec 有效性校验结果必须写入 `openspec_link.yaml`，包含每个 spec/task 的状态（`consistent` / `stale` / `not_implemented` / `medium`）、置信度和校验依据。 |
| REQ-12-10 | 状态为 `stale`（规格存在但代码已变更）或 `not_implemented`（规格存在但代码缺失）的 OpenSpec 内容，不得直接转换为测试矩阵，必须写入 `unknowns.md` 供人工或 Agent 确认。 |


## 产物要求

| 产物 | 内容 |
| --- | --- |
| `openspec_link.yaml` | OpenSpec change ID、proposal/specs/tasks 路径、哈希、同步时间。 |
| `requirements.md` | 从 OpenSpec specs 提取或引用的 EARS 验收项。 |
| `gate_report.yaml` | 是否允许进入 OpenSpec archive 的质量结论。 |
| `timeline.md` | 同时记录 OpenSpec 开发阶段和 OpenGuard 验证阶段的关键步骤引用。 |

## 验收标准

- 未安装 OpenSpec 时，OpenGuard 工作流不受影响。
- 安装 OpenSpec 时，OpenGuard 能自动识别并提示可联动。
- OpenGuard 报告能追溯到 OpenSpec change 和具体 spec/task。
- OpenSpec archive 前能看到 OpenGuard 的门禁结论或人工豁免。
