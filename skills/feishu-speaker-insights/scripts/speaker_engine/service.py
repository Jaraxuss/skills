from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable

from .agent import (
    _begin_task,
    agent_analysis_correct,
    agent_analyze_complete,
    agent_analyze_start,
    agent_enroll_confirm,
    agent_enroll_start,
    agent_task_status,
    capabilities,
)
from .embedding import EmbeddingEngine
from .errors import StructuredError
from .review import cleanup_review_artifacts, run_next_review_job
from .storage import DataStore
from .util import atomic_write_json, load_structured, sha256_file


LOG = logging.getLogger("feishu_speaker_service")
SERVICE_API_VERSION = 1
AUDIO_SUFFIXES = {".ogg", ".opus", ".wav", ".mp3", ".m4a", ".aac", ".flac"}
TRANSCRIPT_SUFFIXES = {".txt", ".md", ".json", ".yaml", ".yml"}
INTERNAL_REPORT_FIELDS = {
    "audio",
    "transcript",
    "cache_path",
    "npz_path",
    "manifest_path",
    "run_path",
    "run_dir",
    "detailed_report",
    "final_results",
}


def service_capabilities() -> dict[str, Any]:
    return {
        **capabilities(),
        "service_api": SERVICE_API_VERSION,
        "business_api": True,
        "relative_customer_paths": True,
        "single_worker": True,
        "business_cli_is_http_client": True,
    }


def _customer_descriptor(store: DataStore, customer_id: str) -> dict[str, Any]:
    customer_id = customer_id.strip()
    if not customer_id:
        raise StructuredError("CUSTOMER_REQUIRED", "必须提供客户ID。")
    for item in store.discover_customers():
        if str(item.get("customer_id")) == customer_id:
            return {
                "id": customer_id,
                "name": str(item.get("name") or customer_id),
                "directory_relpath": str(item.get("directory_relpath") or item.get("name") or ""),
            }
    raise StructuredError(
        "CUSTOMER_NOT_FOUND",
        f"客户目录不存在：{customer_id}",
        details={"customer_id": customer_id},
    )


def _safe_customer_source(
    store: DataStore,
    customer_id: str,
    raw_relative: Any,
    suffixes: set[str],
    field: str,
) -> Path:
    value = str(raw_relative or "").strip()
    relative = Path(value)
    if (
        not value
        or relative.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise StructuredError(
            "INVALID_SOURCE_PATH",
            f"{field} 必须是当前客户目录内的相对路径。",
            details={"field": field, "value": value},
        )
    root = store.customer_source_dir(customer_id).resolve()
    protected = (root / "声纹数据").resolve()
    candidate = (root / relative).resolve()
    if (
        not candidate.is_file()
        or candidate.suffix.lower() not in suffixes
        or root not in candidate.parents
        or candidate == protected
        or protected in candidate.parents
    ):
        raise StructuredError(
            "INVALID_SOURCE_PATH",
            f"{field} 不存在、类型不受支持或超出客户目录。",
            details={"field": field, "value": value},
        )
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise StructuredError(
                "SOURCE_SYMLINK_BLOCKED",
                f"{field} 不能通过软链接读取。",
                details={"field": field, "value": value},
            )
    return candidate


def _meeting_manifest(
    store: DataStore, customer_id: str, raw: dict[str, Any], index: int
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StructuredError("INVALID_MEETING", "录音和转写必须成组提供。")
    audio = _safe_customer_source(
        store,
        customer_id,
        raw.get("audio_relpath"),
        AUDIO_SUFFIXES,
        f"meetings[{index}].audio_relpath",
    )
    transcript = _safe_customer_source(
        store,
        customer_id,
        raw.get("transcript_relpath"),
        TRANSCRIPT_SUFFIXES,
        f"meetings[{index}].transcript_relpath",
    )
    audio_sha = sha256_file(audio)
    transcript_sha = sha256_file(transcript)
    digest = hashlib.sha256(f"{audio_sha}\0{transcript_sha}".encode("utf-8")).hexdigest()
    return {
        "id": f"meeting-{digest[:16]}",
        "title": audio.stem,
        "audio": str(audio),
        "transcript": str(transcript),
    }


def _attendees(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise StructuredError("INVALID_ATTENDEES", "attendees 必须是数组。")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise StructuredError(
                "INVALID_ATTENDEE",
                "每位参会人必须包含姓名。",
                details={"index": index},
            )
        organization = str(item.get("organization") or "customer").strip().lower()
        if organization == "staff":
            organization = "yingdao"
        if organization not in {"customer", "yingdao", "external"}:
            raise StructuredError(
                "INVALID_ATTENDEE",
                "参会人归属必须是 customer、yingdao 或 external。",
                details={"index": index, "organization": organization},
            )
        normalized = {
            "name": str(item["name"]).strip(),
            "role": str(item.get("role") or "").strip(),
            "organization": organization,
        }
        if item.get("id"):
            normalized["id"] = str(item["id"])
        result.append(normalized)
    return result


def _base_request(payload: dict[str, Any]) -> dict[str, Any]:
    if int(payload.get("schema_version", 0)) != 1:
        raise StructuredError("UNSUPPORTED_SCHEMA", "schema_version 必须为 1。")
    conversation = payload.get("conversation") or {}
    if not isinstance(conversation, dict):
        raise StructuredError("INVALID_CONVERSATION", "conversation 必须是对象。")
    return {
        "schema_version": 1,
        "external_request_id": str(payload.get("external_request_id") or "").strip() or None,
        "conversation": {
            key: str(conversation.get(key) or "").strip()
            for key in ("channel", "chat_id", "user_id", "trigger_message_id")
            if str(conversation.get(key) or "").strip()
        },
    }


def analysis_request(payload: dict[str, Any], store: DataStore) -> dict[str, Any]:
    request = _base_request(payload)
    customer = _customer_descriptor(store, str(payload.get("customer_id") or ""))
    raw_meeting = payload.get("meeting")
    if not isinstance(raw_meeting, dict):
        raise StructuredError("MEETING_REQUIRED", "必须提供一组录音和转写。")
    manifest = {
        "schema_version": 1,
        "customer": customer,
        "meeting": _meeting_manifest(store, customer["id"], raw_meeting, 0),
        "attendees": _attendees(payload.get("attendees")),
        "known_label_map": payload.get("known_label_map") or {},
        "excluded_labels": payload.get("excluded_labels") or [],
    }
    return {**request, "manifest": manifest}


def enrollment_request(payload: dict[str, Any], store: DataStore) -> dict[str, Any]:
    request = _base_request(payload)
    customer = _customer_descriptor(store, str(payload.get("customer_id") or ""))
    raw_meetings = payload.get("meetings")
    if not isinstance(raw_meetings, list) or not raw_meetings:
        raise StructuredError("MEETINGS_REQUIRED", "首次建库必须提供至少一组录音和转写。")
    attendees = _attendees(payload.get("attendees"))
    target = payload.get("target_person")
    if isinstance(target, str):
        target = {"name": target}
    if not isinstance(target, dict) or not str(target.get("name") or "").strip():
        raise StructuredError("TARGET_PERSON_REQUIRED", "简单建库必须明确目标人员。")
    target_attendee = _attendees([target])[0]
    target_name = target_attendee["name"]
    if not any(item["name"] == target_name for item in attendees):
        attendees.append(target_attendee)
    meetings = [
        _meeting_manifest(store, customer["id"], item, index)
        for index, item in enumerate(raw_meetings)
    ]
    manifest = {
        "schema_version": 1,
        "customer": customer,
        "meeting": meetings[0],
        "meetings": meetings,
        "attendees": attendees,
        "known_label_map": payload.get("known_label_map") or {},
        "excluded_labels": payload.get("excluded_labels") or [],
    }
    review_mode = str(payload.get("review_mode") or "auto")
    if review_mode not in {"auto", "web"}:
        raise StructuredError("INVALID_REVIEW_MODE", "review_mode 只能是 auto 或 web。")
    return {
        **request,
        "manifest": manifest,
        "target_person": {
            key: target_attendee[key]
            for key in ("name", "role", "organization")
        },
        "review_mode": review_mode,
    }


def _enqueue(request: dict[str, Any], operation: str, store: DataStore) -> tuple[dict[str, Any], bool]:
    intent = (
        {
            "target_person": request.get("target_person"),
            "review_mode": request.get("review_mode", "auto"),
        }
        if operation == "enroll"
        else {}
    )
    try:
        task, reused, _ = _begin_task(operation, request["manifest"], request, store, intent)
    except RuntimeError as exc:
        if str(exc) == "external_request_conflict":
            raise StructuredError(
                "EXTERNAL_REQUEST_CONFLICT",
                "同一外部请求ID已经对应另一组输入。",
                details={"external_request_id": request.get("external_request_id")},
            ) from exc
        raise
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise StructuredError(
            "INVALID_BUSINESS_REQUEST",
            str(exc) or "业务请求校验失败。",
            details={"operation": operation},
        ) from exc
    if reused:
        return task, True
    request_path = Path(task["artifact_dir"]) / "request.json"
    atomic_write_json(request_path, request)
    task = store.update_task(
        task["task_id"],
        status="queued",
        phase="queued_enrollment" if operation == "enroll" else "queued_acoustic",
        checkpoint={"request_path": str(request_path), "conversation": request.get("conversation") or {}},
        progress={"current": 0, "total": 1, "percent": 0.0, "message": "任务已进入队列"},
        clear_cancel=True,
    )
    return task, False


def enqueue_analysis(payload: dict[str, Any], store: DataStore) -> tuple[dict[str, Any], bool]:
    return _enqueue(analysis_request(payload, store), "analyze", store)


def enqueue_enrollment(payload: dict[str, Any], store: DataStore) -> tuple[dict[str, Any], bool]:
    return _enqueue(enrollment_request(payload, store), "enroll", store)


def _task_links(task_id: str, operation: str, base_url: str) -> dict[str, str]:
    noun = "enrollment-tasks" if operation == "enroll" else "analysis-tasks"
    root = f"{base_url.rstrip('/')}/api/v1/{noun}/{task_id}"
    result = {"status_url": root}
    if operation == "analyze":
        result.update(
            semantic_request_url=f"{root}/semantic-request",
            report_url=f"{root}/report",
        )
    return result


def task_payload(
    task_id: str, store: DataStore, base_url: str, *, reused: bool = False
) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task["operation"] == "enroll":
        # Browser confirmation can finish a task while the Agent is only polling.
        agent_task_status(task_id, store)
        task = store.get_task(task_id)
    checkpoint = task.get("checkpoint") or {}
    progress = task.get("progress")
    session_id = checkpoint.get("session_id")
    if session_id:
        try:
            session = store.get_review_session(str(session_id))
            if session.get("job") and session["job"].get("progress"):
                progress = session["job"]["progress"]
        except KeyError:
            pass
    response: dict[str, Any] = {
        "ok": True,
        "task_id": task["task_id"],
        "operation": task["operation"],
        "status": task["status"],
        "phase": task["phase"],
        "reused": reused,
        "attempt_count": int(task.get("attempt_count") or 0),
        "progress": progress,
        **_task_links(task_id, task["operation"], base_url),
    }
    if task.get("error_code"):
        response["error"] = {
            "error_code": task["error_code"],
            "message": str((task.get("error_details") or {}).get("message") or task["error_code"]),
            "retryable": task["status"] in {"failed", "awaiting_semantic"},
            "details": task.get("error_details") or {},
        }
    if task["operation"] == "enroll" and checkpoint.get("review_mode"):
        response.update(
            review_mode=checkpoint.get("review_mode"),
            review_url=checkpoint.get("review_url"),
            reason=checkpoint.get("reason"),
            message_markdown=checkpoint.get("message_markdown"),
            target_person=checkpoint.get("target_person"),
            candidates=[
                {
                    key: item.get(key)
                    for key in (
                        "code",
                        "display_label",
                        "meeting_title",
                        "transcript_label",
                        "timestamp",
                        "text",
                        "window_count",
                        "usable_seconds",
                    )
                }
                for item in checkpoint.get("candidates") or []
            ],
        )
        if checkpoint.get("audition_audio"):
            response["audition_url"] = (
                f"{base_url.rstrip('/')}/api/v1/enrollment-tasks/{task_id}/audition"
            )
    return response


def semantic_request_payload(task_id: str, store: DataStore) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task["operation"] != "analyze":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是识别任务。")
    checkpoint = task.get("checkpoint") or {}
    path = Path(str(checkpoint.get("semantic_request") or ""))
    if not path.is_file():
        raise StructuredError(
            "SEMANTIC_REQUEST_NOT_READY",
            "声学分析尚未完成。",
            details={"status": task["status"], "phase": task["phase"]},
            retryable=True,
        )
    payload = load_structured(path)
    transcript_index = payload.get("transcript_index")
    if isinstance(transcript_index, str):
        transcript_path = Path(transcript_index)
        if not transcript_path.is_file():
            raise StructuredError(
                "TRANSCRIPT_INDEX_MISSING",
                "语义请求对应的转写索引不存在。",
                retryable=True,
            )
        payload["transcript_index"] = load_structured(transcript_path)
    return payload


def submit_semantic_result(
    task_id: str, payload: dict[str, Any], store: DataStore
) -> tuple[dict[str, Any], bool]:
    task = store.get_task(task_id)
    if task["operation"] != "analyze":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是识别任务。")
    if task["status"] not in {"awaiting_semantic", "queued", "running", "completed"}:
        raise StructuredError(
            "TASK_STATE_CONFLICT",
            f"当前状态不能提交语义结果：{task['status']}",
            details={"status": task["status"], "phase": task["phase"]},
        )
    semantic_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if task.get("semantic_hash") == semantic_hash and task["status"] in {
        "queued",
        "running",
        "completed",
    }:
        return task, True
    if task["status"] == "completed":
        raise StructuredError(
            "TASK_ALREADY_COMPLETED",
            "任务已完成；身份纠正请使用 corrections 接口。",
        )
    if task["status"] in {"queued", "running"} and task["phase"] != "semantic_revision_required":
        raise StructuredError("TASK_STATE_CONFLICT", "语义结果已经在处理中。")
    checkpoint = task.get("checkpoint") or {}
    if not checkpoint.get("acoustic"):
        raise StructuredError("ACOUSTIC_CHECKPOINT_MISSING", "声学检查点不存在。", retryable=True)
    response_path = Path(task["artifact_dir"]) / "semantic_response.json"
    atomic_write_json(response_path, payload)
    task = store.update_task(
        task_id,
        status="queued",
        phase="queued_finalize",
        checkpoint={**checkpoint, "semantic_response": str(response_path)},
        semantic_hash=semantic_hash,
        progress={"current": 0, "total": 1, "percent": 0.0, "message": "语义结果已提交，等待生成报告"},
        clear_cancel=True,
    )
    return task, False


def confirm_enrollment(
    task_id: str, payload: dict[str, Any], store: DataStore
) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task["operation"] != "enroll":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是建库任务。")
    request = {**payload, "task_id": task_id}
    confirmation_path = Path(task["artifact_dir"]) / "confirmation.json"
    atomic_write_json(confirmation_path, request)
    return agent_enroll_confirm(confirmation_path, store)


def audition_path(task_id: str, store: DataStore) -> Path:
    task = store.get_task(task_id)
    if task["operation"] != "enroll":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是建库任务。")
    path = Path(str((task.get("checkpoint") or {}).get("audition_audio") or ""))
    if not path.is_file():
        raise StructuredError("AUDITION_NOT_READY", "试听音频尚未生成或已经清理。", retryable=True)
    return path


def report_paths(task_id: str, store: DataStore) -> dict[str, Path]:
    task = store.get_task(task_id)
    if task["operation"] != "analyze":
        raise StructuredError("TASK_TYPE_MISMATCH", "该任务不是识别任务。")
    checkpoint = task.get("checkpoint") or {}
    latest = checkpoint.get("latest_correction") or {}
    outputs = latest.get("outputs") or (checkpoint.get("result") or {}).get("outputs") or {}
    mapping = {
        "feishu": outputs.get("feishu_summary"),
        "json": outputs.get("json") or task.get("result_path"),
        "markdown": outputs.get("report"),
    }
    result: dict[str, Path] = {}
    for key, value in mapping.items():
        path = Path(str(value or ""))
        if path.is_file():
            result[key] = path
    if not result:
        raise StructuredError(
            "REPORT_NOT_READY",
            "报告尚未生成。",
            details={"status": task["status"], "phase": task["phase"]},
            retryable=True,
        )
    return result


def public_report_payload(
    task_id: str,
    report_format: str,
    store: DataStore,
    base_url: str,
) -> dict[str, Any]:
    """Return a report without backend filesystem or profile artifact paths."""
    if report_format not in {"feishu", "json"}:
        raise StructuredError(
            "INVALID_REPORT_FORMAT", "结构化报告格式必须是 feishu 或 json。"
        )
    path = report_paths(task_id, store).get(report_format)
    if path is None:
        raise StructuredError(
            "REPORT_FORMAT_NOT_READY",
            f"{report_format} 报告尚未生成。",
            retryable=True,
        )

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: sanitize(item)
                for key, item in value.items()
                if key not in INTERNAL_REPORT_FIELDS
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    payload = sanitize(load_structured(path))
    report_root = f"{base_url.rstrip('/')}/api/v1/analysis-tasks/{task_id}/report"
    payload["report_urls"] = {
        "json": f"{report_root}?format=json",
        "markdown": f"{report_root}?format=markdown",
    }
    return payload


def apply_corrections(task_id: str, payload: dict[str, Any], store: DataStore) -> dict[str, Any]:
    task = store.get_task(task_id)
    path = Path(task["artifact_dir"]) / "corrections.request.json"
    atomic_write_json(path, payload)
    return agent_analysis_correct(task_id, path, store)


class ServiceWorker:
    """One in-process scheduler owning the only model instance."""

    def __init__(
        self,
        store: DataStore,
        *,
        base_url: str,
        download: bool = False,
        engine_factory: Callable[[], EmbeddingEngine] | None = None,
    ) -> None:
        self.store = store
        self.base_url = base_url
        self.download = download
        self._engine: EmbeddingEngine | None = None
        self._engine_factory = engine_factory

    def engine(self) -> EmbeddingEngine:
        if self._engine is None:
            self._engine = (
                self._engine_factory()
                if self._engine_factory is not None
                else EmbeddingEngine(download=self.download)
            )
        return self._engine

    def _process_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task["task_id"])
        request_path = Path(task["artifact_dir"]) / "request.json"
        try:
            if task["operation"] == "analyze":
                if task["phase"] == "queued_finalize":
                    semantic = Path(
                        str((task.get("checkpoint") or {}).get("semantic_response") or "")
                    )
                    return agent_analyze_complete(task_id, semantic, self.store)

                def progress(value: dict[str, Any]) -> None:
                    self.store.update_task_progress(task_id, value)

                return agent_analyze_start(
                    request_path,
                    self.store,
                    download=self.download,
                    engine=self.engine(),
                    should_cancel=lambda: self.store.task_cancel_requested(task_id),
                    on_progress=progress,
                )
            if task["operation"] == "enroll":
                return agent_enroll_start(
                    request_path,
                    self.store,
                    base_url=self.base_url,
                    download=self.download,
                    engine=self.engine(),
                )
            raise StructuredError("TASK_TYPE_MISMATCH", f"不支持的任务类型：{task['operation']}")
        except InterruptedError:
            if self.store.task_cancel_requested(task_id):
                self.store.update_task(
                    task_id,
                    status="cancelled",
                    phase="cancelled",
                    progress={"message": "任务已取消"},
                )
                return self.store.get_task(task_id)
            raise

    def run_once(self) -> dict[str, Any] | None:
        finalize = self.store.next_queued_task(finalize_only=True)
        if finalize is not None:
            return self._process_task(finalize)
        if self.store.has_queued_review_job():
            return run_next_review_job(
                self.store,
                download=self.download,
                engine=self.engine(),
            )
        task = self.store.next_queued_task()
        if task is not None:
            return self._process_task(task)
        cleanup_review_artifacts(self.store)
        return None
