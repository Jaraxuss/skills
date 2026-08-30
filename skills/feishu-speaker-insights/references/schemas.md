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

Allowed strengths: `strong`, `medium`, `weak`. Allowed types: `self_identification`, `direct_address_response`, `explicit_address`, `role_semantics`, `third_party_reference`.

The evidence timestamp belongs to `source_label`; `target_label` is the speaker label whose identity it supports.

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

Allowed categories: `主张`, `需求`, `担忧`, `决策`, `行动项`. Produce two to five substantive points per resolved person when the transcript supports them; fewer is valid when content is sparse.

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
```

Commands print a final JSON object containing output paths so an agent does not have to infer them from terminal prose.
