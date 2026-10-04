---
name: codex-session-continue
description: 根据 Codex 会话 thread ID（UUID，如 01a0fca2-e17f-7e91-a86d-253ead48728e）在 ~/.antigravity_cockpit/instances/codex/ 各实例的 state_5.sqlite 中定位对应的 rollout JSONL 会话日志文件。当用户给出 UUID 并说"基于这个会话继续"、"基于xxx会话继续"、"continue from session"等，需要在另一个 Codex 实例/账号中接力之前的会话时使用。
---

# Codex Session Continue

## Overview

用户运行多个 Codex 实例副本（各自登录不同账号）以规避单账号额度限制。当某个实例额度用尽，需要在当前环境中基于另一个实例的历史会话继续任务。本 skill 只负责一件事：**把 thread ID 解析为 rollout JSONL 文件路径**，之后的阅读理解由你（Agent）自行决定策略。

## 步骤

1. 从用户消息中提取 UUID 格式的 thread ID（形如 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）。
2. 运行查找脚本：

   ```bash
   bash <skill-dir>/scripts/find_rollout.sh <thread-id>
   ```

   - 命中：stdout 输出 rollout 文件的绝对路径（立刻停止，无需再查其他实例）。
   - 未命中：stderr 输出 `NOT_FOUND`，退出码 1。此时告知用户未找到，不要猜测路径。

3. 拿到路径后阅读该 JSONL 文件，理解之前的会话上下文，然后结合用户本次给出的新目标继续任务。

## 阅读 rollout JSONL 的建议

- 文件为 JSONL，每行一条记录：用户消息、assistant 回复、工具调用及其结果、session_meta 等。
- **文件可能非常大（几十 MB），不要一次全读**。先看行数/大小，再决定策略。
- 推荐先还原对话主线：提取 user 消息与 assistant 的最终文本回复（可用 `jq`/`grep` 按行过滤），跳过工具调用细节。
- 需要近期操作细节时，再读文件尾部最近的记录；单条 tool output 很长时注意截断，避免撑爆上下文。
