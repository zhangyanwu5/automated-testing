"""CLI 消息 — 中文。"""
from __future__ import annotations

WELCOME = """\
欢迎使用 OpenGuard
面向 AI 编码宿主的自动化测试框架

本次初始化将配置：
  • openguard/ 项目工作区
  • 项目测试画像与 OpenGuard 配置
  • OpenGuard 忽略规则
  • /opg:* AI 工具 slash commands
  • openguard-* AI Agent 操作 skills
"""

QUICK_START = """\
快速开始：
  /opg:run    开始一次测试任务（AI 自主推进准备，完成后等你确认执行）
  /opg:apply  确认后执行测试
  /opg:archive 归档并沉淀经验
"""

HELP_USAGE = """\
OpenGuard – 面向 AI 编码宿主的自动化测试与代码质量框架

用法：
  openguard <命令> [选项]

命令：
  init        在当前项目初始化 openguard/ 工作区。
  update      刷新 /opg:* slash commands、schema 和模板。
  new <目标>   开始一次新的 QA change（需求、代码修改或缺陷修复）。
  continue    将当前 change 推进到下一个缺失产物。
  apply       执行代码 Review 和测试矩阵，采集证据，生成报告。
  archive     归档已完成的 change，沉淀稳定知识。
  help        显示此帮助。

策略选项：
  --scan-scope   auto | full | incremental   （默认：auto）
  --test-suite   smoke | incremental | requirement-full | regression | full
  --review-level off | changed | risk-based | full
  --gate         local | ci | release

Slash Commands（由 init / update 安装）：
  /opg:new <目标>   →  openguard new
  /opg:continue    →  openguard continue
  /opg:apply       →  openguard apply
  /opg:archive     →  openguard archive

运行 `openguard <命令> --help` 查看命令专属选项。
"""

ALREADY_INIT_MSG = (
    "OpenGuard 已在 {openguard_dir} 初始化。\n"
    "使用 `openguard init --reconfigure` 重新配置项目画像，\n"
    "或使用 `openguard update` 刷新 /opg:* 命令和模板。"
)

REQUIRED_INPUT_HEADER = "真实执行前需补充的信息："

SCANNING_PROJECT        = "正在扫描项目…"
SCANNING_DETECTED       = "扫描项目 — 检测到 {type}"
DETECTED_PROJECT        = "检测到 {type} 项目："
NO_DETECT_PROJECT       = "无法检测项目类型："
RECOMMENDED             = "推荐配置："
SELECT_AI_TOOLS         = "? 请选择你使用的 AI 编程工具（可多选）："

CREATED_WORKSPACE       = "已创建 openguard/ 工作区：{path}"
WRITING_CONFIG          = "正在写入 openguard/config.yaml"
WRITTEN_FILE            = "已写入 {path}"
INSTALLING_COMMANDS     = "正在安装 /opg:* 命令"
INSTALLED_COMMANDS      = "已为 {hosts} 安装 /opg:* 命令（{total} 个文件）"
NO_HOST_SKIP_COMMANDS   = "未选择 AI 工具，跳过 /opg:* 命令安装。"
NO_HOST_RUN_UPDATE      = "配置 AI 工具后运行 `openguard update` 以完成安装。"
INSTALLING_SKILLS       = "正在安装 openguard-* skills"
INSTALLED_SKILLS        = "已为 {hosts} 安装 openguard-* skills（{total} 个文件）"
INSTALLED_SKILLS_FALLBACK = "已安装 openguard-* skills（fallback: openguard/commands/）"

UNITY_EDITOR_DETECTED  = "  检测到 Unity Editor（{source}）："
USE_EDITOR_PROMPT      = "  使用该编辑器？[Y/n]: "
ENTER_EDITOR_PATH      = "  请输入 Unity Editor 路径: "
AUTO_SELECT_EDITOR     = "  自动选择 Unity Editor（--yes）：{path}"
SELECT_UNITY_EDITOR    = "? 请选择要使用的 Unity Editor："
SKIPPED_FILL_LATER     = "  ? {item}: （跳过 — 稍后在 openguard/config.yaml 中填写）"
SKIPPED_FILL_LATER_INLINE = "    （跳过 — 稍后在 openguard/config.yaml 中填写）"
INIT_COMPLETE          = "OpenGuard 初始化完成。"
