# 声纹后端 API

OpenClaw、其他 Agent 或业务 CLI 调用声纹服务时阅读本文。后端是客户目录、SQLite、声纹文件、模型、任务状态和校准缓存的唯一业务所有者。

默认地址通过 `FEISHU_SPEAKER_API_URL` 配置；Mac 通常是 `http://127.0.0.1:8765`，当前 Ubuntu 是 `http://192.168.31.169:8765`。API 仅供本机或可信局域网使用，不得暴露到公网。

## 通用规则

- 先调用 `GET /api/v1/capabilities`，确认 `service_api: 1`。
- 调用 `GET /api/v1/customers` 获取稳定客户 ID；不要自行读取 SQLite 或推测客户目录。
- 业务请求只使用客户目录内相对路径。后端拒绝绝对路径、`..`、软链接逃逸和 `声纹数据` 子目录。
- 所有写请求使用 `Content-Type: application/json`。当前可信局域网部署不使用 Token，也不开放 CORS。
- 创建长任务返回 HTTP `202`。按 `status_url` 轮询，不保持长连接。
- 技术任务 ID 只在 Agent 状态中传递，不能要求用户输入、朗读或复制。

错误固定为：

```json
{
  "ok": false,
  "error_code": "MISSING_VIEWPOINT_LABELS",
  "message": "每个有效标签都必须提供观点、摘要或非实质说明。",
  "retryable": true,
  "details": {"missing_labels": ["说话人 3"]}
}
```

`retryable: true` 时修复 `details` 指出的输入并继续同一任务，不要重新创建相同任务。

## 后续录音识别

创建任务：

```http
POST /api/v1/analysis-tasks
Content-Type: application/json
```

```json
{
  "schema_version": 1,
  "external_request_id": "飞书触发消息ID或Agent内部稳定ID",
  "conversation": {
    "channel": "feishu",
    "chat_id": "会话ID",
    "user_id": "用户ID",
    "trigger_message_id": "消息ID"
  },
  "customer_id": "jiangsu-kesheng",
  "meeting": {
    "audio_relpath": "录音/media.ogg",
    "transcript_relpath": "录音/transcript.md"
  },
  "attendees": [],
  "known_label_map": {},
  "excluded_labels": []
}
```

后端从录音文件名生成标题，从文件摘要生成内部会议 ID，并根据当前声纹版本计算候选组合。相同来源、管线、候选版本和意图返回原任务；同一 `external_request_id` 指向不同输入时返回 `409 EXTERNAL_REQUEST_CONFLICT`。

接口：

```text
GET  /api/v1/analysis-tasks/{task_id}
GET  /api/v1/analysis-tasks/{task_id}/semantic-request
POST /api/v1/analysis-tasks/{task_id}/semantic-result
GET  /api/v1/analysis-tasks/{task_id}/report?format=feishu|json|markdown
POST /api/v1/analysis-tasks/{task_id}/cancel
POST /api/v1/analysis-tasks/{task_id}/retry
POST /api/v1/analysis-tasks/{task_id}/corrections
```

典型状态：

```text
queued → running/transcoding → running/extracting_embeddings
→ awaiting_semantic → queued/queued_finalize → running/finalizing → completed
```

只有到达 `awaiting_semantic` 后才读取 `semantic-request`。响应包含转写索引、候选人员和 `required_labels`。一次提交：

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

字段细节见 [数据格式](schemas.md)。语义结果必须覆盖每个标签；校验失败后任务回到 `awaiting_semantic / semantic_revision_required`。

完成后优先读取 `format=feishu` 并发送其中的 `message_markdown`。用户索要详情时再读取 `format=markdown`；`format=json` 是完整权威结果。不得由 Agent 重写声纹排序或另造报告规则。

人工纠正请求沿用语义工作流中的会话绑定字段和 `corrections` 数组，只生成版本化报告，返回 `voiceprint_changed: false`。

## 简单首次建库

```http
POST /api/v1/enrollment-tasks
Content-Type: application/json
```

```json
{
  "schema_version": 1,
  "external_request_id": "触发消息ID",
  "conversation": {
    "channel": "feishu",
    "chat_id": "会话ID",
    "user_id": "用户ID",
    "trigger_message_id": "消息ID"
  },
  "customer_id": "customer-id",
  "meetings": [
    {"audio_relpath": "录音/会议1.ogg", "transcript_relpath": "录音/会议1.txt"},
    {"audio_relpath": "录音/会议2.ogg", "transcript_relpath": "录音/会议2.txt"}
  ],
  "attendees": [
    {"name": "目标人员", "role": "职位", "organization": "customer"}
  ],
  "target_person": {"name": "目标人员"},
  "review_mode": "auto"
}
```

接口：

```text
GET  /api/v1/enrollment-tasks/{task_id}
GET  /api/v1/enrollment-tasks/{task_id}/audition
POST /api/v1/enrollment-tasks/{task_id}/confirm
POST /api/v1/enrollment-tasks/{task_id}/cancel
POST /api/v1/enrollment-tasks/{task_id}/retry
```

一个明确目标人、最多三组非红色单聚类候选时返回 `review_mode: feishu_quick`、固定消息、合并试听地址和 A/B/C。否则返回 `review_mode: web_full`、原因和 `review_url`。两种模式共用同一个审核会话。

确认请求：

```json
{
  "included_codes": ["A", "C"],
  "confirmation_text": "确认建库",
  "confirmation_message_id": "确认消息ID",
  "channel": "feishu",
  "chat_id": "会话ID",
  "user_id": "用户ID"
}
```

单候选可以省略 `included_codes`。多候选必须先由用户选择，Agent 回显后等待明确的“确认建库”。网页也可直接接管同一任务；网页提交后轮询状态会得到 `completed`。

## 进度、取消和恢复

任务状态包含：

```json
{
  "status": "running",
  "phase": "extracting_embeddings",
  "progress": {
    "current": 18,
    "total": 42,
    "percent": 42.9,
    "message": "正在提取声纹 18/42"
  }
}
```

取消和重试使用空 JSON 对象 `{}`。运行中取消采用协作停止；服务异常重启后，根据 SQLite 检查点恢复。报告定稿优先于审核包准备，审核包准备优先于新的声学分析；同优先级按创建时间执行。
