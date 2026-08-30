from __future__ import annotations

from typing import Any

from .util import normalize_text


ALLOWED_CONTEXT_TYPES = {
    "self_identification",
    "direct_address_response",
    "explicit_address",
    "role_semantics",
    "third_party_reference",
}
ALLOWED_STRENGTHS = {"strong", "medium", "weak"}
ALLOWED_VIEWPOINT_CATEGORIES = {"主张", "需求", "担忧", "决策", "行动项"}
STRENGTH_WEIGHT = {"strong": 3, "medium": 2, "weak": 1}


def _transcript_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    rows = index.get("utterances", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid transcript index")
    return rows


def _find_grounding(
    index: dict[str, Any], label: str, timestamp: str, excerpt: str
) -> dict[str, Any] | None:
    expected = normalize_text(excerpt)
    if not expected:
        return None
    for row in _transcript_rows(index):
        if row.get("label") != label or row.get("timestamp") != timestamp:
            continue
        if expected in normalize_text(str(row.get("text", ""))):
            return row
    return None


def validate_context(
    payload: dict[str, Any],
    transcript_index: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels = set(transcript_index.get("labels", {}))
    by_name = {item["name"]: item for item in candidates}
    by_id = {item["person_id"]: item for item in candidates}
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in payload.get("items", []):
        try:
            if not isinstance(raw, dict):
                raise ValueError("item is not an object")
            target_label = str(raw["target_label"])
            source_label = str(raw["source_label"])
            timestamp = str(raw["timestamp"])
            excerpt = str(raw["excerpt"])
            evidence_type = str(raw["type"])
            strength = str(raw["strength"])
            if target_label not in labels or source_label not in labels:
                raise ValueError("unknown transcript label")
            if evidence_type not in ALLOWED_CONTEXT_TYPES:
                raise ValueError("unsupported evidence type")
            if strength not in ALLOWED_STRENGTHS:
                raise ValueError("unsupported strength")
            if evidence_type == "role_semantics":
                strength = "weak"
            supported = str(raw.get("supported_person_id") or raw.get("supported_person") or "")
            person = by_id.get(supported) or by_name.get(supported)
            if person is None:
                raise ValueError("supported person is outside the candidate cohort")
            grounding = _find_grounding(transcript_index, source_label, timestamp, excerpt)
            if grounding is None:
                raise ValueError("excerpt is not grounded at the supplied label and timestamp")
            valid.append(
                {
                    "target_label": target_label,
                    "supported_person_id": person["person_id"],
                    "supported_person": person["name"],
                    "strength": strength,
                    "type": evidence_type,
                    "source_label": source_label,
                    "timestamp": timestamp,
                    "excerpt": excerpt,
                    "source_utterance_index": grounding["index"],
                }
            )
        except Exception as exc:
            rejected.append({"item": raw, "reason": str(exc)})
    return valid, rejected


def validate_viewpoints(
    payload: dict[str, Any], transcript_index: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels = set(transcript_index.get("labels", {}))
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in payload.get("items", []):
        try:
            if not isinstance(raw, dict):
                raise ValueError("item is not an object")
            label = str(raw["transcript_label"])
            timestamp = str(raw["timestamp"])
            category = str(raw["category"])
            point = str(raw["point"]).strip()
            excerpt = str(raw["source_excerpt"])
            if label not in labels:
                raise ValueError("unknown transcript label")
            if category not in ALLOWED_VIEWPOINT_CATEGORIES:
                raise ValueError("unsupported viewpoint category")
            if len(point) < 4:
                raise ValueError("viewpoint is too short")
            grounding = _find_grounding(transcript_index, label, timestamp, excerpt)
            if grounding is None:
                raise ValueError("source excerpt is not grounded at the supplied label and timestamp")
            key = (label, timestamp, point)
            if key in seen:
                continue
            seen.add(key)
            valid.append(
                {
                    "transcript_label": label,
                    "timestamp": timestamp,
                    "category": category,
                    "point": point,
                    "source_excerpt": excerpt,
                    "source_utterance_index": grounding["index"],
                }
            )
        except Exception as exc:
            rejected.append({"item": raw, "reason": str(exc)})
    return valid, rejected


def aggregate_context(
    label: str, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    relevant = [item for item in evidence if item["target_label"] == label]
    scores: dict[str, int] = {}
    strong_non_role: dict[str, bool] = {}
    for item in relevant:
        person_id = item["supported_person_id"]
        scores[person_id] = scores.get(person_id, 0) + STRENGTH_WEIGHT[item["strength"]]
        if item["strength"] == "strong" and item["type"] != "role_semantics":
            strong_non_role[person_id] = True
    if not scores:
        return {
            "person_id": None,
            "strength": "none",
            "score": 0,
            "margin": None,
            "evidence": relevant,
            "scores": {},
        }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    person_id, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    margin = score - second
    if strong_non_role.get(person_id) and score >= 3 and margin >= 2:
        strength = "strong"
    elif score >= 2 and margin >= 1:
        strength = "medium"
    else:
        strength = "weak"
    return {
        "person_id": person_id,
        "strength": strength,
        "score": score,
        "margin": margin,
        "evidence": relevant,
        "scores": scores,
    }


def resolve_one(
    acoustic: dict[str, Any], context: dict[str, Any], people: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    acoustic_status = acoustic["acoustic_status"]
    acoustic_confidence = acoustic["acoustic_confidence"]
    voice_person = acoustic.get("matched_person_id")
    top1 = acoustic.get("top1_person_id")
    context_person = context.get("person_id")
    context_strength = context.get("strength", "none")
    strong_context = context_strength == "strong" and context_person is not None
    conflict = bool(voice_person and strong_context and context_person != voice_person)
    result = {
        **acoustic,
        "context_person_id": context_person,
        "context_person": people.get(context_person, {}).get("name") if context_person else None,
        "context_strength": context_strength,
        "context_evidence": context.get("evidence", []),
        "voice_context_conflict": conflict,
        "needs_review": False,
        "final_person_id": None,
        "final_identity": "未知",
        "final_status": "未知",
        "final_confidence": "低",
        "decision_basis": "unknown",
    }
    if acoustic_status == "mixed":
        result.update(
            final_status="混合/不确定",
            final_confidence="低",
            decision_basis="mixed_voiceprint",
        )
    elif acoustic_status == "matched" and voice_person:
        person = people[voice_person]
        if conflict:
            result.update(
                final_person_id=voice_person,
                final_identity=person["name"],
                final_status="声纹已匹配，需复核",
                final_confidence="中" if acoustic_confidence == "高" else "低",
                decision_basis="voiceprint_over_context_conflict",
                needs_review=True,
            )
        else:
            result.update(
                final_person_id=voice_person,
                final_identity=person["name"],
                final_status="声纹已匹配",
                final_confidence=acoustic_confidence,
                decision_basis=(
                    "voiceprint_and_context"
                    if context_person == voice_person and context_strength != "none"
                    else "voiceprint"
                ),
            )
    elif acoustic_status == "near_threshold":
        if strong_context and context_person == top1:
            person = people[context_person]
            result.update(
                final_person_id=context_person,
                final_identity=person["name"],
                final_status="上下文辅助推断",
                final_confidence="中",
                decision_basis="near_voiceprint_plus_strong_context",
            )
        else:
            result.update(
                final_status="未知，需复核" if strong_context else "匹配倾向但证据不足",
                final_confidence="低",
                decision_basis="near_voiceprint_unresolved",
                needs_review=bool(strong_context),
            )
    elif acoustic_status == "insufficient_audio":
        result.update(
            final_status="有效语音不足",
            final_confidence="低",
            decision_basis="insufficient_audio",
        )
    return result


def resolve_results(
    acoustic_results: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    candidate_people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    people = {item["person_id"]: item for item in candidate_people}
    resolved: list[dict[str, Any]] = []
    for row in acoustic_results:
        context = aggregate_context(row["transcript_label"], evidence)
        resolved.append(resolve_one(row, context, people))
    return resolved
