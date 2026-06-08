#!/usr/bin/env python3
import argparse
import copy
import json
import math
import sys
import time
import os
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import shared logic from fetch_clients
from fetch_clients import (
    ApiError,
    SkillConfigError,
    build_session,
    get_appstudio_token,
    get_ascode,
    get_nested,
    load_json,
    login_to_yingdao_boss,
    request_json,
    resolve_output_paths,
    sanitize_filename,
    DEFAULT_CONFIG_PATH,
    SHARED_RUNTIME_DIR,
)

DEFAULT_LATEST_CLIENTS_PATH = SHARED_RUNTIME_DIR / "latest-clients.json"
DEFAULT_LATEST_CONTRACTS_PATH = SHARED_RUNTIME_DIR / "latest-contracts.json"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Yingdao Boss contract/order data for fetched clients."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.local.json",
    )
    parser.add_argument(
        "--clients-input",
        default=str(DEFAULT_LATEST_CLIENTS_PATH),
        help="Path to the shared clients json output file",
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
        "--client-no",
        default="",
        help="Fetch contracts for a specific client number (customNo)",
    )
    parser.add_argument(
        "--client-name",
        default="",
        help="Fetch contracts for a specific client name",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also write a timestamped archive snapshot while updating the shared latest file.",
    )
    return parser.parse_args()


def load_clients(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillConfigError(
            f"Clients file not found: {path}. Run fetch_clients.py first."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SkillConfigError(f"Invalid JSON in clients file {path}: {exc}") from exc


def build_contract_query_payload(config: dict[str, Any], custom_no: str, current_page: int, page_size: int) -> dict[str, Any]:
    return {
        "customNo": custom_no,
        "statusList": ["approved", "auditing"],
        "paymentStatusList": [],
        "page": current_page,
        "size": page_size,
        "sortColumn": "id",
        "isAsc": False
    }

def extract_contract_page_block(response: dict[str, Any], page_size: int) -> tuple[list[dict[str, Any]], int, int | None]:
    rows = response.get("data") or []
    if not isinstance(rows, list):
        raise ApiError("Contract data ('data' field) is not a list")

    page_info = response.get("page") or {}
    total = page_info.get("total")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None

    pages = page_info.get("pages")
    try:
        pages = int(pages) if pages is not None else None
    except (TypeError, ValueError):
        pages = None

    if pages is None and total is not None and page_size > 0:
        pages = max(1, math.ceil(total / page_size))

    return rows, pages or 1, total

def download_contracts(session: Any, config: dict[str, Any], access_token: str, custom_no: str, current_page: int, page_size: int) -> dict[str, Any]:
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "referer": config["endpoints"]["referer"],
    }
    payload = build_contract_query_payload(config, custom_no, current_page, page_size)
    return request_json(
        session,
        "POST",
        config["endpoints"]["contracts_query_url"],
        headers=headers,
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True),
    )

def fetch_contracts_for_clients(config: dict[str, Any], clients: list[dict[str, Any]], page_size: int, target_client_no: str = "", target_client_name: str = "") -> list[dict[str, Any]]:
    session = build_session(config)
    print("Authenticating with Yingdao Boss for contracts...", file=sys.stderr)
    access_token = login_to_yingdao_boss(session, config)

    all_contracts = []
    
    unique_clients = []
    seen_custom_no = set()
    for row in clients:
        custom_no = row.get("客户编号")
        client_name = row.get("组织名称", "")
        
        if target_client_no and custom_no != target_client_no:
            continue
        if target_client_name and target_client_name not in client_name:
            continue
            
        if custom_no and custom_no not in seen_custom_no:
            seen_custom_no.add(custom_no)
            unique_clients.append(custom_no)

    print(f"Found {len(unique_clients)} unique clients. Fetching contracts...", file=sys.stderr)
    
    def fetch_single_client(custom_no, idx, total_len):
        client_contracts = []
        print(f"[{idx}/{total_len}] Fetching contracts for client: {custom_no}", file=sys.stderr)
        current_page = 1
        
        while True:
            response = download_contracts(session, config, access_token, custom_no, current_page, page_size)
            page_rows, returned_pages, _ = extract_contract_page_block(response, page_size)
            
            # Inject customNo to identify later if needed
            for r in page_rows:
                r["_customNo"] = custom_no
                
            client_contracts.extend(page_rows)
            
            if current_page >= returned_pages or not page_rows:
                break
                
            current_page += 1
            
        return client_contracts

    # Use ThreadPoolExecutor to fetch clients concurrently
    max_workers = config.get("network", {}).get("max_threads", 5)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_single_client, cno, i, len(unique_clients)) for i, cno in enumerate(unique_clients, 1)]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                all_contracts.extend(result)
            except Exception as e:
                print(f"Error fetching contract: {e}", file=sys.stderr)

    return all_contracts


def build_output_document(config: dict[str, Any], bg: str, all_contracts: list[dict[str, Any]]) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "schema": "yingdao-boss-client-fetch-contracts.v1",
        "meta": {
            "fetched_at": fetched_at,
            "business_group": bg,
            "total_contracts": len(all_contracts),
        },
        "rows": all_contracts,
    }

def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    try:
        config = load_json(config_path)
        
        # Load clients
        clients_input_path = Path(args.clients_input).expanduser().resolve()
        clients_doc = load_clients(clients_input_path)
        clients_rows = clients_doc.get("rows", [])
        business_group = clients_doc.get("meta", {}).get("business_group", "unknown")
        
        page_size = args.page_size or config.get("defaults", {}).get("page_size") or 100
        
        # Fetch contracts
        all_contracts = fetch_contracts_for_clients(config, clients_rows, page_size, args.client_no, args.client_name)
        document = build_output_document(config, business_group, all_contracts)
        
        # If fetching for a specific client, write to a designated file and do NOT overwrite the main shared dataset
        if args.client_no or args.client_name:
            client_id = args.client_name or args.client_no
            safe_name = "".join(c for c in client_id if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_")
            if not safe_name:
                safe_name = "custom_client"
                
            # output_dir should be <workspace_root>/runtime/yingdao-boss
            # config_path is like .../skills/skills/yingdao-boss-client-fetch/config.local.json
            output_dir = config_path.parent.parent.parent / "runtime" / "yingdao-boss"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_file = output_dir / f"contracts-{safe_name}.json"
            output_file.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            
            print(f"\n✅ Fetched contracts for specific client '{client_id}'. Saved to: {output_file}")
            return 0

        # Output resolution, similar to clients script
        # Temporarily patch DEFAULT_LATEST_OUTPUT_PATH so resolve_output_paths uses our contracts path
        import fetch_clients
        original_default_latest = fetch_clients.DEFAULT_LATEST_OUTPUT_PATH
        fetch_clients.DEFAULT_LATEST_OUTPUT_PATH = config_path.parent.parent / "yingdao-boss" / "latest-contracts.json"

        output_paths = resolve_output_paths(config, config_path, business_group + "-contracts", args.output, args.archive)
        
        # Restore
        fetch_clients.DEFAULT_LATEST_OUTPUT_PATH = original_default_latest

        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            json.dumps(
                {
                    "ok": True,
                    "business_group": business_group,
                    "total_contracts": len(all_contracts),
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
