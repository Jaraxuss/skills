from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from .constants import PIPELINE_CONFIG
from .embedding import normalize
from .transcript import Candidate


def internal_consistency_filter(
    candidates: list[Candidate],
    embeddings: np.ndarray,
    limit: int,
) -> tuple[list[Candidate], np.ndarray, dict[str, Any]]:
    if len(candidates) != len(embeddings):
        raise ValueError("Candidate/embedding count mismatch")
    if len(candidates) < 4:
        return candidates, embeddings, {"threshold": None, "removed": 0}
    similarity = embeddings @ embeddings.T
    np.fill_diagonal(similarity, np.nan)
    median_similarity = np.nanmedian(similarity, axis=1)
    center = float(np.median(median_similarity))
    mad = float(np.median(np.abs(median_similarity - center)))
    threshold = center - max(0.06, 2.5 * 1.4826 * mad)
    keep = np.where(median_similarity >= threshold)[0].tolist()
    minimum_keep = min(len(candidates), 8)
    if len(keep) < minimum_keep:
        keep = np.argsort(median_similarity)[-minimum_keep:].tolist()
    keep.sort(
        key=lambda index: 0.75 * float(median_similarity[index])
        + 0.25 * candidates[index].quality,
        reverse=True,
    )
    keep = keep[:limit]
    keep.sort(key=lambda index: candidates[index].start)
    return (
        [candidates[index] for index in keep],
        embeddings[keep],
        {
            "median_internal_similarity": center,
            "mad": mad,
            "threshold": threshold,
            "removed": len(candidates) - len(keep),
        },
    )


def split_reference_holdout(
    candidates: list[Candidate], embeddings: np.ndarray, holdout_fraction: float
) -> tuple[list[Candidate], np.ndarray, list[Candidate], np.ndarray]:
    count = len(candidates)
    if count < int(PIPELINE_CONFIG["minimum_profile_windows"]):
        raise RuntimeError(f"At least 6 consistent windows are required, got {count}")
    holdout_count = max(2, int(round(count * holdout_fraction)))
    holdout_count = min(holdout_count, count - 4)
    holdout_indices = set(
        int(index) for index in np.linspace(1, count - 2, holdout_count, dtype=int)
    )
    reference_indices = [index for index in range(count) if index not in holdout_indices]
    held_indices = sorted(holdout_indices)
    return (
        [candidates[index] for index in reference_indices],
        embeddings[reference_indices],
        [candidates[index] for index in held_indices],
        embeddings[held_indices],
    )


def build_profile_arrays(
    candidates: list[Candidate], embeddings: np.ndarray
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    filtered_candidates, filtered_embeddings, consistency = internal_consistency_filter(
        candidates,
        embeddings,
        int(PIPELINE_CONFIG["max_profile_windows_per_person"]),
    )
    seconds = float(sum(item.duration for item in filtered_candidates))
    if len(filtered_candidates) < int(PIPELINE_CONFIG["minimum_profile_windows"]):
        raise RuntimeError(
            f"Only {len(filtered_candidates)} consistent windows remain; at least 6 are required"
        )
    if seconds < float(PIPELINE_CONFIG["minimum_profile_seconds"]):
        raise RuntimeError(
            f"Only {seconds:.1f} seconds remain; at least "
            f"{PIPELINE_CONFIG['minimum_profile_seconds']:.1f} are required"
        )
    ref_candidates, references, held_candidates, heldouts = split_reference_holdout(
        filtered_candidates,
        filtered_embeddings,
        float(PIPELINE_CONFIG["holdout_fraction"]),
    )
    center = normalize(np.mean(references, axis=0))
    arrays = {
        "references": references.astype(np.float32),
        "heldouts": heldouts.astype(np.float32),
        "center": center.astype(np.float32),
        "quality_weights": np.asarray(
            [max(0.05, item.quality) for item in ref_candidates], dtype=np.float32
        ),
    }
    metadata = {
        "candidate_count": len(candidates),
        "filtered_count": len(filtered_candidates),
        "reference_count": len(ref_candidates),
        "holdout_count": len(held_candidates),
        "reference_seconds": float(sum(item.duration for item in ref_candidates)),
        "holdout_seconds": float(sum(item.duration for item in held_candidates)),
        "consistency": consistency,
        "reference_windows": [asdict(item) for item in ref_candidates],
        "holdout_windows": [asdict(item) for item in held_candidates],
    }
    return arrays, metadata


def score_to_bank(vector: np.ndarray, bank: np.ndarray, top_k: int) -> float:
    scores = np.asarray(bank @ vector, dtype=np.float32)
    count = min(top_k, scores.size)
    if count == 0:
        return float("nan")
    return float(np.mean(np.partition(scores, -count)[-count:]))


def balanced_threshold(genuine: np.ndarray, impostor: np.ndarray) -> tuple[float, dict[str, float]]:
    all_scores = np.unique(np.concatenate([genuine, impostor]))
    if all_scores.size == 1:
        threshold = float(all_scores[0])
    else:
        choices = (all_scores[:-1] + all_scores[1:]) / 2.0
        best = (-1.0, float(choices[0]))
        for choice in choices:
            true_accept = float(np.mean(genuine >= choice))
            true_reject = float(np.mean(impostor < choice))
            balanced = (true_accept + true_reject) / 2.0
            if balanced > best[0] or (balanced == best[0] and choice > best[1]):
                best = (balanced, float(choice))
        threshold = best[1]
    impostor_q99 = float(np.quantile(impostor, 0.99))
    genuine_q10 = float(np.quantile(genuine, 0.10))
    if genuine_q10 > impostor_q99:
        threshold = (genuine_q10 + impostor_q99) / 2.0
    true_accept = float(np.mean(genuine >= threshold))
    true_reject = float(np.mean(impostor < threshold))
    return threshold, {
        "genuine_min": float(np.min(genuine)),
        "genuine_q10": genuine_q10,
        "genuine_median": float(np.median(genuine)),
        "impostor_max": float(np.max(impostor)),
        "impostor_q99": impostor_q99,
        "impostor_median": float(np.median(impostor)),
        "true_accept_rate": true_accept,
        "true_reject_rate": true_reject,
        "balanced_accuracy": (true_accept + true_reject) / 2.0,
    }


def calibrate_profiles(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    people = list(profiles)
    fallback = {
        "accept_threshold": float(PIPELINE_CONFIG["default_accept_threshold"]),
        "margin_threshold": float(PIPELINE_CONFIG["default_margin_threshold"]),
        "source": "conservative_default",
        "holdout_count": 0,
        "holdout_top1_accuracy": None,
        "rows": [],
    }
    if len(people) < 2:
        return fallback
    rows: list[dict[str, Any]] = []
    genuine: list[float] = []
    impostor: list[float] = []
    margins: list[float] = []
    correct = 0
    total = 0
    top_k = int(PIPELINE_CONFIG["top_reference_count"])
    for actual in people:
        heldouts = profiles[actual]["arrays"].get("heldouts")
        if heldouts is None or not len(heldouts):
            return fallback
        for index, vector in enumerate(heldouts):
            scores = {
                person_id: score_to_bank(
                    vector, profiles[person_id]["arrays"]["references"], top_k
                )
                for person_id in people
            }
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            correct_score = scores[actual]
            other_score = max(score for person_id, score in scores.items() if person_id != actual)
            genuine.append(correct_score)
            impostor.extend(
                score for person_id, score in scores.items() if person_id != actual
            )
            margins.append(correct_score - other_score)
            correct += int(ranked[0][0] == actual)
            total += 1
            rows.append(
                {
                    "actual_person_id": actual,
                    "holdout_index": index,
                    "top1_person_id": ranked[0][0],
                    "top1_score": ranked[0][1],
                    "correct_margin": correct_score - other_score,
                    "scores": scores,
                }
            )
    if not genuine or not impostor:
        return fallback
    threshold, distribution = balanced_threshold(
        np.asarray(genuine, dtype=np.float32), np.asarray(impostor, dtype=np.float32)
    )
    margin_q10 = float(np.quantile(np.asarray(margins, dtype=np.float32), 0.10))
    margin_threshold = max(
        float(PIPELINE_CONFIG["minimum_margin_floor"]), min(0.15, margin_q10 * 0.5)
    )
    return {
        "accept_threshold": threshold,
        "margin_threshold": margin_threshold,
        "source": "dynamic_candidate_cohort",
        "holdout_count": total,
        "holdout_top1_accuracy": correct / total if total else None,
        "margin_q10": margin_q10,
        "rows": rows,
        **distribution,
    }


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cutoff = float(np.sum(sorted_weights)) / 2.0
    index = int(np.searchsorted(np.cumsum(sorted_weights), cutoff, side="left"))
    return float(sorted_values[min(index, len(sorted_values) - 1)])


def match_label(
    candidates: list[Candidate],
    embeddings: np.ndarray,
    profiles: dict[str, dict[str, Any]],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    people = list(profiles)
    accept_threshold = float(calibration["accept_threshold"])
    margin_threshold = float(calibration["margin_threshold"])
    if not people:
        return {
            "acoustic_status": "unknown",
            "acoustic_confidence": "未知",
            "matched_person_id": None,
            "top1_person_id": None,
            "top1_score": None,
            "top2_person_id": None,
            "top2_score": None,
            "score_margin": None,
            "usable_windows": len(candidates),
            "usable_seconds": float(sum(item.duration for item in candidates)),
            "notes": ["当前客户范围内没有可用声纹档案"],
            "scores": {},
            "segment_votes": {},
        }
    if embeddings.size == 0:
        return {
            "acoustic_status": "insufficient_audio",
            "acoustic_confidence": "低",
            "matched_person_id": None,
            "top1_person_id": None,
            "top1_score": None,
            "top2_person_id": None,
            "top2_score": None,
            "score_margin": None,
            "usable_windows": 0,
            "usable_seconds": 0.0,
            "notes": ["没有通过质量筛选的语音窗口"],
            "scores": {},
            "segment_votes": {},
        }

    per_person: dict[str, list[float]] = {person_id: [] for person_id in people}
    votes: dict[str, int] = {person_id: 0 for person_id in people}
    top_k = int(PIPELINE_CONFIG["top_reference_count"])
    for vector in embeddings:
        scores = {
            person_id: score_to_bank(
                vector, profiles[person_id]["arrays"]["references"], top_k
            )
            for person_id in people
        }
        for person_id, score in scores.items():
            per_person[person_id].append(score)
        ranked_segment = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        segment_margin = (
            ranked_segment[0][1] - ranked_segment[1][1]
            if len(ranked_segment) > 1
            else float("inf")
        )
        if ranked_segment[0][1] >= accept_threshold and segment_margin >= margin_threshold:
            votes[ranked_segment[0][0]] += 1

    weights = np.asarray([max(0.05, item.quality) for item in candidates], dtype=np.float32)
    aggregate = {
        person_id: weighted_median(np.asarray(scores, dtype=np.float32), weights)
        for person_id, scores in per_person.items()
    }
    ranked = sorted(aggregate.items(), key=lambda item: item[1], reverse=True)
    top1_person_id, top1_score = ranked[0]
    if len(ranked) > 1:
        top2_person_id, top2_score = ranked[1]
        margin: float | None = top1_score - top2_score
    else:
        top2_person_id, top2_score, margin = None, None, None

    usable_seconds = float(sum(item.duration for item in candidates))
    accepted_votes = sorted(
        ((person_id, count) for person_id, count in votes.items() if count),
        key=lambda item: item[1],
        reverse=True,
    )
    mixed = False
    if len(accepted_votes) >= 2:
        accepted_total = sum(count for _, count in accepted_votes)
        minority = accepted_votes[1][1]
        mixed = (
            minority >= int(PIPELINE_CONFIG["mixed_minority_windows"])
            and minority / accepted_total
            >= float(PIPELINE_CONFIG["mixed_minority_fraction"])
        )
    enough_audio = (
        usable_seconds >= float(PIPELINE_CONFIG["minimum_accept_seconds"])
        and len(candidates) >= int(PIPELINE_CONFIG["minimum_accept_windows"])
    )
    passes_score = top1_score >= accept_threshold
    passes_margin = margin is None or margin >= margin_threshold
    notes: list[str] = []
    matched_person_id: str | None = None
    if mixed:
        status = "mixed"
        confidence = "低"
        notes.append("同一转写标签内出现多个通过阈值的身份投票")
    elif passes_score and passes_margin and enough_audio:
        status = "matched"
        matched_person_id = top1_person_id
        high = (
            len(ranked) > 1
            and top1_score
            >= accept_threshold + float(PIPELINE_CONFIG["high_confidence_score_surplus"])
            and margin is not None
            and margin
            >= margin_threshold + float(PIPELINE_CONFIG["high_confidence_margin_surplus"])
            and usable_seconds >= float(PIPELINE_CONFIG["high_confidence_seconds"])
        )
        confidence = "高" if high else "中"
    elif top1_score >= accept_threshold - float(PIPELINE_CONFIG["uncertain_score_tolerance"]):
        status = "near_threshold"
        confidence = "低"
        if not enough_audio:
            notes.append("有效语音量不足")
        if not passes_margin:
            notes.append("第一名与第二名分差不足")
        if not passes_score:
            notes.append("第一名分数略低于接受阈值")
    else:
        status = "unknown"
        confidence = "低"
        notes.append("第一名分数低于接受阈值")
    return {
        "acoustic_status": status,
        "acoustic_confidence": confidence,
        "matched_person_id": matched_person_id,
        "top1_person_id": top1_person_id,
        "top1_score": top1_score,
        "top2_person_id": top2_person_id,
        "top2_score": top2_score,
        "score_margin": margin,
        "usable_windows": len(candidates),
        "usable_seconds": usable_seconds,
        "notes": notes,
        "scores": aggregate,
        "segment_votes": votes,
    }
