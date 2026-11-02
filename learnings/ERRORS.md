# zk-orchestrator-worker 踩坑库

> 格式：`ID | 场景 | 坑 | 正确做法 | 状态`
> 状态：`open`（未验证）→ `resolved`（已验证）→ `stale`（已过时，不删只标）

| ID | 场景 | 坑 | 正确做法 | 状态 |
|---|---|---|---|---|
| ERR-20261018-01 | 跨平台复用本技能 | 原版写死 `@explore`/`@general`/`@reviewer`，换到 M-Code 或其他平台这些名字不存在，Skill 整段失效 | 按角色能力特征映射，不按名字匹配；本环境没有就先定义子代理 | resolved |
| ERR-20261018-02 | 验收环节 | 派给施工单位同一个子代理做验收，它替自己的产出说话，问题全放过 | Type-B 必须换独立的审查者角色，且开全新上下文 | resolved |
| ERR-20261102-01 | `opencode run` 模型与角色参数 | 1) 裸传 `-m auto/deepseek-v4.1-flash` 报 UnknownError；2) 传 `--agent explore` 报 subagent 警告并退回可写的 `build` | 1) 必须带 provider 前缀 `magpie/auto/deepseek-v4.1-flash`；2) 只读侦察/验收用 `--agent plan`，施工用 `--agent build --auto`（已内置于 `dispatch.py`） | resolved |
