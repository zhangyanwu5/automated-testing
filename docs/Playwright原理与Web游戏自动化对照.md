# Playwright 原理与 Web / 游戏自动化对照

> 本文整理自多段对话笔记：先讲 **Playwright 的架构与通信**，再说明 **Web 上如何模拟用户操作**，最后对照 **Unity / UE 原生游戏** 能否用 Playwright、应如何用引擎测试与截图比对。已去掉重复段落、对话痕迹与冗余引导语。

---

## 导读：文档结构

| 章节 | 内容 |
|------|------|
| **一** | 三层架构、协议、WebSocket、核心对象、稳定性、多浏览器、与竞品差异 |
| **二** | 与 OS 层模拟的区别、鼠标/键盘/表单要点 |
| **三** | 能力边界、WebGL、推荐工具链、可借鉴的设计理念 |
| **四** | UE / Unity 分层输入、校验方式、官方框架、扩展思路（合并原多节重复表述） |
| **五** | 像素级比对与容差；Playwright / Unity / UE；Unity 极简示例与 UE 摘要 |
| **六** | 总结 |
| **七** | 与 ATF v2 文档集的衔接（体系 / 流水线 / Roadmap / 技术总览；交叉引用与多宿主建议） |
| **修订说明** | 合并记录与订正说明（可选阅） |

---

## 一、Playwright 架构与实现要点

### 1.1 核心结论

Playwright 采用 **客户端 → Playwright Server（独立进程）→ 浏览器** 的分层与 **进程外自动化**：测试进程与浏览器进程隔离，通过 **统一协议（Playwright Protocol）** 屏蔽 Chromium / Firefox / WebKit 差异，配合 **WebSocket 长连接** 做双向、低延迟通信。

**数据流（概念）**：`测试脚本 → 语言绑定客户端 → Server → 浏览器原生协议（CDP / Juggler / WDP）→ 浏览器进程`

### 1.2 三层角色

1. **客户端层**  
   JS/TS、Python、Java、C# 等绑定；暴露 `page.goto()`、`locator.click()` 等 API；可同步或异步。

2. **核心层（Playwright Core）**  
   - Server：命令转换与连接管理  
   - **Playwright Protocol**（如 `protocol.yml` 描述）：与具体浏览器无关的指令与事件模型  
   - 连接管理：持久 **WebSocket**，命令与事件双向流  
   - **BrowserContext**：会话级隔离（Cookie、Storage 等）

3. **浏览器层**  
   实际浏览器进程；**Chromium** 走 CDP，**Firefox** 走团队维护的 Juggler（CDP 理念），**WebKit** 走 WDP。官方分发自带浏览器二进制以保证一致性。

### 1.3 为何用 WebSocket

相比短连接 HTTP：**握手少、延迟低**；浏览器可 **主动推送** DOM/网络事件；连接稳定，适合并行多命令与事件驱动模型。

### 1.4 关键抽象与稳定性（合并原分散描述）

| 概念 | 作用 |
|------|------|
| **BrowserContext** | 轻量隔离单元，接近「独立配置档」；创建快，适合并行与登录态复用。 |
| **Page** | 单标签页；内置导航与操作相关等待；多 frame；网络拦截与模拟。 |
| **Locator** | 基于可访问性/文本/角色等相对稳定特征；**不长期持有 DOM 引用**，操作前重新解析，减少陈旧引用问题；可链式缩小范围。 |
| **自动等待** | 动作前：可见、稳定、可交互等；导航：`load` / `networkidle` 等策略；`expect` 断言轮询直至超时。 |

以上与下文「点击一次」的流程一致，不重复展开。

### 1.5 多浏览器与运行模式

- 三种引擎由 **协议适配** 统一到同一套上层 API。  
- **有头 / 无头** API 一致；无头适合 CI，有头适合调试；支持视口、设备与地理位置等模拟。

### 1.6 与 Selenium、Puppeteer 对照

| 特性 | Playwright | Selenium WebDriver | Puppeteer |
|------|------------|-------------------|-----------|
| 架构 | 客户端–Server–浏览器，进程外 | 驱动–浏览器，常见 HTTP | 多直连 CDP，无统一跨浏览器层 |
| 浏览器 | Chromium / Firefox / WebKit 一等支持 | 依赖各驱动适配 | 以 Chromium 为主 |
| 通信 | WebSocket 长连接、双向 | 常见短连接/轮询 | WebSocket、双向 |
| 隔离 | BrowserContext，创建快 | 常需新浏览器实例，更重 | 有类似能力但生态与 API 不同 |
| 定位与等待 | Locator + 内置自动等待 | 常需手写等待与重试 | 需更多自管等待 |

### 1.7 示例：`page.click(selector)` 端到端（简版）

1. 客户端将调用序列化为 **Playwright Protocol** 消息。  
2. **Server** 经 WebSocket 发往对应浏览器会话。  
3. 适配为 **CDP / Juggler / WDP** 指令。  
4. 浏览器：**解析节点 → 自动等待可交互 → 合成指针事件链 → 执行点击 → 产生导航/DOM 事件**。  
5. 结果与事件经 WebSocket 回到客户端，`await` 结束。

---

## 二、Web 端如何模拟用户操作

**与「系统级键鼠模拟」的区别**：Playwright 主要在 **浏览器进程内** 通过 DevTools 类协议驱动 **DOM/输入管线**，在视口坐标上合成 **完整事件序列**（如 `mousedown` → `mouseup` → `click`），而不是依赖全局 OS 钩子（Selenium 部分老路径会更接近驱动层，此处不展开历史对比）。

**要点摘要**：

- **鼠标**：Locator 解析元素与视口几何；支持 `steps` 等参数模拟移动轨迹；与自动等待结合。  
- **键盘**：`keyboard` 低级事件与 `fill`/`press` 等高级封装；组合键与 IME 场景可查官方文档。  
- **表单**：聚焦、禁用态检测、`set_input_files` 绕过系统文件对话框等。

**稳定性**与第一节「Locator + 自动等待」同一套机制：动作前条件、失败重算定位、断言重试等，此处不重复列举条目。

---

## 三、原生游戏（Unity/UE）与 Playwright

### 3.1 核心结论

- Playwright **面向 HTML/DOM 与浏览器事件**，**不能直接驱动 Unity/UE 原生窗口**（无 DOM、无同一套调试协议）。  
- **WebGL 发布到浏览器**时，只能在 **浏览器能看到的范围** 内做键鼠与截图类验证；**拿不到游戏内任意内部状态**，画布内 UI 也难稳定用 DOM 方式定位。

### 3.2 技术栈差异（为何冲突）

| 维度 | Web（Playwright） | Unity/UE 原生 |
|------|-------------------|----------------|
| 渲染 | DOM/CSS/合成层 | D3D/OpenGL/Vulkan 等 |
| 输入 | 浏览器事件管道 | Input System / Enhanced Input 等 |
| 进程与接口 | 浏览器 + CDP 等 | 游戏进程，无 Playwright 协议 |

### 3.3 推荐工具链（精简）

**Unity**：Unity Test Framework（Edit/Play Mode）、UGUI 相关测试包、WebGL 场景下可叠加浏览器工具；商业化/图像方案如 GameDriver 等按需选用。

**Unreal**：Automation System、Gauntlet（多客户端/规模化）、Automation Driver（Slate/UMG）；同样可按需引入图像或第三方方案。

### 3.4 从 Playwright 可借鉴的设计（只说一次）

- **分层**：测试 API → 会话/命令层 → 引擎或设备适配。  
- **轻量隔离**：对标 BrowserContext 的「快速重置场景/存档/实例」。  
- **智能等待**：等加载、动画、网络或游戏内 `Ready` 标志，少写死 `sleep`。  
- **稳定定位**：引擎内用路径/元数据/组件标识，或图像/OCR，而不是易碎的随意索引。

---

## 四、引擎内模拟玩家与结果校验

以下 **UE** 与 **Unity** 并列，结构对称，避免原文在两引擎间重复三遍「分层+等待+截图」。

### 4.1 共同原则

| 目的 | 做法 |
|------|------|
| 尽量像玩家 | **优先走引擎官方输入管线**（UE：Enhanced Input 注入；Unity：新 Input System 模拟），再考虑直接调 UI 回调（仅适合纯 UI、不测输入链路）。 |
| 验证结果 | **状态断言**（血量、坐标、GameState）+ **UI 断言** + **截图/像素对比**（见第五节）。 |
| 系统级键鼠 | Win32 `SendInput` / `keybd_event` 等仅适合反作弊、多进程黑盒等特殊场景，一般功能测试优先引擎内注入。 |

### 4.2 Unreal Engine

**输入层级（由浅入深）**：

1. **Enhanced Input**：`UEnhancedInputLocalPlayerSubsystem::InjectInputForAction`，与正式映射一致，**首选**。  
2. **PlayerInput / InputComponent**：绕过部分映射时中阶方案。  
3. **OS 层模拟**：最高「物理真实度」，维护成本高，用于特定兼容性/反作弊场景。

**UI**：`FAutomationDriver` + 控件元数据（如 `FDriverMetaData::Id`）；或直接 `Broadcast` 按钮事件（不测输入链时）。

**校验**：`TestTrue`/`TestEqual`、Latent Command 等待异步条件、日志订阅、`FScreenshotRequest` + 对比命令（与第五节合并，不重复原理）。

**框架**：Automation System（含 Functional Test、与 Slate 集成）、Gauntlet（外部进程编排多客户端）。功能对照可在项目选型时自行制表，本文从略以避免与第三节重复。

### 4.3 Unity

**输入层级**：

1. **新 Input System**：`InputSystem` 的模拟 API（如 `SimulatePress`/`SimulateRelease` 等，以当前文档版本为准查官方），走绑定与 Action，**首选**。  
2. 旧 Input Manager：老项目兼容方案，维护成本高。  
3. **直接 `onClick.Invoke()` / 调角色方法**：不经过输入系统，**不能**代表真实玩家键位与缓冲逻辑。  
4. **Win32 等**：同 UE，用于特殊黑盒场景。

**校验**：`Assert` 系列、UGUI/TMP 状态、`ReadPixels` + 自写或与库做像素差异（第五节）。

**框架**：**Unity Test Framework**：Play Mode 下可跑完整场景；与输入模拟、异步等待、CI 集成。

**扩展**：自研 **GameLocator**、**WaitUntil 条件等待**、**每用例重置场景/存档**，直接对应 3.4 的借鉴列表；第三方 GameDriver、SikuliX 等与 UE 一节同类，不重复展开厂商列表。

### 4.4 截图对比与 AI（预告第五节）

引擎与 Playwright 的 **默认** 截图回归：**像素矩阵 + 容差阈值 + 可选忽略区域**，**不是**语义 AI。仅部分商用视觉产品会叠加 AI 布局/语义判断，与普通自动化无关。

---

## 五、截图对比原理（Playwright / Unity / UE）

### 5.1 通用原理（无 AI）

1. **基准图**：人工确认通过的参考帧。  
2. **当前帧**：测试运行时截取。  
3. 转为 **RGBA 像素数组**，逐像素或带预处理（灰度、模糊、区域 mask）做差异累计。  
4. **全局/局部阈值**：低于阈值判通过，避免抗锯齿、粒子随机等导致的「全红」。

Playwright 的视觉对比同样属于 **像素级 + 配置化容差/掩膜**，不是默认启用大模型看图。

### 5.2 Unity（极简思路 + 示例）

引擎未提供与 UE 同等级的一站式封装时，常见做法是 `Texture2D.ReadPixels` 得到当前帧，与基准 `Texture2D` 做通道差与比例统计。

```csharp
Color[] GetPixels(Texture2D tex) => tex.GetPixels();

float CalcDiffPercent(Texture2D a, Texture2D b)
{
    if (a.width != b.width || a.height != b.height)
        return 100f;

    Color[] p1 = a.GetPixels();
    Color[] p2 = b.GetPixels();
    int diffCount = 0;
    int total = p1.Length;

    for (int i = 0; i < total; i++)
    {
        float dr = Mathf.Abs(p1[i].r - p2[i].r);
        float dg = Mathf.Abs(p1[i].g - p2[i].g);
        float db = Mathf.Abs(p1[i].b - p2[i].b);
        if (dr > 0.05f || dg > 0.05f || db > 0.05f)
            diffCount++;
    }
    return (float)diffCount / total * 100f;
}

void CheckScreenEqual(Texture2D reference)
{
    var current = new Texture2D(reference.width, reference.height);
    current.ReadPixels(new Rect(0, 0, reference.width, reference.height), 0, 0);
    current.Apply();

    float diff = CalcDiffPercent(reference, current);
    Assert.IsTrue(diff < 1.5f, $"画面差异过大：{diff:F2}%");
}
```

进阶：灰度化、只比 ROI、高斯模糊降噪等，均属传统图像处理。

### 5.3 UE 原生能力摘要

- **Automation System** 集成截图对比；基类如 **`UScreenshotFunctionalTest`**，`TakeScreenshotAndCompare` + **`FAutomationScreenshotOptions`**（`MaximumGlobalError`、`MaximumLocalError`、`bIgnoreAntiAliasing`、`IgnoreRegions` 等）。  
- **Session Frontend** 查看用例与差异热力图；基准图常置于版本控制的 Approved 目录策略依团队规范而定。  
- **CI**：`-runautomationtests` 等参数过滤截图用例（具体命令随 UE 版本文档为准）。

与 5.1 重复的原理句已删并上收至「通用原理」。

---

## 六、总结

Playwright 的价值在于 **统一协议 + 进程外控制 + 长连接 + 强默认等待与定位模型**，从而在 **Web** 场景获得高可靠自动化。  
**Unity/UE 原生游戏**应使用 **引擎测试与输入注入**，Playwright 仅覆盖 **WebGL 在浏览器内** 的一层外壳；**截图回归**在三条技术栈上都是 **像素级数学比对为主**，按需加掩膜与阈值，与 AI 无必然关系。

---

## 七、与 ATF v2 文档的衔接（产品视角）

仓库内 **ATF v2** 从零规格与路线与本文互补：不假设具体实现，但把「编排、通道、判定」写成可交付契约。阅读顺序建议：

| 文档 | 与本文的衔接点 |
|------|----------------|
| [docs/v2/AI_AUTOMATED_TESTING_SYSTEM.md](./v2/AI_AUTOMATED_TESTING_SYSTEM.md) | §2.4 明确 Web / WebGL / 原生宿主与观测路径；§3.3 区分 **像素基线** 与 **语义判定**；建设原则强调宿主与控制面选择。 |
| [docs/v2/ATF_PIPELINE_AND_SCAN_SPEC.md](./v2/ATF_PIPELINE_AND_SCAN_SPEC.md) | 执行阶段 5.3 将控制通道与「进程外客户端—长连接—被控端」分层类比；禁止对原生宿主默认假设 DOM。 |
| [docs/v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md](./v2/AUTOMATION_KNOWLEDGE_AND_AI_LAYER.md) | L0/L1 与 AKP：编排与证据链仍以进程外控制为准；AKP 为结构化认知输入，不替代 freshness 与运行时观测。 |
| [docs/v2/ROADMAP.md](./v2/ROADMAP.md) | `baseline` / M6R / M11 / M12 的里程碑语义与本文 **分层、等待、定位、像素对比** 对齐；不新增独立里程碑，作校准用。 |
| [docs/v2/TECHNICAL_OVERVIEW.md](./v2/TECHNICAL_OVERVIEW.md) | **编排器、调度器、执行适配器、证据、Oracle** 等与本文「进程外—通道—宿主」一一可映射；实现拆模块时以此为分解边界。 |

若产品同时包含 **H5/管理端（真 DOM）** 与 **原生或 WebGL 客户端**，宜在需求与测试矩阵中**分列宿主**，分别采用浏览器工具链与引擎/桥接工具链，避免混用同一套定位假设。

---

## 修订说明（可选阅）

- **合并**：架构、WebSocket、Context/Locator/等待、与竞品表只保留一处；游戏可借鉴点只写一节。  
- **删除**：多处的「需要我帮你…」、「已完成思考」、重复视频块与占位词「表格」；重复三遍的 GameDriver/Sikuli 列举改为第三节一次带过。  
- **订正与弱化**：Unity `InputSystem.SimulatePress(Keyboard.current.spaceKey)` 等 API 名称随版本变化，正文改为「以官方 Input System 文档为准」的表述，避免过时符号误导。  
- **新文件名**：`Playwright原理与Web游戏自动化对照.md` — 标明「原理 + Web + 引擎对照」三条主线。
- **2026-04-30**：新增 **§七** 与 ATF v2 文档集（含《技术总览》）的交叉引用及多宿主矩阵建议。

若你希望 **完全保留** 原文中的 UE C++ 长示例或 Python 调用片段，可把对应块从旧文件按需粘贴进「附录」小节。
