# 只读 CLI 回退

仅在 `customer-wechat-readonly` MCP 不可用时读取本页。历史 CLI 模块名仍为 `scripts.customer_wechat_cli`，它调用与 MCP 相同的只读 API，支持微信及飞书已纳入资料；不要因此改成直接查询聊天源。

Ubuntu 项目目录为 `/home/velen/velen/customer-wechat`，解释器为 `/home/velen/miniconda3/envs/llm/bin/python`，只读凭据由客户端从 `~/.config/customer-wechat/agent.json` 加载，不输出或复制凭据。

在 Ubuntu 上执行：

```bash
cd /home/velen/velen/customer-wechat
PYTHONNOUSERSITE=1 /home/velen/miniconda3/envs/llm/bin/python -m scripts.customer_wechat_cli customers '用户给出的客户名'
```

从 Mac 访问时优先通过 `ssh velen@192.168.31.169` 在 Ubuntu 执行同一命令；内网不可达再用 `ssh velen@ubuntu-server`。本地复制了 Skill 不等于本地已安装 MCP 或具备 Agent 凭据。

下面的 `<客户ID>`、`<会话ID>` 等是占位，执行前替换成实际只读查询结果；不是可直接运行的固定 ID：

```text
python -m scripts.customer_wechat_cli conversations <客户ID> --query '联系人或群名'
python -m scripts.customer_wechat_cli knowledge '主题词' --customer-id <客户ID>
python -m scripts.customer_wechat_cli search <客户ID> '主题词' --conversation-id <会话ID> --page 1
python -m scripts.customer_wechat_cli history <客户ID> <会话ID> --start <Unix秒> --end <Unix秒>
python -m scripts.customer_wechat_cli history <客户ID> <会话ID> --start <同一起点> --end <同一终点> --cursor '<next_cursor>'
python -m scripts.customer_wechat_cli message <消息ID>
python -m scripts.customer_wechat_cli read '<查询返回的文档URI>'
```

实际使用上面的 Ubuntu 绝对解释器并设置 `PYTHONNOUSERSITE=1`。CLI 没有 `--source` 参数；限定渠道时从会话列表选出符合渠道的会话 ID 后读取，不能发明参数。`customers`、`conversations` 的 CLI 没有翻页参数；返回 `pages>1` 且仍需后续候选时，用项目内 `agent_access.client.AgentClient` 的对应方法传 `page/page_size`，不要认为只有第一页候选。

保持主 Skill 的范围规则：单客户语义检索必须传 `--customer-id`；仅用户明确要求所有客户时才省略。查询失败或为空，不改用不限客户的调用。
