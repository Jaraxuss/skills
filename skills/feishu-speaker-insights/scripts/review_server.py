from __future__ import annotations

import contextlib
import json
import logging
import re
import secrets
import subprocess
import tempfile
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from speaker_engine.review import (
    cleanup_review_artifacts,
    commit_review_session,
    create_enrollment_review,
    create_profile_revision_review,
    create_profile_review,
    normalize_review_manifest,
    restart_cancelled_enrollment_review,
    run_next_review_job,
    save_review_decision,
    validate_review_decision,
)
from speaker_engine.storage import DataStore
from speaker_engine.util import atomic_write_json, load_structured


LOG = logging.getLogger("feishu_speaker_review")
AUDIO_SUFFIXES = {".ogg", ".opus", ".wav", ".mp3", ".m4a", ".aac", ".flac"}
TRANSCRIPT_SUFFIXES = {".txt", ".json", ".yaml", ".yml"}
SPEAKER_LABEL_PATTERN = re.compile(
    r"^\s*(说话人\s*\d+)\s+(?:(?:\d{1,2}:)?\d{1,2}:\d{2})(?=\s|$)",
    re.MULTILINE,
)


def _client(request: Request) -> dict[str, Any]:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:512],
    }


def _require_csrf(
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> None:
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF token is missing or invalid")


def _api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if str(exc) == "review_revision_conflict":
        return HTTPException(status_code=409, detail="审核内容已被其他操作更新，请刷新后重试")
    if "source_changed" in str(exc):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _safe_customer_file(store: DataStore, customer_id: str, raw_path: str, suffixes: set[str]) -> Path:
    candidate = Path(raw_path).expanduser().resolve()
    customer_root = store.customer_source_dir(customer_id).resolve()
    # The customer may keep recordings in its customer directory, while the
    # protected ``声纹数据`` subtree must never be selected as input.
    customer_data = customer_root / "声纹数据"
    if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
        raise ValueError("文件不存在或类型不受支持")
    if customer_root not in candidate.parents or customer_data in candidate.parents:
        raise ValueError("网页只能选择当前客户目录中的原始录音或转写文件")
    return candidate


def _session_summary(store: DataStore, session: dict[str, Any]) -> dict[str, Any]:
    """Expose human-readable, UI-safe task metadata without source paths."""
    customer = store.get_customer(str(session["customer_id"]))
    manifest: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        manifest = load_structured(Path(session["manifest_path"]))
    meetings = manifest.get("meetings") or ([manifest["meeting"]] if manifest.get("meeting") else [])
    titles = [str(item.get("title") or "录音") for item in meetings]
    display_title = str(manifest.get("display_title") or "")
    if not display_title:
        display_title = "、".join(titles[:2])
        if len(titles) > 2:
            display_title += f" 等 {len(titles)} 份录音"
    return {
        "customer_name": str(customer["name"]),
        "display_title": display_title or "声纹审核任务",
        "meeting_titles": titles,
        "recording_count": len(titles),
        "task_type": str(session.get("kind") or "enrollment"),
    }


def _session_payload(store: DataStore, session_id: str, include_package: bool = True) -> dict[str, Any]:
    session = store.get_review_session(session_id)
    result = {key: value for key, value in session.items() if key not in {"manifest_path", "package_path", "result_path"}}
    result.update(_session_summary(store, session))
    result["playback_count"] = store.audit_count(session_id, "review_segment_played")
    if include_package and session.get("package_path") and Path(session["package_path"]).is_file():
        package = load_structured(Path(session["package_path"]))
        # The browser needs timestamps/transcript text but never an arbitrary
        # server pathname.  Audio is available only through segment_id.
        sources = package.get("sources") or [package["source"]]
        package["source"] = {
            key: package["source"].get(key)
            for key in (
                "source_id", "meeting_id", "title", "audio_sha256",
                "transcript_sha256", "playable",
            )
            if package["source"].get(key) is not None
        }
        package["sources"] = [
            {
                key: item.get(key)
                for key in (
                    "source_id", "meeting_id", "title", "audio_sha256",
                    "transcript_sha256", "playable",
                )
                if item.get(key) is not None
            }
            for item in sources
        ]
        if isinstance(package.get("profile_revision"), dict):
            package["profile_revision"] = {
                key: package["profile_revision"].get(key)
                for key in ("person_id", "base_version")
            }
        package["manifest"]["meeting"].pop("audio", None)
        package["manifest"]["meeting"].pop("transcript", None)
        for meeting in package["manifest"].get("meetings") or []:
            meeting.pop("audio", None)
            meeting.pop("transcript", None)
        result["package"] = package
    return result


def _audio_stream(command: list[str]) -> Iterator[bytes]:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        if process.stdout is not None:
            for block in iter(lambda: process.stdout.read(64 * 1024), b""):
                yield block
    finally:
        with contextlib.suppress(Exception):
            process.kill()
        with contextlib.suppress(Exception):
            process.wait(timeout=1)


def create_app(store: DataStore, *, base_url: str, download: bool = False) -> FastAPI:
    def worker_loop() -> None:
        while not app.state.stop_event.is_set():
            try:
                result = run_next_review_job(store, download=download)
                cleanup_review_artifacts(store)
                if result:
                    LOG.info("review job processed: %s (%s)", result["session_id"], result["status"])
            except Exception:
                LOG.exception("review worker failed")
            app.state.stop_event.wait(0.8)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        app.state.stop_event = threading.Event()
        thread = threading.Thread(target=worker_loop, name="speaker-review-worker", daemon=True)
        app.state.worker_thread = thread
        thread.start()
        try:
            yield
        finally:
            app.state.stop_event.set()
            thread.join(timeout=3)

    app = FastAPI(title="声纹建库控制台", version="1.0", lifespan=lifespan)
    app.state.store = store
    app.state.base_url = base_url.rstrip("/")
    app.state.download = download

    @app.get("/api/v1/csrf")
    def csrf(response: Response) -> dict[str, str]:
        token = secrets.token_urlsafe(32)
        response.set_cookie("speaker_review_csrf", token, httponly=False, samesite="strict")
        return {"token": token}

    @app.get("/api/v1/customers")
    def customers() -> dict[str, Any]:
        return {"customers": store.discover_customers()}

    @app.get("/api/v1/console/summary")
    def console_summary() -> dict[str, Any]:
        summary = store.console_summary()
        recent = [
            _session_payload(store, item["session_id"], include_package=False)
            for item in store.list_review_sessions()[:8]
        ]
        return {**summary, "recent_sessions": recent}

    @app.get("/api/v1/customers/{customer_id}/files")
    def customer_files(customer_id: str) -> dict[str, Any]:
        root = store.customer_source_dir(customer_id).resolve()
        customer_data = root / "声纹数据"
        values: list[dict[str, str]] = []
        seen_paths: set[Path] = set()
        for item in sorted(root.rglob("*")):
            resolved = item.resolve()
            if (
                not item.is_file()
                or resolved in seen_paths
                or root not in resolved.parents
                or customer_data in resolved.parents
            ):
                continue
            seen_paths.add(resolved)
            suffix = item.suffix.lower()
            if suffix in AUDIO_SUFFIXES:
                kind = "audio"
            elif suffix in TRANSCRIPT_SUFFIXES:
                kind = "transcript"
            else:
                continue
            values.append({"path": str(resolved), "relative_path": str(item.relative_to(root)), "kind": kind})
            if len(values) >= 500:
                break
        return {"customer_id": customer_id, "files": values}

    @app.get("/api/v1/customers/{customer_id}/transcript-preview")
    def transcript_preview(customer_id: str, path: str) -> dict[str, Any]:
        """Return a bounded, read-only preview of one selectable transcript.

        The browser only supplies a path that was previously listed for the
        selected customer.  Validate it again here so this endpoint cannot be
        used to read arbitrary server files.
        """
        try:
            source = _safe_customer_file(store, customer_id, path, TRANSCRIPT_SUFFIXES)
            limit = 20_000
            content = source.read_text(encoding="utf-8-sig", errors="replace")
            return {
                "customer_id": customer_id,
                "relative_path": str(source.relative_to(store.customer_source_dir(customer_id))),
                "content": content[:limit],
                "truncated": len(content) > limit,
            }
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/customers/{customer_id}/transcript-speakers")
    async def transcript_speakers(
        customer_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        """Extract Feishu's anonymous speaker labels from selected transcripts.

        This only creates UI suggestions; it does not create people or write a
        profile.  Do the extraction server-side so every selected transcript is
        scanned in full, rather than being limited by the preview response.
        """
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            payload = await request.json()
            raw_paths = payload.get("paths") if isinstance(payload, dict) else None
            if not isinstance(raw_paths, list) or not raw_paths:
                raise ValueError("请选择至少一份转写文件")
            if len(raw_paths) > 500:
                raise ValueError("一次最多识别 500 份转写文件")
            labels: list[str] = []
            per_transcript: list[dict[str, Any]] = []
            seen: set[str] = set()
            for raw_path in raw_paths:
                if not isinstance(raw_path, str):
                    raise ValueError("转写文件路径无效")
                source = _safe_customer_file(store, customer_id, raw_path, TRANSCRIPT_SUFFIXES)
                found: list[str] = []
                for match in SPEAKER_LABEL_PATTERN.finditer(source.read_text(encoding="utf-8-sig", errors="replace")):
                    label = re.sub(r"\s+", " ", match.group(1)).strip()
                    if label not in found:
                        found.append(label)
                    if label not in seen:
                        seen.add(label)
                        labels.append(label)
                per_transcript.append({
                    "relative_path": str(source.relative_to(store.customer_source_dir(customer_id))),
                    "labels": found,
                })
            return {"customer_id": customer_id, "labels": labels, "transcripts": per_transcript}
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/customers/{customer_id}/profiles")
    def customer_profiles(customer_id: str) -> dict[str, Any]:
        people = store.list_people(customer_id, include_staff=True)
        return {
            "customer_id": customer_id,
            "people": [
                {**person, "versions": store.list_profile_versions(person["person_id"])}
                for person in people
            ],
        }

    @app.get("/api/v1/profiles")
    def profiles(
        page: int = 1,
        page_size: int = 20,
        customer_id: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        try:
            return store.list_profiles(
                page=page,
                page_size=page_size,
                customer_id=customer_id,
                scope=scope,
                status=status,
                keyword=keyword,
            )
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/profiles/{person_id}/versions")
    def profile_versions(person_id: str) -> dict[str, Any]:
        try:
            person = store.get_person(person_id)
            return {
                "person": {
                    key: person.get(key)
                    for key in (
                        "person_id", "name", "role", "scope", "organization", "customer_id",
                        "current_version", "voiceprint_enabled",
                    )
                },
                "versions": store.list_profile_versions(person_id),
            }
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/profiles/{person_id}/versions/{version}")
    def profile_version_detail(person_id: str, version: int) -> dict[str, Any]:
        try:
            return store.profile_version_detail(person_id, version)
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/customers/{customer_id}/candidates")
    def customer_candidates(customer_id: str) -> dict[str, Any]:
        store.get_customer(customer_id)
        return {"customer_id": customer_id, "candidates": store.list_candidates(customer_id)}

    @app.post("/api/v1/profile-candidates/{candidate_id}/review")
    async def candidate_review(
        candidate_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            _, path = store.get_candidate(candidate_id)
            result = create_profile_review(path, store, base_url=app.state.base_url)
            store.audit_event("profile_review_created_via_web", session_id=result["session_id"], client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profile-candidates/{candidate_id}/reject")
    async def reject_candidate(
        candidate_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            candidate, _ = store.get_candidate(candidate_id)
            store.mark_candidate(
                candidate_id,
                "rejected",
                {"rejected_by": str(payload.get("reviewer") or ""), "rejected_at": str(payload.get("at") or "")},
            )
            store.audit_event("profile_candidate_rejected", actor=str(payload.get("reviewer") or ""), value={"candidate_id": candidate_id}, client=_client(request))
            return {"candidate_id": candidate_id, "status": "rejected", "customer_id": candidate["customer_id"]}
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions")
    async def create_session(
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        raw_manifest = payload.get("manifest") if isinstance(payload, dict) else None
        if not isinstance(raw_manifest, dict):
            raise HTTPException(status_code=400, detail="请求必须包含 manifest 对象")
        try:
            manifest = normalize_review_manifest(raw_manifest)
            customer_id = str(manifest["customer"]["id"])
            for meeting in manifest.get("meetings") or [manifest["meeting"]]:
                _safe_customer_file(store, customer_id, meeting["audio"], AUDIO_SUFFIXES)
                _safe_customer_file(store, customer_id, meeting["transcript"], TRANSCRIPT_SUFFIXES)
            with tempfile.TemporaryDirectory(prefix="speaker-review-api-") as temporary:
                path = Path(temporary) / "manifest.json"
                atomic_write_json(path, manifest)
                result = create_enrollment_review(path, store, base_url=app.state.base_url)
            store.audit_event("review_session_created_via_web", session_id=result["session_id"], client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/enrollment-sessions")
    def sessions(customer_id: str | None = None) -> dict[str, Any]:
        return {
            "sessions": [
                _session_payload(store, item["session_id"], include_package=False)
                for item in store.list_review_sessions(customer_id)
            ]
        }

    @app.get("/api/v1/enrollment-sessions/{session_id}")
    def session(session_id: str) -> dict[str, Any]:
        try:
            return _session_payload(store, session_id)
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions/{session_id}/segments/{segment_id}/playback")
    def playback(
        session_id: str,
        segment_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            package = _session_payload(store, session_id)["package"]
            if segment_id not in {item["segment_id"] for item in package["segments"]}:
                raise KeyError(segment_id)
            store.audit_event(
                "review_segment_played", session_id=session_id, value={"segment_id": segment_id}, client=_client(request)
            )
            return {"ok": True, "playback_count": store.audit_count(session_id, "review_segment_played")}
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.get("/api/v1/enrollment-sessions/{session_id}/segments/{segment_id}/audio")
    def segment_audio(session_id: str, segment_id: str) -> StreamingResponse:
        try:
            full_session = store.get_review_session(session_id)
            package = load_structured(Path(full_session["package_path"]))
            segment = next(item for item in package["segments"] if item["segment_id"] == segment_id)
            source_id = str(segment.get("source_id") or "source-1")
            sources = package.get("sources") or [package["source"]]
            source = next(
                item for item in sources if str(item.get("source_id") or "source-1") == source_id
            )
            if not source.get("audio_path"):
                raise FileNotFoundError("该历史版本没有可试听的原始录音路径")
            audio = Path(source["audio_path"]).resolve()
            if not audio.is_file():
                raise FileNotFoundError(audio)
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{float(segment['start']):.3f}",
                "-to", f"{float(segment['end']):.3f}", "-i", str(audio), "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1",
            ]
            return StreamingResponse(_audio_stream(command), media_type="audio/wav")
        except StopIteration as exc:
            raise HTTPException(status_code=404, detail="片段不存在") from exc
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.put("/api/v1/enrollment-sessions/{session_id}/decision")
    async def put_decision(
        session_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            result = save_review_decision(
                session_id,
                dict(payload.get("decision") or {}),
                int(payload["revision"]),
                store,
                client=_client(request),
            )
            return _session_payload(store, result["session_id"])
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions/{session_id}/validate")
    async def validate(
        session_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            decision = payload.get("decision")
            if decision is None:
                decision = store.get_review_session(session_id).get("decision") or {}
            return validate_review_decision(session_id, dict(decision), store)
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions/{session_id}/commit")
    async def commit(
        session_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            return commit_review_session(
                session_id,
                int(payload["revision"]),
                store,
                client=_client(request),
            )
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions/{session_id}/cancel")
    async def cancel(
        session_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            result = store.cancel_review_session(
                session_id,
                client=_client(request),
            )
            cleanup_review_artifacts(store)
            return _session_payload(store, result["session_id"], include_package=False)
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/enrollment-sessions/{session_id}/restart")
    async def restart(
        session_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            return restart_cancelled_enrollment_review(
                session_id,
                store,
                base_url=app.state.base_url,
                client=_client(request),
            )
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/rollback")
    async def rollback(
        person_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            result = store.rollback_profile(person_id, payload.get("to_version"))
            store.audit_event("profile_rolled_back", actor=str(payload.get("reviewer") or ""), value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/current-version")
    async def set_current_profile_version(
        person_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            result = store.set_current_profile_version(person_id, int(payload["version"]))
            store.audit_event("profile_current_version_changed", value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/disable")
    async def disable_profile(
        person_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            result = store.set_profile_enabled(person_id, False)
            store.audit_event("profile_disabled", value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/enable")
    async def enable_profile(
        person_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            result = store.set_profile_enabled(person_id, True)
            store.audit_event("profile_enabled", value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/versions/{version}/fork")
    async def fork_profile_version(
        person_id: str,
        version: int,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            included = payload.get("included_window_ids")
            if included is not None and not isinstance(included, list):
                raise ValueError("included_window_ids must be a list")
            result = store.fork_profile_version(
                person_id,
                version,
                [str(item) for item in included] if included is not None else None,
                make_current=bool(payload.get("make_current", True)),
            )
            store.audit_event("profile_version_forked", value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/versions/{version}/review")
    async def create_profile_revision_session(
        person_id: str,
        version: int,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        try:
            result = create_profile_revision_review(
                person_id,
                version,
                store,
                base_url=app.state.base_url,
            )
            store.audit_event(
                "profile_revision_review_created",
                session_id=result["session_id"],
                value={"person_id": person_id, "base_version": version},
                client=_client(request),
            )
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    @app.post("/api/v1/profiles/{person_id}/quarantine")
    async def quarantine(
        person_id: str,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
        speaker_review_csrf: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_csrf(speaker_review_csrf, x_csrf_token)
        payload = await request.json()
        try:
            result = store.quarantine_profile(person_id, str(payload.get("reviewer") or ""))
            store.audit_event("profile_quarantined", actor=str(payload.get("reviewer") or ""), value=result, client=_client(request))
            return result
        except Exception as exc:
            raise _api_error(exc) from exc

    frontend_dist = Path(__file__).resolve().parent.parent / "review_app" / "dist"
    if frontend_dist.is_dir():
        assets = frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            candidate = (frontend_dist / path).resolve()
            if path and candidate.is_file() and frontend_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app


def run_server(store: DataStore, *, host: str, port: int, base_url: str, download: bool = False) -> dict[str, Any]:
    import uvicorn

    log_dir = store.root / "service-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "review-service.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    app = create_app(store, base_url=base_url, download=download)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return {"status": "stopped"}
