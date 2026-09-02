# Agent 端到端工作流

OpenClaw 或其他 Agent 发起首次建库、后续识别或报告纠正时阅读本文。HTTP 字段和状态见 [后端 API](api.md)，语义内容见 [数据格式](schemas.md)。

## 共同入口

1. 请求 `GET /api/v1/capabilities`，确认 `service_api: 1`。
2. 请求 `GET /api/v1/customers`，用稳定 ID 或唯一精确名称选客户；歧义时再问用户。
3. 将飞书录音和转写下载到该客户目录，业务请求只传相对于客户目录的路径。
4. Agent 保存后端返回的技术任务 ID，但不展示给用户，也不让用户输入或朗读。
5. 后端不可用时停止并返回可重试状态，不读取 SQLite、不运行本地模型、不猜客户根目录。

API 地址优先来自 `FEISHU_SPEAKER_API_URL`。没有直接 HTTP 能力时，可运行同名 `agent` CLI；它只是 HTTP 客户端，不会回退为本地业务逻辑。

## 简单首次建库

适用场景是用户明确只为一个人建库。调用 `POST /api/v1/enrollment-tasks` 后轮询任务：

- `review_mode: feishu_quick`：发送后端给出的 `message_markdown`，并从 `audition_url` 取得唯一的合并试听音频。提示音的一声、两声、三声稳定对应 A、B、C，不依赖飞书附件顺序。
- `review_mode: web_full`：发送 `review_url` 和后端给出的原因，结束聊天内逐标签确认。

快捷模式规则：

- 唯一候选时，用户明确回复或语音说“确认建库”即可。
- 两到三个候选时，用户先说“保留 A、C”之类选择；Agent 回显选择后，再等待“确认建库”。
- “可以”“嗯”“就这样”等模糊回复不是正式授权。
- 最终调用 `/confirm`，提交所选代码以及原飞书会话、用户和确认消息 ID。
- 用户随时可以打开同一任务附带的 `review_url`；网页完成后，轮询状态会变为 `completed`，不得再重复提交。

首次建库可包含多组录音和转写。若出现多个目标人、超过三组候选、红色风险、多个有效聚类或需要逐片段选择，后端会自动切换网页审核。

## 后续录音识别

1. 调用 `POST /api/v1/analysis-tasks`，传客户 ID、单组录音/转写相对路径和可选参会人。
2. 轮询任务。`queued` 或 `running` 时只向用户报告可读进度，不重复创建任务。
3. 到达 `awaiting_semantic` 后读取 `/semantic-request`。根据转写索引一次生成：
   - 可回查的上下文身份证据；
   - 覆盖每个 `required_labels` 的核心观点、发言摘要或有依据的非实质分类。
4. 提交 `/semantic-result`。若返回 `semantic_revision_required`，按 `details` 修复同一任务，不新建任务。
5. 完成后读取 `/report?format=feishu`，原样发送 `message_markdown`。用户需要完整内容时再读取 `format=markdown`；结构化处理使用 `format=json`。

不要让 OpenClaw 自行改变 Top-1/Top-2、相似度、身份状态或消息模板。报告中的相似度是候选集声纹证据，不是认证概率。

## 纠正与扩充分离

用户说“这次说话人 2 实际是王总”时，调用 `/corrections` 生成本次报告的纠正版。纠正必须绑定原会话和确认消息，结果固定包含 `voiceprint_changed: false`。

只有用户另行明确要求“把这次语音加入王总声纹”时，才进入声纹候选审核。不得因为报告纠正自动修改正式声纹。

## 幂等、恢复和停止条件

- OpenClaw使用触发消息 ID 或稳定内部 ID 作为 `external_request_id`。
- 相同源文件、模型/算法和候选声纹版本会复用原任务；任一当前声纹版本变化后可生成新任务。
- 同一外部请求 ID 指向不同文件会返回冲突，必须检查调用方状态，不能换 ID 静默重试。
- `retryable: true` 时继续原任务；`retryable: false` 时停止并说明原因。
- 用户取消时调用任务 `/cancel`；运行中任务会在安全边界协作停止。
- 混合标签暂不自动二次拆分；多个扩充候选暂不自动合并。
