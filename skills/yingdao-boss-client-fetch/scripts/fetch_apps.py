#!/usr/bin/env python3
"""
fetch_apps.py

Fetches the "App Dashboard" (Application List) for Yingdao Boss clients.
It supports fetching all clients or targeting specific ones via --client-no or --client-name.
Because the App Dashboard requires a `tenantUuid` rather than the `organizationUuid`,
this script first resolves the `tenantUuid` by calling the `mergeInfo` API.

Usage:
  python3 fetch_apps.py [--client-name "江苏润天"]
"""

import argparse
import json
import sys
import os
import time
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fetch_clients import build_session, login_to_yingdao_boss, request_json, ApiError

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Application lists from Yingdao Boss for clients.")
    parser.add_argument(
        "--config",
        default="runtime/yingdao-boss-client-fetch/config.local.json",
        help="Path to the JSON configuration file",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON file path (overrides config defaults if provided)",
    )
    parser.add_argument(
        "--clients-input",
        default="runtime/yingdao-boss/latest-clients.json",
        help="Path to the input clients JSON file",
    )
    parser.add_argument(
        "--client-no",
        default="",
        help="Fetch apps ONLY for this specific client number (e.g. 20230727-021242)",
    )
    parser.add_argument(
        "--client-name",
        default="",
        help="Fetch apps ONLY for clients whose name contains this string (e.g. 江苏润天)",
    )
    return parser.parse_args()


def get_tenant_uuid(session: Any, config: dict[str, Any], boss_access_token: str, organization_uuid: str) -> str:
    """
    Calls the mergeInfo API to get the enterpriseUuid (which serves as tenantUuid) 
    for a given organizationUuid.
    """
    # Fallback to the endpoint if not in config
    merge_info_url = config.get("endpoints", {}).get(
        "merge_info_url", 
        "https://boss-api.shadow-rpa.net/boss/api/v1/organization/mergeInfo"
    )
    
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {boss_access_token}",
        "referer": config["endpoints"].get("referer", "https://boss.shadow-rpa.net/"),
    }
    
    params = {"organizationUuid": organization_uuid}
    
    try:
        resp = request_json(
            session,
            "GET",
            merge_info_url,
            headers=headers,
            params=params,
            verify=(config.get("ssl_verify") or {}).get("default", True)
        )
        
        data_block = resp.get("data")
        if not data_block or not isinstance(data_block, dict):
            print(f"Warning: mergeInfo for {organization_uuid} returned no data block.", file=sys.stderr)
            return ""
            
        enterprise_uuid = data_block.get("enterpriseUuid", "")
        return enterprise_uuid
    except Exception as e:
        print(f"Failed to get tenantUuid for {organization_uuid}: {e}", file=sys.stderr)
        return ""


def get_app_dashboard_page(session: Any, config: dict[str, Any], boss_access_token: str, tenant_uuid: str, current_page: int, page_size: int) -> dict[str, Any]:
    """
    Fetches a single page of the app dashboard list for a given tenant.
    """
    app_dashboard_url = config.get("endpoints", {}).get(
        "app_dashboard_url", 
        "https://boss-api.shadow-rpa.net/boss/api/v3/aftersales/appData/queryAppDashboardInfo"
    )
    
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {boss_access_token}",
        "content-type": "application/json",
        "referer": config["endpoints"].get("referer", "https://boss.shadow-rpa.net/"),
    }
    
    payload = {
        "tenantUuid": tenant_uuid,
        "status": "r",
        "orderBy": "order by month_run_dura desc",
        "pageIndex": current_page,
        "pageSize": page_size
    }
    
    return request_json(
        session,
        "POST",
        app_dashboard_url,
        headers=headers,
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True)
    )

def extract_app_page_block(response: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    """
    Parses the response and returns (rows, total_pages, total_items).
    """
    data_block = response.get("data")
    if not data_block or not isinstance(data_block, dict):
        raise ApiError("Could not locate data block in response")
        
    rows = data_block.get("result") or []
    if not isinstance(rows, list):
        raise ApiError("App result data is not a list")

    page_info = data_block.get("pageDTO") or {}
    total = page_info.get("total", 0)
    pages = page_info.get("pages", 1)
    
    return rows, pages, total


def fetch_apps_for_clients(config: dict[str, Any], clients: list[dict[str, Any]], page_size: int, target_client_no: str = "", target_client_name: str = "") -> list[dict[str, Any]]:
    session = build_session(config)
    print("Authenticating with Yingdao Boss for apps...", file=sys.stderr)
    boss_access_token = login_to_yingdao_boss(session, config)

    all_apps = []
    
    unique_clients = []
    seen_org_uuids = set()
    
    # Filter clients
    for row in clients:
        custom_no = row.get("客户编号")
        client_name = row.get("组织名称", "")
        org_uuid = row.get("组织UUID")
        
        if not org_uuid:
            continue
            
        if target_client_no and custom_no != target_client_no:
            continue
        if target_client_name and target_client_name not in client_name:
            continue
            
        if org_uuid not in seen_org_uuids:
            seen_org_uuids.add(org_uuid)
            unique_clients.append({
                "custom_no": custom_no,
                "client_name": client_name,
                "org_uuid": org_uuid
            })

    print(f"Found {len(unique_clients)} unique clients. Fetching apps...", file=sys.stderr)
    
    def fetch_single_client(client_info, idx, total_len):
        client_apps = []
        cname = client_info["client_name"]
        org_uuid = client_info["org_uuid"]
        custom_no = client_info["custom_no"]
        
        print(f"[{idx}/{total_len}] Resolving tenantUuid for client: {cname} ({custom_no})", file=sys.stderr)
        
        # 1. Resolve tenantUuid
        tenant_uuid = get_tenant_uuid(session, config, boss_access_token, org_uuid)
        if not tenant_uuid:
            print(f"[{idx}/{total_len}] Skipping {cname}: Could not resolve tenantUuid.", file=sys.stderr)
            return []
            
        print(f"[{idx}/{total_len}] Fetching apps for client: {cname} (Tenant: {tenant_uuid})", file=sys.stderr)
        
        # 2. Fetch pages
        current_page = 1
        while True:
            try:
                response = get_app_dashboard_page(session, config, boss_access_token, tenant_uuid, current_page, page_size)
                page_rows, returned_pages, _ = extract_app_page_block(response)
                
                # Inject tracking metadata
                for r in page_rows:
                    r["_customNo"] = custom_no
                    r["_organizationUuid"] = org_uuid
                    r["_organizationName"] = cname
                    
                client_apps.extend(page_rows)
                
                if current_page >= returned_pages or not page_rows:
                    break
                    
                current_page += 1
            except Exception as e:
                print(f"[{idx}/{total_len}] Error fetching page {current_page} for {cname}: {e}", file=sys.stderr)
                break
                
        return client_apps

    # Use ThreadPoolExecutor to fetch clients concurrently
    max_workers = config.get("network", {}).get("max_threads", 5)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_single_client, c, i, len(unique_clients)) for i, c in enumerate(unique_clients, 1)]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                all_apps.extend(result)
            except Exception as e:
                print(f"Error executing fetch task: {e}", file=sys.stderr)

    return all_apps


def build_output_document(config: dict[str, Any], bg: str, all_apps: list[dict[str, Any]]) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "schema": "yingdao-boss-client-fetch-apps.v1",
        "meta": {
            "fetched_at": fetched_at,
            "business_group": bg,
            "total_apps": len(all_apps),
        },
        "rows": all_apps,
    }

def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()

    if not config_path.is_file():
        print(f"Error: Config file not found at {config_path}", file=sys.stderr)
        return 1

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading config {config_path}: {e}", file=sys.stderr)
        return 1

    clients_path = Path(args.clients_input).expanduser().resolve()
    if not clients_path.is_file():
        print(f"Error: Clients input file not found at {clients_path}", file=sys.stderr)
        return 1

    try:
        with open(clients_path, "r", encoding="utf-8") as f:
            clients_doc = json.load(f)
    except Exception as e:
        print(f"Error reading clients file {clients_path}: {e}", file=sys.stderr)
        return 1

    clients = clients_doc.get("rows", [])
    if not clients:
        print(f"Warning: No clients found in {clients_path}.", file=sys.stderr)
        return 0

    page_size = config.get("defaults", {}).get("page_size", 100)
    bg = clients_doc.get("meta", {}).get("business_group", config.get("defaults", {}).get("default_business_group", ""))

    try:
        all_apps = fetch_apps_for_clients(
            config, 
            clients, 
            page_size, 
            target_client_no=args.client_no, 
            target_client_name=args.client_name
        )
    except ApiError as e:
        print(f"API Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    out_doc = build_output_document(config, bg, all_apps)

    # Determine output path
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        # Save dynamically based on whether it's targeted or bulk
        project_root = Path(__file__).parent.parent.parent.parent  # up to Z7Z8/skills
        runtime_dir = project_root / "runtime" / "yingdao-boss"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        
        if args.client_name:
            out_path = runtime_dir / f"apps-{args.client_name}.json"
        elif args.client_no:
            # Try to get actual name
            cname = args.client_no
            for c in clients:
                if c.get("客户编号") == args.client_no:
                    cname = c.get("组织名称", args.client_no)
                    break
            out_path = runtime_dir / f"apps-{cname}.json"
        else:
            out_path = runtime_dir / "latest-apps.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_doc, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved {len(all_apps)} app records to {out_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output {out_path}: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
