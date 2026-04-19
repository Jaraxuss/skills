#!/usr/bin/env python3
import argparse
import base64
import copy
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
    import urllib3
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ModuleNotFoundError as exc:
    print(
        "Missing dependency: {}. Run `pip install -r skills/yingdao-boss-client-fetch/scripts/requirements.txt` first.".format(exc.name),
        file=sys.stderr,
    )
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "runtime" / "yingdao-boss-client-fetch" / "config.local.json"
TEMPLATE_CONFIG_PATH = SKILL_DIR / "config.template.json"
SHARED_RUNTIME_DIR = REPO_ROOT / "runtime" / "yingdao-boss"
DEFAULT_LATEST_OUTPUT_PATH = SHARED_RUNTIME_DIR / "latest-clients.json"
DEFAULT_ARCHIVE_DIR = SHARED_RUNTIME_DIR / "archive"

PUBLIC_KEY_PEM = b"""
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCnDN8jzUpF33WzhHT2x5no2WDu9IoppXzrdWCgojtnV6bV/iQXvNziOSKcTG5HcM550Ymv3W5qgNxsJ3nHG0l6vS2MK9BGH9Zo9Zd2+ye9D2WJVXWSYHkhJHnlvxOHSbq5C0ZgyJAIWSH6YL0JrO1R0tbW9MkEnEAR84AzWaiRNwIDAQAB
-----END PUBLIC KEY-----
"""


class SkillConfigError(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Yingdao Boss client data for a business group."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.local.json",
    )
    parser.add_argument(
        "--business-group",
        default="",
        help="Override defaults.default_business_group for this run",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional custom output file path. When provided, it overrides the shared-latest storage path.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=0,
        help="Override defaults.page_size for this run",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also write a timestamped archive snapshot while updating the shared latest file.",
    )
    return parser.parse_args()



def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillConfigError(
            f"Config file not found: {path}. Copy {TEMPLATE_CONFIG_PATH.name} to runtime/yingdao-boss-client-fetch/config.local.json (or pass --config) and fill auth.username, auth.password, and defaults.default_business_group first."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SkillConfigError(f"Invalid JSON in config file {path}: {exc}") from exc



def require_string(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise SkillConfigError(
            f"Missing required config: {field_name}. First-time setup requires auth.username, auth.password, and defaults.default_business_group."
        )
    return text



def resolve_run_settings(config: dict[str, Any], args: argparse.Namespace) -> tuple[str, int]:
    auth = config.get("auth") or {}
    defaults = config.get("defaults") or {}

    require_string(auth.get("username"), "auth.username")
    require_string(auth.get("password"), "auth.password")

    business_group = (args.business_group or defaults.get("default_business_group") or "").strip()
    if not business_group:
        raise SkillConfigError(
            "Missing required config: defaults.default_business_group. First-time setup requires auth.username, auth.password, and defaults.default_business_group."
        )

    page_size = args.page_size or defaults.get("page_size") or 100
    try:
        page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise SkillConfigError("defaults.page_size must be an integer") from exc
    if page_size <= 0:
        raise SkillConfigError("defaults.page_size must be greater than 0")

    return business_group, page_size



def rsa_encrypt(password: str) -> str:
    public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
    encrypted_password = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted_password).decode("utf-8")



def build_session(config: dict[str, Any]) -> requests.Session:
    session = requests.Session()
    session.trust_env = bool((config.get("network") or {}).get("use_env_proxy", False))
    return session



def request_json(session: requests.Session, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = session.request(method=method, url=url, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise ApiError(f"HTTP request failed for {method} {url}: {exc}") from exc
    except ValueError as exc:
        raise ApiError(f"Non-JSON response from {method} {url}") from exc



def get_nested(data: Any, path: Iterable[Any]) -> Any:
    current = data
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current



def extract_required(data: Any, candidate_paths: list[list[Any]], label: str) -> Any:
    for path in candidate_paths:
        value = get_nested(data, path)
        if value not in (None, ""):
            return value
    raise ApiError(f"Could not extract {label} from API response")



def login_to_yingdao_boss(session: requests.Session, config: dict[str, Any]) -> str:
    auth = config["auth"]
    endpoints = config["endpoints"]
    verify = (config.get("ssl_verify") or {}).get("boss_login", False)
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    username = str(auth["username"]).strip()
    password = str(auth["password"]).strip()
    payload = {
        "username": username,
        "password": rsa_encrypt(password),
    }
    headers = {"content-type": "application/json;charset=UTF-8"}
    response = request_json(
        session,
        "POST",
        endpoints["boss_login_url"],
        headers=headers,
        json=payload,
        verify=verify,
    )
    return extract_required(response, [["data", "accessToken"]], "Boss accessToken")



def get_ascode(session: requests.Session, config: dict[str, Any], access_token: str) -> str:
    headers = {"authorization": f"Bearer {access_token}"}
    response = request_json(
        session,
        "GET",
        config["endpoints"]["boss_ascode_url"],
        headers=headers,
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )
    return extract_required(response, [["data"]], "Boss ascode")



def get_appstudio_token(session: requests.Session, config: dict[str, Any], ascode: str) -> str:
    response = request_json(
        session,
        "GET",
        config["endpoints"]["appstudio_token_url"],
        params={"code": ascode},
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )
    return extract_required(response, [["data", "accessToken"]], "AppStudio accessToken")



def build_query_payload(config: dict[str, Any], business_group: str, current_page: int, page_size: int) -> dict[str, Any]:
    datasource = config["datasource"]
    fixed_filters = copy.deepcopy(datasource.get("fixed_filters") or [])
    business_group_filter = copy.deepcopy(datasource.get("business_group_filter") or {})
    business_group_filter["values"] = [business_group]

    return {
        "nsId": datasource["nsId"],
        "name": datasource.get("name", "queryTable"),
        "variables": {
            "input_key": {"value": datasource.get("input_key", "")},
            "listView_shaixuan": {
                "instanceValues": [*fixed_filters, business_group_filter],
            },
            "buildShowColumnsData": {
                "data": datasource.get("build_show_columns") or [],
            },
            "table1": {"currentPage": current_page, "pageSize": page_size},
            "getSortCondition": {"value": datasource.get("sort_value")},
        },
        "pageId": datasource["pageId"],
        "envId": datasource.get("envId", 1),
        "editorMode": datasource.get("editorMode", False),
    }



def download_boss_table(session: requests.Session, config: dict[str, Any], appstudio_token: str, business_group: str, current_page: int, page_size: int) -> dict[str, Any]:
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {appstudio_token}",
        "content-type": "application/json",
        "referer": config["endpoints"]["referer"],
    }
    payload = build_query_payload(config, business_group, current_page, page_size)
    return request_json(
        session,
        "POST",
        config["endpoints"]["datasource_exec_url"],
        headers=headers,
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )



def extract_page_block(response: dict[str, Any], page_size: int) -> tuple[list[dict[str, Any]], int, int | None]:
    candidate_paths = [
        ["data", "result", "data", "data"],
        ["data", "result", "data"],
        ["result", "data", "data"],
        ["data", "data"],
        ["data"],
    ]
    block = None
    for path in candidate_paths:
        value = get_nested(response, path)
        if isinstance(value, dict) and "dataList" in value:
            block = value
            break
    if block is None:
        raise ApiError("Could not locate datasource page block containing dataList")

    rows = block.get("dataList") or []
    if not isinstance(rows, list):
        raise ApiError("Datasource response field dataList is not a list")

    total = block.get("total")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None

    pages = block.get("pages")
    try:
        pages = int(pages) if pages is not None else None
    except (TypeError, ValueError):
        pages = None

    if pages is None and total is not None and page_size > 0:
        pages = max(1, math.ceil(total / page_size))

    return rows, pages or 1, total



def fetch_all_rows(config: dict[str, Any], business_group: str, page_size: int) -> dict[str, Any]:
    session = build_session(config)
    print("Authenticating with Yingdao Boss...", file=sys.stderr)
    access_token = login_to_yingdao_boss(session, config)
    ascode = get_ascode(session, config, access_token)
    appstudio_token = get_appstudio_token(session, config, ascode)

    current_page = 1
    total_pages = None
    total_rows = None
    rows: list[dict[str, Any]] = []

    while True:
        print(f"Fetching page {current_page}...", file=sys.stderr)
        response = download_boss_table(session, config, appstudio_token, business_group, current_page, page_size)
        page_rows, returned_pages, returned_total = extract_page_block(response, page_size)
        rows.extend(page_rows)

        if total_pages is None:
            total_pages = returned_pages
        if total_rows is None and returned_total is not None:
            total_rows = returned_total

        if current_page >= returned_pages:
            break
        if not page_rows:
            break

        current_page += 1

    return {
        "business_group": business_group,
        "page_size": page_size,
        "page_count": total_pages or current_page,
        "row_count": len(rows),
        "total": total_rows,
        "rows": rows,
    }



def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "boss_clients"



def resolve_storage_mode(config: dict[str, Any], archive_flag: bool) -> tuple[bool, bool]:
    storage = config.get("storage") or {}
    mode = str(storage.get("mode") or "latest").strip().lower()
    if mode not in {"latest", "archive", "both"}:
        raise SkillConfigError("storage.mode must be one of: latest, archive, both")

    write_latest = mode in {"latest", "both"}
    write_archive = mode in {"archive", "both"}
    if archive_flag:
        write_archive = True
        if mode == "archive":
            write_latest = False
        else:
            write_latest = True
    return write_latest, write_archive



def resolve_path(value: str, base_dir: Path, fallback: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return fallback
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path



def resolve_output_paths(config: dict[str, Any], config_path: Path, business_group: str, output_arg: str, archive_flag: bool) -> list[Path]:
    if output_arg:
        return [Path(output_arg).expanduser().resolve()]

    storage = config.get("storage") or {}
    write_latest, write_archive = resolve_storage_mode(config, archive_flag)
    paths: list[Path] = []

    latest_path = resolve_path(
        storage.get("latest_output_path", ""),
        config_path.parent,
        DEFAULT_LATEST_OUTPUT_PATH,
    )
    archive_dir = resolve_path(
        storage.get("archive_dir", ""),
        config_path.parent,
        DEFAULT_ARCHIVE_DIR,
    )

    if write_latest:
        paths.append(latest_path)
    if write_archive:
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
        filename = f"{sanitize_filename(business_group)}-{timestamp}.json"
        paths.append(archive_dir / filename)

    return paths



def build_output_document(config: dict[str, Any], fetch_result: dict[str, Any]) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat()
    datasource = config.get("datasource") or {}
    return {
        "schema": "yingdao-boss-client-fetch.v1",
        "meta": {
            "fetched_at": fetched_at,
            "business_group": fetch_result["business_group"],
            "page_size": fetch_result["page_size"],
            "page_count": fetch_result["page_count"],
            "row_count": fetch_result["row_count"],
            "total": fetch_result["total"],
            "nsId": datasource.get("nsId"),
            "pageId": datasource.get("pageId"),
        },
        "rows": fetch_result["rows"],
    }



def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    try:
        config = load_json(config_path)
        business_group, page_size = resolve_run_settings(config, args)
        fetch_result = fetch_all_rows(config, business_group, page_size)
        document = build_output_document(config, fetch_result)

        output_paths = resolve_output_paths(config, config_path, business_group, args.output, args.archive)
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            json.dumps(
                {
                    "ok": True,
                    "business_group": document["meta"]["business_group"],
                    "page_count": document["meta"]["page_count"],
                    "row_count": document["meta"]["row_count"],
                    "outputs": [str(p) for p in output_paths],
                    "latest_output": str(output_paths[0]) if output_paths else None,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (SkillConfigError, ApiError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
