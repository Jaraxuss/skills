# Agent 端到端工作流

OpenClaw 或其他 Agent 发起首次声纹建库、后续录音分析、报告纠正时阅读本文。所有命令都输出单个 JSON 对象；技术任务 ID 只在 Agent 内部传递，不能要求用户输入或朗读。

## 能力探测

每次部署或升级后先运行：

```text
speaker_insights.py capabilities
```

`agent_api` 或 `engine_schema` 不兼容时停止执行并升级 Skill。不要根据自然语言终端日志猜测接口。

## 简单首次建库

适用条件：用户明确只想为一个人建库；审核包最多三组非红色候选；没有需要逐片段拆分的混合风险。一个录音只有一个重要说话人也属于此流程。复杂任务由引擎自动返回 `web_full`，不要强行留在聊天中。

### 1. 发起

写入请求 JSON：

```json
{
  "schema_version": 1,
  "external_request_id": "openclaw内部请求ID",
  "conversation": {
    "channel": "feishu",
    "chat_id": "飞书会话ID",
    "user_id": "发起人ID",
    "trigger_message_id": "发起消息ID"
  },
  "manifest": {
    "schema_version": 1,
    "customer": {"id": "customer-id", "name": "客户名称"},
    "meetings": [
      {"audio": "/绝对路径/录音1.ogg", "transcript": "/绝对路径/录音1.txt"},
      {"audio": "/绝对路径/录音2.ogg", "transcript": "/绝对路径/录音2.txt"}
    ],
    "attendees": [
      {"name": "目标人员", "role": "职位", "organization": "customer"}
    ]
  },
  "target_person": {"name": "目标人员"},
  "review_mode": "auto"
}
```

执行：

```text
speaker_insights.py agent enroll-start --request REQUEST.json --base-url http://HOST:8765
```

相同客户、源文件哈希、模型/算法版本、候选声纹版本和建库意图会得到相同 `request_hash`，SQLite 返回原任务及检查点，不重复转码或提取向量。

### 2. 呈现试听

- `review_mode: feishu_quick`：把 `message_markdown` 和唯一的 `audition_audio` 发给用户。合并音频用一声、两声、三声提示音稳定对应 A、B、C，不依赖多个飞书附件的显示顺序。
- `review_mode: web_full`：返回 `review_url`，说明存在多人员、混合或复杂选择，需要打开审核台。

不要把 `task_id`、`session_id`、`candidate_id` 发给用户要求操作。A/B/C 只是本轮可说出口的短代号。

### 3. 收集选择并确认

- 只有一个候选：用户直接说“确认建库”即可，后端自动选择唯一候选。
- 两到三个候选：用户可说“保留 A、C，排除 B”。Agent 必须先回显“将保留 A、C”，之后等待用户说“确认建库”。
- “可以”“嗯”“就这样”等模糊回复不能视为最终授权。

最终确认后，Agent 用内部保存的任务 ID 生成请求：

```json
{
  "task_id": "仅Agent持有",
  "included_codes": ["A", "C"],
  "confirmation_text": "确认建库",
  "confirmation_message_id": "本次确认消息ID",
  "channel": "feishu",
  "chat_id": "飞书会话ID",
  "user_id": "确认用户ID"
}
```

执行：

```text
speaker_insights.py agent enroll-confirm --request CONFIRMATION.json
```

后端验证会话和用户绑定、来源哈希、候选选择、6 段/12 秒、向量一致性与确认消息重放。完全相同的重试返回原结果；同一确认消息对应不同选择时返回 `CONFIRMATION_MESSAGE_REPLAY_CONFLICT`。

## 后续录音识别

### 1. 声学阶段

请求使用单场 `meeting` 清单：

```json
{
  "schema_version": 1,
  "external_request_id": "openclaw内部请求ID",
  "conversation": {
    "channel": "feishu",
    "chat_id": "飞书会话ID",
    "user_id": "发起人ID",
    "trigger_message_id": "消息ID"
  },
  "manifest": {
    "schema_version": 1,
    "customer": {"id": "customer-id", "name": "客户名称"},
    "meeting": {
      "id": "内部会议ID",
      "title": "录音文件名",
      "audio": "/绝对路径/新录音.ogg",
      "transcript": "/绝对路径/新录音.txt"
    },
    "attendees": [],
    "known_label_map": {},
    "excluded_labels": []
  }
}
```

```text
speaker_insights.py agent analyze-start --request REQUEST.json
```

返回 `semantic_request`。相同源文件、模型/算法和实际候选声纹版本会复用声学检查点；任一正式声纹版本变化都会产生新的候选组合哈希和任务。

### 2. 一次生成语义结果

Agent 读取 `semantic_request.json` 中的转写索引和 `required_labels`，生成一个文件：

```json
{
  "context": {"schema_version": 1, "items": []},
  "viewpoints": {
    "schema_version": 1,
    "items": [],
    "non_substantive_labels": []
  }
}
```

具体字段见 [数据格式](schemas.md)。每个标签必须有观点、发言摘要或有原文依据的非实质分类。

```text
speaker_insights.py agent analyze-complete \
  --task INTERNAL_TASK_ID --semantic-response SEMANTIC.json
```

成功后优先发送 `feishu_summary` 指向 JSON 中的 `message_markdown`。不要让 OpenClaw 自行改写排名或另造消息模板；用户需要详情时再发送 `detailed_report`。

## 报告纠正与声纹扩充分离

用户说“这次的说话人 2 实际是王总”时，只纠正本次报告：

```json
{
  "confirmation_message_id": "纠正消息ID",
  "channel": "feishu",
  "chat_id": "原会话ID",
  "user_id": "用户ID",
  "corrections": [
    {"transcript_label": "说话人 2", "person_id": "已知人员ID"}
  ]
}
```

```text
speaker_insights.py agent analysis-correct \
  --task INTERNAL_TASK_ID --corrections CORRECTIONS.json
```

该命令生成版本化的纠正报告，并返回 `voiceprint_changed: false`。不要因为纠正而自动扩充声纹。用户另行明确要求“把这次语音加入王总声纹”时，才进入候选审核流程。

## 幂等、恢复与错误

SQLite `task_executions` 保存：

- 原始录音和转写哈希；
- 模型、算法和配置哈希；
- 实际候选人员、当前声纹版本及 NPZ 哈希；
- 整体请求哈希和语义响应哈希；
- 当前阶段、检查点、结果路径、错误和短租约。

任务只在执行计算时持有租约；等待 Agent 生成语义或等待用户确认时会释放。进程异常后，原请求会从已保存的审核包或声学结果继续；不会把每个窗口都单独写进 SQLite。若异常发生在尚未形成声学检查点的窗口处理中，该阶段会安全重跑，但正式声纹提交仍由会话锁、来源哈希和原子文件替换保证不会产生半成品。

错误 JSON 固定为：

```json
{
  "ok": false,
  "error_code": "MISSING_VIEWPOINT_LABELS",
  "message": "每个转写标签都必须包含可回查的核心观点、发言摘要或非实质发言说明。",
  "retryable": true,
  "details": {"missing_labels": ["说话人 3"]}
}
```

`retryable: true` 时修复 `details` 指出的输入并重试同一任务；不要新建一份相同任务。可用以下命令读取检查点：

```text
speaker_insights.py agent task-status --task INTERNAL_TASK_ID
```

## 当前刻意保留的边界

- 混合标签只标记为混合/不确定，暂不自动二次拆分。
- 同一人员在多场新录音中产生的多个扩充候选仍分别审核，暂不合并。
- 以上两项均不能由 Agent 私自绕过或自动写入正式声纹。
