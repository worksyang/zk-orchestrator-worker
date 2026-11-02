---
name: zk-orchestrator-worker
description: 主控-工作者（Orchestrator-Worker）多代理编排与跨 CLI 派发技能。当任务多步骤、跨文件、需要"先调研再动手再验收"时使用；也当用户说"你派子代理去写""派出 subagent 来写""让子代理去做""扔给子代理""subagent 去干""派活给 subagent""多代理干活""编排一下""拆解任务""并行开工""省 token 干活""大任务分几步""你来指挥别自己动手""调 opencode 去干"时使用——出现"派/扔/交/让 + 子代理/subagent/下属/opencode"这类说法一律命中。核心：① 主控只做规划、派活、验收三件事，读文件、写代码、跑命令全部外包给侦察(scout)/施工(worker)/验收(reviewer)三类子代理；② 默认尽可能全部派发给 OpenCode（默认模型 magpie/auto/deepseek-v4.1-flash，low 模式），Antigravity 深度支持（后台异步并行 + 自动完成唤醒 + agy agentapi 推送双保险），其他 Agent CLI（Claude Code、Codex、Pi Agent）浅支持。
license: MIT
metadata:
  version: "2.0.0"
  author: 震凯的小助理
---

# zk-orchestrator-worker — 主控只动嘴，脏活全外包给 OpenCode

把"贵脑子"从执行里解放出来：主控只做**规划、派活、验收**；读文件、写代码、跑命令全部交给子代理；子代理的中间过程**永远不回流**到主控上下文。

本技能同时承担两件事：
1. **派发方法论**：规定侦察（`scout`）、施工（`worker`）、验收（`reviewer`）三个角色与派单三件套。
2. **统一派发引擎（`scripts/dispatch.py`）**：**默认把所有子代理任务派发给本机 OpenCode**（默认锁死 `magpie/auto/deepseek-v4.1-flash` 的 `low` 模式），对 **Antigravity (`agy`)** 做深度异步唤醒支持，对 **Claude Code / Codex / Pi Agent** 做浅支持。

---

## 一、派发引擎与平台支持矩阵（先看怎么派）

### 1. 统一派单脚本命令

不要手拼复杂的 CLI 参数，直接调本技能自带的纯 Python 3 派单脚本（自动处理 `magpie/` 前缀、角色权限隔离、JSON 解析与外部日志落盘）：

```bash
# 1) 只读侦察（scout → 自动映射 opencode 的 plan 只读模式 + deepseek-v4.1-flash low）
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py \
  --role scout --cwd "/目标工作目录" "目标：... 输出：... 边界：只读，不要改任何文件"

# 2) 全权限施工（worker → 自动映射 opencode 的 build --auto 模式 + deepseek-v4.1-flash low）
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py \
  --role worker --cwd "/目标工作目录" "目标：... 输出：... 边界：..."

# 3) 独立审查验收（reviewer → 自动映射 opencode 的 plan 只读模式 + 全新会话）
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py \
  --role reviewer --cwd "/目标工作目录" "目标：... 输出：... 边界：只读，发现问题只报告、不修复"
```

- **默认模型**：`magpie/auto/deepseek-v4.1-flash`（哪怕你传 `--model auto/deepseek-v4.1-flash`，脚本也会自动补齐 `magpie/` 前缀，避免 OpenCode 报错）。
- **默认推理档位**：`--variant low`。
- **续接会话**：如果需要让刚才那个施工子代理返工，带上输出头里的 `session=ses_xxx`：`--session ses_xxx`。
- **切换其他外部 CLI（浅支持）**：只有用户明确点名时，才加 `--engine codex`、`--engine claude`、`--engine pi` 或 `--engine agy`；不点名时**一律默认 `--engine opencode`**。

---

### 2. Antigravity 深度支持（异步并行 + 自动唤醒机制）

在 **Antigravity** 中担任主控时，**严禁使用内置的 Gemini `invoke_subagent` 去干普通脏活**，默认一律通过 `run_command` 调上面的 `dispatch.py` 把活派给 OpenCode (`auto/deepseek-v4.1-flash` low 模式)：

1. **怎么做到不卡死主 Agent、并行派活？**
   - 调用 `run_command` 运行 `dispatch.py` 时，如果预计任务超过 5 秒（或要一次并行派多个子代理），把 **`WaitMsBeforeAsync` 设为 `500`（或 `1000`），`IsDaemon` 保持 `false`**。
   - Antigravity 会在 0.5 秒后自动把该子代理切入后台任务（Background Task），主控立刻腾出手来继续响应用户或派发第 2、第 3 个并行子任务。
2. **子代理干完活怎么主动通知主控？**
   - **第一重（原生进程退出唤醒，默认主力）**：当后台的 `dispatch.py` 跑完退出（进程终止）的那一秒，Antigravity 底层会自动向主控注入一条高优先级的 `<SYSTEM_MESSAGE>`（含完整返回结果），**自动唤醒主控进入下一轮验收**，无需轮询（禁止 `sleep` 轮询）。
   - **第二重（`agy agentapi` 跨进程主动推送，兜底双保险）**：如果某个超长任务需要彻底脱离当前工具生命周期（例如完全 detached 运行），在命令末尾加上 `--notify-agy always`。脚本会在 OpenCode 跑完后自动读取当前会话的 `ANTIGRAVITY_CONVERSATION_ID` 和 `ANTIGRAVITY_LS_ADDRESS`，调用 `agy agentapi send-message` 把结果硬推回主会话唤醒你。

---

### 3. 其他宿主 CLI 浅支持（怎么防「跑完不响铃」）

当你在 **Claude Code、Codex CLI、OpenCode、Pi Agent** 里担任主控，同样想调用本技能把活派给 OpenCode（`auto/deepseek-v4.1-flash` low）时：

| 当前主控宿主 | 怎么调用 `dispatch.py` 才能保证跑完自动反馈？ |
|---|---|
| **Claude Code** | 直接用 Bash 工具设 `run_in_background: true` 跑 `dispatch.py`，跑完会自动通知主控。 |
| **Codex CLI / Pi Agent / OpenCode** | ⚠️ 这三家的普通后台 shell 跑完**不会主动唤醒主控**！所以如果要并行/后台跑，请用宿主自带的原生子代理（`spawn_agent` / `subagent` / `task`）包一层，让原生子代理在前台同步跑 `dispatch.py`；或者主控直接在前台同步跑 `dispatch.py` 等它返回。 |

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

开工后如果发现自己又准备去 `read` / `grep` / 搜代码了，先停一下自问：**"这活能不能派给 OpenCode 子代理？"** 能，就派。

为什么：主控的上下文最贵，也最脆弱。一次大范围搜索就能塞进几万 token 的无关内容，此后主控的每一个判断都被稀释。子代理跑在独立的 `opencode run` 进程里，**中间过程传不上来，这是设计，不是限制**。

### 原则 2：派活按三个标准角色（自动映射 OpenCode 权限）

本技能固定三个角色，`dispatch.py` 已经把它们的权限在底层锁死：

| 任务类别 | `--role` 参数 | 底层自动映射的 OpenCode 模式 | 能力特征 |
|---|---|---|---|
| **侦察** | `--role scout` | `--agent plan`（只读） | 找文件、摸结构、搜关键词、看依赖；**底层禁改文件** |
| **施工** | `--role worker` | `--agent build --auto`（全权限） | 写代码、改文件、跑命令、测功能；**有完整写权限** |
| **验收** | `--role reviewer` | `--agent plan`（只读 + 新会话） | 独立检查产出是否达标；**只读、不能改**、必须给证据 |
| **判断** | **主控自己** | 主控自身 | 架构取舍、审美、要不要做、多个方案选哪个 |

**核心纪律**：
- **默认全走 OpenCode**：侦察、施工、验收默认全用 `dispatch.py` 调 `magpie/auto/deepseek-v4.1-flash`（`low` 模式）。
- **验收必须开新会话**：`--role reviewer` 绝不能传施工那轮的 `--session`，必须开全新上下文独立盲审；且因为主控（比如 Antigravity 的 Gemini）和子代理（OpenCode 的 DeepSeek V4.1 Flash）本身就是**跨模型家族组合**，天然享受跨家族纠错红利（同模型自查纠错率 12%，跨家族 52%）。

### 原则 3：派单必须带三件套

每个传给 `dispatch.py` 的提示词都必须写全这三样，缺一个子代理就会漂移：

1. **目标**：要交付什么（具体到文件、函数、标准）
2. **输出格式**：回什么（摘要？文件路径？结构化结论？多少字以内？）
3. **边界**：什么能动、什么绝对不能碰

### 原则 4：验收分两档

产出回来后，按检查类型分两档处理：

| 档位 | 检查内容 | 谁来做 |
|---|---|---|
| **Type-A（机器可验）** | 文件存在吗？退出码是 0 吗？测试通过吗？ | **主控自己看一眼**，或交给 `--role worker` 跑 |
| **Type-B（价值判断）** | 做得好不好？能不能交付？符合原始目标吗？ | **必须另起一个 `--role reviewer` 独立审查** |

---

## 四、标准六步工作流

1. **规划**（主控）：把任务拆成清单，给每步标上类别（`scout` / `worker` / `reviewer`）
2. **映射**（主控）：默认全部映射到 `dispatch.py`（`engine=opencode, model=magpie/auto/deepseek-v4.1-flash, variant=low`），写在派单开头
3. **侦察**（`--role scout`）：摸清现状再动手。跳过侦察直接施工，是返工的最大来源
4. **施工**（`--role worker`）：按派单模板干活。互相独立的子任务可以并行跑多个 `dispatch.py`（Antigravity 下设 `WaitMsBeforeAsync: 500`）
5. **验收**（`--role reviewer`）：对照**原始目标**逐条查，不是对照施工子代理自己的说法
6. **终审**（主控）：过了就交付；没过，带着具体问题（可用 `--session` 续接原施工会话）打回重做

---

## 五、三个派单模板（直接抄进 `dispatch.py` 参数）

**1. 派给「只读侦察者」（`--role scout`）：**
```bash
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py --role scout --cwd "<目录>" "
目标：搞清楚 <X> 的结构——涉及哪些文件、关键逻辑在哪
输出：只回一份清单（文件路径 + 每个文件干什么），不超过 200 字
边界：只读，不要改任何文件
"
```

**2. 派给「全权限执行者」（`--role worker`）：**
```bash
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py --role worker --cwd "<目录>" "
目标：实现 <X>，验收标准是 <Y>
输出：改了哪些文件、每个文件改了什么、怎么验证的
边界：只动 <A/B> 文件，不要碰 <C>
"
```

**3. 派给「独立审查者」（`--role reviewer`）：**
```bash
python3 -B /Users/works14/.agents/skills/zk-orchestrator-worker/scripts/dispatch.py --role reviewer --cwd "<目录>" "
目标：独立验收 <X> 是否符合 <Y 标准>
输出：逐条给通过/不通过 + 证据（文件路径+行号，或命令+输出）
边界：只读，发现问题只报告、不修复
"
```

---

## 六、防偷懒三条硬规矩与输出要求

1. **子代理说"应该好了" = 没完成。** 必须有实际产出和验证证据，才算完成。
2. **主控不许连续两轮只读不派。** 如果发现自己读了三轮还没派过活，说明已经失控了——立刻停下来调 `dispatch.py`。
3. **每轮结束写一行进度。** 格式：`[谁] 干了什么 → 下一步`。

- 主控对外只输出：**规划清单**、**派单**、**验收结论**、**进度行**
- 自检清单（交付前过一遍）：
  - [ ] 主控自己没下场干脏活（或干了但有正当理由）
  - [ ] 默认走的是 `dispatch.py` → OpenCode (`magpie/auto/deepseek-v4.1-flash`, `low`)
  - [ ] 每个派单都带齐三件套（目标 / 输出 / 边界）
  - [ ] Type-B 验收交给了全新的 `--role reviewer` 会话，不是施工那一位
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
