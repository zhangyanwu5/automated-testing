# AI 游戏自动化测试框架

面向游戏项目的自主化测试框架：输入需求文档与项目代码，框架自主完成测试用例生成、适配器构建、执行与报告。

## 安装与在真实项目上跑通

命令行安装、`atf-scan` / 矩阵填充 / `run` 整跑、以及当前 CLI 占位执行器的边界说明，见仓库根目录 **[README.md](../README.md)**。

## 文档

| 文档 | 内容 |
| --- | --- |
| [OVERVIEW.md](./v1/OVERVIEW.md) | 框架要解决的问题、边界、核心设计理念 |
| [ARCHITECTURE.md](./v1/ARCHITECTURE.md) | 分层结构、模块职责、关键接口、解耦策略 |
| [PROJECT_STRUCTURE.md](./v1/PROJECT_STRUCTURE.md) | 代码目录组织与依赖方向约定 |
| [v2 规格与路线图](./v2/) | 扫描、流水线、目录约定、路线图与实现 Todo |
| [v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md) | L0/L1 分工、自动化知识包（AKP）契约、AI 语义层工程化与安全约束 |

建议阅读顺序：OVERVIEW → ARCHITECTURE → PROJECT_STRUCTURE；流水线与门禁契约读 `v2/ATF_PIPELINE_AND_SCAN_SPEC.md`；若关注「扫描之后如何让 Agent 理解策划与代码、并驱动全自动化」，读 `v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md` 与 `v2/AI_AUTOMATED_TESTING_SYSTEM.md` §7；实现细节可对照 `docs/v2/TODO.md`。

## 一句话说明

传统自动化测试需要人工编写用例、写适配器、维护脚本；本框架把这部分工作交给 AI 完成，人只负责提供需求文档和被测项目代码。

## 当前状态

核心库已提供扫描索引、测试矩阵、整跑与报告管线；宿主侧真实执行需自行接入编排与执行器。演进与目标形态见 [OVERVIEW.md §5 演进路径](./v1/OVERVIEW.md#5-演进路径)。
