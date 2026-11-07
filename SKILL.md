---
name: zk-orchestrator-worker
description: 主控-工作者（Orchestrator-Worker）多代理编排技能。当任务多步骤、跨文件、需要"先调研再动手再验收"时使用；也当用户说"你派子代理去写""派出 subagent 来写""让子代理去做""扔给子代理""subagent 去干""派活给 subagent""多代理干活""编排一下""拆解任务""并行开工""省 token 干活""大任务分几步""你来指挥别自己动手"时使用——出现"派/扔/交/让 + 子代理/subagent/下属"这类说法一律命中。核心：① 主控只做规划、派活、验收三件事，读文件、写代码、跑命令全部外包给侦察(scout)/施工(worker)/验收(reviewer)三类子代理；② 默认一律使用当前宿主平台内置的原生 Subagent 派活（不用代码/脚本派工）：在 Antigravity 环境，若用户未指定 pro 模型，默认全部使用 flash 模型（Model="flash"）调用内置 invoke_subagent 干活，不使用 OpenCode；在 OpenCode 等其他平台，同样直接调用平台内置的原生 subagent 工具派工。
license: MIT
metadata:
  version: "3.0.0"
  author: 震凯的小助理
---

# zk-orchestrator-worker — 主控只动嘴，脏活全交宿主内置 Subagent

把"贵脑子"从执行里解放出来：主控只做**规划、派活、验收**；读文件、写代码、跑命令全部交给子代理；子代理的中间过程**永远不回流**到主控上下文。

本技能的核心铁律：
1. **派发方法论**：规定侦察（`scout`）、施工（`worker`）、验收（`reviewer`）三个角色与派单三件套（目标、输出格式、边界）。
2. **宿主原生优先（禁止默认用脚本跨端派工）**：任何平台下，只要用户没有特殊点名跨 CLI，**默认一律使用当前平台内置的原生 Subagent 工具派活**，绝不用外部 Shell/Python 脚本（`dispatch.py`）套壳派发：
   - **Antigravity 环境**：只用内置 `invoke_subagent`（及 `send_message`），**不使用 OpenCode**；只要用户没有明确指定用 `pro` 模型，**默认一律使用 `flash` 模型（`Model: "flash"`）作为 subagent 干活**。
   - **OpenCode 环境（及其他 Agent CLI）**：同样**不要用代码/脚本去派工**，直接使用 OpenCode 自身内置的原生 Subagent 工具（如内置 `task` 工具）派活。

---

## 一、各平台原生 Subagent 派发矩阵（先看怎么派）

### 1. 各宿主平台原生工具与角色映射表

| 宿主平台 | 原生派工工具 | 默认模型策略 | `scout`（只读侦察） | `worker`（全权限施工） | `reviewer`（独立验收） | 返工/追问方式 |
|---|---|---|---|---|---|---|
| **Antigravity** | `invoke_subagent` | 用户未指定 `pro` 时，**强制传 `Model: "flash"`** | `TypeName: "research"`（原生只读沙箱） | `TypeName: "self"`（或 `define_subagent` 施工角色） | 新调 `invoke_subagent`（新会话独立盲审） | 对原 `conversationId` 调 `send_message` |
| **OpenCode** | 内置 `task` 工具 | 宿主内置子代理默认轻量模型 | 调只读 `explore` / `plan` 类子代理 | 调具备写权限的内置 `general` / `build` 子代理 | 新起独立 `task` 会话只读审查 | 按内置 `task` 会话续接或重派 |
| **Claude Code** | 内置 `Agent` / `Task` | 宿主内置子代理模型（如 Haiku/Sonnet） | `subagent_type: "Explore"`（只读） | `subagent_type: "general-purpose"`（可读写） | 新起独立子代理只读验收 | 续接 agentId 或带上下文重派 |
| **Codex CLI** | 内置 `spawn_agent` | 宿主内置子代理模型 | 只读边界提示词 + 内置子代理 | 全权限内置子代理 | 新起独立子代理只读验收 | `send_input` 续接或重派 |

---

### 2. Antigravity 环境派发铁律（内置 `invoke_subagent` + 默认 `flash`）

在 **Antigravity** 中担任主控时，**严禁调用 `run_command` 跑外部脚本或调 OpenCode**（外部 Shell 会占用前端聊天线程、锁死输入框）。必须 100% 走系统内置的 Subagent 工具链：

1. **模型铁律：未指定 `pro` 一律用 `flash`**
   - 调用 `invoke_subagent` 时，只要用户没有明确说“子代理用 Pro 模型”，**必须显式传入 `Model: "flash"`**（超简单高频检索可用 `Model: "flash_lite"`）。
   - 切勿省略 `Model` 参数（省略会默认 `inherit` 继承主控昂贵的重型模型）。
2. **三角色原生参数标准**
   - **只读侦察（`scout`）**：
     - `TypeName: "research"`，`Model: "flash"`，`Role: "Scout: <2-5词任务名>"`
     - `research` 是平台原生只读沙箱，底层禁写文件、禁外部网络，天然防越权。
   - **全权限施工（`worker`）**：
     - `TypeName: "self"`，`Model: "flash"`，`Role: "Worker: <2-5词任务名>"`
     - 若多个施工子代理并行改代码怕冲突，可设置 `Workspace: "branch"` 或 `"share"` 进行工作区隔离；也可先用 `define_subagent` 动态声明专职施工角色（`EnableWriteTools: true`）再调用。
   - **独立审查验收（`reviewer`）**：
     - 必须**重新调用 `invoke_subagent` 开启全新子会话**（严禁对刚才施工的 `conversationId` 发消息自查）。
     - 纯静态代码审查用 `TypeName: "research"`（`Model: "flash"`）；需要跑测试命令验收时用 `TypeName: "self"`（`Model: "flash"`，并在提示词边界中锁死“只跑测试验证，严禁修改业务文件”）。
3. **原生异步与响应式唤醒（Reactive Wakeup）**
   - `invoke_subagent` 是平台一等公民，天然在侧边栏独立运行，**0.01 秒交还前端输入框**，用户可随时插话聊天。
   - 严禁写循环或用 `schedule` / `sleep` 轮询子代理状态；派发后直接并行派下一个或结束本轮对话，子代理干完后系统会自动推送消息唤醒主控。
   - 若验收未通过需要原施工子代理返工，直接用 `send_message(Recipient="<原施工conversationId>", Message="...")` 把修改意见发给它。

---

### 3. OpenCode 及其他平台派发铁律（只用内置 Subagent，不用代码派）

1. **在 OpenCode 中担任主控时**：
   - **严禁通过 Bash 工具跑 `dispatch.py` 或命令行套娃执行 `opencode run`**。
   - 必须直接调用 OpenCode **自身内置的原生 Subagent 工具（如 `task` 工具）**来派发侦察、施工和验收任务。
2. **在 Claude Code / Codex CLI / Pi Agent 中担任主控时**：
   - 同样**不要用代码或外部脚本派工**，一律直接调用该平台内置的原生 Subagent 工具（`Task` / `Agent` / `spawn_agent`）。

---

## 二、何时使用 / 何时不用

**用**（满足任意一条）：
- 任务 ≥3 步，或跨多个文件
- 需要先摸清现状再动手
- 一件活包含"调研 + 实现 + 验收"多个阶段
- 用户明确说"编排/派活/多代理/拆解/让子代理去干"

**不用**（主控直接做，别为编排而编排）：
- 单文件小改动、错别字、改一行配置
- 纯问答、查一个事实
- 派单的开销 > 自己干的成本

---

## 三、四个核心原则

### 原则 1：主控绝不下场

主控只做三件事：**规划、派活、验收**。

开工后如果发现自己又准备去连续 `read` / `grep` / 搜代码了，先停一下自问：**"这活能不能派给内置 Subagent？"** 能，就派。

为什么：主控的上下文最贵，也最脆弱。一次大范围搜索就能塞进几万 token 的无关内容，此后主控的每一个判断都被稀释。内置 Subagent 跑在独立的子会话上下文里，**中间探索过程不污染主会话，这是设计，不是限制**。

### 原则 2：派活按三个标准角色（映射内置 Subagent 权限）

本技能固定三个角色，按各平台内置 Subagent 的能力边界严格对号入座：

| 任务类别 | 角色代号 | Antigravity 内置映射 | OpenCode / 其他平台内置映射 | 能力特征 |
|---|---|---|---|---|
| **侦察** | `scout` | `invoke_subagent(TypeName="research", Model="flash")` | 内置只读子代理（如 `explore` / `plan`） | 找文件、摸结构、搜关键词、看依赖；**只读不改文件** |
| **施工** | `worker` | `invoke_subagent(TypeName="self", Model="flash")` | 内置全权限子代理（如 `general` / `build`） | 写代码、改文件、跑命令、测功能；**有完整写权限** |
| **验收** | `reviewer` | 新调 `invoke_subagent(..., Model="flash")`（新会话） | 新起独立内置子代理会话（只读） | 独立检查产出是否达标；**只读、不能改**、必须给证据 |
| **判断** | **主控自己** | 主控自身 | 主控自身 | 架构取舍、审美、要不要做、多个方案选哪个 |

**核心纪律**：
- **默认全走宿主内置 Subagent**：不跨端调外部 CLI，不用脚本套壳。
- **Antigravity 默认锁死 `flash`**：除非用户点名要 `pro`，否则侦察、施工、验收全部传 `Model: "flash"`。
- **验收必须开新会话**：`reviewer` 绝不能复用施工那轮的子代理会话（`conversationId`），必须开全新上下文独立盲审。

### 原则 3：派单必须带三件套

每个传给内置 Subagent 的 `Prompt` 都必须写全这三样，缺一个子代理就会漂移：

1. **目标**：要交付什么（具体到文件、函数、标准）
2. **输出格式**：回什么（摘要？文件路径？结构化结论？多少字以内？）
3. **边界**：什么能动、什么绝对不能碰

### 原则 4：验收分两档

产出回来后，按检查类型分两档处理：

| 档位 | 检查内容 | 谁来做 |
|---|---|---|
| **Type-A（机器可验）** | 文件存在吗？退出码是 0 吗？测试通过吗？ | **主控自己看一眼**，或交给 `worker` 顺手验证 |
| **Type-B（价值判断）** | 做得好不好？能不能交付？符合原始目标吗？ | **必须另起一个全新 `reviewer` 子代理独立审查** |

---

## 四、标准六步工作流

1. **规划**（主控）：把任务拆成清单，给每步标上类别（`scout` / `worker` / `reviewer`）。
2. **映射**（主控）：映射到当前宿主内置 Subagent（Antigravity 下默认 `Model: "flash"`；OpenCode 下调内置 `task` 工具）。
3. **侦察**（`scout`）：先派只读子代理摸清现状再动手。跳过侦察直接施工，是返工的最大来源。
4. **施工**（`worker`）：按派单模板干活。互相独立的子任务可以一次并行调多个内置 Subagent。
5. **验收**（`reviewer`）：开启全新子代理会话，对照**原始目标**逐条查，不是对照施工子代理自己的说法。
6. **终审**（主控）：过了就交付；没过，带着具体问题（Antigravity 下用 `send_message` 发给原施工子代理 `conversationId`）打回重做。

---

## 五、三个标准派单模板（直接填入内置 Subagent 的 Prompt）

### 1. 派给「只读侦察者」（`scout`）

- **Antigravity 调用参数**：
  - `TypeName`: `"research"`
  - `Model`: `"flash"`（用户未指定 `pro` 时必填）
  - `Role`: `"Scout: <模块名>侦察"`
- **Prompt 模板（全平台通用）**：
```text
目标：搞清楚 <X> 的结构——涉及哪些文件、关键逻辑在哪（工作目录：<目录路径>）
输出：只回一份清单（文件路径 + 每个文件干什么 + 核心结论），不超过 200 字
边界：只读，不要改任何文件；不要创建临时文件
```

### 2. 派给「全权限执行者」（`worker`）

- **Antigravity 调用参数**：
  - `TypeName`: `"self"`
  - `Model`: `"flash"`（用户未指定 `pro` 时必填）
  - `Role`: `"Worker: <模块名>施工"`
- **Prompt 模板（全平台通用）**：
```text
目标：在 <目录路径> 下实现 <X>，验收标准是 <Y>
输出：改了哪些文件、每个文件改了什么、执行了什么验证命令及结果
边界：只动 <A/B> 文件，绝对不要碰 <C>；不确定的地方直接停下回报，不要猜测
```

### 3. 派给「独立审查者」（`reviewer`）

- **Antigravity 调用参数**：
  - `TypeName`: `"research"`（纯代码审查）或 `"self"`（需跑测试命令时）
  - `Model`: `"flash"`（用户未指定 `pro` 时必填）
  - `Role`: `"Reviewer: <模块名>独立验收"`
- **Prompt 模板（全平台通用）**：
```text
目标：独立验收 <目录路径> 下的 <X> 是否符合 <Y 标准>
输出：逐条给【通过/不通过】+ 证据（文件路径+行号，或验证命令+实际输出）
边界：只读审查，发现问题只报告、绝对不要自己动手修复
```

---

## 六、防偷懒三条硬规矩与输出要求

1. **子代理说"应该好了" = 没完成。** 必须有实际产出和验证证据，才算完成。
2. **主控不许连续两轮只读不派。** 如果发现自己读了三轮还没派过活，说明已经失控了——立刻停下来调用内置 Subagent。
3. **每轮结束写一行进度。** 格式：`[谁] 干了什么 → 下一步`。

- 主控对外只输出：**规划清单**、**派单**、**验收结论**、**进度行**
- 自检清单（交付前过一遍）：
  - [ ] 主控自己没下场干脏活（或干了但有正当理由）
  - [ ] 默认走的是当前平台**内置原生 Subagent**，没有用代码/脚本（`dispatch.py`）套壳派工
  - [ ] 在 Antigravity 下，用户未指定 `pro` 时，全部显式传了 `Model: "flash"`，且未使用 OpenCode
  - [ ] 在 OpenCode 下，直接使用了内置 Subagent 工具，未用外部脚本套娃
  - [ ] 每个派单都带齐三件套（目标 / 输出 / 边界）
  - [ ] Type-B 验收交给了全新的 `reviewer` 子代理会话，不是施工那一位
  - [ ] 本次若踩了新坑或发现更优派法，已按自我进化协议写入 `learnings/`

---

## 七、自我进化协议（触发式，避免记忆膨胀）

> 本技能通过 `learnings/` 目录自我进化。**不是每次调用都写**，只在触发时写，且**先查重**。

**触发条件**（满足任一才记录）：
- 派发或参数映射失败
- 同一任务**连续失败 2 次**
- 用户或主控纠正了本技能的说法
- 发现更省 token / 更快 / 更准的派法
- 子代理产出"看着对但实际不对"，说明派单三件套漏了东西

**写入流程**：
1. 打开 `learnings/ERRORS.md`（坑）或 `learnings/BEST_PRACTICES.md`（好做法）
2. **先 grep 查重**：`grep -i "关键词" learnings/*.md`，已有则更新原条目，**不新增**
3. 无重复才追加，格式：`ID | 场景 | 坑/做法 | 正确做法/适用条件 | 状态`

---

## 附录：跨 CLI 显式点名备选（`scripts/dispatch.py`）

> ⚠️ **默认禁用**：日常任务严禁调用 `scripts/dispatch.py`。
> **唯一启用条件**：仅当用户在对话中**明确点名要求跨平台调用外部 CLI**（例如在 Antigravity 中明确说“这活你去调外部 OpenCode / Codex CLI 跑一下”）时，才允许通过命令行调用 `/Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py`。
