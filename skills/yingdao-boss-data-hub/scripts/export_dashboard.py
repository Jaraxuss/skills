#!/usr/bin/env python3
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from fetch_clients import (
    ApiError,
    SkillConfigError,
    build_session,
    load_json,
    login_to_yingdao_boss,
    request_json,
    DEFAULT_CONFIG_PATH,
    SHARED_RUNTIME_DIR,
)

DEFAULT_LATEST_CLIENTS_PATH = SHARED_RUNTIME_DIR / "latest-clients.json"
DEFAULT_OUTPUT_DIR = Path("/tmp")

SHEET_NAME_LIST = [
    "企业月数据", "企业汇总数据", "应用月数据", "应用汇总数据", "应用TOP数据",
    "用户月数据", "用户汇总数据", "用户TOP数据", "运行明细数据", "数据大盘",
    "应用TOP增加数据", "应用TOP减少数据",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export tenant dashboard data from Yingdao Boss platform."
    )
    parser.add_argument(
        "--client-names",
        nargs="+",
        required=True,
        metavar="NAME",
        help="One or more client names (组织名称) to export dashboards for",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.local.json",
    )
    parser.add_argument(
        "--clients-input",
        default=str(DEFAULT_LATEST_CLIENTS_PATH),
        help="Path to latest-clients.json (used to look up 组织UUID by 组织名称)",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory to save downloaded xlsx files (default: /tmp or config value)",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Override endDate (format: YYYYMMDD). Defaults to yesterday.",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Override startDate (format: YYYYMMDD). Defaults to endDate minus 365 days.",
    )
    return parser.parse_args()


def compute_date_range(end_date_str: str, start_date_str: str = "") -> tuple[str, str]:
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y%m%d").date()
        except ValueError as exc:
            raise SkillConfigError(
                f"Invalid --end-date format (expected YYYYMMDD): {end_date_str}"
            ) from exc
    else:
        end_date = datetime.now().date() - timedelta(days=1)
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y%m%d").date()
        except ValueError as exc:
            raise SkillConfigError(
                f"Invalid --start-date format (expected YYYYMMDD): {start_date_str}"
            ) from exc
    else:
        start_date = end_date - timedelta(days=365)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def lookup_org_uuids(clients_path: Path, client_names: list[str]) -> dict[str, str]:
    """Read latest-clients.json and map 组织名称 → 组织UUID for the requested names."""
    try:
        data = load_json(clients_path)
    except SkillConfigError as exc:
        raise SkillConfigError(
            f"Cannot read clients file: {clients_path}. "
            "Run fetch_clients.py first to generate the latest client data."
        ) from exc

    rows = data.get("rows") or []
    name_to_uuid: dict[str, str] = {}
    for row in rows:
        name = str(row.get("组织名称") or "").strip()
        uuid = str(row.get("组织UUID") or "").strip()
        if name and uuid:
            name_to_uuid[name] = uuid

    result: dict[str, str] = {}
    missing: list[str] = []
    for name in client_names:
        if name in name_to_uuid:
            result[name] = name_to_uuid[name]
        else:
            missing.append(name)

    if missing:
        raise SkillConfigError(
            f"Could not find 组织UUID for the following clients in {clients_path}: {missing}. "
            "Check that the names exactly match the 组织名称 field and that latest-clients.json is up to date."
        )
    return result


def _boss_headers(access_token: str, referer: str) -> dict[str, str]:
    return {
        "accept": "*/*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "origin": "https://boss.shadow-rpa.net",
        "referer": referer,
    }


def submit_export_request(
    session: requests.Session,
    config: dict[str, Any],
    access_token: str,
    org_uuid: str,
    start_date: str,
    end_date: str,
) -> None:
    """POST the export request for one organization."""
    url = config["endpoints"]["export_tenant_url"]
    payload = {
        "organizationUuid": org_uuid,
        "startDate": start_date,
        "endDate": end_date,
        "sheetNameList": SHEET_NAME_LIST,
    }
    resp = request_json(
        session, "POST", url,
        headers=_boss_headers(access_token, config["endpoints"]["referer"]),
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )
    if not resp.get("success"):
        raise ApiError(f"Export request failed for org {org_uuid}: {resp}")


def fetch_task_page(
    session: requests.Session,
    config: dict[str, Any],
    access_token: str,
    page_size: int = 10,
) -> list[dict[str, Any]]:
    """Fetch the most recent export tasks (sorted desc by createTime)."""
    url = config["endpoints"]["export_task_page_url"]
    payload = {"pageNum": 1, "pageSize": page_size, "taskType": "user"}
    resp = request_json(
        session, "POST", url,
        headers=_boss_headers(access_token, config["endpoints"]["referer"]),
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )
    return resp.get("data") or []


def poll_for_tasks(
    session: requests.Session,
    config: dict[str, Any],
    access_token: str,
    name_to_uuid: dict[str, str],
    end_date: str,
    poll_interval: int,
    poll_max_seconds: int,
    task_page_size: int,
) -> dict[str, dict[str, str]]:
    """
    Poll the task list until every requested client has a matching success task.

    Matching criteria (per task):
      - code == "tenant_board_export"
      - status == "success"
      - fileName contains the client 组织名称
      - fileName contains end_date (ensures we match THIS export, not a historical one)

    Returns {client_name: {"uuid": ..., "fileName": ...}}.
    """
    found: dict[str, dict[str, str]] = {}
    remaining: set[str] = set(name_to_uuid.keys())
    deadline = time.monotonic() + poll_max_seconds

    print(f"Polling for {len(remaining)} export task(s) (max {poll_max_seconds}s)...", file=sys.stderr)

    while remaining and time.monotonic() < deadline:
        tasks = fetch_task_page(session, config, access_token, page_size=task_page_size)
        newly_found: list[str] = []

        for task in tasks:
            if task.get("code") != "tenant_board_export":
                continue
            if task.get("status") != "success":
                continue
            file_name = task.get("fileName") or ""

            for name in list(remaining):
                if name in file_name and end_date in file_name:
                    found[name] = {"uuid": task["uuid"], "fileName": file_name}
                    newly_found.append(name)
                    break

        for name in newly_found:
            remaining.discard(name)
            print(f"  Found task for: {name}", file=sys.stderr)

        if remaining:
            elapsed = int(poll_max_seconds - (deadline - time.monotonic()))
            print(
                f"  [{elapsed}s] Waiting for: {sorted(remaining)}",
                file=sys.stderr,
            )
            time.sleep(poll_interval)

    if remaining:
        raise ApiError(
            f"Timed out after {poll_max_seconds}s waiting for export tasks: "
            f"{sorted(remaining)}. The server may still be processing; try running again."
        )

    return found


def download_task_file(
    session: requests.Session,
    config: dict[str, Any],
    access_token: str,
    task_uuid: str,
    file_name: str,
    output_dir: Path,
) -> Path:
    """Call download/with/audit to obtain the pre-signed URL, then download the xlsx."""
    url = config["endpoints"]["export_download_url"]
    resp = request_json(
        session, "POST", url,
        headers=_boss_headers(access_token, config["endpoints"]["referer"]),
        json={"uuid": task_uuid},
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )
    download_url = resp.get("data") or ""
    if not download_url:
        raise ApiError(f"No download URL returned for task {task_uuid}: {resp}")

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = file_name if file_name.endswith(".xlsx") else f"{file_name}.xlsx"
    output_path = output_dir / safe_name

    try:
        file_resp = session.get(download_url, timeout=120)
        file_resp.raise_for_status()
        output_path.write_bytes(file_resp.content)
    except requests.RequestException as exc:
        raise ApiError(f"Failed to download xlsx for task {task_uuid}: {exc}") from exc

    return output_path


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    clients_path = Path(args.clients_input).expanduser().resolve()

    try:
        config = load_json(config_path)

        endpoints = config.get("endpoints") or {}
        for key in ("export_tenant_url", "export_task_page_url", "export_download_url", "referer"):
            if not endpoints.get(key):
                raise SkillConfigError(
                    f"Missing endpoints.{key} in config. "
                    "Please sync config.local.json from the latest config.template.json."
                )

        export_cfg = config.get("export_dashboard") or {}
        poll_interval = int(export_cfg.get("poll_interval_seconds") or 10)
        poll_max = int(export_cfg.get("poll_max_seconds") or 180)
        task_page_size = int(export_cfg.get("task_page_size") or 10)
        output_dir = Path(
            args.output_dir or export_cfg.get("output_dir") or "/tmp"
        ).expanduser().resolve()

        start_date, end_date = compute_date_range(args.end_date, args.start_date)
        print(f"Date range: {start_date} → {end_date}", file=sys.stderr)

        client_names: list[str] = args.client_names

        # Step 1: look up org UUIDs from latest-clients.json
        print(f"Looking up 组织UUID for {len(client_names)} client(s)...", file=sys.stderr)
        name_to_uuid = lookup_org_uuids(clients_path, client_names)

        # Step 2: authenticate (Boss accessToken only — no AppStudio chain needed)
        session = build_session(config)
        print("Authenticating with Yingdao Boss...", file=sys.stderr)
        access_token = login_to_yingdao_boss(session, config)

        # Step 3: submit export requests for all clients
        print(f"Submitting {len(client_names)} export request(s)...", file=sys.stderr)
        for name, org_uuid in name_to_uuid.items():
            print(f"  → {name} ({org_uuid})", file=sys.stderr)
            submit_export_request(session, config, access_token, org_uuid, start_date, end_date)

        # Step 4: poll until all tasks appear as success
        found_tasks = poll_for_tasks(
            session, config, access_token,
            name_to_uuid=name_to_uuid,
            end_date=end_date,
            poll_interval=poll_interval,
            poll_max_seconds=poll_max,
            task_page_size=task_page_size,
        )

        # Step 5: download each xlsx
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for name, task_info in found_tasks.items():
            task_uuid = task_info["uuid"]
            file_name = task_info["fileName"]
            print(f"  Downloading: {file_name}.xlsx", file=sys.stderr)
            try:
                output_path = download_task_file(
                    session, config, access_token, task_uuid, file_name, output_dir
                )
                results.append({"client": name, "status": "ok", "file": str(output_path)})
                print(f"  Saved: {output_path}", file=sys.stderr)
            except ApiError as exc:
                errors.append({"client": name, "status": "error", "error": str(exc)})
                print(f"  ERROR: {exc}", file=sys.stderr)

        summary = {
            "ok": len(errors) == 0,
            "start_date": start_date,
            "end_date": end_date,
            "results": results + errors,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    except (SkillConfigError, ApiError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
