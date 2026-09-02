from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .constants import MODEL_CONFIG, PIPELINE_CONFIG, SCHEMA_VERSION
from .errors import StructuredError
from .reporting import write_outputs
from .review import (
    commit_review_session,
    create_enrollment_review,
    normalize_review_manifest,
    prepare_review_session,
    save_review_decision,
)
from .storage import DataStore
from .transcript import convert_to_wav, parse_transcript, read_window
from .util import (
    atomic_write_json,
    load_structured,
    normalize_text,
    now_iso,
    safe_component,
    sha256_file,
)
from .workflow import analyze_acoustic, analyze_finalize, validate_manifest


AGENT_API_VERSION = 1
ENGINE_SCHEMA_VERSION = 2


def capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "engine_schema": ENGINE_SCHEMA_VERSION,
        "agent_api": AGENT_API_VERSION,
        "browser_review": True,
        "feishu_quick_enrollment": True,
        "batch_enrollment": True,
        "analysis_resume": True,
        "no_user_visible_task_ids": True,
        "machine_readable_errors": True,
        "fixed_feishu_summary": True,
        "analysis_correction_isolated": True,
        "calibration_cache": True,
        "profile_revision": True,
        "model": MODEL_CONFIG,
    }


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pipeline_hash() -> str:
    return _canonical_hash(
        {
            "schema": SCHEMA_VERSION,
            "model": MODEL_CONFIG,
            "pipeline": PIPELINE_CONFIG,
        }
    )


def _meetings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("meetings") or [manifest["meeting"]])


def _source_fingerprint(manifest: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    sources = []
    for meeting in _meetings(manifest):
        audio = Path(str(meeting["audio"]))
        transcript = Path(str(meeting["transcript"]))
        sources.append(
            {
                "meeting_id": str(meeting["id"]),
                "title": str(meeting["title"]),
                "audio_sha256": sha256_file(audio),
                "transcript_sha256": sha256_file(transcript),
            }
        )
    stable = sorted(
        sources,
        key=lambda item: (
            item["audio_sha256"], item["transcript_sha256"], item["meeting_id"]
        ),
    )
    return _canonical_hash(stable), stable


def _cohort_fingerprint(
    store: DataStore, manifest: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    transcript_labels: set[str] = set()
    for meeting in _meetings(manifest):
        transcript_labels.update(
            item.label for item in parse_transcript(Path(str(meeting["transcript"])))
        )
    profiles = store.analysis_profiles(
        str(manifest["customer"]["id"]),
        manifest.get("attendees", []),
        transcript_labels,
    )
    rows = []
    for person_id, profile in profiles.items():
        rows.append(
            {
                "person_id": person_id,
                "version": int(profile["version"]),
                "npz_sha256": sha256_file(Path(profile["npz_path"])),
            }
        )
    rows.sort(key=lambda item: item["person_id"])
    return _canonical_hash(rows), rows


def _request_manifest(payload: dict[str, Any], *, batch: bool) -> dict[str, Any]:
    raw = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
    try:
        return normalize_review_manifest(raw) if batch else validate_manifest(raw)
    except StructuredError:
        raise
    except Exception as exc:
        raise StructuredError(
            "INVALID_MANIFEST", str(exc), details={"field": "manifest"}
        ) from exc


def _task_identity(
    operation: str,
    manifest: dict[str, Any],
    store: DataStore,
    intent: dict[str, Any],
) -> dict[str, Any]:
    store.upsert_manifest(manifest)
    source_hash, sources = _source_fingerprint(manifest)
    pipeline_hash = _pipeline_hash()
    cohort_hash, cohort = _cohort_fingerprint(store, manifest)
    manifest_scope = {
        "customer": manifest["customer"],
        "attendees": sorted(
            manifest.get("attendees", []),
            key=lambda item: (
                str(item.get("organization") or ""),
                str(item.get("id") or ""),
                str(item.get("name") or ""),
            ),
        ),
        "known_label_map": manifest.get("known_label_map", {}),
        "excluded_labels": sorted(manifest.get("excluded_labels", [])),
    }
    request_hash = _canonical_hash(
        {
            "operation": operation,
            "customer_id": manifest["customer"]["id"],
            "source_hash": source_hash,
            "pipeline_hash": pipeline_hash,
            "cohort_hash": cohort_hash,
            "manifest_scope": manifest_scope,
            "intent": intent,
        }
    )
    return {
        "source_hash": source_hash,
        "sources": sources,
        "pipeline_hash": pipeline_hash,
        "cohort_hash": cohort_hash,
        "cohort": cohort,
        "request_hash": request_hash,
    }


def _begin_task(
    operation: str,
    manifest: dict[str, Any],
    request: dict[str, Any],
    store: DataStore,
    intent: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    identity = _task_identity(operation, manifest, store, intent)
    task_id = f"task-{safe_component(operation, 'agent')}-{identity['request_hash'][:16]}"
    task, reused = store.create_or_reuse_task(
        task_id=task_id,
        operation=operation,
        customer_id=str(manifest["customer"]["id"]),
        request_hash=identity["request_hash"],
        source_hash=identity["source_hash"],
        pipeline_hash=identity["pipeline_hash"],
        cohort_hash=identity["cohort_hash"],
        external_request_id=str(request.get("external_request_id") or "") or None,
    )
    return task, reused, identity


def _task_response(task: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    checkpoint = task.get("checkpoint") or {}
    return {
        "ok": True,
        "task_id": task["task_id"],
        "operation": task["operation"],
        "status": task["status"],
        "phase": task["phase"],
        "reused": reused,
        **checkpoint,
    }


def _conversation_context(request: dict[str, Any]) -> dict[str, str]:
    raw = request.get("conversation") if isinstance(request.get("conversation"), dict) else {}
    result: dict[str, str] = {}
    for key in ("channel", "chat_id", "user_id", "trigger_message_id"):
        value = str(raw.get(key) or request.get(key) or "").strip()
        if value:
            result[key] = value
    return result


def _verify_confirmation_context(
    expected: dict[str, Any], supplied: dict[str, str]
) -> None:
    for key in ("channel", "chat_id", "user_id"):
        expected_value = str(expected.get(key) or "").strip()
        if expected_value and str(supplied.get(key) or "").strip() != expected_value:
            raise StructuredError(
                "CONFIRMATION_CONTEXT_MISMATCH",
                "确认消息不属于发起建库的会话或用户。",
                details={"field": key},
                retryable=False,
            )


def _failure_details(exc: Exception) -> tuple[str, dict[str, Any]]:
    if isinstance(exc, StructuredError):
        return exc.code, exc.details
    return type(exc).__name__.upper(), {"message": str(exc)}


def _target_person(package: dict[str, Any], request: dict[str, Any]) -> dict[str, Any] | None:
    raw = request.get("target_person")
    target_id = str(raw.get("person_id") or "") if isinstance(raw, dict) else ""
    target_name = (
        str(raw.get("name") or "").strip()
        if isinstance(raw, dict)
        else str(raw or "").strip()
    )
    people = [item for item in package.get("people", []) if item.get("person_id")]
    if target_id:
        return next((item for item in people if str(item["person_id"]) == target_id), None)
    if target_name:
        return next((item for item in people if str(item["name"]) == target_name), None)
    eligible = [item for item in people if item.get("scope") in {"customer", "staff"}]
    return eligible[0] if len(eligible) == 1 else None


def _quick_candidates(package: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    reasons: list[str] = []
    segment_by_id = {str(item["segment_id"]): item for item in package.get("segments", [])}
    for label in package.get("labels", []):
        if label.get("excluded_by_manifest"):
            continue
        clusters = [item for item in label.get("clusters", []) if item.get("segment_ids")]
        if label.get("risk") == "red" or len(clusters) != 1:
            reasons.append(f"{label.get('label')} 存在混合或多个声纹聚类")
            continue
        cluster = clusters[0]
        representative_ids = list(cluster.get("representative_segment_ids") or [])
        if not representative_ids:
            reasons.append(f"{label.get('label')} 没有可试听代表片段")
            continue
        representative = segment_by_id[representative_ids[0]]
        candidates.append(
            {
                "candidate_id": str(cluster["cluster_id"]),
                "display_label": str(label.get("label") or representative.get("display_label")),
                "meeting_title": str(representative.get("meeting_title") or "录音"),
                "transcript_label": str(representative.get("label") or ""),
                "timestamp": str(representative.get("timestamp") or "00:00"),
                "text": str(representative.get("text") or ""),
                "segment_ids": list(cluster["segment_ids"]),
                "representative_segment_id": str(representative["segment_id"]),
                "window_count": int(cluster.get("window_count") or 0),
                "usable_seconds": float(cluster.get("seconds") or 0.0),
            }
        )
    if len(candidates) > 3:
        reasons.append("可试听候选超过3组")
    return candidates, reasons


def _audition_bundle(
    package: dict[str, Any], candidates: list[dict[str, Any]], destination: Path
) -> Path:
    segment_by_id = {str(item["segment_id"]): item for item in package["segments"]}
    sources = package.get("sources") or [package["source"]]
    source_by_id = {
        str(item.get("source_id") or "source-1"): item for item in sources
    }
    sample_rate = int(PIPELINE_CONFIG["sample_rate"])
    parts: list[np.ndarray] = []
    with tempfile.TemporaryDirectory(prefix="speaker-agent-audition-") as temporary:
        wav_by_source: dict[str, Path] = {}
        for index, candidate in enumerate(candidates, start=1):
            segment = segment_by_id[candidate["representative_segment_id"]]
            source_id = str(segment.get("source_id") or "source-1")
            if source_id not in wav_by_source:
                wav_path = Path(temporary) / f"{source_id}.wav"
                convert_to_wav(Path(source_by_id[source_id]["audio_path"]), wav_path, sample_rate)
                wav_by_source[source_id] = wav_path
            # One, two, or three short tones audibly bind the following clip to A/B/C.
            tone_time = np.arange(int(sample_rate * 0.16), dtype=np.float32) / sample_rate
            tone = (0.12 * np.sin(2 * np.pi * 880 * tone_time)).astype(np.float32)
            short_gap = np.zeros(int(sample_rate * 0.10), dtype=np.float32)
            for _ in range(index):
                parts.extend([tone, short_gap])
            parts.append(np.zeros(int(sample_rate * 0.45), dtype=np.float32))
            with sf.SoundFile(wav_by_source[source_id]) as audio:
                wave = read_window(
                    audio,
                    float(segment["start"]),
                    float(segment["end"]),
                    sample_rate,
                )
            parts.append(np.asarray(wave, dtype=np.float32))
            parts.append(np.zeros(int(sample_rate * 0.8), dtype=np.float32))
    combined = np.concatenate(parts) if parts else np.empty(0, dtype=np.float32)
    if not len(combined):
        raise StructuredError("NO_AUDITION_AUDIO", "没有可生成试听的有效语音。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, combined, sample_rate, format="OGG", subtype="VORBIS")
    return destination


def _agent_enrollment_payload(
    package: dict[str, Any], request: dict[str, Any], review_url: str | None, destination: Path
) -> dict[str, Any]:
    target = _target_person(package, request)
    candidates, reasons = _quick_candidates(package)
    forced_web = str(request.get("review_mode") or "auto") == "web"
    quick = bool(target and 1 <= len(candidates) <= 3 and not reasons and not forced_web)
    if not quick:
        return {
            "review_mode": "web_full",
            "review_url": review_url,
            "reason": "；".join(reasons) or ("未明确唯一建库人员" if target is None else "用户指定网页审核"),
            "target_person": target,
            "candidate_count": len(candidates),
        }
    codes = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rendered = []
    for index, item in enumerate(candidates):
        rendered.append({**item, "code": codes[index]})
    audio_path = _audition_bundle(package, rendered, destination / "audition_bundle.ogg")
    lines = [
        f"准备为 **{target['name']}** 建立声纹，共有 {len(rendered)} 组候选语音：",
        "",
    ]
    for item in rendered:
        summary = item["text"].replace("\n", " ").strip()
        if len(summary) > 60:
            summary = summary[:60] + "…"
        lines.append(
            f"{item['code']}｜{item['meeting_title']}｜{item['timestamp']}｜{summary or item['transcript_label']}"
        )
    lines.extend(
        [
            "",
            "试听音频中，一声、两声、三声提示音分别对应 A、B、C。",
            "请直接说要保留的候选；系统回显后，回复或语音说“确认建库”即可生效。",
        ]
    )
    return {
        "review_mode": "feishu_quick",
        "review_url": review_url,
        "target_person": target,
        "audition_audio": str(audio_path),
        "candidates": rendered,
        "message_markdown": "\n".join(lines),
    }


def _agent_enroll_start_impl(
    request_path: Path,
    store: DataStore,
    *,
    base_url: str | None = None,
    download: bool = False,
) -> dict[str, Any]:
    request = load_structured(request_path.resolve())
    manifest = _request_manifest(request, batch=True)
    intent = {
        "target_person": request.get("target_person"),
        "review_mode": request.get("review_mode", "auto"),
    }
    task, reused, identity = _begin_task("enroll", manifest, request, store, intent)
    checkpoint = task.get("checkpoint") or {}
    if reused and checkpoint.get("agent_enrollment"):
        session_id = checkpoint.get("session_id")
        if session_id:
            session = store.get_review_session(str(session_id))
            if session["status"] == "committed":
                result = load_structured(Path(session["result_path"]))
                task = store.update_task(
                    task["task_id"],
                    status="completed",
                    phase="completed",
                    checkpoint={**checkpoint, "result": result},
                    result_path=Path(session["result_path"]),
                    completed=True,
                )
                return _task_response(task, reused=True)
        return _task_response(task, reused=True)
    owner = f"agent-enroll:{os.getpid()}"
    try:
        store.claim_task(task["task_id"], owner)
    except RuntimeError as exc:
        if str(exc) == "task_already_running":
            return _task_response(store.get_task(task["task_id"]), reused=True)
        raise
    task_dir = Path(task["artifact_dir"])
    manifest_path = task_dir / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    session_id = str(checkpoint.get("session_id") or "")
    review_url = checkpoint.get("review_url")
    if session_id:
        prior_session = store.get_review_session(session_id)
        if prior_session["status"] in {
            "failed",
            "cancelled",
            "expired",
            "source_changed",
        }:
            session_id = ""
            review_url = None
    if not session_id:
        created = create_enrollment_review(manifest_path, store, base_url=base_url)
        session_id = str(created["session_id"])
        review_url = created.get("review_url")
        checkpoint = {
            "session_id": session_id,
            "review_url": review_url,
            "source_hash": identity["source_hash"],
            "conversation": _conversation_context(request),
        }
        store.update_task(
            task["task_id"], status="running", phase="review_session_created", checkpoint=checkpoint
        )
    session = store.get_review_session(session_id)
    if session["status"] in {"queued", "preparing"}:
        job = store.claim_review_job_for_session(session_id)
        if job is None:
            waiting = store.update_task(
                task["task_id"],
                status="waiting_worker",
                phase="review_preparing",
                checkpoint=checkpoint,
            )
            return _task_response(waiting, reused=reused)
        try:
            session = prepare_review_session(
                session_id, store, download=download, job_id=str(job["job_id"])
            )
        except Exception as exc:
            store.finish_review_job(
                str(job["job_id"]),
                "failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            store.set_review_session(
                session_id,
                status="failed",
                error_message=f"{type(exc).__name__}: {exc}",
                event_type="review_prepare_failed",
            )
            raise
        if session["status"] == "review_required":
            store.finish_review_job(
                str(job["job_id"]),
                "completed",
                {"phase": "completed", "message": "审核包已准备完成"},
            )
        elif session["status"] in {"cancelled", "expired"}:
            store.finish_review_job(
                str(job["job_id"]),
                "cancelled",
                {"phase": "cancelled", "message": "任务已取消"},
            )
        else:
            store.finish_review_job(
                str(job["job_id"]),
                "failed",
                error=str(session.get("error_message") or session["status"]),
            )
    if session["status"] != "review_required":
        raise StructuredError(
            "ENROLLMENT_PREPARE_FAILED",
            str(session.get("error_message") or session["status"]),
            details={"session_id": session_id, "status": session["status"]},
            retryable=session["status"] == "failed",
        )
    package = load_structured(Path(session["package_path"]))
    agent_payload = _agent_enrollment_payload(
        package, request, review_url, Path(session["package_path"]).parent
    )
    agent_path = Path(session["package_path"]).parent / "agent_enrollment.json"
    atomic_write_json(agent_path, agent_payload)
    phase = (
        "waiting_chat_confirmation"
        if agent_payload["review_mode"] == "feishu_quick"
        else "waiting_web_review"
    )
    checkpoint = {
        **checkpoint,
        "agent_enrollment": str(agent_path),
        **agent_payload,
    }
    task = store.update_task(
        task["task_id"], status="waiting_confirmation", phase=phase, checkpoint=checkpoint
    )
    return _task_response(task, reused=reused)


def agent_enroll_start(
    request_path: Path,
    store: DataStore,
    *,
    base_url: str | None = None,
    download: bool = False,
) -> dict[str, Any]:
    try:
        return _agent_enroll_start_impl(
            request_path, store, base_url=base_url, download=download
        )
    except Exception as exc:
        try:
            request = load_structured(request_path.resolve())
            manifest = _request_manifest(request, batch=True)
            task, _, _ = _begin_task(
                "enroll",
                manifest,
                request,
                store,
                {
                    "target_person": request.get("target_person"),
                    "review_mode": request.get("review_mode", "auto"),
                },
            )
            code, details = _failure_details(exc)
            store.update_task(
                task["task_id"],
                status="failed",
                phase="enrollment_failed",
                error_code=code,
                error_details=details,
            )
        except Exception:
            pass
        raise


def _explicit_confirmation(value: str) -> bool:
    normalized = normalize_text(value)
    return any(
        phrase in normalized
        for phrase in ("确认建库", "确认创建声纹", "确认建立声纹", "确认声纹建库")
    )


def agent_enroll_confirm(request_path: Path, store: DataStore) -> dict[str, Any]:
    request = load_structured(request_path.resolve())
    task_id = str(request.get("task_id") or "")
    if not task_id:
        raise StructuredError("TASK_ID_REQUIRED", "OpenClaw必须在后台传入任务ID。")
    task = store.get_task(task_id)
    if task["operation"] != "enroll":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是首次建库任务。")
    if task["status"] == "completed":
        return _task_response(task, reused=True)
    confirmation_text = str(request.get("confirmation_text") or "")
    if not _explicit_confirmation(confirmation_text):
        raise StructuredError(
            "CONFIRMATION_REQUIRED",
            "需要用户明确回复或语音说“确认建库”。",
            retryable=True,
        )
    message_id = str(request.get("confirmation_message_id") or "").strip()
    if not message_id:
        raise StructuredError(
            "CONFIRMATION_MESSAGE_REQUIRED",
            "确认必须绑定到飞书消息ID；用户不需要输入技术ID。",
            retryable=True,
        )
    checkpoint = task.get("checkpoint") or {}
    conversation = _conversation_context(request)
    _verify_confirmation_context(checkpoint.get("conversation") or {}, conversation)
    agent_path = Path(str(checkpoint.get("agent_enrollment") or ""))
    if not agent_path.is_file():
        raise StructuredError("ENROLLMENT_REVIEW_MISSING", "快捷审核数据不存在。")
    agent_payload = load_structured(agent_path)
    if agent_payload.get("review_mode") != "feishu_quick":
        raise StructuredError("WEB_REVIEW_REQUIRED", "该任务必须在网页审核台完成。")
    raw_selected = request.get("included_candidates") or request.get("included_codes") or []
    if isinstance(raw_selected, str):
        raw_selected = [item.strip() for item in raw_selected.replace("，", ",").split(",")]
    selected_values = {str(item).strip().upper() for item in raw_selected if str(item).strip()}
    candidate_by_code = {str(item["code"]).upper(): item for item in agent_payload["candidates"]}
    candidate_by_id = {str(item["candidate_id"]).upper(): item for item in agent_payload["candidates"]}
    selected: list[dict[str, Any]] = []
    for value in selected_values:
        item = candidate_by_code.get(value) or candidate_by_id.get(value)
        if item and item not in selected:
            selected.append(item)
    if not selected and len(agent_payload["candidates"]) == 1:
        selected = [agent_payload["candidates"][0]]
    if not selected:
        raise StructuredError(
            "NO_ENROLLMENT_CANDIDATES_SELECTED",
            "至少需要保留一组候选语音。",
            retryable=True,
        )
    commit_hash = _canonical_hash(
        {
            "task_id": task_id,
            "target_person_id": agent_payload["target_person"]["person_id"],
            "selected_candidate_ids": sorted(item["candidate_id"] for item in selected),
            "confirmation_message_id": message_id,
        }
    )
    pending_commit = checkpoint.get("pending_commit") or {}
    if (
        pending_commit.get("confirmation_message_id") == message_id
        and pending_commit.get("commit_hash") != commit_hash
    ):
        raise StructuredError(
            "CONFIRMATION_MESSAGE_REPLAY_CONFLICT",
            "同一条确认消息不能对应不同的候选选择。",
            retryable=False,
        )
    session_id = str(checkpoint["session_id"])
    session = store.get_review_session(session_id)
    if session["status"] == "committed":
        result = load_structured(Path(session["result_path"]))
        task = store.update_task(
            task_id,
            status="completed",
            phase="completed",
            checkpoint={**checkpoint, "result": result},
            result_path=Path(session["result_path"]),
            completed=True,
        )
        return _task_response(task, reused=True)
    package = load_structured(Path(session["package_path"]))
    target_id = str(agent_payload["target_person"]["person_id"])
    assignments = {str(item["segment_id"]): "skip" for item in package["segments"]}
    for candidate in selected:
        for segment_id in candidate["segment_ids"]:
            assignments[str(segment_id)] = target_id
    decision = {
        "assignments": assignments,
        "new_people": [],
        "acknowledge_warnings": True,
        "confirmation": {
            "mode": "feishu_message_confirmed",
            "message_id": message_id,
            "user_id": str(request.get("user_id") or "") or None,
            "chat_id": str(request.get("chat_id") or "") or None,
            "confirmation_text": confirmation_text,
            "confirmed_at": now_iso(),
        },
    }
    checkpoint = {
        **checkpoint,
        "pending_commit": {
            "commit_hash": commit_hash,
            "confirmation_message_id": message_id,
            "selected_candidate_ids": sorted(item["candidate_id"] for item in selected),
        },
    }
    store.update_task(
        task_id,
        status="waiting_confirmation",
        phase="commit_pending",
        checkpoint=checkpoint,
    )
    existing_decision = session.get("decision") or {}
    existing_confirmation = existing_decision.get("confirmation") or {}
    if (
        existing_decision.get("assignments") == assignments
        and existing_confirmation.get("message_id") == message_id
    ):
        saved = session
    else:
        saved = save_review_decision(
            session_id,
            decision,
            int(session["revision"]),
            store,
            actor=str(request.get("user_id") or "") or None,
            client={"channel": "feishu", "message_id": message_id},
        )
    result = commit_review_session(
        session_id,
        int(saved["revision"]),
        store,
        actor=str(request.get("user_id") or "") or None,
        client={"channel": "feishu", "message_id": message_id},
    )
    if result.get("status") != "committed":
        raise StructuredError(
            "ENROLLMENT_SELECTION_INVALID",
            "所选语音尚不满足建库要求。",
            details={
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
            },
            retryable=True,
        )
    result_path = Path(store.get_review_session(session_id)["result_path"])
    audition = agent_payload.get("audition_audio")
    if audition:
        Path(str(audition)).unlink(missing_ok=True)
    checkpoint = {
        **checkpoint,
        "selected_candidates": [item["candidate_id"] for item in selected],
        "confirmation_message_id": message_id,
        "commit_hash": commit_hash,
        "result": result,
    }
    task = store.update_task(
        task_id,
        status="completed",
        phase="completed",
        checkpoint=checkpoint,
        result_path=result_path,
        completed=True,
    )
    return _task_response(task, reused=False)


def _agent_analyze_start_impl(
    request_path: Path, store: DataStore, *, download: bool = False
) -> dict[str, Any]:
    request = load_structured(request_path.resolve())
    manifest = _request_manifest(request, batch=False)
    task, reused, identity = _begin_task("analyze", manifest, request, store, {})
    checkpoint = task.get("checkpoint") or {}
    if reused and checkpoint.get("acoustic"):
        return _task_response(task, reused=True)
    owner = f"agent-analyze:{os.getpid()}"
    try:
        store.claim_task(task["task_id"], owner)
    except RuntimeError as exc:
        if str(exc) == "task_already_running":
            return _task_response(store.get_task(task["task_id"]), reused=True)
        raise
    task_dir = Path(task["artifact_dir"])
    manifest_path = task_dir / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    store.update_task(task["task_id"], status="running", phase="acoustic_analysis")
    acoustic = analyze_acoustic(manifest_path, store, download=download)
    semantic_request = {
        "schema_version": 1,
        "task_id": task["task_id"],
        "instructions": {
            "context": "仅提取能够在转写索引中按标签、时间戳和原文回查的身份线索。",
            "viewpoints": "覆盖每个required_labels；有意义但不足以提炼观点时输出发言摘要。",
        },
        "transcript_index": acoustic["transcript_index"],
        "candidate_people": load_structured(Path(acoustic["acoustic_bundle"]))[
            "candidate_people"
        ],
        "required_labels": list(
            load_structured(Path(acoustic["transcript_index"])).get("labels", {})
        ),
        "response_schema": {
            "context": {"schema_version": 1, "items": []},
            "viewpoints": {
                "schema_version": 1,
                "items": [],
                "non_substantive_labels": [],
            },
        },
    }
    semantic_path = task_dir / "semantic_request.json"
    atomic_write_json(semantic_path, semantic_request)
    checkpoint = {
        "source_hash": identity["source_hash"],
        "cohort_hash": identity["cohort_hash"],
        "conversation": _conversation_context(request),
        "acoustic": acoustic,
        "semantic_request": str(semantic_path),
    }
    task = store.update_task(
        task["task_id"],
        status="awaiting_semantic",
        phase="awaiting_semantic",
        checkpoint=checkpoint,
    )
    return _task_response(task, reused=reused)


def agent_analyze_start(
    request_path: Path, store: DataStore, *, download: bool = False
) -> dict[str, Any]:
    try:
        return _agent_analyze_start_impl(request_path, store, download=download)
    except Exception as exc:
        try:
            request = load_structured(request_path.resolve())
            manifest = _request_manifest(request, batch=False)
            task, _, _ = _begin_task("analyze", manifest, request, store, {})
            code, details = _failure_details(exc)
            store.update_task(
                task["task_id"],
                status="failed",
                phase="acoustic_analysis_failed",
                error_code=code,
                error_details=details,
            )
        except Exception:
            pass
        raise


def _agent_analyze_complete_impl(
    task_id: str, semantic_response_path: Path, store: DataStore
) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task["operation"] != "analyze":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是后续录音分析任务。")
    if task["status"] == "completed":
        return _task_response(task, reused=True)
    checkpoint = task.get("checkpoint") or {}
    acoustic = checkpoint.get("acoustic")
    if not isinstance(acoustic, dict):
        raise StructuredError(
            "ACOUSTIC_CHECKPOINT_MISSING", "声学分析检查点不存在，请重新启动分析。", retryable=True
        )
    response = load_structured(semantic_response_path.resolve())
    context = response.get("context") or {"schema_version": 1, "items": []}
    viewpoints = response.get("viewpoints")
    if not isinstance(viewpoints, dict):
        raise StructuredError(
            "VIEWPOINTS_REQUIRED", "语义响应必须包含viewpoints对象。", retryable=True
        )
    owner = f"agent-finalize:{os.getpid()}"
    try:
        store.claim_task(task_id, owner)
    except RuntimeError as exc:
        if str(exc) == "task_already_running":
            return _task_response(store.get_task(task_id), reused=True)
        raise
    task_dir = Path(task["artifact_dir"])
    context_path = task_dir / "context.json"
    viewpoints_path = task_dir / "viewpoints.json"
    atomic_write_json(context_path, context)
    atomic_write_json(viewpoints_path, viewpoints)
    semantic_hash = _canonical_hash({"context": context, "viewpoints": viewpoints})
    store.update_task(
        task_id,
        status="running",
        phase="semantic_validation",
        semantic_hash=semantic_hash,
    )
    try:
        result = analyze_finalize(
            Path(acoustic["run_dir"]), context_path, viewpoints_path, store
        )
    except StructuredError as exc:
        store.update_task(
            task_id,
            status="awaiting_semantic",
            phase="semantic_revision_required",
            checkpoint={**checkpoint, "semantic_response": str(semantic_response_path.resolve())},
            semantic_hash=semantic_hash,
            error_code=exc.code,
            error_details=exc.details,
        )
        raise
    result_path = Path(result["outputs"]["json"])
    checkpoint = {
        **checkpoint,
        "semantic_response": str(semantic_response_path.resolve()),
        "result": result,
        "feishu_summary": result["outputs"]["feishu_summary"],
        "detailed_report": result["outputs"]["report"],
    }
    task = store.update_task(
        task_id,
        status="completed",
        phase="completed",
        checkpoint=checkpoint,
        result_path=result_path,
        semantic_hash=semantic_hash,
        completed=True,
    )
    return _task_response(task, reused=False)


def agent_analyze_complete(
    task_id: str, semantic_response_path: Path, store: DataStore
) -> dict[str, Any]:
    try:
        return _agent_analyze_complete_impl(task_id, semantic_response_path, store)
    except StructuredError:
        raise
    except Exception as exc:
        code, details = _failure_details(exc)
        try:
            store.update_task(
                task_id,
                status="failed",
                phase="finalization_failed",
                error_code=code,
                error_details=details,
            )
        except Exception:
            pass
        raise


def agent_task_status(task_id: str, store: DataStore) -> dict[str, Any]:
    task = store.get_task(task_id)
    checkpoint = task.get("checkpoint") or {}
    session_id = checkpoint.get("session_id")
    if task["operation"] == "enroll" and session_id:
        session = store.get_review_session(str(session_id))
        if session["status"] == "committed" and task["status"] != "completed":
            result = load_structured(Path(session["result_path"]))
            task = store.update_task(
                task_id,
                status="completed",
                phase="completed",
                checkpoint={**checkpoint, "result": result},
                result_path=Path(session["result_path"]),
                completed=True,
            )
    return _task_response(task, reused=True)


def agent_analysis_correct(
    task_id: str, corrections_path: Path, store: DataStore
) -> dict[str, Any]:
    """Create a corrected report version without creating or promoting voiceprints."""
    task = store.get_task(task_id)
    checkpoint = task.get("checkpoint") or {}
    result = checkpoint.get("result") or {}
    outputs = result.get("outputs") or {}
    final_path = Path(str(outputs.get("json") or task.get("result_path") or ""))
    if not final_path.is_file():
        raise StructuredError("ANALYSIS_RESULT_MISSING", "分析结果不存在，无法纠正。")
    correction = load_structured(corrections_path.resolve())
    message_id = str(correction.get("confirmation_message_id") or "").strip()
    if not message_id:
        raise StructuredError(
            "CORRECTION_MESSAGE_REQUIRED", "人工纠正必须绑定到飞书消息ID。", retryable=True
        )
    _verify_confirmation_context(
        checkpoint.get("conversation") or {}, _conversation_context(correction)
    )
    correction_input_hash = _canonical_hash(
        {
            "task_id": task_id,
            "confirmation_message_id": message_id,
            "corrections": correction.get("corrections") or [],
        }
    )
    payload = load_structured(final_path)
    rows = [dict(item) for item in payload["results"]]
    by_label = {str(item["transcript_label"]): item for item in rows}
    people = {str(item["person_id"]): item for item in payload["candidate_people"]}
    applied = []
    for raw in correction.get("corrections", []):
        label = str(raw.get("transcript_label") or "")
        row = by_label.get(label)
        if row is None:
            raise StructuredError(
                "UNKNOWN_TRANSCRIPT_LABEL",
                f"转写标签不存在：{label}",
                details={"transcript_label": label},
                retryable=True,
            )
        person_id = str(raw.get("person_id") or "") or None
        identity = str(raw.get("identity") or "").strip()
        if person_id:
            if person_id not in people:
                raise StructuredError(
                    "UNKNOWN_PERSON", f"候选人员不存在：{person_id}", retryable=True
                )
            identity = str(people[person_id]["name"])
        if not identity:
            raise StructuredError(
                "CORRECTION_IDENTITY_REQUIRED", f"{label} 缺少纠正身份。", retryable=True
            )
        row.update(
            final_person_id=person_id,
            final_identity_key=f"person:{person_id}" if person_id else f"human:{identity}",
            final_identity=identity,
            final_status="人工纠正（仅本次报告）",
            final_confidence="人工确认",
            decision_basis="human_report_correction",
            needs_review=False,
            human_correction={
                "message_id": message_id,
                "user_id": correction.get("user_id"),
                "corrected_at": now_iso(),
            },
        )
        applied.append({"transcript_label": label, "identity": identity})
    if not applied:
        raise StructuredError("NO_CORRECTIONS", "没有提供需要纠正的说话人标签。")
    acoustic = checkpoint.get("acoustic") or {}
    bundle = load_structured(Path(acoustic["acoustic_bundle"]))
    context = load_structured(Path(acoustic["run_dir"]) / "validated_context.json")
    viewpoints = load_structured(Path(acoustic["run_dir"]) / "validated_viewpoints.json")
    correction_id = f"correction-{safe_component(message_id, 'message')}"
    correction_dir = Path(acoustic["run_dir"]) / "corrections" / correction_id
    correction_dir.mkdir(parents=True, exist_ok=True)
    correction_record_path = correction_dir / "correction.json"
    if correction_record_path.is_file():
        existing = load_structured(correction_record_path)
        if existing.get("input_hash") == correction_input_hash:
            return {"ok": True, "reused": True, **existing}
        raise StructuredError(
            "CORRECTION_MESSAGE_REPLAY_CONFLICT",
            "同一条纠正消息不能产生两份不同的报告修改。",
            retryable=False,
        )
    corrected_outputs = write_outputs(
        correction_dir,
        bundle,
        rows,
        context.get("items", []),
        payload.get("context", {}).get("rejected", []),
        viewpoints.get("items", []),
        viewpoints.get("non_substantive_labels", []),
        payload.get("viewpoints", {}).get("rejected", []),
        payload.get("profile_candidates", []),
    )
    correction_record = {
        "schema_version": 1,
        "task_id": task_id,
        "correction_id": correction_id,
        "confirmation_message_id": message_id,
        "input_hash": correction_input_hash,
        "applied": applied,
        "outputs": corrected_outputs,
        "voiceprint_changed": False,
        "created_at": now_iso(),
    }
    atomic_write_json(correction_record_path, correction_record)
    store.update_task(
        task_id,
        checkpoint={
            **checkpoint,
            "latest_correction": correction_record,
            "profile_expansion_requires_separate_confirmation": True,
        },
    )
    return {"ok": True, "reused": False, **correction_record}
