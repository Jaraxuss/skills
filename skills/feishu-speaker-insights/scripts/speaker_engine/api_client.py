from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .errors import StructuredError
from .util import load_structured


DEFAULT_API_URL = "http://127.0.0.1:8765"


def resolve_api_url(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("FEISHU_SPEAKER_API_URL") or DEFAULT_API_URL).rstrip("/")


def _request(
    api_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {}
        if isinstance(value, dict) and value.get("error_code"):
            raise StructuredError(
                str(value["error_code"]),
                str(value.get("message") or value["error_code"]),
                retryable=bool(value.get("retryable")),
                details=dict(value.get("details") or {}),
            ) from exc
        detail = value.get("detail") if isinstance(value, dict) else None
        raise StructuredError(
            "BACKEND_HTTP_ERROR",
            str(detail or f"声纹后端返回 HTTP {exc.code}"),
            details={"status_code": exc.code},
            retryable=exc.code >= 500,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StructuredError(
            "BACKEND_UNAVAILABLE",
            "无法连接声纹后端；业务命令不会回退为本地数据库操作。",
            details={"api_url": api_url, "reason": str(exc)},
            retryable=True,
        ) from exc
    if not isinstance(value, dict):
        raise StructuredError("INVALID_BACKEND_RESPONSE", "声纹后端返回了无效响应。")
    return value


def agent_api_command(
    command: str,
    *,
    api_url: str | None = None,
    request_path: Path | None = None,
    task_id: str | None = None,
    semantic_path: Path | None = None,
    corrections_path: Path | None = None,
    report_format: str | None = None,
    output_path: Path | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    base = resolve_api_url(api_url)
    if command == "enroll-start":
        if request_path is None:
            raise StructuredError("REQUEST_REQUIRED", "缺少建库请求文件。")
        return _request(base, "POST", "/api/v1/enrollment-tasks", load_structured(request_path.resolve()))
    if command == "enroll-confirm":
        if request_path is None:
            raise StructuredError("REQUEST_REQUIRED", "缺少建库确认文件。")
        payload = load_structured(request_path.resolve())
        internal_id = str(payload.pop("task_id", "") or task_id or "")
        if not internal_id:
            raise StructuredError("TASK_ID_REQUIRED", "确认文件缺少内部任务ID。")
        return _request(base, "POST", f"/api/v1/enrollment-tasks/{internal_id}/confirm", payload)
    if command == "analyze-start":
        if request_path is None:
            raise StructuredError("REQUEST_REQUIRED", "缺少识别请求文件。")
        return _request(base, "POST", "/api/v1/analysis-tasks", load_structured(request_path.resolve()))
    if command == "analyze-complete":
        if not task_id or semantic_path is None:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID或语义结果。")
        return _request(
            base,
            "POST",
            f"/api/v1/analysis-tasks/{task_id}/semantic-result",
            load_structured(semantic_path.resolve()),
        )
    if command == "task-status":
        if not task_id:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID。")
        noun = "enrollment-tasks" if task_id.startswith("task-enroll-") else "analysis-tasks"
        return _request(base, "GET", f"/api/v1/{noun}/{task_id}")
    if command == "semantic-request":
        if not task_id:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID。")
        value = _request(base, "GET", f"/api/v1/analysis-tasks/{task_id}/semantic-request")
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return {"ok": True, "output": str(output_path.resolve())}
        return value
    if command in {"task-cancel", "task-retry"}:
        if not task_id:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID。")
        selected = operation or ("enroll" if task_id.startswith("task-enroll-") else "analyze")
        noun = "enrollment-tasks" if selected == "enroll" else "analysis-tasks"
        action = "cancel" if command == "task-cancel" else "retry"
        return _request(base, "POST", f"/api/v1/{noun}/{task_id}/{action}", {})
    if command == "report":
        if not task_id:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID。")
        selected_format = report_format or "feishu"
        if selected_format in {"feishu", "json"}:
            value = _request(
                base,
                "GET",
                f"/api/v1/analysis-tasks/{task_id}/report?format={selected_format}",
            )
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                return {"ok": True, "format": selected_format, "output": str(output_path.resolve())}
            return value
        if selected_format != "markdown":
            raise StructuredError("INVALID_REPORT_FORMAT", "报告格式必须是 feishu、json 或 markdown。")
        url = f"{base}/api/v1/analysis-tasks/{task_id}/report?format=markdown"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            try:
                value = json.loads(exc.read().decode("utf-8"))
            except Exception:
                value = {}
            if isinstance(value, dict) and value.get("error_code"):
                raise StructuredError(
                    str(value["error_code"]),
                    str(value.get("message") or value["error_code"]),
                    retryable=bool(value.get("retryable")),
                    details=dict(value.get("details") or {}),
                ) from exc
            raise StructuredError(
                "BACKEND_HTTP_ERROR",
                f"声纹后端返回 HTTP {exc.code}",
                details={"status_code": exc.code},
                retryable=exc.code >= 500,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise StructuredError(
                "BACKEND_UNAVAILABLE",
                "无法从声纹后端读取详细报告。",
                details={"api_url": base, "reason": str(exc)},
                retryable=True,
            ) from exc
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            return {"ok": True, "format": "markdown", "output": str(output_path.resolve())}
        return {"ok": True, "format": "markdown", "content": content.decode("utf-8")}
    if command == "analysis-correct":
        if not task_id or corrections_path is None:
            raise StructuredError("TASK_ID_REQUIRED", "缺少任务ID或纠正内容。")
        return _request(
            base,
            "POST",
            f"/api/v1/analysis-tasks/{task_id}/corrections",
            load_structured(corrections_path.resolve()),
        )
    raise StructuredError("UNKNOWN_AGENT_COMMAND", f"不支持的业务命令：{command}")
