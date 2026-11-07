# zk-orchestrator-worker 踩坑库

> 格式：`ID | 场景 | 坑 | 正确做法 | 状态`
> 状态：`open`（未验证）→ `resolved`（已验证）→ `stale`（已过时，不删只标）

| ID | 场景 | 坑 | 正确做法 | 状态 |
|---|---|---|---|---|
| ERR-20261018-01 | 跨平台复用本技能 | 原版写死 `@explore`/`@general`/`@reviewer`，换到 M-Code 或其他平台这些名字不存在，Skill 整段失效 | 按角色能力特征映射，不按名字匹配；本环境没有就先定义子代理 | resolved |
| ERR-20261018-02 | 验收环节 | 派给施工单位同一个子代理做验收，它替自己的产出说话，问题全放过 | Type-B 必须换独立的审查者角色，且开全新上下文 | resolved |
| ERR-20261102-01 | `opencode run` 模型与角色参数 | 1) 裸传 `-m auto/deepseek-v4.1-flash` 报 UnknownError；2) 传 `--agent explore` 报 subagent 警告并退回可写的 `build` | 1) 必须带 provider 前缀 `magpie/auto/deepseek-v4.1-flash`；2) 只读侦察/验收用 `--agent plan`，施工用 `--agent build --auto`（已内置于 `dispatch.py`） | resolved |
| ERR-20261102-02 | OpenCode 子代理内部套娃派单或跨目录只读 | 子代理在 `--role scout` (`--agent plan`) 下自己再调内部 `task` 工具或读 `--cwd` 以外目录（如 `/Applications`）会被权限拒绝并拖慢耗时 | 派单提示词中明确加「不要调用内部 task 子代理，直接读文件」；需跨目录只读检查时可用 `--role worker` 并在边界锁死「只读不改任何文件」 | resolved |
| ERR-20261107-01 | `dispatch.py` 的 `--cwd` 与 shell 引号转义 | 1) 把 `--cwd` 设为 `/Users/works14` 主目录会导致 OpenCode 启动时全盘扫描卡死；2) 用双引号 `"..."` 包裹含反引号 `` `cmd` `` 的提示词会被 zsh 在派单前当成子命令执行 | 1) `--cwd` 必须指向具体子项目目录（或 `/tmp`），严禁传用户主目录 `/Users/works14`；2) 传给 `dispatch.py` 的长提示词一律用单引号 `'...'` 包裹 | stale |
| ERR-20261108-01 | 用外部 Shell 脚本（`dispatch.py`）跨端派工 | 在 Antigravity 中用 `run_command` 调外部 CLI 即使设 `WaitMsBeforeAsync=500` 也会被前端 UI 判定为未结束的 Tool Call 从而锁死输入框，用户发消息或打断还会触发后台 Task 重启被杀 | 废除默认用脚本跨端派工；各平台一律默认走自己内置的原生 Subagent（Antigravity 用 `invoke_subagent` + 默认 `Model: "flash"`；OpenCode 用内置 `task` 工具） | resolved |
