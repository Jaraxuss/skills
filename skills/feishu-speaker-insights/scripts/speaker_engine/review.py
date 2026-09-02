from __future__ import annotations

import contextlib
import json
import os
import tempfile
import hashlib
import math
import uuid
from collections.abc import Callable
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np

from .constants import PIPELINE_CONFIG
from .embedding import EmbeddingEngine
from .matching import build_profile_arrays, internal_consistency_filter, match_label
from .storage import DataStore
from .transcript import (
    Candidate,
    build_candidates,
    convert_to_wav,
    parse_transcript,
    select_temporally_diverse,
    transcript_index,
)
from .util import (
    atomic_save_npz,
    atomic_write_json,
    file_lock,
    load_structured,
    now_iso,
    safe_component,
    sha256_file,
    stable_id,
    utc_compact,
)
from .workflow import _calibration_for_profiles, _model_manifest, audio_duration, validate_manifest


SPECIAL_ASSIGNMENTS = {"unknown", "background", "skip", "noise"}


def normalize_review_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize either the legacy one-meeting or browser batch manifest.

    Browser-created enrollment sessions deliberately have no user-entered
    meeting title or id.  The filename is the readable title and the server
    derives a stable, collision-resistant id for each source.
    """
    raw_meetings = raw.get("meetings")
    if raw_meetings is None:
        return validate_manifest(raw)
    if not isinstance(raw_meetings, list) or not raw_meetings:
        raise ValueError("请至少选择一组录音和转写")
    normalized_meetings: list[dict[str, Any]] = []
    for index, raw_meeting in enumerate(raw_meetings, start=1):
        if not isinstance(raw_meeting, dict):
            raise ValueError("每组录音和转写必须是对象")
        audio_value = str(raw_meeting.get("audio") or "").strip()
        transcript_value = str(raw_meeting.get("transcript") or "").strip()
        title = Path(audio_value).stem.strip()
        candidate = json.loads(json.dumps(raw, ensure_ascii=False))
        candidate.pop("meetings", None)
        candidate["meeting"] = {
            "id": safe_component(f"{index}-{audio_value}", "meeting"),
            "title": title or f"录音 {index}",
            "audio": audio_value,
            "transcript": transcript_value,
        }
        checked = validate_manifest(candidate)
        for field in ("audio_sha256", "transcript_sha256"):
            if raw_meeting.get(field):
                checked["meeting"][field] = str(raw_meeting[field])
        normalized_meetings.append(checked["meeting"])
    result = json.loads(json.dumps(raw, ensure_ascii=False))
    result["meeting"] = normalized_meetings[0]
    result["meetings"] = normalized_meetings
    result.setdefault("known_label_map", {})
    result.setdefault("excluded_labels", [])
    # Validate customer and attendees exactly as the CLI does, using the first
    # normalized recording as the required legacy meeting field.
    return validate_manifest(result)


def _review_meetings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("meetings") or [manifest["meeting"]])


def _review_initial_sample_count(candidates: list[Candidate]) -> int:
    """Bound expensive review embeddings by usable speech, not meeting length."""
    if not candidates:
        return 0
    desired = math.ceil(
        sum(item.duration for item in candidates)
        / float(PIPELINE_CONFIG["review_initial_seconds_per_window"])
    )
    desired = max(int(PIPELINE_CONFIG["review_initial_min_windows_per_label"]), desired)
    desired = min(int(PIPELINE_CONFIG["review_initial_max_windows_per_label"]), desired)
    return min(len(candidates), desired)


def _review_cancel_probe(store: DataStore, session_id: str, interval: int = 4) -> Callable[[], bool]:
    """Return a cheap cooperative cancellation callback for embedding loops."""
    count = 0

    def should_cancel() -> bool:
        nonlocal count
        count += 1
        if count % interval:
            return False
        return store.get_review_session(session_id)["status"] in {"cancelled", "expired"}

    return should_cancel


def _ensure_review_active(store: DataStore, session_id: str) -> None:
    status = store.get_review_session(session_id)["status"]
    if status in {"cancelled", "expired"}:
        raise InterruptedError(f"review_{status}")


def _report_review_progress(
    store: DataStore,
    job_id: str | None,
    phase: str,
    message: str,
    **details: Any,
) -> None:
    """Expose progress to the review UI without changing review state."""
    if not job_id:
        return
    payload = {"phase": phase, "message": message, **details}
    store.update_review_job_progress(job_id, payload)


def _recording_digest(meetings: list[dict[str, Any]], key: str) -> str:
    value = "\0".join(str(item.get(key) or "") for item in meetings)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _snapshot_sources(manifest: dict[str, Any]) -> dict[str, Any]:
    """Attach immutable source hashes before a review job enters the queue."""
    meetings = _review_meetings(manifest)
    for meeting in meetings:
        meeting["audio_sha256"] = sha256_file(Path(meeting["audio"]))
        meeting["transcript_sha256"] = sha256_file(Path(meeting["transcript"]))
    manifest["meeting"] = meetings[0]
    if "meetings" in manifest:
        manifest["meetings"] = meetings
    return manifest


def _session_id(meeting_id: str) -> str:
    # Timestamps aid inspection but are second-granular, so a restart issued
    # immediately after cancellation needs an independent collision guard.
    return f"review-{safe_component(meeting_id, 'meeting')}-{utc_compact()}-{uuid.uuid4().hex[:8]}"


def create_enrollment_review(
    manifest_path: Path,
    store: DataStore,
    *,
    base_url: str | None = None,
    expires_days: int = 7,
) -> dict[str, Any]:
    """Queue a review package without making any profile writable."""
    manifest = _snapshot_sources(normalize_review_manifest(load_structured(manifest_path.resolve())))
    store.upsert_manifest(manifest)
    customer_id = str(manifest["customer"]["id"])
    meetings = _review_meetings(manifest)
    session_id = _session_id(str(meetings[0]["id"]))
    session_dir = store.session_dir(customer_id, session_id)
    local_manifest = session_dir / "manifest.json"
    atomic_write_json(local_manifest, manifest)
    session = store.create_review_session(
        customer_id,
        session_id,
        "enrollment",
        local_manifest,
        _recording_digest(meetings, "audio_sha256"),
        _recording_digest(meetings, "transcript_sha256"),
        expires_days,
    )
    review_url = f"{base_url.rstrip('/')}/sessions/{session_id}" if base_url else None
    return {"session_id": session_id, "status": session["status"], "review_url": review_url}


def restart_cancelled_enrollment_review(
    session_id: str,
    store: DataStore,
    *,
    base_url: str | None = None,
    actor: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a fresh enrollment session from a cancelled session's manifest.

    The cancelled session remains immutable for auditability.  Restarting never
    reuses its pending vectors and always snapshots the current source files.
    """
    session = store.get_review_session(session_id)
    if session["status"] != "cancelled":
        raise ValueError("只有已取消的首次建库任务可以重新启动")
    if session["kind"] != "enrollment":
        raise ValueError("当前只支持重新启动首次建库任务")
    manifest_path = Path(session["manifest_path"])
    if not manifest_path.is_file():
        raise FileNotFoundError("原任务的输入清单不存在，无法重新启动")
    result = create_enrollment_review(manifest_path, store, base_url=base_url)
    store.audit_event(
        "review_session_restarted",
        session_id=session_id,
        actor=actor,
        value={"new_session_id": result["session_id"]},
        client=client,
    )
    return {**result, "restarted_from": session_id}


def create_profile_review(
    candidate_path: Path,
    store: DataStore,
    *,
    base_url: str | None = None,
    expires_days: int = 7,
) -> dict[str, Any]:
    """Turn a pending analysis candidate into the same browser review flow."""
    candidate = load_structured(candidate_path.resolve())
    if candidate.get("status") != "pending_confirmation":
        raise ValueError("只有待确认的候选声纹可以创建审核会话")
    customer_id = str(candidate.get("customer_id") or "")
    person_id = str(candidate.get("person_id") or "")
    person = store.get_person(person_id)
    if person.get("scope") == "customer" and person.get("customer_id") != customer_id:
        raise RuntimeError("Cross-customer profile review was blocked")
    meeting = candidate.get("meeting") or {}
    # Candidates written by older Skill releases did not retain the meeting
    # paths.  Their enrollment draft did, so retain a review path after a
    # layout migration without weakening the path restrictions below.
    legacy_run_id = str(candidate.get("run_id") or "")
    if not meeting and legacy_run_id:
        legacy_draft = (
            store.customer_dir(customer_id)
            / "enrollments"
            / legacy_run_id
            / "enrollment_draft.json"
        )
        if legacy_draft.is_file():
            meeting = (load_structured(legacy_draft).get("manifest") or {}).get("meeting") or {}
    if not meeting.get("audio") or not meeting.get("transcript"):
        raise ValueError("候选缺少原始会议路径，不能生成可试听的审核会话")
    customer = json.loads(store.get_customer(customer_id)["metadata_json"])
    manifest = validate_manifest(
        {
            "schema_version": 1,
            "customer": customer,
            "meeting": meeting,
            "attendees": [
                {
                    "id": person["person_id"],
                    "name": person["name"],
                    "role": person["role"],
                    "organization": person["organization"],
                }
            ],
        }
    )
    session_id = _session_id(f"candidate-{candidate['candidate_id']}")
    session_dir = store.session_dir(customer_id, session_id)
    manifest_path = session_dir / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    session = store.create_review_session(
        customer_id,
        session_id,
        "profile_expansion",
        manifest_path,
        sha256_file(Path(meeting["audio"])),
        sha256_file(Path(meeting["transcript"])),
        expires_days,
    )
    # This package reuses an existing candidate vector bank; it must never be
    # queued for model inference a second time.
    store.finish_review_job(f"job-{session_id}", "cancelled", {"reused_candidate": candidate["candidate_id"]})
    vector_path = store.resolve_storage_path(str(candidate["npz_path"]), customer_id)
    with np.load(vector_path, allow_pickle=False) as values:
        vectors = np.asarray(values["embeddings"], dtype=np.float32)
    raw_windows = list(candidate.get("windows") or [])
    if len(raw_windows) != len(vectors):
        raise ValueError("候选窗口与向量数量不一致")
    segments: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_windows):
        segments.append({
            "segment_id": f"seg-{safe_component(session_id)}-{index:04d}",
            "vector_index": index,
            "label": str(raw.get("label") or candidate.get("transcript_label") or "候选片段"),
            "utterance_index": int(raw.get("utterance_index", index)),
            "timestamp": str(raw.get("timestamp", "00:00")),
            "start": float(raw["start"]), "end": float(raw["end"]), "duration": float(raw["duration"]),
            "quality": float(raw.get("quality", 1.0)), "rms_dbfs": float(raw.get("rms_dbfs", -20.0)),
            "voiced_fraction": float(raw.get("voiced_fraction", 1.0)), "clipping_ratio": float(raw.get("clipping_ratio", 0.0)),
            "text": str(raw.get("text", "")),
        })
    pending_path = session_dir / "pending_vectors.npz"
    atomic_save_npz(pending_path, embeddings=vectors)
    label = str(candidate.get("transcript_label") or segments[0]["label"] if segments else "候选片段")
    package = {
        "schema_version": 1, "session_id": session_id, "kind": "profile_expansion", "status": "review_required",
        "manifest": manifest,
        "source": {"audio_path": meeting["audio"], "audio_sha256": sha256_file(Path(meeting["audio"])), "transcript_path": meeting["transcript"], "transcript_sha256": sha256_file(Path(meeting["transcript"]))},
        "model": {"id": "reused_candidate", "revision": "existing"}, "transcript_index": {"labels": {}},
        "people": [person], "calibration": candidate.get("voiceprint", {"accept_threshold": 0.58}), "segments": segments,
        "labels": [{"label": label, "risk": "yellow", "risk_notes": ["后续会议候选扩充，需人工确认后才生成新版本"], "suggestion": {"person_id": person_id, "name": person["name"], "source": "candidate_prediction"}, "quality": {"window_count": len(segments), "usable_seconds": float(sum(item["duration"] for item in segments))}, "acoustic": candidate.get("voiceprint", {}), "clusters": [{"cluster_id": f"{safe_component(label)}-c1", "window_count": len(segments), "seconds": float(sum(item["duration"] for item in segments)), "representative_segment_ids": [item["segment_id"] for item in segments[:3]], "segment_ids": [item["segment_id"] for item in segments]}], "outlier_segment_ids": []}],
        "pending_vector_file": pending_path.name,
        "selection_requirements": {"minimum_windows": int(PIPELINE_CONFIG["minimum_profile_windows"]), "minimum_seconds": float(PIPELINE_CONFIG["minimum_profile_seconds"])},
    }
    package_path = session_dir / "review_package.json"
    atomic_write_json(package_path, package)
    store.set_review_session(session_id, status="review_required", package_path=package_path, event_type="profile_review_prepared")
    review_url = f"{base_url.rstrip('/')}/sessions/{session_id}" if base_url else None
    return {"session_id": session_id, "status": "review_required", "review_url": review_url}


def _profile_revision_customer(store: DataStore, person: dict[str, Any]) -> dict[str, Any]:
    if person.get("scope") == "customer" and person.get("customer_id"):
        return store.get_customer(str(person["customer_id"]))
    return store.ensure_shared_review_customer()


def _profile_revision_sources(
    store: DataStore,
    person: dict[str, Any],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve optional playback paths without exposing them to the browser."""
    registration = manifest.get("registration") if isinstance(manifest.get("registration"), dict) else {}
    raw_sources = [
        item
        for item in list(registration.get("source_recordings") or [])
        + list(manifest.get("sources") or [])
        if isinstance(item, dict)
    ]
    safe_sources = store._safe_sources(manifest)

    def same_source(left: dict[str, Any], right: dict[str, Any]) -> bool:
        for key in ("source_id", "meeting_id"):
            if left.get(key) and right.get(key) and str(left[key]) == str(right[key]):
                return True
        return bool(left.get("title") and left.get("title") == right.get("title"))

    values: list[dict[str, Any]] = []
    for index, source in enumerate(safe_sources, start=1):
        raw = next((item for item in raw_sources if same_source(source, item)), {})
        value = {**source, "source_id": str(source.get("source_id") or f"source-{index}")}
        source_customer_id = str(
            source.get("customer_id") or raw.get("customer_id") or person.get("customer_id") or ""
        )
        if source_customer_id:
            value["customer_id"] = source_customer_id
        for kind in ("audio", "transcript"):
            path: Path | None = None
            raw_path = str(raw.get(f"{kind}_path") or "").strip()
            if raw_path:
                candidate = Path(raw_path).expanduser().resolve()
                if candidate.is_file():
                    path = candidate
            relative = str(
                source.get(f"{kind}_relative_path")
                or raw.get(f"{kind}_relative_path")
                or ""
            ).strip()
            if path is None and relative and source_customer_id and source_customer_id != "__shared_staff__":
                with contextlib.suppress(Exception):
                    root = store.customer_source_dir(source_customer_id).resolve()
                    candidate = (root / relative).resolve()
                    if root in candidate.parents and candidate.is_file():
                        path = candidate
            if path is not None:
                expected = str(source.get(f"{kind}_sha256") or raw.get(f"{kind}_sha256") or "")
                if not expected or sha256_file(path) == expected:
                    value[f"{kind}_path"] = str(path)
        value["playable"] = bool(value.get("audio_path"))
        values.append(value)
    return values


def create_profile_revision_review(
    person_id: str,
    base_version: int,
    store: DataStore,
    *,
    base_url: str | None = None,
    expires_days: int = 7,
) -> dict[str, Any]:
    """Create an immediately reviewable task from one immutable profile version."""
    base = store.load_profile(person_id, int(base_version))
    person = base["person"]
    provenance = store._profile_provenance(base)
    windows = provenance["references"] + provenance["heldouts"]
    if not windows:
        raise ValueError("该历史版本没有可审核的窗口来源，不能创建新版")
    if not any(
        item.get("provenance_status") != "legacy_source_unavailable"
        for item in windows
    ):
        raise ValueError(
            "该历史版本缺少可回查的窗口来源，不能创建版本修订；"
            "仍可用于声纹识别和经审核的候选扩充"
        )

    owner = _profile_revision_customer(store, person)
    customer_id = str(owner["customer_id"])
    customer = json.loads(str(owner.get("metadata_json") or "{}"))
    customer.update({"id": customer_id, "name": str(owner["name"])})
    session_id = _session_id(f"revision-{person_id}-v{int(base_version):04d}")
    session_dir = store.session_dir(customer_id, session_id)
    base_npz_path = Path(base["npz_path"])
    base_manifest_path = Path(base["manifest_path"])
    base_npz_sha256 = sha256_file(base_npz_path)
    base_manifest_sha256 = sha256_file(base_manifest_path)
    display_title = f"{person['name']} · v{int(base_version):04d} 版本修订"
    manifest = {
        "schema_version": 1,
        "kind": "profile_revision",
        "display_title": display_title,
        "customer": customer,
        "meeting": {
            "id": f"profile-{safe_component(person_id)}-v{int(base_version):04d}",
            "title": display_title,
        },
        "attendees": [
            {
                "id": person_id,
                "name": person["name"],
                "role": person.get("role", ""),
                "organization": person.get("organization", "yingdao"),
            }
        ],
        "profile_revision": {
            "person_id": person_id,
            "base_version": int(base_version),
        },
    }
    manifest_path = session_dir / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    store.create_review_session(
        customer_id,
        session_id,
        "profile_revision",
        manifest_path,
        base_npz_sha256,
        base_manifest_sha256,
        expires_days,
    )

    sources = _profile_revision_sources(store, person, base["manifest"])
    source_by_id = {str(item["source_id"]): item for item in sources}
    vectors: list[np.ndarray] = []
    segments: list[dict[str, Any]] = []
    grouped_segments: dict[tuple[str, str], list[str]] = defaultdict(list)
    grouped_seconds: dict[tuple[str, str], float] = defaultdict(float)
    for index, window in enumerate(windows):
        source_id = str(window.get("source_id") or "source-unknown")
        source = source_by_id.get(source_id)
        if source is None:
            source = {
                "source_id": source_id,
                "title": str(window.get("meeting_title") or "历史声纹素材"),
                "playable": False,
            }
            sources.append(source)
            source_by_id[source_id] = source
        array_kind = str(window["array_kind"])
        array_index = int(window["array_index"])
        vectors.append(np.asarray(base["arrays"][array_kind][array_index], dtype=np.float32))
        segment_id = f"seg-{safe_component(session_id)}-{index:04d}"
        title = str(source.get("title") or window.get("meeting_title") or "历史声纹素材")
        label = str(window.get("label") or "已入库片段")
        duration = float(window.get("duration") or 0.0)
        segments.append(
            {
                **window,
                "segment_id": segment_id,
                "source_window_id": str(window["window_id"]),
                "vector_index": index,
                "source_id": source_id,
                "meeting_title": title,
                "label": label,
                "display_label": f"{title} · {label}",
                "utterance_index": int(window.get("utterance_index") or array_index),
                "timestamp": str(window.get("timestamp") or "00:00"),
                "start": float(window.get("start") or 0.0),
                "end": float(window.get("end") or float(window.get("start") or 0.0) + duration),
                "duration": duration,
                "quality": float(window.get("quality") or 0.5),
                "rms_dbfs": float(window.get("rms_dbfs") or -30.0),
                "voiced_fraction": float(window.get("voiced_fraction") or 1.0),
                "clipping_ratio": float(window.get("clipping_ratio") or 0.0),
                "text": str(window.get("text") or ""),
                "playable": bool(source.get("playable")),
            }
        )
        grouped_segments[(source_id, label)].append(segment_id)
        grouped_seconds[(source_id, label)] += duration

    pending_path = session_dir / "pending_vectors.npz"
    atomic_save_npz(pending_path, embeddings=np.stack(vectors).astype(np.float32))
    labels: list[dict[str, Any]] = []
    for index, ((source_id, label), segment_ids) in enumerate(grouped_segments.items(), start=1):
        source = source_by_id[source_id]
        title = str(source.get("title") or "历史声纹素材")
        labels.append(
            {
                "label": f"{title} · {label}",
                "meeting_title": title,
                "risk": "green",
                "risk_notes": [f"来自 v{int(base_version):04d}，取消选择后不会进入新版本"],
                "suggestion": {
                    "person_id": person_id,
                    "name": person["name"],
                    "source": "base_profile_version",
                },
                "quality": {
                    "window_count": len(segment_ids),
                    "usable_seconds": grouped_seconds[(source_id, label)],
                },
                "acoustic": {},
                "clusters": [
                    {
                        "cluster_id": f"revision-{index}-c1",
                        "window_count": len(segment_ids),
                        "seconds": grouped_seconds[(source_id, label)],
                        "representative_segment_ids": segment_ids[:3],
                        "segment_ids": segment_ids,
                    }
                ],
                "outlier_segment_ids": [],
            }
        )
    package = {
        "schema_version": 1,
        "session_id": session_id,
        "kind": "profile_revision",
        "status": "review_required",
        "display_title": display_title,
        "manifest": manifest,
        "source": sources[0] if sources else {"source_id": "source-unknown", "playable": False},
        "sources": sources,
        "model": base["manifest"].get("model") or {},
        "people": [person],
        "calibration": {},
        "labels": labels,
        "segments": segments,
        "pending_vector_file": pending_path.name,
        "selection_requirements": {
            "minimum_windows": int(PIPELINE_CONFIG["minimum_profile_windows"]),
            "minimum_seconds": float(PIPELINE_CONFIG["minimum_profile_seconds"]),
        },
        "profile_revision": {
            "person_id": person_id,
            "base_version": int(base_version),
            "base_npz_path": str(base_npz_path),
            "base_npz_sha256": base_npz_sha256,
            "base_manifest_path": str(base_manifest_path),
            "base_manifest_sha256": base_manifest_sha256,
        },
    }
    package_path = session_dir / "review_package.json"
    atomic_write_json(package_path, package)
    decision = {
        "assignments": {item["segment_id"]: person_id for item in segments},
        "new_people": [],
        "make_current": True,
    }
    session = store.set_review_session(
        session_id,
        status="review_required",
        package_path=package_path,
        decision=decision,
        event_type="profile_revision_review_prepared",
    )
    store.finish_review_job(
        f"job-{session_id}",
        "completed",
        {"phase": "completed", "message": "历史版本已载入审核工作区"},
    )
    review_url = f"{base_url.rstrip('/')}/enrollments/{session_id}" if base_url else None
    return {"session_id": session_id, "status": session["status"], "review_url": review_url}


def _candidate_key(candidate: Candidate) -> tuple[int, float, float]:
    return candidate.utterance_index, round(candidate.start, 4), round(candidate.end, 4)


def _cluster_indices(vectors: np.ndarray, threshold: float = 0.70) -> list[list[int]]:
    """Small deterministic connected-component clustering for a label."""
    if len(vectors) == 0:
        return []
    if len(vectors) == 1:
        return [[0]]
    similarity = vectors @ vectors.T
    visited: set[int] = set()
    groups: list[list[int]] = []
    for start in range(len(vectors)):
        if start in visited:
            continue
        queue: deque[int] = deque([start])
        visited.add(start)
        group: list[int] = []
        while queue:
            current = queue.popleft()
            group.append(current)
            for neighbor in np.flatnonzero(similarity[current] >= threshold).tolist():
                if neighbor != current and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(int(neighbor))
        groups.append(sorted(group))
    return sorted(groups, key=lambda group: (-len(group), group[0]))


def _representatives(candidates: list[Candidate], vectors: np.ndarray, indices: list[int]) -> list[int]:
    if not indices:
        return []
    if len(indices) == 1:
        return indices
    local_vectors = vectors[indices]
    medoid = indices[int(np.argmax(np.mean(local_vectors @ local_vectors.T, axis=1)))]
    chronological = sorted(indices, key=lambda index: candidates[index].start)
    early = max(chronological[: max(1, len(chronological) // 3)], key=lambda index: candidates[index].quality)
    late = max(chronological[-max(1, len(chronological) // 3) :], key=lambda index: candidates[index].quality)
    result: list[int] = []
    for index in (medoid, early, late):
        if index not in result:
            result.append(index)
    return result


def _risk_for_clusters(
    candidates: list[Candidate], clusters: list[list[int]], primary_indices: set[int]
) -> tuple[str, list[str]]:
    if not candidates:
        return "red", ["没有通过质量筛选的有效语音窗口"]
    seconds = float(sum(item.duration for item in candidates))
    primary = max(clusters, key=len) if clusters else []
    main_share = len(primary) / len(candidates) if candidates else 0.0
    meaningful = [group for group in clusters if len(group) >= 2]
    notes: list[str] = []
    if len(meaningful) >= 2 and len(meaningful[1]) / len(candidates) >= 0.20:
        notes.append("存在两个以上有效语音聚类，疑似标签混合")
        return "red", notes
    if len(candidates) < int(PIPELINE_CONFIG["minimum_profile_windows"]) or seconds < float(
        PIPELINE_CONFIG["minimum_profile_seconds"]
    ):
        notes.append("语音窗口数或有效语音秒数不足，暂不适合正式建库")
        return "yellow", notes
    if main_share < 0.8 or len(primary_indices) < len(candidates):
        notes.append("存在少量离群窗口，提交时建议排除后复核")
        return "yellow", notes
    return "green", notes


def _person_rows(store: DataStore, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attendees = store.upsert_manifest(manifest)
    return {item["person_id"]: item for item in attendees.values() if item.get("person_id")}


def _suggestion(
    label: str,
    manifest: dict[str, Any],
    people_by_id: dict[str, dict[str, Any]],
    acoustic: dict[str, Any],
) -> dict[str, Any]:
    known = manifest.get("known_label_map", {})
    by_name = {person["name"]: person for person in people_by_id.values()}
    if label in known and known[label] in by_name:
        person = by_name[known[label]]
        return {"person_id": person["person_id"], "name": person["name"], "source": "known_label_map"}
    if label in by_name:
        person = by_name[label]
        return {"person_id": person["person_id"], "name": person["name"], "source": "exact_named_label"}
    top1 = acoustic.get("top1_person_id")
    if top1 and top1 in people_by_id:
        person = people_by_id[top1]
        return {"person_id": top1, "name": person["name"], "source": "voiceprint_top1"}
    return {"person_id": None, "name": None, "source": None}


def prepare_review_session(
    session_id: str,
    store: DataStore,
    download: bool = False,
    *,
    job_id: str | None = None,
    engine: EmbeddingEngine | None = None,
) -> dict[str, Any]:
    session = store.get_review_session(session_id)
    if session["status"] in {"cancelled", "expired", "committed"}:
        return session
    manifest = normalize_review_manifest(load_structured(Path(session["manifest_path"])))
    meetings = _review_meetings(manifest)
    for meeting in meetings:
        audio_path = Path(meeting["audio"])
        transcript_path = Path(meeting["transcript"])
        if (
            sha256_file(audio_path) != meeting.get("audio_sha256")
            or sha256_file(transcript_path) != meeting.get("transcript_sha256")
        ):
            return store.set_review_session(
                session_id,
                status="source_changed",
                error_message=f"录音或转写在审核准备前已变化：{meeting['title']}",
                event_type="review_source_changed",
            )

    people_by_id = _person_rows(store, manifest)
    candidates: list[Candidate] = []
    vector_parts: list[np.ndarray] = []
    candidate_source_ids: list[str] = []
    label_order: list[tuple[str, str]] = []
    sources: list[dict[str, Any]] = []
    sampling_by_label: dict[tuple[str, str], dict[str, Any]] = {}
    meeting_total = len(meetings)
    _report_review_progress(
        store,
        job_id,
        "model_loading",
        "正在加载本地声纹模型…",
        meeting_total=meeting_total,
    )
    with tempfile.TemporaryDirectory(prefix="speaker-review-prepare-") as temporary:
        temporary_root = Path(temporary)
        engine = engine or EmbeddingEngine(download=download)
        for meeting_index, meeting in enumerate(meetings, start=1):
            _ensure_review_active(store, session_id)
            source_id = f"source-{meeting_index}"
            audio_path = Path(meeting["audio"])
            transcript_path = Path(meeting["transcript"])
            wav_path = temporary_root / f"{source_id}.wav"
            _report_review_progress(
                store,
                job_id,
                "transcoding",
                f"正在转码第 {meeting_index} / {meeting_total} 份录音：{meeting['title']}",
                meeting_index=meeting_index,
                meeting_total=meeting_total,
                meeting_title=meeting["title"],
            )
            convert_to_wav(audio_path, wav_path, int(PIPELINE_CONFIG["sample_rate"]))
            _ensure_review_active(store, session_id)
            _report_review_progress(
                store,
                job_id,
                "screening",
                f"正在筛选第 {meeting_index} / {meeting_total} 份录音的有效语音：{meeting['title']}",
                meeting_index=meeting_index,
                meeting_total=meeting_total,
                meeting_title=meeting["title"],
            )
            utterances = parse_transcript(transcript_path, audio_duration(wav_path))
            index = transcript_index(utterances)
            raw_candidates = build_candidates(wav_path, utterances, PIPELINE_CONFIG)
            raw_by_label: dict[str, list[Candidate]] = defaultdict(list)
            for candidate in raw_candidates:
                raw_by_label[candidate.label].append(candidate)

            local_candidates: list[Candidate] = []
            local_vector_parts: list[np.ndarray] = []
            should_cancel = _review_cancel_probe(store, session_id)
            source_label_candidates = [
                (str(raw_label), raw_by_label.get(str(raw_label), [])) for raw_label in index["labels"]
            ]
            initial_counts = {
                raw_label: _review_initial_sample_count(source_candidates)
                for raw_label, source_candidates in source_label_candidates
            }
            embedding_total = sum(initial_counts.values())
            embedding_done = 0
            _report_review_progress(
                store,
                job_id,
                "embedding",
                f"正在提取第 {meeting_index} / {meeting_total} 份录音的声纹：0 / {embedding_total} 个窗口",
                meeting_index=meeting_index,
                meeting_total=meeting_total,
                meeting_title=meeting["title"],
                embedding_completed=embedding_done,
                embedding_total=embedding_total,
                valid_window_count=len(raw_candidates),
            )
            for label_index, (raw_label, source_candidates) in enumerate(source_label_candidates, start=1):
                source_candidates = raw_by_label.get(str(raw_label), [])
                initial_count = initial_counts[raw_label]
                selected = select_temporally_diverse(source_candidates, initial_count)
                def report_embedding_progress(completed: int, total: int, *, label_value: str = raw_label) -> None:
                    _report_review_progress(
                        store,
                        job_id,
                        "embedding",
                        (
                            f"正在提取第 {meeting_index} / {meeting_total} 份录音的声纹："
                            f"{embedding_done + completed} / {embedding_total} 个窗口（{label_value}）"
                        ),
                        meeting_index=meeting_index,
                        meeting_total=meeting_total,
                        meeting_title=meeting["title"],
                        label=label_value,
                        label_index=label_index,
                        label_total=len(source_label_candidates),
                        embedding_completed=embedding_done + completed,
                        embedding_total=embedding_total,
                        valid_window_count=len(raw_candidates),
                    )
                selected_vectors = (
                    engine.embed_candidates(
                        wav_path,
                        selected,
                        should_cancel=should_cancel,
                        on_progress=report_embedding_progress,
                    )
                    if selected
                    else np.empty((0, 192), dtype=np.float32)
                )
                embedding_done += len(selected)
                expanded = False
                initial_clusters = _cluster_indices(selected_vectors)
                meaningful = [group for group in initial_clusters if len(group) >= 2]
                if (
                    len(meaningful) >= 2
                    and len(meaningful[1]) / len(selected) >= 0.20
                    and len(selected) < len(source_candidates)
                ):
                    room = int(PIPELINE_CONFIG["review_max_windows_per_label"]) - len(selected)
                    extra_count = min(
                        int(PIPELINE_CONFIG["review_mixed_expansion_windows"]),
                        len(source_candidates) - len(selected),
                        max(0, room),
                    )
                    selected_keys = {_candidate_key(item) for item in selected}
                    remaining = [item for item in source_candidates if _candidate_key(item) not in selected_keys]
                    extras = select_temporally_diverse(remaining, extra_count)
                    if extras:
                        embedding_total += len(extras)
                        _report_review_progress(
                            store,
                            job_id,
                            "embedding",
                            (
                                f"检测到 {raw_label} 疑似混合，正在追加复核："
                                f"{embedding_done} / {embedding_total} 个窗口"
                            ),
                            meeting_index=meeting_index,
                            meeting_total=meeting_total,
                            meeting_title=meeting["title"],
                            label=raw_label,
                            label_index=label_index,
                            label_total=len(source_label_candidates),
                            embedding_completed=embedding_done,
                            embedding_total=embedding_total,
                            valid_window_count=len(raw_candidates),
                        )
                        extra_vectors = engine.embed_candidates(
                            wav_path,
                            extras,
                            should_cancel=should_cancel,
                            on_progress=report_embedding_progress,
                        )
                        embedding_done += len(extras)
                        pairs = list(zip(selected, selected_vectors)) + list(zip(extras, extra_vectors))
                        pairs.sort(key=lambda item: (item[0].start, item[0].end, item[0].utterance_index))
                        selected = [item[0] for item in pairs]
                        selected_vectors = np.stack([item[1] for item in pairs]).astype(np.float32)
                        expanded = True
                sampling_by_label[(source_id, str(raw_label))] = {
                    "candidate_window_count": len(source_candidates),
                    "candidate_seconds": float(sum(item.duration for item in source_candidates)),
                    "initial_sample_count": initial_count,
                    "embedded_window_count": len(selected),
                    "expanded_for_mixture": expanded,
                }
                local_candidates.extend(selected)
                if len(selected_vectors):
                    local_vector_parts.append(np.asarray(selected_vectors, dtype=np.float32))
            local_vectors = (
                np.concatenate(local_vector_parts, axis=0)
                if local_vector_parts
                else np.empty((0, 192), dtype=np.float32)
            )
            if len(local_candidates) != len(local_vectors):
                raise RuntimeError(f"{meeting['title']} 的语音窗口与向量数量不一致")
            candidates.extend(local_candidates)
            vector_parts.append(np.asarray(local_vectors, dtype=np.float32))
            candidate_source_ids.extend([source_id] * len(local_candidates))
            label_order.extend((source_id, str(label)) for label in index["labels"])
            sources.append(
                {
                    "source_id": source_id,
                    "meeting_id": meeting["id"],
                    "title": meeting["title"],
                    "audio_path": str(audio_path),
                    "audio_sha256": meeting["audio_sha256"],
                    "transcript_path": str(transcript_path),
                    "transcript_sha256": meeting["transcript_sha256"],
                    "transcript_index": index,
                }
            )
        _ensure_review_active(store, session_id)
        _report_review_progress(
            store,
            job_id,
            "clustering",
            "正在汇总声纹聚类并生成审核包…",
            meeting_total=meeting_total,
            embedded_window_count=len(candidates),
        )
    vectors = np.concatenate(vector_parts, axis=0) if vector_parts else np.empty((0, 192), dtype=np.float32)

    profiles = store.analysis_profiles(
        str(manifest["customer"]["id"]),
        manifest.get("attendees", []),
        {candidate.label for candidate in candidates},
    )
    calibration = _calibration_for_profiles(
        store, str(manifest["customer"]["id"]), profiles
    )
    labels: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    candidate_indices_by_label: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index_number, candidate in enumerate(candidates):
        source_id = candidate_source_ids[index_number]
        source = next(item for item in sources if item["source_id"] == source_id)
        candidate_indices_by_label[(source_id, candidate.label)].append(index_number)
        segments.append(
            {
                "segment_id": f"seg-{safe_component(session_id)}-{index_number:04d}",
                "vector_index": index_number,
                "label": candidate.label,
                "display_label": f"{source['title']} · {candidate.label}",
                "source_id": source_id,
                "meeting_id": source["meeting_id"],
                "meeting_title": source["title"],
                "utterance_index": candidate.utterance_index,
                "timestamp": candidate.timestamp,
                "start": candidate.start,
                "end": candidate.end,
                "duration": candidate.duration,
                "quality": candidate.quality,
                "rms_dbfs": candidate.rms_dbfs,
                "voiced_fraction": candidate.voiced_fraction,
                "clipping_ratio": candidate.clipping_ratio,
                "text": candidate.text,
            }
        )
    segments_by_vector = {item["vector_index"]: item for item in segments}

    excluded = set(str(item) for item in manifest.get("excluded_labels", []))
    sources_by_id = {item["source_id"]: item for item in sources}
    for source_id, raw_label in label_order:
        source = sources_by_id[source_id]
        display_label = f"{source['title']} · {raw_label}"
        original_indices = candidate_indices_by_label.get((source_id, raw_label), [])
        label_candidates = [candidates[item] for item in original_indices]
        label_vectors = vectors[original_indices] if original_indices else np.empty((0, 192), dtype=np.float32)
        filtered, _, consistency = internal_consistency_filter(
            label_candidates, label_vectors, int(PIPELINE_CONFIG["max_profile_windows_per_person"])
        )
        primary_keys = {_candidate_key(item) for item in filtered}
        primary_local = {
            index_number
            for index_number, candidate in enumerate(label_candidates)
            if _candidate_key(candidate) in primary_keys
        }
        clusters = _cluster_indices(label_vectors)
        displayed = clusters[:3]
        overflow = [index_number for cluster in clusters[3:] for index_number in cluster]
        risk, risk_notes = _risk_for_clusters(label_candidates, clusters, primary_local)
        sampling = sampling_by_label.get((source_id, raw_label), {})
        if sampling.get("expanded_for_mixture"):
            risk_notes = [*risk_notes, "首轮样本疑似混合，已额外抽取 8 个窗口复核"]
        acoustic = match_label(label_candidates, label_vectors, profiles, calibration)
        suggestion = _suggestion(raw_label, manifest, people_by_id, acoustic)
        rendered_clusters = []
        for cluster_index, cluster in enumerate(displayed, start=1):
            global_indices = [original_indices[item] for item in cluster]
            rendered_clusters.append(
                {
                    "cluster_id": f"{safe_component(f'{source_id}-{raw_label}', 'speaker')}-c{cluster_index}",
                    "window_count": len(cluster),
                    "seconds": float(sum(candidates[item].duration for item in global_indices)),
                    "primary_overlap": sum(item in primary_local for item in cluster),
                    "representative_segment_ids": [
                        segments_by_vector[original_indices[item]]["segment_id"]
                        for item in _representatives(label_candidates, label_vectors, cluster)
                    ],
                    "segment_ids": [segments_by_vector[item]["segment_id"] for item in global_indices],
                }
            )
        labels.append(
            {
                "label": display_label,
                "raw_label": raw_label,
                "meeting_id": source["meeting_id"],
                "meeting_title": source["title"],
                "excluded_by_manifest": raw_label in excluded or display_label in excluded,
                "suggestion": suggestion,
                "risk": risk,
                "risk_notes": risk_notes,
                "quality": {
                    "window_count": len(label_candidates),
                    "usable_seconds": float(sum(item.duration for item in label_candidates)),
                    "internal_consistency": consistency,
                    **sampling,
                },
                "acoustic": acoustic,
                "clusters": rendered_clusters,
                "outlier_segment_ids": [segments_by_vector[original_indices[item]]["segment_id"] for item in overflow],
            }
        )

    session_dir = store.session_dir(str(manifest["customer"]["id"]), session_id)
    pending_path = session_dir / "pending_vectors.npz"
    atomic_save_npz(pending_path, embeddings=vectors)
    package = {
        "schema_version": 1,
        "session_id": session_id,
        "kind": session["kind"],
        "status": "review_required",
        "created_at": now_iso(),
        "manifest": manifest,
        "display_title": (
            meetings[0]["title"]
            if len(meetings) == 1
            else f"首次建库（{len(meetings)} 份录音）"
        ),
        # ``source`` remains for compatibility with existing single-recording
        # sessions.  New sessions always verify and expose ``sources``.
        "source": {key: value for key, value in sources[0].items() if key != "transcript_index"},
        "sources": [{key: value for key, value in item.items() if key != "transcript_index"} for item in sources],
        "model": _model_manifest(engine),
        "transcript_index": {"meetings": {item["source_id"]: item["transcript_index"] for item in sources}},
        "people": list(people_by_id.values()),
        "calibration": calibration,
        "labels": labels,
        "segments": segments,
        "pending_vector_file": pending_path.name,
        "selection_requirements": {
            "minimum_windows": int(PIPELINE_CONFIG["minimum_profile_windows"]),
            "minimum_seconds": float(PIPELINE_CONFIG["minimum_profile_seconds"]),
        },
    }
    package_path = session_dir / "review_package.json"
    _report_review_progress(
        store,
        job_id,
        "writing_package",
        "正在写入待审核声纹包…",
        meeting_total=meeting_total,
        embedded_window_count=len(candidates),
    )
    atomic_write_json(package_path, package)
    return store.set_review_session(
        session_id,
        status="review_required",
        package_path=package_path,
        error_message="",
        event_type="review_prepared",
    )


def run_next_review_job(
    store: DataStore,
    download: bool = False,
    *,
    engine: EmbeddingEngine | None = None,
) -> dict[str, Any] | None:
    job = store.claim_review_job()
    if job is None:
        return None
    try:
        session = prepare_review_session(
            str(job["session_id"]),
            store,
            download=download,
            job_id=str(job["job_id"]),
            engine=engine,
        )
        if session["status"] == "review_required":
            store.finish_review_job(
                str(job["job_id"]),
                "completed",
                {"session_id": session["session_id"], "phase": "completed", "message": "审核包已准备完成"},
            )
        elif session["status"] in {"cancelled", "expired"}:
            store.finish_review_job(
                str(job["job_id"]),
                "cancelled",
                {"session_id": session["session_id"], "phase": "cancelled", "message": "任务已取消"},
            )
        else:
            store.finish_review_job(str(job["job_id"]), "failed", error=str(session.get("error_message") or session["status"]))
        return session
    except InterruptedError as exc:
        session = store.get_review_session(str(job["session_id"]))
        if session["status"] in {"cancelled", "expired"}:
            store.finish_review_job(
                str(job["job_id"]),
                "cancelled",
                {"session_id": session["session_id"], "phase": "cancelled", "message": "任务已取消"},
            )
            return session
        store.finish_review_job(str(job["job_id"]), "failed", error=f"{type(exc).__name__}: {exc}")
        store.set_review_session(
            str(job["session_id"]), status="failed", error_message=f"{type(exc).__name__}: {exc}", event_type="review_prepare_failed"
        )
        raise
    except Exception as exc:
        store.finish_review_job(str(job["job_id"]), "failed", error=f"{type(exc).__name__}: {exc}")
        store.set_review_session(
            str(job["session_id"]), status="failed", error_message=f"{type(exc).__name__}: {exc}", event_type="review_prepare_failed"
        )
        raise


def _load_package(session: dict[str, Any]) -> dict[str, Any]:
    if not session.get("package_path"):
        raise RuntimeError("审核包尚未准备完成")
    return load_structured(Path(session["package_path"]))


def failed_review_retry_eligibility(
    session: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return whether a failed review still has enough state to resume editing."""
    if session.get("status") != "failed":
        return False, None
    package_path_value = session.get("package_path")
    if not package_path_value:
        return False, "任务在审核包生成前失败，请重新创建任务"
    package_path = Path(package_path_value)
    if not package_path.is_file():
        return False, "原审核包已经不存在，请重新创建任务"
    try:
        package = load_structured(package_path)
    except Exception:
        return False, "原审核包无法读取，请重新创建任务"
    if not package.get("segments"):
        return False, "原审核包没有可编辑片段，请重新创建任务"
    pending_path = package_path.parent / str(
        package.get("pending_vector_file") or "pending_vectors.npz"
    )
    if not pending_path.is_file():
        return False, "待审核声纹向量已经清理，请重新创建任务"
    return True, None


def retry_failed_review_session(
    session_id: str,
    revision: int,
    store: DataStore,
    *,
    actor: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resume a failed commit in-place without recomputing its review package."""
    with file_lock(store.locks_dir / f"review-{session_id}.lock"):
        session = store.get_review_session(session_id)
        # A repeated request after a successful recovery is harmless and
        # returns the already editable session.
        if session["status"] == "review_required":
            return session
        if session["status"] != "failed":
            raise RuntimeError(f"此会话不可恢复编辑：{session['status']}")
        if int(session["revision"]) != int(revision):
            raise RuntimeError("review_revision_conflict")
        eligible, reason = failed_review_retry_eligibility(session)
        if not eligible:
            raise RuntimeError(reason or "失败任务无法恢复编辑")
        package = _load_package(session)
        try:
            _verify_source(session, package, store)
        except Exception as exc:
            store.set_review_session(
                session_id,
                status="source_changed",
                error_message=str(exc),
                actor=actor,
                client=client,
                event_type="review_retry_source_changed",
            )
            raise
        return store.set_review_session(
            session_id,
            status="review_required",
            error_message="",
            expected_revision=revision,
            bump_revision=True,
            actor=actor,
            client=client,
            event_type="review_failed_reopened",
        )


def _verify_source(session: dict[str, Any], package: dict[str, Any], store: DataStore) -> None:
    if package.get("kind") == "profile_revision":
        revision = package.get("profile_revision") or {}
        person_id = str(revision.get("person_id") or "")
        base_version = int(revision.get("base_version") or 0)
        # Resolve the immutable profile through the registry again instead of
        # trusting browser-visible paths or a stale package location.
        base = store.load_profile(person_id, base_version)
        if sha256_file(Path(base["npz_path"])) != str(revision.get("base_npz_sha256") or ""):
            raise RuntimeError("source_changed: 基础声纹向量在审核过程中发生变化")
        if sha256_file(Path(base["manifest_path"])) != str(
            revision.get("base_manifest_sha256") or ""
        ):
            raise RuntimeError("source_changed: 基础声纹版本信息在审核过程中发生变化")
        return
    sources = package.get("sources") or [package["source"]]
    for source in sources:
        title = str(source.get("title") or "录音")
        expected_audio = str(source.get("audio_sha256") or session["source_audio_sha256"])
        expected_transcript = str(source.get("transcript_sha256") or session["source_transcript_sha256"])
        if sha256_file(Path(source["audio_path"])) != expected_audio:
            raise RuntimeError(f"source_changed: 录音在审核过程中发生变化：{title}")
        if sha256_file(Path(source["transcript_path"])) != expected_transcript:
            raise RuntimeError(f"source_changed: 转写在审核过程中发生变化：{title}")


def _assignment_person(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if not value.get("include", True):
            return None
        return str(value.get("person_id") or value.get("assignment") or "").strip() or None
    return None


def _decision_groups(
    package: dict[str, Any], decision: dict[str, Any]
) -> tuple[dict[str, list[int]], dict[str, dict[str, Any]], list[str]]:
    people = {str(item["person_id"]): dict(item) for item in package.get("people", []) if item.get("person_id")}
    errors: list[str] = []
    draft_ids: dict[str, str] = {}
    for new_person in decision.get("new_people", []):
        if not isinstance(new_person, dict):
            errors.append("新增人员格式无效")
            continue
        name = str(new_person.get("name", "")).strip()
        role = str(new_person.get("role", "")).strip()
        organization = str(new_person.get("organization", "customer")).strip().lower()
        if not name:
            errors.append("新增人员缺少姓名")
            continue
        if organization not in {"customer", "yingdao"}:
            errors.append(f"新增人员所属方无效：{name}")
            continue
        scope = "staff" if organization == "yingdao" else "customer"
        person_id = stable_id(
            "staff" if scope == "staff" else "person",
            "global" if scope == "staff" else package["manifest"]["customer"]["id"],
            name,
        )
        draft_id = str(new_person.get("draft_id") or new_person.get("person_id") or "").strip()
        if draft_id:
            draft_ids[draft_id] = person_id
        people[person_id] = {
            "person_id": person_id,
            "name": name,
            "role": role,
            "organization": organization,
            "scope": scope,
            "customer_id": None if scope == "staff" else package["manifest"]["customer"]["id"],
            "new_person": True,
        }
    segment_by_id = {str(item["segment_id"]): item for item in package["segments"]}
    groups: dict[str, list[int]] = defaultdict(list)
    for segment_id, raw_value in (decision.get("assignments") or {}).items():
        segment = segment_by_id.get(str(segment_id))
        if segment is None:
            errors.append(f"未知审核片段：{segment_id}")
            continue
        person_id = _assignment_person(raw_value)
        if not person_id or person_id in SPECIAL_ASSIGNMENTS:
            continue
        person_id = draft_ids.get(person_id, person_id)
        if person_id not in people:
            errors.append(f"片段分配给了不在参会名单中的人员：{person_id}")
            continue
        groups[person_id].append(int(segment["vector_index"]))
    return dict(groups), people, errors


def validate_review_decision(session_id: str, decision: dict[str, Any], store: DataStore) -> dict[str, Any]:
    session = store.get_review_session(session_id)
    package = _load_package(session)
    try:
        _verify_source(session, package, store)
    except RuntimeError as exc:
        store.set_review_session(session_id, status="source_changed", error_message=str(exc), event_type="review_source_changed")
        return {"valid": False, "errors": [str(exc)], "warnings": [], "groups": []}
    groups, people, errors = _decision_groups(package, decision)
    if package.get("kind") == "profile_revision":
        target_person_id = str((package.get("profile_revision") or {}).get("person_id") or "")
        if decision.get("new_people"):
            errors.append("版本修订任务不能新增或改派人员")
        unexpected = [person_id for person_id in groups if person_id != target_person_id]
        if unexpected:
            errors.append("版本修订任务只能保留到原声纹人员")
        if target_person_id and target_person_id not in groups:
            errors.append("请为新版本至少保留一组有效声纹片段")
    if not groups:
        errors.append("请至少为一位人员保留可建库的片段")
    pending_path = Path(session["package_path"]).parent / str(package["pending_vector_file"])
    if not pending_path.is_file():
        errors.append("待审核向量已清理，无法提交")
        return {"valid": False, "errors": errors, "warnings": [], "groups": []}
    with np.load(pending_path, allow_pickle=False) as data:
        vectors = np.asarray(data["embeddings"], dtype=np.float32)
    candidates = [Candidate(**{
        "label": item["label"], "utterance_index": item["utterance_index"], "start": item["start"], "end": item["end"],
        "timestamp": item["timestamp"], "text": item["text"], "duration": item["duration"], "rms_dbfs": item["rms_dbfs"],
        "voiced_fraction": item["voiced_fraction"], "clipping_ratio": item["clipping_ratio"], "quality": item["quality"],
    }) for item in package["segments"]]
    summaries: list[dict[str, Any]] = []
    centers: dict[str, np.ndarray] = {}
    for person_id, indices in groups.items():
        unique_indices = sorted(set(indices))
        chosen = [candidates[index] for index in unique_indices]
        chosen_vectors = vectors[unique_indices]
        if not np.isfinite(chosen_vectors).all() or chosen_vectors.ndim != 2 or chosen_vectors.shape[1] != 192:
            errors.append(f"{people[person_id]['name']} 的向量无效")
            continue
        try:
            arrays, stats = build_profile_arrays(chosen, chosen_vectors)
            centers[person_id] = arrays["center"]
            summaries.append(
                {
                    "person_id": person_id,
                    "name": people[person_id]["name"],
                    "role": people[person_id].get("role", ""),
                    "window_count": len(chosen),
                    "usable_seconds": float(sum(item.duration for item in chosen)),
                    "statistics": stats,
                }
            )
        except Exception as exc:
            errors.append(f"{people[person_id]['name']}：{exc}")
    warnings: list[str] = []
    ids = sorted(centers)
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            similarity = float(centers[left] @ centers[right])
            if similarity >= 0.84:
                warnings.append(
                    f"{people[left]['name']} 与 {people[right]['name']} 的本次中心相似度较高（{similarity:.3f}），请确认未混入同一人。"
                )
    if warnings and not bool(decision.get("acknowledge_warnings")):
        errors.append("请确认跨人员相似度警告后再提交")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "groups": summaries}


def save_review_decision(
    session_id: str,
    decision: dict[str, Any],
    revision: int,
    store: DataStore,
    *,
    actor: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = store.get_review_session(session_id)
    if session["status"] != "review_required":
        raise RuntimeError(f"此会话不可编辑：{session['status']}")
    return store.set_review_session(
        session_id,
        decision=decision,
        expected_revision=revision,
        actor=actor,
        client=client,
        event_type="review_decision_saved",
    )


def _candidate_from_segment(segment: dict[str, Any]) -> Candidate:
    return Candidate(
        label=str(segment["label"]),
        utterance_index=int(segment["utterance_index"]),
        start=float(segment["start"]),
        end=float(segment["end"]),
        timestamp=str(segment["timestamp"]),
        text=str(segment["text"]),
        duration=float(segment["duration"]),
        rms_dbfs=float(segment["rms_dbfs"]),
        voiced_fraction=float(segment["voiced_fraction"]),
        clipping_ratio=float(segment["clipping_ratio"]),
        quality=float(segment["quality"]),
    )


def _profile_vector_provenance(
    statistics: dict[str, Any], source_windows: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(item.get("label") or ""),
            int(item.get("utterance_index") or 0),
            round(float(item.get("start") or 0.0), 3),
            round(float(item.get("end") or 0.0), 3),
            str(item.get("text") or ""),
        )

    pool: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in source_windows:
        pool[key(item)].append(item)
    result: dict[str, list[dict[str, Any]]] = {"references": [], "heldouts": []}
    for kind, field in (("references", "reference_windows"), ("heldouts", "holdout_windows")):
        for index, window in enumerate(statistics.get(field) or []):
            matches = pool.get(key(window)) or []
            source = matches.pop(0) if matches else {}
            result[kind].append(
                {
                    **source,
                    **window,
                    "window_id": f"{'ref' if kind == 'references' else 'holdout'}-{index:04d}",
                    "array_kind": kind,
                    "array_index": index,
                }
            )
    return result


def _relative_source_path(root: Path, raw_path: str) -> str | None:
    try:
        return str(Path(raw_path).resolve().relative_to(root))
    except ValueError:
        return None


def _commit_profile_revision(
    session: dict[str, Any],
    package: dict[str, Any],
    decision: dict[str, Any],
    validation: dict[str, Any],
    store: DataStore,
    *,
    actor: str | None,
    client: dict[str, Any] | None,
) -> dict[str, Any]:
    session_id = str(session["session_id"])
    revision = package["profile_revision"]
    person_id = str(revision["person_id"])
    base_version = int(revision["base_version"])
    groups, _, errors = _decision_groups(package, decision)
    if errors:
        return {
            "status": "validation_failed",
            "valid": False,
            "errors": errors,
            "warnings": [],
        }
    selected_indices = sorted(set(groups.get(person_id) or []))
    segment_by_vector = {
        int(item["vector_index"]): item for item in package.get("segments", [])
    }
    included_window_ids = [
        str(segment_by_vector[index]["source_window_id"])
        for index in selected_indices
    ]
    make_current = bool(decision.get("make_current", True))
    person = store.get_person(person_id)
    before_pointer = person.get("current_version")
    journal_path = Path(session["package_path"]).parent / "commit_journal.json"
    created_version: int | None = None
    atomic_write_json(
        journal_path,
        {
            "session_id": session_id,
            "state": "committing",
            "person_id": person_id,
            "base_version": base_version,
            "before_pointer": before_pointer,
        },
    )
    try:
        profile = store.fork_profile_version(
            person_id,
            base_version,
            included_window_ids,
            make_current=make_current,
            review_session_id=session_id,
            confirmation_mode="web_reviewed_revision",
        )
        created_version = int(profile["new_version"])
        result = {
            "schema_version": 1,
            "session_id": session_id,
            "status": "committed",
            "kind": "profile_revision",
            "committed_at": now_iso(),
            "created_profiles": [profile],
            "profile_revision": profile,
            "validation": validation,
            "playback_count": store.audit_count(session_id, "review_segment_played"),
        }
        result_path = Path(session["package_path"]).parent / "review_result.json"
        atomic_write_json(result_path, result)
        atomic_write_json(
            journal_path,
            {"session_id": session_id, "state": "committed", "result": str(result_path)},
        )
        pending_path = Path(session["package_path"]).parent / str(package["pending_vector_file"])
        if pending_path.exists():
            pending_path.unlink()
        store.set_review_session(
            session_id,
            status="committed",
            result_path=result_path,
            actor=actor,
            client=client,
            event_type="profile_revision_commit_completed",
        )
        return result
    except Exception as exc:
        store.restore_profile_pointer(person_id, before_pointer)
        if created_version is not None:
            with store.connect() as db:
                db.execute(
                    "UPDATE profile_versions SET status = 'failed_commit' "
                    "WHERE person_id = ? AND version = ?",
                    (person_id, created_version),
                )
        atomic_write_json(
            journal_path,
            {
                "session_id": session_id,
                "state": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "before_pointer": before_pointer,
                "created_version": created_version,
            },
        )
        store.set_review_session(
            session_id,
            status="failed",
            error_message=f"{type(exc).__name__}: {exc}",
            actor=actor,
            client=client,
            event_type="profile_revision_commit_failed",
        )
        raise


def commit_review_session(
    session_id: str,
    revision: int,
    store: DataStore,
    *,
    actor: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor = str(actor or "").strip() or None
    with file_lock(store.locks_dir / f"review-{session_id}.lock"):
        session = store.get_review_session(session_id)
        if session["status"] == "committed":
            return load_structured(Path(session["result_path"]))
        if session["status"] != "review_required":
            raise RuntimeError(f"此会话不可提交：{session['status']}")
        if int(session["revision"]) != int(revision):
            raise RuntimeError("review_revision_conflict")
        decision = session.get("decision") or {}
        confirmation = (
            decision.get("confirmation")
            if isinstance(decision.get("confirmation"), dict)
            else {}
        )
        confirmation_mode = str(confirmation.get("mode") or "web_confirmed")
        validation = validate_review_decision(session_id, decision, store)
        if not validation["valid"]:
            return {"status": "validation_failed", **validation}
        package = _load_package(session)
        groups, people, errors = _decision_groups(package, decision)
        if errors:
            return {"status": "validation_failed", "valid": False, "errors": errors, "warnings": []}
        store.set_review_session(
            session_id, status="committing", actor=actor, client=client, event_type="review_commit_started"
        )
        if package.get("kind") == "profile_revision":
            return _commit_profile_revision(
                session,
                package,
                decision,
                validation,
                store,
                actor=actor,
                client=client,
            )
        journal_path = Path(session["package_path"]).parent / "commit_journal.json"
        before_pointers: dict[str, int | None] = {}
        created: list[dict[str, Any]] = []
        candidates_created: list[dict[str, Any]] = []
        try:
            manifest = normalize_review_manifest(package["manifest"])
            # 用户可在审核时新增缺失的客户或我方参会人；所属方决定写入
            # 当前客户命名空间还是共享员工命名空间。
            existing_ids = {str(item.get("id") or "") for item in manifest.get("attendees", [])}
            for person in people.values():
                if person.get("new_person") and person["person_id"] not in existing_ids:
                    manifest["attendees"].append(
                        {
                            "id": person["person_id"],
                            "name": person["name"],
                            "role": person.get("role", ""),
                            "organization": person["organization"],
                        }
                    )
            attendee_map = store.upsert_manifest(manifest)
            by_id = {item["person_id"]: item for item in attendee_map.values() if item.get("person_id")}
            pending_path = Path(session["package_path"]).parent / str(package["pending_vector_file"])
            with np.load(pending_path, allow_pickle=False) as data:
                vectors = np.asarray(data["embeddings"], dtype=np.float32)
            segment_by_vector = {int(item["vector_index"]): item for item in package["segments"]}
            atomic_write_json(
                journal_path,
                {"session_id": session_id, "state": "committing", "before_pointers": before_pointers, "created": created},
            )
            for person_id, indices in groups.items():
                person = store.get_person(by_id[person_id]["person_id"])
                before_pointers[person_id] = person.get("current_version")
                unique_indices = sorted(set(indices))
                selected_candidates = [_candidate_from_segment(segment_by_vector[index]) for index in unique_indices]
                selected_vectors = vectors[unique_indices]
                arrays, stats = build_profile_arrays(selected_candidates, selected_vectors)
                source_windows = [segment_by_vector[index] for index in unique_indices]
                selected_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for window in source_windows:
                    selected_by_source[str(window.get("source_id") or "source-1")].append(window)
                source_records = []
                customer_source_root = store.customer_source_dir(str(manifest["customer"]["id"])).resolve()
                for source in package.get("sources") or [package["source"]]:
                    source_id = str(source.get("source_id") or "source-1")
                    if source_id not in selected_by_source:
                        continue
                    source_record = {
                        "source_id": source_id,
                        "customer_id": str(manifest["customer"]["id"]),
                        "meeting_id": source.get("meeting_id"),
                        "title": source.get("title"),
                        "audio_sha256": source["audio_sha256"],
                        "transcript_sha256": source["transcript_sha256"],
                        "selected_window_count": len(selected_by_source[source_id]),
                    }
                    audio_relative = _relative_source_path(customer_source_root, source["audio_path"])
                    transcript_relative = _relative_source_path(customer_source_root, source["transcript_path"])
                    if audio_relative:
                        source_record["audio_relative_path"] = audio_relative
                    if transcript_relative:
                        source_record["transcript_relative_path"] = transcript_relative
                    source_records.append(source_record)
                if person.get("current_version") is None:
                    profile_manifest = {
                        "model": package["model"],
                        "review_session_id": session_id,
                        "confirmation_mode": confirmation_mode,
                        "confirmation": confirmation,
                        "registration": {
                            "confirmed_at": now_iso(),
                            "source_audio_sha256": package["source"]["audio_sha256"],
                            "source_transcript_sha256": package["source"]["transcript_sha256"],
                            "source_recordings": source_records,
                            "source_windows": source_windows,
                        },
                        "statistics": stats,
                        "vector_provenance": _profile_vector_provenance(stats, source_windows),
                        "creation_mode": "enrollment",
                        "sources": [
                            {
                                "kind": "reviewed_initial_enrollment",
                                "meeting_id": item.get("meeting_id"),
                                "title": item.get("title"),
                            }
                            for item in source_records
                        ],
                    }
                    created.append(store.save_profile(person, arrays, profile_manifest))
                else:
                    candidate_id = f"cand-{safe_component(session_id)}-{safe_component(person_id)}"
                    candidate = store.save_candidate(
                        str(manifest["customer"]["id"]),
                        person_id,
                        session_id,
                        candidate_id,
                        selected_vectors,
                        {
                            "kind": "reviewed_profile_expansion",
                            "review_session_id": session_id,
                            "predicted_identity": person["name"],
                            "usable_seconds": float(sum(item.duration for item in selected_candidates)),
                            "windows": source_windows,
                            "source": package["source"],
                            "sources": package.get("sources") or [package["source"]],
                            "voiceprint": {"accept_threshold": package["calibration"]["accept_threshold"]},
                            "confirmation": {
                                **confirmation,
                                "mode": confirmation_mode,
                            },
                        },
                    )
                    candidates_created.append(candidate)
                    from .workflow import promote_candidate

                    created.append(promote_candidate(
                        store.resolve_storage_path(
                            str(candidate["npz_path"]).replace(".npz", ".json"), str(manifest["customer"]["id"])
                        ),
                        person_id,
                        actor,
                        store,
                    )["profile"])
                atomic_write_json(
                    journal_path,
                    {"session_id": session_id, "state": "committing", "before_pointers": before_pointers, "created": created},
                )
            result = {
                "schema_version": 1,
                "session_id": session_id,
                "status": "committed",
                "committed_at": now_iso(),
                "created_profiles": created,
                "promoted_candidates": [item["candidate_id"] for item in candidates_created],
                "validation": validation,
                "playback_count": store.audit_count(session_id, "review_segment_played"),
                "confirmation_mode": confirmation_mode,
            }
            result_path = Path(session["package_path"]).parent / "review_result.json"
            atomic_write_json(result_path, result)
            atomic_write_json(journal_path, {"session_id": session_id, "state": "committed", "result": str(result_path)})
            if pending_path.exists():
                pending_path.unlink()
            store.set_review_session(
                session_id,
                status="committed",
                result_path=result_path,
                actor=actor,
                client=client,
                event_type="review_commit_completed",
            )
            return result
        except Exception as exc:
            for person_id, version in before_pointers.items():
                try:
                    store.restore_profile_pointer(person_id, version)
                    with store.connect() as db:
                        db.execute(
                            "UPDATE profile_versions SET status = 'failed_commit' WHERE person_id = ? AND version > ?",
                            (person_id, int(version or 0)),
                        )
                except Exception:
                    pass
            atomic_write_json(
                journal_path,
                {"session_id": session_id, "state": "failed", "error": f"{type(exc).__name__}: {exc}", "before_pointers": before_pointers},
            )
            store.set_review_session(
                session_id,
                status="failed",
                error_message=f"{type(exc).__name__}: {exc}",
                actor=actor,
                client=client,
                event_type="review_commit_failed",
            )
            raise


def cleanup_review_artifacts(store: DataStore) -> list[str]:
    """Remove only pending vectors for cancelled or expired sessions."""
    expired = store.expire_review_sessions()
    cleaned: list[str] = []
    for session in store.list_review_sessions():
        if session["status"] not in {"cancelled", "expired"} or not session.get("package_path"):
            continue
        package_path = Path(session["package_path"])
        with np.errstate(all="ignore"):
            try:
                package = load_structured(package_path)
                pending = package_path.parent / str(package.get("pending_vector_file", "pending_vectors.npz"))
                if pending.exists():
                    pending.unlink()
                    cleaned.append(session["session_id"])
            except Exception:
                continue
    return cleaned + expired
