from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .constants import MODEL_CONFIG, PIPELINE_CONFIG
from .embedding import EmbeddingEngine, normalize
from .errors import StructuredError
from .matching import build_profile_arrays, calibrate_profiles, match_label
from .reporting import write_outputs
from .resolution import (
    deterministic_named_label_context,
    ensure_viewpoint_coverage,
    resolve_results,
    validate_context,
    validate_viewpoints,
)
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
    load_structured,
    now_iso,
    require_absolute_file,
    safe_component,
    sha256_file,
    utc_compact,
)


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    if int(raw.get("schema_version", 0)) != 1:
        raise ValueError("manifest.schema_version must be 1")
    customer = raw.get("customer") or {}
    meeting = raw.get("meeting") or {}
    if not str(customer.get("id", "")).strip() or not str(customer.get("name", "")).strip():
        raise ValueError("customer.id and customer.name are required")
    for field in ["id", "title", "audio", "transcript"]:
        if not str(meeting.get(field, "")).strip():
            raise ValueError(f"meeting.{field} is required")
    audio_path = require_absolute_file(str(meeting["audio"]), "meeting.audio")
    transcript_path = require_absolute_file(str(meeting["transcript"]), "meeting.transcript")
    attendees = raw.get("attendees") or []
    if not isinstance(attendees, list) or not attendees:
        raise ValueError("At least one attendee is required")
    normalized = json.loads(json.dumps(raw, ensure_ascii=False))
    normalized["meeting"]["audio"] = str(audio_path)
    normalized["meeting"]["transcript"] = str(transcript_path)
    normalized.setdefault("known_label_map", {})
    normalized.setdefault("excluded_labels", [])
    return normalized


def load_manifest(path: Path) -> dict[str, Any]:
    return validate_manifest(load_structured(path.resolve()))


def make_run_id(meeting_id: str, kind: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    return f"{safe_component(meeting_id, 'meeting')}-{kind}-{utc_compact()}-{suffix}"


def audio_duration(wav_path: Path) -> float:
    with sf.SoundFile(wav_path) as audio:
        return len(audio) / audio.samplerate


def customer_upsert(manifest_path: Path, store: DataStore) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    people = store.upsert_manifest(manifest)
    return {
        "customer": manifest["customer"],
        "people": list(people.values()),
        "customer_path": str(store.customer_dir(manifest["customer"]["id"])),
    }


def enrollment_prepare(manifest_path: Path, store: DataStore) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    attendees = store.upsert_manifest(manifest)
    customer_id = manifest["customer"]["id"]
    meeting = manifest["meeting"]
    enrollment_id = make_run_id(meeting["id"], "enroll")
    enrollment_dir = store.enrollment_dir(customer_id, enrollment_id)
    audio_path = Path(meeting["audio"])
    transcript_path = Path(meeting["transcript"])
    with tempfile.TemporaryDirectory(prefix="speaker-enroll-prepare-") as temporary:
        wav_path = Path(temporary) / "meeting.wav"
        convert_to_wav(audio_path, wav_path, int(PIPELINE_CONFIG["sample_rate"]))
        utterances = parse_transcript(transcript_path, audio_duration(wav_path))
        candidates = build_candidates(wav_path, utterances, PIPELINE_CONFIG)

    labels: list[str] = []
    for row in utterances:
        if row.label not in labels:
            labels.append(row.label)
    known = manifest.get("known_label_map", {})
    label_details: list[dict[str, Any]] = []
    for label in labels:
        label_candidates = [item for item in candidates if item.label == label]
        proposed = None
        source = None
        if label in known and known[label] in attendees:
            proposed = known[label]
            source = "known_label_map"
        elif label in attendees:
            proposed = label
            source = "exact_named_label"
        label_details.append(
            {
                "label": label,
                "proposed_person": proposed,
                "proposal_source": source,
                "candidate_windows": len(label_candidates),
                "candidate_seconds": float(sum(item.duration for item in label_candidates)),
                "mean_quality": (
                    float(np.mean([item.quality for item in label_candidates]))
                    if label_candidates
                    else None
                ),
                "eligible_by_quantity": (
                    len(label_candidates) >= int(PIPELINE_CONFIG["minimum_profile_windows"])
                    and sum(item.duration for item in label_candidates)
                    >= float(PIPELINE_CONFIG["minimum_profile_seconds"])
                ),
            }
        )
    draft = {
        "schema_version": 1,
        "enrollment_id": enrollment_id,
        "status": "awaiting_confirmation",
        "created_at": now_iso(),
        "manifest": manifest,
        "source": {
            "audio_sha256": sha256_file(audio_path),
            "transcript_sha256": sha256_file(transcript_path),
        },
        "attendees": list(attendees.values()),
        "labels": label_details,
        "transcript_index": transcript_index(utterances),
        "candidate_windows": [item.to_dict() for item in candidates],
        "confirmation_required": True,
    }
    draft_path = enrollment_dir / "enrollment_draft.json"
    atomic_write_json(draft_path, draft)
    return {
        "status": draft["status"],
        "enrollment_id": enrollment_id,
        "draft": str(draft_path),
        "customer_data": str(store.customer_dir(customer_id)),
        "labels": label_details,
    }


def _candidate_from_dict(value: dict[str, Any]) -> Candidate:
    return Candidate(**value)


def _model_manifest(engine: EmbeddingEngine) -> dict[str, Any]:
    return {
        "id": MODEL_CONFIG["id"],
        "revision": MODEL_CONFIG["revision"],
        "embedding_size": MODEL_CONFIG["embedding_size"],
        "source_revision": MODEL_CONFIG["source_revision"],
        "checkpoint_sha256": engine.checkpoint_sha256,
        "device": "cpu",
    }


def _calibration_for_profiles(
    store: DataStore,
    customer_id: str,
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cohort = sorted(f"{person_id}:v{profile['version']}" for person_id, profile in profiles.items())
    fingerprint = {
        "calibration_schema": 1,
        "model": MODEL_CONFIG,
        "threshold_defaults": {
            "accept": PIPELINE_CONFIG["default_accept_threshold"],
            "margin": PIPELINE_CONFIG["default_margin_threshold"],
            "minimum_margin_floor": PIPELINE_CONFIG["minimum_margin_floor"],
        },
        "profiles": [
            {
                "person_id": person_id,
                "version": int(profile["version"]),
                "npz_sha256": sha256_file(Path(profile["npz_path"])),
            }
            for person_id, profile in sorted(profiles.items())
        ],
    }
    cohort_hash = hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]
    cache_dir = store.customer_dir(customer_id) / "calibrations"
    cache_path = cache_dir / f"{cohort_hash}.json"
    if cache_path.is_file():
        cached = load_structured(cache_path)
        required = {
            "accept_threshold",
            "margin_threshold",
            "source",
            "cohort",
            "cohort_hash",
            "fingerprint",
        }
        if (
            required.issubset(cached)
            and cached.get("cohort") == cohort
            and cached.get("cohort_hash") == cohort_hash
            and cached.get("fingerprint") == fingerprint
        ):
            return {**cached, "cache_hit": True, "cache_path": str(cache_path)}
    calibration = calibrate_profiles(profiles)
    payload = {
        **calibration,
        "cohort": cohort,
        "cohort_hash": cohort_hash,
        "fingerprint": fingerprint,
        "cache_hit": False,
        "cache_path": str(cache_path),
    }
    atomic_write_json(cache_path, payload)
    return payload


def _group_enrollment_candidates(
    resolved_mapping: dict[str, dict[str, Any]],
    candidates: list[Candidate],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for label, person in resolved_mapping.items():
        item = grouped.setdefault(
            person["person_id"],
            {"person": person, "labels": [], "candidates": []},
        )
        item["labels"].append(label)
    for candidate in candidates:
        person = resolved_mapping.get(candidate.label)
        if person is not None:
            grouped[person["person_id"]]["candidates"].append(candidate)
    return list(grouped.values())


def enrollment_commit(
    draft_path: Path,
    confirmation_path: Path,
    store: DataStore,
    download: bool = False,
) -> dict[str, Any]:
    draft = load_structured(draft_path.resolve())
    confirmation = load_structured(confirmation_path.resolve())
    if draft.get("status") != "awaiting_confirmation":
        raise ValueError("Enrollment draft is not awaiting confirmation")
    if int(confirmation.get("schema_version", 0)) != 1:
        raise ValueError("confirmation.schema_version must be 1")
    confirmed_by = str(confirmation.get("confirmed_by", "")).strip()
    label_map = confirmation.get("label_map") or {}
    if not confirmed_by or not isinstance(label_map, dict) or not label_map:
        raise ValueError("confirmed_by and a non-empty label_map are required")
    manifest = validate_manifest(draft["manifest"])
    customer_id = manifest["customer"]["id"]
    attendees = store.upsert_manifest(manifest)
    valid_labels = {item["label"] for item in draft["labels"]}
    excluded = set(manifest.get("excluded_labels", [])) | set(
        confirmation.get("excluded_labels", [])
    )
    resolved_mapping: dict[str, dict[str, Any]] = {}
    for label, name in label_map.items():
        if label not in valid_labels:
            raise ValueError(f"Unknown transcript label in confirmation: {label}")
        if label in excluded:
            raise ValueError(f"A label cannot be mapped and excluded: {label}")
        resolved_mapping[label] = store.resolve_attendee_name(customer_id, attendees, str(name))
    audio_path = Path(manifest["meeting"]["audio"])
    transcript_path = Path(manifest["meeting"]["transcript"])
    if draft["source"]["audio_sha256"] != sha256_file(audio_path):
        raise RuntimeError("Enrollment audio changed after confirmation draft was created")
    if draft["source"]["transcript_sha256"] != sha256_file(transcript_path):
        raise RuntimeError("Enrollment transcript changed after confirmation draft was created")

    engine = EmbeddingEngine(download=download)
    prepared: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="speaker-enroll-commit-") as temporary:
        wav_path = Path(temporary) / "meeting.wav"
        convert_to_wav(audio_path, wav_path, int(PIPELINE_CONFIG["sample_rate"]))
        utterances = parse_transcript(transcript_path, audio_duration(wav_path))
        all_candidates = build_candidates(wav_path, utterances, PIPELINE_CONFIG)
        for group in _group_enrollment_candidates(resolved_mapping, all_candidates):
            person = group["person"]
            labels = group["labels"]
            candidates = group["candidates"]
            candidates = select_temporally_diverse(
                candidates,
                int(PIPELINE_CONFIG["max_enrollment_candidates_per_person"]),
            )
            try:
                if len(candidates) < int(PIPELINE_CONFIG["minimum_profile_windows"]):
                    raise RuntimeError(
                        f"Only {len(candidates)} quality windows; at least 6 are required"
                    )
                embeddings = engine.embed_candidates(wav_path, candidates)
                arrays, profile_stats = build_profile_arrays(candidates, embeddings)
                prepared.append(
                    {
                        "labels": labels,
                        "person": person,
                        "arrays": arrays,
                        "profile_stats": profile_stats,
                        "all_embeddings": embeddings,
                        "all_candidates": candidates,
                    }
                )
            except Exception as exc:
                skipped.append(
                    {
                        "labels": labels,
                        "person_id": person["person_id"],
                        "name": person["name"],
                        "reason": str(exc),
                    }
                )

    created: list[dict[str, Any]] = []
    staged: list[dict[str, Any]] = []
    enrollment_id = draft["enrollment_id"]
    for item in prepared:
        person = store.get_person(item["person"]["person_id"])
        if person.get("current_version") is not None:
            candidate_id = (
                f"cand-{safe_component(enrollment_id)}-{safe_component(person['person_id'])}"
            )
            payload = store.save_candidate(
                customer_id,
                person["person_id"],
                enrollment_id,
                candidate_id,
                item["all_embeddings"],
                {
                    "kind": "confirmed_enrollment_for_existing_profile",
                    "predicted_identity": person["name"],
                    "transcript_label": item["labels"][0],
                    "transcript_labels": item["labels"],
                    "usable_seconds": float(
                        sum(candidate.duration for candidate in item["all_candidates"])
                    ),
                    "windows": [candidate.to_dict() for candidate in item["all_candidates"]],
                    "source": draft["source"],
                    "meeting": manifest["meeting"],
                    "confirmation": {
                        "confirmed_by": confirmed_by,
                        "confirmation_file": str(confirmation_path.resolve()),
                    },
                },
            )
            staged.append(payload)
            continue
        profile_manifest = {
            "model": _model_manifest(engine),
            "registration": {
                "enrollment_id": enrollment_id,
                "source_label": item["labels"][0],
                "source_labels": item["labels"],
                "audio": str(audio_path),
                "transcript": str(transcript_path),
                **draft["source"],
                "confirmed_by": confirmed_by,
                "confirmation_file": str(confirmation_path.resolve()),
            },
            "statistics": item["profile_stats"],
            "sources": [
                {
                    "kind": "initial_enrollment",
                    "meeting_id": manifest["meeting"]["id"],
                    "audio_sha256": draft["source"]["audio_sha256"],
                }
            ],
        }
        created.append(store.save_profile(person, item["arrays"], profile_manifest))

    profiles = store.analysis_profiles(
        customer_id,
        manifest.get("attendees", []),
        [item["label"] for item in draft["labels"]],
    )
    calibration = _calibration_for_profiles(store, customer_id, profiles)
    result = {
        "schema_version": 1,
        "enrollment_id": enrollment_id,
        "status": "committed",
        "confirmed_by": confirmed_by,
        "confirmed_mapping": {
            label: {
                "person_id": person["person_id"],
                "name": person["name"],
                "role": person["role"],
                "scope": person["scope"],
            }
            for label, person in resolved_mapping.items()
        },
        "excluded_labels": sorted(excluded),
        "created_profiles": created,
        "existing_profiles_staged_as_candidates": staged,
        "skipped_profiles": skipped,
        "calibration": calibration,
        "model": _model_manifest(engine),
        "committed_at": now_iso(),
    }
    enrollment_dir = draft_path.resolve().parent
    result_path = enrollment_dir / "enrollment_result.json"
    atomic_write_json(result_path, result)
    draft["status"] = "committed"
    draft["committed_at"] = now_iso()
    draft["result"] = str(result_path)
    atomic_write_json(draft_path.resolve(), draft)
    return {**result, "result_path": str(result_path)}


def analyze_acoustic(
    manifest_path: Path,
    store: DataStore,
    download: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    store.upsert_manifest(manifest)
    customer_id = manifest["customer"]["id"]
    meeting = manifest["meeting"]
    run_id = make_run_id(meeting["id"], "analysis")
    run_dir = store.create_run(customer_id, meeting["id"], run_id, "analysis")
    audio_path = Path(meeting["audio"])
    transcript_path = Path(meeting["transcript"])
    try:
        with tempfile.TemporaryDirectory(prefix="speaker-analysis-") as temporary:
            wav_path = Path(temporary) / "meeting.wav"
            convert_to_wav(audio_path, wav_path, int(PIPELINE_CONFIG["sample_rate"]))
            utterances = parse_transcript(transcript_path, audio_duration(wav_path))
            index = transcript_index(utterances)
            profiles = store.analysis_profiles(
                customer_id,
                manifest.get("attendees", []),
                index["labels"].keys(),
            )
            calibration = _calibration_for_profiles(store, customer_id, profiles)
            engine = EmbeddingEngine(download=download) if profiles else None
            all_candidates = build_candidates(wav_path, utterances, PIPELINE_CONFIG)
            results: list[dict[str, Any]] = []
            vector_dir = run_dir / "candidate_vectors"
            labels = list(index["labels"])
            for label in labels:
                candidates = [item for item in all_candidates if item.label == label]
                candidates = select_temporally_diverse(
                    candidates,
                    int(PIPELINE_CONFIG["max_test_windows_per_label"]),
                )
                embeddings = (
                    engine.embed_candidates(wav_path, candidates)
                    if engine is not None
                    else np.empty((0, 192), dtype=np.float32)
                )
                match = match_label(candidates, embeddings, profiles, calibration)
                vector_path = vector_dir / f"{safe_component(label, 'speaker')}.npz"
                atomic_save_npz(
                    vector_path,
                    embeddings=embeddings,
                    quality_weights=np.asarray(
                        [max(0.05, item.quality) for item in candidates], dtype=np.float32
                    ),
                )
                results.append(
                    {
                        "transcript_label": label,
                        **match,
                        "candidate_windows": [item.to_dict() for item in candidates],
                        "candidate_vector_path": str(vector_path),
                    }
                )
        model_manifest = (
            _model_manifest(engine)
            if engine is not None
            else {
                "id": MODEL_CONFIG["id"],
                "revision": MODEL_CONFIG["revision"],
                "embedding_size": 192,
                "device": "cpu",
                "not_loaded_reason": "no candidate profiles",
            }
        )
        candidate_people = [
            {
                "person_id": person_id,
                "name": profile["person"]["name"],
                "role": profile["person"]["role"],
                "scope": profile["person"]["scope"],
                "customer_id": profile["person"]["customer_id"],
                "profile_version": profile["version"],
            }
            for person_id, profile in profiles.items()
        ]
        bundle = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "awaiting_semantic_evidence",
            "customer": manifest["customer"],
            "meeting": manifest["meeting"],
            "source": {
                "audio_sha256": sha256_file(audio_path),
                "transcript_sha256": sha256_file(transcript_path),
            },
            "model": model_manifest,
            "calibration": calibration,
            "candidate_people": candidate_people,
            "acoustic_results": results,
            "created_at": now_iso(),
        }
        bundle_path = run_dir / "acoustic_bundle.json"
        index_path = run_dir / "transcript_index.json"
        context_template = run_dir / "context_evidence.template.json"
        viewpoints_template = run_dir / "viewpoints.template.json"
        atomic_write_json(bundle_path, bundle)
        atomic_write_json(index_path, index)
        atomic_write_json(
            context_template,
            {
                "schema_version": 1,
                "instructions": (
                    "Extract only transcript-grounded identity evidence. Explicitly named "
                    "people may be outside the voiceprint cohort; role semantics cannot add one."
                ),
                "candidate_people": candidate_people,
                "items": [],
            },
        )
        atomic_write_json(
            viewpoints_template,
            {
                "schema_version": 1,
                "instructions": (
                    "Cover every required label with at least one grounded viewpoint or "
                    "speech summary. Use non_substantive_labels only for grounded background, "
                    "incidental speech, or noise. Empty coverage cannot be finalized."
                ),
                "required_labels": list(index["labels"]),
                "items": [],
                "non_substantive_labels": [],
            },
        )
        store.update_run(run_id, "awaiting_semantic_evidence")
        summaries = [
            {
                key: value
                for key, value in row.items()
                if key not in {"candidate_windows", "candidate_vector_path", "scores"}
            }
            for row in results
        ]
        return {
            "status": bundle["status"],
            "run_id": run_id,
            "run_dir": str(run_dir),
            "acoustic_bundle": str(bundle_path),
            "transcript_index": str(index_path),
            "context_template": str(context_template),
            "viewpoints_template": str(viewpoints_template),
            "results": summaries,
        }
    except Exception:
        store.update_run(run_id, "failed")
        raise


def analyze_finalize(
    run_dir: Path,
    context_path: Path | None,
    viewpoints_path: Path | None,
    store: DataStore,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    bundle = load_structured(run_dir / "acoustic_bundle.json")
    index = load_structured(run_dir / "transcript_index.json")
    if viewpoints_path is None:
        raise StructuredError(
            "VIEWPOINTS_REQUIRED",
            "必须提供覆盖全部转写标签的观点数据。",
            details={"required_labels": list(index.get("labels", {}))},
            retryable=True,
        )
    context_payload = (
        load_structured(context_path.resolve())
        if context_path is not None
        else {"schema_version": 1, "items": []}
    )
    viewpoints_payload = load_structured(viewpoints_path.resolve())
    valid_context, rejected_context = validate_context(
        context_payload, index, bundle["candidate_people"]
    )
    valid_context.extend(
        deterministic_named_label_context(index, bundle["candidate_people"])
    )
    valid_viewpoints, non_substantive_labels, rejected_viewpoints = validate_viewpoints(
        viewpoints_payload, index
    )
    ensure_viewpoint_coverage(index, valid_viewpoints, non_substantive_labels)
    resolved = resolve_results(
        bundle["acoustic_results"], valid_context, bundle["candidate_people"]
    )
    customer_id = bundle["customer"]["id"]
    run_id = bundle["run_id"]
    created_candidates: list[dict[str, Any]] = []
    for row in resolved:
        if (
            row["final_status"] != "声纹已匹配"
            or row["final_confidence"] not in {"高", "中"}
            or row.get("voice_context_conflict")
            or row["usable_seconds"] < float(PIPELINE_CONFIG["candidate_minimum_seconds"])
            or not row.get("final_person_id")
        ):
            continue
        vector_path = Path(row["candidate_vector_path"])
        with np.load(vector_path, allow_pickle=False) as arrays:
            vectors = np.asarray(arrays["embeddings"], dtype=np.float32)
        if not len(vectors):
            continue
        candidate_id = f"cand-{safe_component(run_id)}-{safe_component(row['transcript_label'])}"
        payload = store.save_candidate(
            customer_id,
            row["final_person_id"],
            run_id,
            candidate_id,
            vectors,
            {
                "kind": "analysis_profile_candidate",
                "predicted_identity": row["final_identity"],
                "transcript_label": row["transcript_label"],
                "usable_seconds": row["usable_seconds"],
                "voiceprint": {
                    "top1_score": row["top1_score"],
                    "score_margin": row["score_margin"],
                    "accept_threshold": bundle["calibration"]["accept_threshold"],
                    "margin_threshold": bundle["calibration"]["margin_threshold"],
                    "confidence": row["acoustic_confidence"],
                },
                "windows": row["candidate_windows"],
                "source": bundle["source"],
                "meeting": bundle["meeting"],
            },
        )
        created_candidates.append(payload)

    clean_resolved: list[dict[str, Any]] = []
    for row in resolved:
        clean_resolved.append({key: value for key, value in row.items() if key != "candidate_vector_path"})
    outputs = write_outputs(
        run_dir,
        bundle,
        clean_resolved,
        valid_context,
        rejected_context,
        valid_viewpoints,
        non_substantive_labels,
        rejected_viewpoints,
        created_candidates,
    )
    atomic_write_json(run_dir / "validated_context.json", {"schema_version": 1, "items": valid_context})
    atomic_write_json(
        run_dir / "validated_viewpoints.json",
        {
            "schema_version": 1,
            "items": valid_viewpoints,
            "non_substantive_labels": non_substantive_labels,
        },
    )
    store.update_run(run_id, "completed")
    return {
        "status": "completed",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "outputs": outputs,
        "profile_candidates": [
            {
                "candidate_id": item["candidate_id"],
                "predicted_identity": item["predicted_identity"],
                "metadata_path": str(
                    store.resolve_storage_path(
                        str(item["npz_path"]).replace(".npz", ".json"), customer_id
                    )
                ),
            }
            for item in created_candidates
        ],
        "rejected_context_count": len(rejected_context),
        "rejected_viewpoint_count": len(rejected_viewpoints),
    }


def list_profile_candidates(customer_id: str, store: DataStore) -> dict[str, Any]:
    store.get_customer(customer_id)
    return {"customer_id": customer_id, "candidates": store.list_candidates(customer_id)}


def promote_candidate(
    candidate_path: Path,
    person_id: str,
    confirmed_by: str | None,
    store: DataStore,
) -> dict[str, Any]:
    candidate = load_structured(candidate_path.resolve())
    if candidate.get("status") != "pending_confirmation":
        raise ValueError(f"Candidate is not pending confirmation: {candidate.get('status')}")
    if confirmed_by is not None and not confirmed_by.strip():
        raise ValueError("confirmed_by is required")
    confirmed_by = confirmed_by.strip() if confirmed_by else None
    person = store.get_person(person_id)
    customer_id = candidate["customer_id"]
    if person["scope"] == "customer" and person["customer_id"] != customer_id:
        raise RuntimeError("Cross-customer profile promotion was blocked")
    current = store.load_profile(person_id)
    with np.load(
        store.resolve_storage_path(str(candidate["npz_path"]), customer_id), allow_pickle=False
    ) as arrays:
        vectors = np.asarray(arrays["embeddings"], dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[1] != 192 or len(vectors) < 2:
        raise ValueError("Candidate does not contain enough valid embeddings")
    center = current["arrays"]["center"]
    similarities = vectors @ center
    threshold = float(candidate.get("voiceprint", {}).get("accept_threshold", 0.58))
    consistency = float(np.median(similarities))
    if consistency < threshold - 0.03:
        raise RuntimeError(
            f"Candidate median similarity {consistency:.4f} is inconsistent with "
            f"{person['name']} at threshold {threshold:.4f}"
        )
    keep_indices = np.where(similarities >= threshold - 0.05)[0]
    keep = vectors[keep_indices]
    if len(keep) < 2:
        raise RuntimeError("Too few candidate vectors remain after consistency filtering")
    candidate_holdout_indices = set(range(3, len(keep), 4))
    candidate_reference_indices = [
        index for index in range(len(keep)) if index not in candidate_holdout_indices
    ]
    candidate_refs = np.stack(
        [keep[index] for index in candidate_reference_indices]
    )
    candidate_heldouts = (
        np.stack([keep[index] for index in sorted(candidate_holdout_indices)])
        if candidate_holdout_indices
        else keep[-1:].copy()
    )
    old_refs = current["arrays"]["references"]
    old_heldouts = current["arrays"]["heldouts"]
    old_provenance = store._profile_provenance(current)
    candidate_windows = list(candidate.get("windows") or [])
    kept_windows = [
        candidate_windows[int(index)] if int(index) < len(candidate_windows) else {}
        for index in keep_indices
    ]
    candidate_ref_windows = [kept_windows[index] for index in candidate_reference_indices]
    candidate_holdout_windows = (
        [kept_windows[index] for index in sorted(candidate_holdout_indices)]
        if candidate_holdout_indices
        else [kept_windows[-1]]
    )
    combined_refs = np.concatenate([old_refs, candidate_refs]).astype(np.float32)
    combined_ref_windows = list(old_provenance["references"]) + candidate_ref_windows
    max_refs = int(PIPELINE_CONFIG["max_promoted_references"])
    if len(combined_refs) > max_refs:
        indices = np.linspace(0, len(combined_refs) - 1, max_refs, dtype=int)
        combined_refs = combined_refs[indices]
        combined_ref_windows = [combined_ref_windows[int(index)] for index in indices]
    combined_heldouts = np.concatenate([old_heldouts, candidate_heldouts]).astype(np.float32)
    combined_holdout_windows = list(old_provenance["heldouts"]) + candidate_holdout_windows
    new_center = normalize(np.mean(combined_refs, axis=0))
    old_weights = current["arrays"].get(
        "quality_weights", np.ones(len(old_refs), dtype=np.float32)
    )
    weights = np.concatenate(
        [old_weights[: len(old_refs)], np.ones(len(candidate_refs), dtype=np.float32)]
    )[: len(combined_refs)]
    vector_provenance = {
        "references": [
            {
                **window,
                "window_id": f"ref-{index:04d}",
                "array_kind": "references",
                "array_index": index,
            }
            for index, window in enumerate(combined_ref_windows)
        ],
        "heldouts": [
            {
                **window,
                "window_id": f"holdout-{index:04d}",
                "array_kind": "heldouts",
                "array_index": index,
            }
            for index, window in enumerate(combined_holdout_windows)
        ],
    }
    candidate_source_records: list[dict[str, Any]] = []
    source_root = store.customer_source_dir(customer_id).resolve()
    for source in candidate.get("sources") or [candidate.get("source") or {}]:
        if not isinstance(source, dict):
            continue
        record = {
            key: source.get(key)
            for key in (
                "source_id", "meeting_id", "title", "audio_sha256", "transcript_sha256"
            )
            if source.get(key) not in {None, ""}
        }
        record["customer_id"] = customer_id
        for source_key, target_key in (
            ("audio_path", "audio_relative_path"),
            ("transcript_path", "transcript_relative_path"),
        ):
            with contextlib.suppress(Exception):
                record[target_key] = str(Path(source[source_key]).resolve().relative_to(source_root))
        candidate_source_records.append(record)
    sources = store._safe_sources(current["manifest"]) + candidate_source_records
    profile_manifest = {
        "model": current["manifest"]["model"],
        "review_session_id": candidate.get("review_session_id"),
        "confirmation_mode": candidate.get("confirmation", {}).get("mode", "cli_confirmed"),
        "promotion": {
            "candidate_id": candidate["candidate_id"],
            "confirmed_at": now_iso(),
            "candidate_predicted_identity": candidate["predicted_identity"],
            "median_similarity_to_previous_center": consistency,
        },
        "previous_version": current["version"],
        "parent_version": current["version"],
        "creation_mode": "promotion",
        "sources": sources + [{
            "kind": "confirmed_profile_candidate",
            "candidate_id": candidate["candidate_id"],
            "run_id": candidate["run_id"],
            "audio_sha256": candidate.get("source", {}).get("audio_sha256"),
        }],
        "registration": {
            "source_recordings": sources,
            "source_windows": combined_ref_windows + combined_holdout_windows,
        },
        "vector_provenance": vector_provenance,
        "statistics": {
            "reference_count": len(combined_refs),
            "holdout_count": len(combined_heldouts),
            "reference_seconds": float(sum(float(item.get("duration") or 0.0) for item in combined_ref_windows)),
            "holdout_seconds": float(sum(float(item.get("duration") or 0.0) for item in combined_holdout_windows)),
        },
    }
    if confirmed_by:
        profile_manifest["promotion"]["confirmed_by"] = confirmed_by
    saved = store.save_profile(
        person,
        {
            "references": combined_refs,
            "heldouts": combined_heldouts,
            "center": new_center,
            "quality_weights": weights,
        },
        profile_manifest,
    )
    details = {
        "promoted_person_id": person_id,
        "profile_version": saved["version"],
        "promoted_at": now_iso(),
    }
    if confirmed_by:
        details["confirmed_by"] = confirmed_by
    store.mark_candidate(candidate["candidate_id"], "promoted", details)
    return {"status": "promoted", "profile": saved, "candidate": details}
