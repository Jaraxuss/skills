# 数据格式与命令流程

Read this reference when creating a customer, enrolling profiles, analyzing a meeting, or generating semantic JSON.

## 会议清单

YAML and JSON are accepted. Paths must be absolute.

```yaml
schema_version: 1
customer:
  id: example-customer
  name: 示例客户
meeting:
  id: kickoff-example
  title: 项目启动会
  audio: /absolute/path/meeting.ogg
  transcript: /absolute/path/meeting.txt
attendees:
  - id: optional-stable-id
    name: 客户负责人
    role: 负责人
    organization: customer
  - name: 内部CSM
    role: CSM
    organization: yingdao
known_label_map:
  内部CSM: 内部CSM
excluded_labels:
  - 说话人 5
```

`organization` 只能是 `customer`、`yingdao` 或 `external`。外部参会人仅作为元数据，不会建库；需要建库时必须明确改为客户或我方。

## 旧版 CLI 建库确认

`enroll prepare` creates `enrollment_draft.json`. After showing one consolidated mapping table to the user, create:

```yaml
schema_version: 1
confirmed_by: CSM姓名或用户提供的确认人
label_map:
  内部CSM: 内部CSM
  说话人 1: 客户负责人
  说话人 2: 客户运营
excluded_labels:
  - 外部支持人员
```

每个映射姓名都必须精确对应参会人。即使 `known_label_map` 已提供建议，旧流程仍需确认。OpenClaw 默认不要使用这个两阶段旧接口，改用 [Agent 工作流](agent-workflows.md)。

## Agent 建库与分析（OpenClaw 默认）

首次建库使用 `agent enroll-start` 与 `agent enroll-confirm`；后续录音使用 `agent analyze-start` 与 `agent analyze-complete`。用户不输入技术任务 ID，OpenClaw 从首次命令结果中保存并在后续内部调用时传回。请求、确认绑定、幂等恢复和固定飞书消息格式见 [Agent 工作流](agent-workflows.md)。

## 浏览器建库审核（复杂任务）

多人员、超过三组候选、红色风险或需要逐片段处理的任务使用审核台。也可以由用户主动指定网页审核。使用同一清单创建会话：

```text
speaker_insights.py --customers-root /path/to/客户 enroll review-create \
  --manifest MEETING.yaml --base-url http://HOST:8765
```

It returns `session_id`, `queued`, and `review_url`. The Worker stores its temporary artifacts at:

网页入口不需要用户填写 `meeting.id` 或 `meeting.title`：它从录音文件名派生这两个值，并允许一个首次建库会话包含多组录音和转写。参会人字段填写真人信息，不要求与转写标签同名；标签归属由审核台中的片段分配决定。网页中的“我方”在清单中使用 `organization: yingdao`，其声纹存入全局员工库；“客户”则只存入当前客户。审核台不要求填写确认人，点击“确认建库”即为正式授权。CLI 清单接口仍保持上方的单场会议结构。

```text
<客户>/声纹数据/enrollments/<session-id>/
├── manifest.json
├── review_package.json
├── pending_vectors.npz
├── review_result.json
└── commit_journal.json
```

`pending_vectors.npz` is not a profile and is removed after cancellation, expiration, or successful commit. The browser decision contains a server revision and assignments from `segment_id` to a person ID, `unknown`, `background`, or `skip`. It may contain `new_people`, with name and role. The server is the only component that turns selected windows into `vNNNN`.

## 上下文证据

Create one item only when its timestamp and excerpt can be checked in the transcript index.

```json
{
  "schema_version": 1,
  "items": [
    {
      "target_label": "说话人 2",
      "supported_person": "客户负责人",
      "strength": "strong",
      "type": "direct_address_response",
      "source_label": "内部CSM",
      "timestamp": "12:20",
      "excerpt": "负责人，您怎么看"
    }
  ]
}
```

允许的强度：`strong`、`medium`、`weak`。语义类型：`self_identification`、`direct_address_response`、`explicit_address`、`role_semantics`、`third_party_reference`。转写标签与候选人姓名完全一致时，引擎还会生成确定性的 `exact_named_label` 证据。

证据时间戳属于 `source_label`；`target_label` 是该证据所支持的待识别标签。

`supported_person` 通常必须属于本次声纹候选集。只有原文明确出现姓名的自我介绍或直接称呼，才允许指向候选集外人员；职位语义不能引入新身份。

## 核心观点

Write viewpoints by original transcript label. Finalization groups labels only after identity resolution.

```json
{
  "schema_version": 1,
  "items": [
    {
      "transcript_label": "说话人 2",
      "timestamp": "18:29",
      "category": "需求",
      "point": "希望先明确奖励规则再推进内部推广。",
      "source_excerpt": "先把奖励规则定下来"
    }
  ]
}
```

允许类别：`主张`、`需求`、`担忧`、`决策`、`行动项`、`发言摘要`。原文充足时，每位已识别人员输出 2–5 条实质观点；发言有意义但不足以形成独立观点时，至少输出一条有原文依据的 `发言摘要`。未知说话人也遵循同一规则。

每个原始标签都必须覆盖。只有真正的背景声、偶发路人发言、设备播放或杂音可以排除在观点之外，而且排除理由仍须能回查原文：

```json
{
  "schema_version": 1,
  "items": [],
  "non_substantive_labels": [
    {
      "transcript_label": "说话人 4",
      "classification": "background_or_incidental",
      "reason": "只有路人招呼，没有会议观点。",
      "timestamp": "03:15",
      "source_excerpt": "你们先聊"
    }
  ]
}
```

`analyze finalize` 会拒绝缺失标签。不能把空模板原样提交。

## 只有开始时间的转写

飞书妙记通常只导出开始时间，不要求 `stop_time`。引擎根据文本估算保守时长，并受下一行开始时间和固定上限约束，再在该区间内运行自适应能量 VAD；不会把整段空白都归给上一位说话人。其他导出器提供的 `[start - stop] label` 格式仍兼容。

## 命令

```text
speaker_insights.py paths
speaker_insights.py doctor [--download]
speaker_insights.py capabilities

# OpenClaw / Agent 稳定接口
speaker_insights.py agent enroll-start --request REQUEST.json [--base-url URL]
speaker_insights.py agent enroll-confirm --request CONFIRMATION.json
speaker_insights.py agent analyze-start --request REQUEST.json
speaker_insights.py agent analyze-complete --task TASK_ID --semantic-response SEMANTIC.json
speaker_insights.py agent task-status --task TASK_ID
speaker_insights.py agent analysis-correct --task TASK_ID --corrections CORRECTIONS.json

# 兼容及管理员接口
speaker_insights.py customer upsert --manifest MEETING.yaml
speaker_insights.py enroll prepare --manifest MEETING.yaml
speaker_insights.py enroll commit --draft enrollment_draft.json --confirmation confirmation.yaml
speaker_insights.py analyze acoustic --manifest MEETING.yaml
speaker_insights.py analyze finalize --run-dir RUN_DIR --context context.json --viewpoints viewpoints.json
speaker_insights.py profile candidates --customer CUSTOMER_ID
speaker_insights.py profile promote --candidate CANDIDATE_JSON --person PERSON_ID --confirmed-by NAME
speaker_insights.py profile versions --person PERSON_ID
speaker_insights.py profile set-current --person PERSON_ID --version 1
speaker_insights.py profile disable --person PERSON_ID
speaker_insights.py profile enable --person PERSON_ID
speaker_insights.py profile fork --person PERSON_ID --base-version 1 [--window-ids retained.json] [--keep-current]
speaker_insights.py profile revision-review-create --person PERSON_ID --base-version 1 [--base-url URL]
speaker_insights.py enroll review-create --manifest MEETING.yaml [--base-url URL]
speaker_insights.py enroll review-status --session SESSION_ID
speaker_insights.py enroll review-cancel --session SESSION_ID
speaker_insights.py profile review-create --candidate CANDIDATE.json [--base-url URL]
speaker_insights.py review serve --host 127.0.0.1 --port 8765 --base-url http://127.0.0.1:8765
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --dry-run
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --apply
```

旧的 `profile rollback` 和 `profile quarantine` 仅保留为兼容入口；新流程使用“设为当前版本”和“停用”，不会删除历史版本或清空当前版本指针。

命令最终输出单个包含产物路径的 JSON 对象，Agent 不需要从终端自然语言中猜测结果。
