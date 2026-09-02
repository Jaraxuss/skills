from __future__ import annotations

from typing import Any

from .errors import StructuredError
from .util import normalize_text


ALLOWED_CONTEXT_TYPES = {
    "self_identification",
    "direct_address_response",
    "explicit_address",
    "role_semantics",
    "third_party_reference",
}
ALLOWED_STRENGTHS = {"strong", "medium", "weak"}
ALLOWED_VIEWPOINT_CATEGORIES = {"主张", "需求", "担忧", "决策", "行动项", "发言摘要"}
ALLOWED_NON_SUBSTANTIVE_CLASSES = {"background_or_incidental"}
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


def _outside_identity_is_grounded(name: str, excerpt: str, evidence_type: str) -> bool:
    normalized_name = normalize_text(name)
    normalized_excerpt = normalize_text(excerpt)
    if normalized_name and normalized_name in normalized_excerpt:
        return True
    base_name = normalized_name
    for suffix in ("老师", "先生", "女士", "经理", "总监", "负责人", "总"):
        if base_name.endswith(suffix):
            base_name = base_name[: -len(suffix)]
            break
    if len(base_name) >= 2 and base_name in normalized_excerpt:
        return True
    if evidence_type == "self_identification" and len(base_name) == 1:
        return f"姓{base_name}" in normalized_excerpt
    return False


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
            grounding = _find_grounding(transcript_index, source_label, timestamp, excerpt)
            if grounding is None:
                raise ValueError("excerpt is not grounded at the supplied label and timestamp")
            person = by_id.get(supported) or by_name.get(supported)
            if person is None:
                if evidence_type == "role_semantics":
                    raise ValueError("role semantics cannot introduce an outside-cohort identity")
                if not _outside_identity_is_grounded(supported, excerpt, evidence_type):
                    raise ValueError(
                        "outside-cohort identity is not explicitly grounded in the excerpt"
                    )
                person_id = None
                person_name = supported
                identity_key = f"name:{normalize_text(supported)}"
                in_voiceprint_cohort = False
            else:
                person_id = person["person_id"]
                person_name = person["name"]
                identity_key = f"person:{person_id}"
                in_voiceprint_cohort = True
            valid.append(
                {
                    "target_label": target_label,
                    "supported_person_id": person_id,
                    "supported_person": person_name,
                    "identity_key": identity_key,
                    "in_voiceprint_cohort": in_voiceprint_cohort,
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


def deterministic_named_label_context(
    transcript_index: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_name = {item["name"]: item for item in candidates}
    evidence: list[dict[str, Any]] = []
    for label, rows in transcript_index.get("labels", {}).items():
        person = by_name.get(label)
        if person is None or not rows:
            continue
        grounding = rows[0]
        evidence.append(
            {
                "target_label": label,
                "supported_person_id": person["person_id"],
                "supported_person": person["name"],
                "identity_key": f"person:{person['person_id']}",
                "in_voiceprint_cohort": True,
                "strength": "strong",
                "type": "exact_named_label",
                "source_label": label,
                "timestamp": grounding["timestamp"],
                "excerpt": grounding["text"],
                "source_utterance_index": grounding["index"],
                "generated_by": "deterministic_named_label",
            }
        )
    return evidence


def validate_viewpoints(
    payload: dict[str, Any], transcript_index: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    labels = set(transcript_index.get("labels", {}))
    valid: list[dict[str, Any]] = []
    non_substantive: list[dict[str, Any]] = []
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
    for raw in payload.get("non_substantive_labels", []):
        try:
            if not isinstance(raw, dict):
                raise ValueError("non-substantive item is not an object")
            label = str(raw["transcript_label"])
            classification = str(raw["classification"])
            reason = str(raw["reason"]).strip()
            timestamp = str(raw["timestamp"])
            excerpt = str(raw["source_excerpt"])
            if label not in labels:
                raise ValueError("unknown transcript label")
            if classification not in ALLOWED_NON_SUBSTANTIVE_CLASSES:
                raise ValueError("unsupported non-substantive classification")
            if len(reason) < 4:
                raise ValueError("non-substantive reason is too short")
            grounding = _find_grounding(transcript_index, label, timestamp, excerpt)
            if grounding is None:
                raise ValueError(
                    "non-substantive excerpt is not grounded at the supplied label and timestamp"
                )
            non_substantive.append(
                {
                    "transcript_label": label,
                    "classification": classification,
                    "reason": reason,
                    "timestamp": timestamp,
                    "source_excerpt": excerpt,
                    "source_utterance_index": grounding["index"],
                }
            )
        except Exception as exc:
            rejected.append({"item": raw, "reason": str(exc)})
    return valid, non_substantive, rejected


def ensure_viewpoint_coverage(
    transcript_index: dict[str, Any],
    viewpoints: list[dict[str, Any]],
    non_substantive: list[dict[str, Any]],
) -> None:
    covered = {item["transcript_label"] for item in viewpoints}
    covered.update(item["transcript_label"] for item in non_substantive)
    missing = [label for label in transcript_index.get("labels", {}) if label not in covered]
    if missing:
        raise StructuredError(
            "MISSING_VIEWPOINT_LABELS",
            "每个转写标签都必须包含可回查的核心观点、发言摘要或非实质发言说明。",
            details={"missing_labels": missing},
            retryable=True,
        )


def aggregate_context(
    label: str, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    relevant = [item for item in evidence if item["target_label"] == label]
    scores: dict[str, int] = {}
    strong_non_role: dict[str, bool] = {}
    identities: dict[str, dict[str, Any]] = {}
    for item in relevant:
        identity_key = item["identity_key"]
        scores[identity_key] = scores.get(identity_key, 0) + STRENGTH_WEIGHT[item["strength"]]
        identities[identity_key] = {
            "person_id": item.get("supported_person_id"),
            "person": item["supported_person"],
            "identity_key": identity_key,
            "in_voiceprint_cohort": item["in_voiceprint_cohort"],
        }
        if item["strength"] == "strong" and item["type"] != "role_semantics":
            strong_non_role[identity_key] = True
    if not scores:
        return {
            "person_id": None,
            "person": None,
            "identity_key": None,
            "in_voiceprint_cohort": False,
            "strength": "none",
            "score": 0,
            "margin": None,
            "evidence": relevant,
            "scores": {},
        }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    identity_key, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    margin = score - second
    if strong_non_role.get(identity_key) and score >= 3 and margin >= 2:
        strength = "strong"
    elif score >= 2 and margin >= 1:
        strength = "medium"
    else:
        strength = "weak"
    return {
        **identities[identity_key],
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
    context_identity = context.get("person")
    context_identity_key = context.get("identity_key")
    context_strength = context.get("strength", "none")
    strong_context = context_strength == "strong" and context_identity_key is not None
    conflict = bool(
        acoustic_status == "matched"
        and voice_person
        and strong_context
        and context_identity_key != f"person:{voice_person}"
    )
    result = {
        **acoustic,
        "context_person_id": context_person,
        "context_person": context_identity,
        "context_identity_key": context_identity_key,
        "context_in_voiceprint_cohort": context.get("in_voiceprint_cohort", False),
        "context_strength": context_strength,
        "context_evidence": context.get("evidence", []),
        "voice_context_conflict": conflict,
        "needs_review": False,
        "final_person_id": None,
        "final_identity_key": None,
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
                final_identity_key=f"person:{voice_person}",
                final_identity=person["name"],
                final_status="声纹已匹配，需复核",
                final_confidence="中" if acoustic_confidence == "高" else "低",
                decision_basis="voiceprint_over_context_conflict",
                needs_review=True,
            )
        else:
            result.update(
                final_person_id=voice_person,
                final_identity_key=f"person:{voice_person}",
                final_identity=person["name"],
                final_status="声纹已匹配",
                final_confidence=acoustic_confidence,
                decision_basis=(
                    "voiceprint_and_context"
                    if context_person == voice_person and context_strength != "none"
                    else "voiceprint"
                ),
            )
    elif strong_context:
        if context_person is not None:
            final_identity = people.get(context_person, {}).get("name", context_identity)
            final_status = "上下文辅助识别"
        else:
            final_identity = context_identity
            final_status = "上下文识别（声纹库外）"
        result.update(
            final_person_id=context_person,
            final_identity_key=context_identity_key,
            final_identity=final_identity,
            final_status=final_status,
            final_confidence="中",
            decision_basis=(
                "unaccepted_voiceprint_plus_strong_context"
                if top1 is not None
                else "strong_context_without_voiceprint"
            ),
        )
    elif acoustic_status == "near_threshold":
        result.update(
            final_status="匹配倾向但证据不足",
            final_confidence="低",
            decision_basis="near_voiceprint_unresolved",
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
