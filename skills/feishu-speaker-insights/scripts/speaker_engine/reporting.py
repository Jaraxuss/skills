from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import atomic_write_json, write_csv


def score(value: Any) -> str:
    return "—" if value is None else f"{float(value):.4f}"


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def person_name(person_id: str | None, people: dict[str, dict[str, Any]]) -> str:
    if person_id is None:
        return "—"
    return people.get(person_id, {}).get("name", person_id)


def group_viewpoints(
    resolved: list[dict[str, Any]],
    viewpoints: list[dict[str, Any]],
    non_substantive: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_label = {row["transcript_label"]: row for row in resolved}
    groups: dict[str, dict[str, Any]] = {}
    for item in viewpoints:
        result = rows_by_label.get(item["transcript_label"])
        if result is None:
            continue
        if result.get("final_identity_key"):
            key = result["final_identity_key"]
            title = result["final_identity"]
        else:
            key = f"label:{item['transcript_label']}"
            title = f"{result['final_status']} · {item['transcript_label']}"
        group = groups.setdefault(
            key,
            {
                "group_key": key,
                "identity": title,
                "person_id": result.get("final_person_id"),
                "labels": [],
                "items": [],
                "non_substantive": [],
            },
        )
        if item["transcript_label"] not in group["labels"]:
            group["labels"].append(item["transcript_label"])
        if len(group["items"]) < 5:
            group["items"].append(item)
    for row in resolved:
        if row.get("final_identity_key"):
            key = row["final_identity_key"]
            title = row["final_identity"]
        else:
            key = f"label:{row['transcript_label']}"
            title = f"{row['final_status']} · {row['transcript_label']}"
        group = groups.setdefault(
            key,
            {
                "group_key": key,
                "identity": title,
                "person_id": row.get("final_person_id"),
                "labels": [],
                "items": [],
                "non_substantive": [],
            },
        )
        if row["transcript_label"] not in group["labels"]:
            group["labels"].append(row["transcript_label"])
    for item in non_substantive:
        result = rows_by_label.get(item["transcript_label"])
        if result is None:
            continue
        if result.get("final_identity_key"):
            key = result["final_identity_key"]
        else:
            key = f"label:{item['transcript_label']}"
        groups[key]["non_substantive"].append(item)
    return list(groups.values())


def build_feishu_summary(
    bundle: dict[str, Any],
    resolved: list[dict[str, Any]],
    grouped: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a stable compact payload; OpenClaw should not invent report layout."""
    people = {item["person_id"]: item for item in bundle["candidate_people"]}
    rows_by_label = {row["transcript_label"]: row for row in resolved}
    speakers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    message_lines = [f"**{bundle['meeting']['title']}｜说话人识别与核心观点**", ""]
    for group in grouped:
        rows = [rows_by_label[label] for label in group["labels"] if label in rows_by_label]
        statuses = list(dict.fromkeys(str(row["final_status"]) for row in rows))
        confidences = list(dict.fromkeys(str(row["final_confidence"]) for row in rows))
        matches = []
        for row in rows:
            matches.append(
                {
                    "transcript_label": row["transcript_label"],
                    "status": row["final_status"],
                    "confidence": row["final_confidence"],
                    "top1": {
                        "person_id": row.get("top1_person_id"),
                        "name": person_name(row.get("top1_person_id"), people),
                        "score": row.get("top1_score"),
                    },
                    "top2": {
                        "person_id": row.get("top2_person_id"),
                        "name": person_name(row.get("top2_person_id"), people),
                        "score": row.get("top2_score"),
                    },
                    "score_margin": row.get("score_margin"),
                    "usable_windows": row.get("usable_windows"),
                    "usable_seconds": row.get("usable_seconds"),
                    "needs_review": bool(row.get("needs_review")),
                    "voice_context_conflict": bool(row.get("voice_context_conflict")),
                }
            )
            if row.get("needs_review") or row.get("voice_context_conflict") or row.get("final_status") in {
                "未知",
                "混合/不确定",
                "匹配倾向但证据不足",
                "有效语音不足",
            }:
                warnings.append(
                    {
                        "transcript_label": row["transcript_label"],
                        "status": row["final_status"],
                        "reason": "；".join(row.get("notes", [])) or row.get("decision_basis"),
                    }
                )
        viewpoints = [
            {
                "timestamp": item["timestamp"],
                "category": item["category"],
                "point": item["point"],
            }
            for item in group["items"]
        ]
        non_substantive = [
            {
                "timestamp": item["timestamp"],
                "reason": item["reason"],
            }
            for item in group["non_substantive"]
        ]
        speaker = {
            "identity": group["identity"],
            "person_id": group.get("person_id"),
            "transcript_labels": group["labels"],
            "statuses": statuses,
            "confidences": confidences,
            "matches": matches,
            "viewpoints": viewpoints,
            "non_substantive": non_substantive,
        }
        speakers.append(speaker)
        status_text = "、".join(statuses) or "未知"
        confidence_text = "、".join(confidences) or "低"
        message_lines.append(f"**{group['identity']}｜{status_text}·{confidence_text}**")
        for match in matches:
            first = match["top1"]
            second = match["top2"]
            ranking = f"{first['name']} {score(first['score'])}"
            if second["person_id"] is not None:
                ranking += f"；{second['name']} {score(second['score'])}"
            message_lines.append(f"声纹排序（{match['transcript_label']}）：{ranking}")
        if viewpoints:
            message_lines.append("核心观点：")
            for index, item in enumerate(viewpoints, start=1):
                message_lines.append(
                    f"{index}. `{item['timestamp']}` {item['category']}：{item['point']}"
                )
        elif non_substantive:
            for item in non_substantive:
                message_lines.append(
                    f"- `{item['timestamp']}` 非实质发言：{item['reason']}"
                )
        message_lines.append("")
    if warnings:
        message_lines.append(f"> 有 {len(warnings)} 个标签需要关注；识别结果不会自动修改正式声纹。")
    return {
        "schema_version": 1,
        "meeting": bundle["meeting"],
        "customer": bundle["customer"],
        "speakers": speakers,
        "warnings": warnings,
        "message_markdown": "\n".join(message_lines).strip(),
    }


def write_outputs(
    run_dir: Path,
    bundle: dict[str, Any],
    resolved: list[dict[str, Any]],
    validated_context: list[dict[str, Any]],
    rejected_context: list[dict[str, Any]],
    validated_viewpoints: list[dict[str, Any]],
    non_substantive_labels: list[dict[str, Any]],
    rejected_viewpoints: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    people = {item["person_id"]: item for item in bundle["candidate_people"]}
    grouped = group_viewpoints(resolved, validated_viewpoints, non_substantive_labels)
    payload = {
        "schema_version": 1,
        "run_id": bundle["run_id"],
        "customer": bundle["customer"],
        "meeting": bundle["meeting"],
        "model": bundle["model"],
        "calibration": bundle["calibration"],
        "candidate_people": bundle["candidate_people"],
        "results": resolved,
        "context": {
            "validated": validated_context,
            "rejected": rejected_context,
        },
        "viewpoints": {
            "by_identity": grouped,
            "validated": validated_viewpoints,
            "non_substantive_labels": non_substantive_labels,
            "rejected": rejected_viewpoints,
        },
        "profile_candidates": candidates,
        "disclaimer": "相似度是本次候选集中的声纹证据，不是身份认证概率。",
    }
    json_path = run_dir / "final_results.json"
    csv_path = run_dir / "speaker_results.csv"
    report_path = run_dir / "report.md"
    feishu_path = run_dir / "feishu_summary.json"
    atomic_write_json(json_path, payload)

    flat_rows: list[dict[str, Any]] = []
    for row in resolved:
        flat_rows.append(
            {
                "录音": bundle["meeting"]["title"],
                "原说话人标签": row["transcript_label"],
                "最终身份": row["final_identity"],
                "职位": people.get(row.get("final_person_id"), {}).get("role", ""),
                "最终状态": row["final_status"],
                "最终置信等级": row["final_confidence"],
                "声纹置信等级": row["acoustic_confidence"],
                "第一名": person_name(row.get("top1_person_id"), people),
                "第一名相似度": row.get("top1_score"),
                "接受阈值": bundle["calibration"]["accept_threshold"],
                "第二名": person_name(row.get("top2_person_id"), people),
                "第二名相似度": row.get("top2_score"),
                "分差": row.get("score_margin"),
                "分差阈值": bundle["calibration"]["margin_threshold"],
                "有效片段数": row["usable_windows"],
                "有效语音秒数": row["usable_seconds"],
                "上下文支持": row.get("context_person") or "",
                "上下文强度": row.get("context_strength"),
                "声纹上下文冲突": row.get("voice_context_conflict"),
                "需复核": row.get("needs_review"),
                "判定依据": row.get("decision_basis"),
                "说明": "；".join(row.get("notes", [])),
            }
        )
    write_csv(csv_path, flat_rows)

    calibration = bundle["calibration"]
    lines = [
        "# 声纹匹配与核心观点报告",
        "",
        "> 相似度是本次候选集中的声纹证据，不是身份认证概率；上下文不能覆盖声纹分数。",
        "",
        "## 会议与校准",
        "",
        f"- 客户：{bundle['customer']['name']}（`{bundle['customer']['id']}`）",
        f"- 录音：{bundle['meeting']['title']}（`{bundle['meeting']['id']}`）",
        f"- 模型：`{bundle['model']['id']}@{bundle['model']['revision']}`，CPU，192 维。",
        f"- 内部自动判定阈值（无需用户配置）：相似度 `{calibration['accept_threshold']:.4f}`；分差 `{calibration['margin_threshold']:.4f}`；来源：`{calibration['source']}`。",
        "",
        "## 说话人匹配",
        "",
        "| 原标签 | 最终状态 | 最终身份 | 置信 | 第一名 / 相似度 | 第二名 / 相似度 | 分差 | 有效语音 | 上下文 | 复核 |",
        "|---|---|---|---|---|---|---:|---:|---|---|",
    ]
    for row in resolved:
        context_text = (
            f"{row['context_person']}（{row['context_strength']}）"
            if row.get("context_person")
            else "—"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    escape(row["transcript_label"]),
                    escape(row["final_status"]),
                    escape(row["final_identity"]),
                    escape(row["final_confidence"]),
                    f"{escape(person_name(row.get('top1_person_id'), people))} / {score(row.get('top1_score'))}",
                    f"{escape(person_name(row.get('top2_person_id'), people))} / {score(row.get('top2_score'))}",
                    score(row.get("score_margin")),
                    f"{row['usable_windows']} 段 / {row['usable_seconds']:.1f} 秒",
                    escape(context_text),
                    "是" if row.get("needs_review") else "否",
                ]
            )
            + " |"
        )

    lines.extend(["", "## 可审计上下文证据", ""])
    if validated_context:
        for item in validated_context:
            lines.append(
                f"- `{item['timestamp']}` {item['target_label']} → {item['supported_person']} "
                f"（{item['strength']} / `{item['type']}`）：{item['excerpt']}"
            )
    else:
        lines.append("- 未提供或未验证通过上下文身份线索。")
    if rejected_context:
        lines.append(f"- 有 {len(rejected_context)} 条上下文线索因无法回查原文而被排除。")

    lines.extend(["", "## 每个人在本录音中的核心观点", ""])
    for group in grouped:
        labels = "、".join(group["labels"])
        lines.extend([f"### {group['identity']}（{labels}）", ""])
        if group["items"]:
            for item in group["items"]:
                lines.append(
                    f"- `{item['timestamp']}` **{item['category']}**：{item['point']}"
                )
        elif group["non_substantive"]:
            for item in group["non_substantive"]:
                lines.append(
                    f"- `{item['timestamp']}` **非实质发言**：{item['reason']}"
                )
        lines.append("")

    if candidates:
        lines.extend(["## 待确认声纹候选", ""])
        for item in candidates:
            lines.append(
                f"- {item['predicted_identity']}：`{item['candidate_id']}`，"
                f"{item['usable_seconds']:.1f} 秒；确认前不会写入正式声纹。"
            )
        lines.append("")

    lines.extend(
        [
            "## 限制",
            "",
            "- 第一名和第二名始终作为候选集声纹排序展示；内部阈值只控制是否声明为已匹配及是否允许进入声纹候选库。",
            "- 转写标签可能合并多人；混合标签不会归入个人观点。",
            "- 新会议只生成待确认向量，确认后才会创建新的声纹版本。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    feishu_payload = build_feishu_summary(bundle, resolved, grouped)
    feishu_payload["detailed_report"] = str(report_path)
    feishu_payload["final_results"] = str(json_path)
    atomic_write_json(feishu_path, feishu_payload)
    return {
        "report": str(report_path),
        "json": str(json_path),
        "csv": str(csv_path),
        "feishu_summary": str(feishu_path),
    }
