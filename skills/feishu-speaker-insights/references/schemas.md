# Schemas and command flow

Read this reference when creating a customer, enrolling profiles, analyzing a meeting, or generating semantic JSON.

## Meeting manifest

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

`organization` must be `customer`, `yingdao`, or `external`. External attendees are metadata only and are not enrolled unless explicitly changed to one of the first two scopes.

## Enrollment confirmation

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

Every mapped name must resolve exactly to an attendee. Confirmation is required even when `known_label_map` supplied the proposal.

## Browser enrollment review (default)

The review console replaces the chat-based confirmation flow for normal use. Create a session from the same meeting manifest:

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

## Context evidence

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

Allowed strengths: `strong`, `medium`, `weak`. Semantic input types: `self_identification`, `direct_address_response`, `explicit_address`, `role_semantics`, `third_party_reference`. The engine may additionally emit deterministic `exact_named_label` evidence when a transcript label exactly matches a candidate person.

The evidence timestamp belongs to `source_label`; `target_label` is the speaker label whose identity it supports.

`supported_person` normally names someone in the voiceprint candidate cohort. It may name a person outside that cohort only when the supplied excerpt explicitly grounds the name, such as a self-introduction or direct address. Role semantics cannot introduce a new identity.

## Viewpoints

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

Allowed categories: `主张`, `需求`, `担忧`, `决策`, `行动项`, `发言摘要`. Produce two to five substantive points per resolved person when the transcript supports them. When speech is meaningful but too sparse for an independent viewpoint, produce one grounded `发言摘要`; unknown speakers follow the same rule.

Every original label must be covered. Only genuine background, incidental speech, device playback, or noise may be excluded from viewpoints, and the exclusion must still be grounded:

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

`analyze finalize` rejects missing label coverage. Do not pass the empty template through unchanged.

## Start-only transcript timing

Feishu Minutes exports commonly provide only a start timestamp. No `stop_time` is required. For each row, the engine estimates a conservative duration from its text, caps it at the next row start and a fixed maximum, then uses adaptive energy VAD inside that span. It does not assign the entire gap to the preceding label. Explicit `[start - stop] label` rows remain supported when another exporter supplies them.

## Commands

```text
speaker_insights.py paths
speaker_insights.py doctor [--download]
speaker_insights.py customer upsert --manifest MEETING.yaml
speaker_insights.py enroll prepare --manifest MEETING.yaml
speaker_insights.py enroll commit --draft enrollment_draft.json --confirmation confirmation.yaml
speaker_insights.py analyze acoustic --manifest MEETING.yaml
speaker_insights.py analyze finalize --run-dir RUN_DIR --context context.json --viewpoints viewpoints.json
speaker_insights.py profile candidates --customer CUSTOMER_ID
speaker_insights.py profile promote --candidate CANDIDATE_JSON --person PERSON_ID --confirmed-by NAME
speaker_insights.py profile rollback --person PERSON_ID [--customer CUSTOMER_ID] [--to-version 1]
speaker_insights.py profile quarantine --person PERSON_ID --confirmed-by NAME
speaker_insights.py enroll review-create --manifest MEETING.yaml [--base-url URL]
speaker_insights.py enroll review-status --session SESSION_ID
speaker_insights.py enroll review-cancel --session SESSION_ID
speaker_insights.py profile review-create --candidate CANDIDATE.json [--base-url URL]
speaker_insights.py review serve --host 127.0.0.1 --port 8765 --base-url http://127.0.0.1:8765
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --dry-run
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --apply
```

Commands print a final JSON object containing output paths so an agent does not have to infer them from terminal prose.
