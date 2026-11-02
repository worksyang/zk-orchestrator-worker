# zk-orchestrator-worker 最佳实践

> 格式：`ID | 场景 | 做法 | 适用条件 | 状态`
> 状态：`draft`（初步）→ `proven`（反复验证）

| ID | 场景 | 做法 | 适用条件 | 状态 |
|---|---|---|---|---|
| BP-20261018-01 | 首次在新平台使用 | 开工前先列出本机可用子代理及权限，做一次「角色 → 子代理名」映射并写进对话，后续轮次直接复用 | 任何平台首次调用本技能 | proven |
| BP-20261018-02 | 本环境只有一个模型家族 | 拿不到跨家族纠错收益时，至少让审查者开全新上下文，不继承施工轮对话 | 单模型平台 | draft |
| BP-20261102-01 | Antigravity 及其它 CLI 派发子代理 | 默认统一通过 `scripts/dispatch.py` 派给 OpenCode (`magpie/auto/deepseek-v4.1-flash`, `low`)；Antigravity 下 `run_command` 设 `WaitMsBeforeAsync=500` 即自动转后台并在进程退出时触发 `<SYSTEM_MESSAGE>` 主动唤醒主控，彻底脱离时加 `--notify-agy always` 走 `agy agentapi` 推送 | Antigravity 深度支持 + 全平台默认 OpenCode | proven |
