#!/usr/bin/env python3
"""
fetch_tenant_reports.py

Fetches the "Tenant Data Reports" (queryTenantDataDayListRange) for Yingdao Boss clients.
It supports fetching all clients or targeting specific ones via --client-no or --client-name.

Usage:
  python3 fetch_tenant_reports.py [--client-name "妮茜雅"] [--start-date 20250616] [--end-date 20260615]
"""

import argparse
import json
import sys
import os
import time
import concurrent.futures
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Re-use existing utility methods from fetch_clients
from fetch_clients import build_session, login_to_yingdao_boss, request_json, ApiError

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Tenant Data Reports from Yingdao Boss for clients.")
    parser.add_argument(
        "--config",
        default="runtime/yingdao-boss-data-hub/config.local.json",
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
        help="Fetch reports ONLY for this specific client number",
    )
    parser.add_argument(
        "--client-name",
        default="",
        help="Fetch reports ONLY for clients whose name contains this string",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Start date in YYYYMMDD format (defaults to 365 days before end date)",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="End date in YYYYMMDD format (defaults to yesterday)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of clients to fetch",
    )
    parser.add_argument(
        "--random-select",
        action="store_true",
        help="Randomly select clients when limit is specified",
    )
    return parser.parse_args()


def compute_date_range(start_date_str: str, end_date_str: str) -> tuple[str, str]:
    """
    Computes start and end dates based on input arguments.
    Defaults end_date to yesterday and start_date to 365 days before end_date.
    """
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid --end-date format (expected YYYYMMDD): {end_date_str}") from exc
    else:
        end_date = datetime.now().date() - timedelta(days=1)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid --start-date format (expected YYYYMMDD): {start_date_str}") from exc
    else:
        start_date = end_date - timedelta(days=365)

    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def get_tenant_uuid(session: Any, config: dict[str, Any], boss_access_token: str, organization_uuid: str) -> str:
    """
    Calls the mergeInfo API to get the enterpriseUuid (which serves as tenantUuid) 
    for a given organizationUuid.
    """
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
            return organization_uuid
            
        enterprise_uuid = data_block.get("enterpriseUuid", "")
        return enterprise_uuid or organization_uuid
    except Exception as e:
        print(f"Warning: Failed to get mergeInfo for {organization_uuid} ({e}). Falling back to org_uuid.", file=sys.stderr)
        return organization_uuid


def get_tenant_reports(session: Any, config: dict[str, Any], boss_access_token: str, tenant_uuid: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """
    Fetches the daily tenant data report for a given tenant UUID.
    """
    url = config.get("endpoints", {}).get(
        "tenant_data_day_list_range_url",
        "https://boss-api.shadow-rpa.net/boss/api/v3/aftersales/tenantData/queryTenantDataDayListRange"
    )
    
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {boss_access_token}",
        "content-type": "application/json",
        "referer": config["endpoints"].get("referer", "https://boss.shadow-rpa.net/"),
    }
    
    payload = {
        "tenantUuid": tenant_uuid,
        "startDate": start_date,
        "endDate": end_date
    }
    
    resp = request_json(
        session,
        "POST",
        url,
        headers=headers,
        json=payload,
        verify=(config.get("ssl_verify") or {}).get("default", True)
    )
    
    if not resp.get("success"):
        raise ApiError(f"API returned success=false: {resp.get('code')} - {resp.get('msg')}")
        
    data_list = resp.get("data") or []
    if not isinstance(data_list, list):
        raise ApiError("Tenant reports result data is not a list")
        
    return data_list


def fetch_reports_for_clients(
    config: dict[str, Any], 
    clients: list[dict[str, Any]], 
    start_date: str,
    end_date: str,
    target_client_no: str = "", 
    target_client_name: str = "",
    limit: int = 0,
    random_select: bool = False
) -> list[dict[str, Any]]:
    session = build_session(config)
    print("Authenticating with Yingdao Boss for reports...", file=sys.stderr)
    boss_access_token = login_to_yingdao_boss(session, config)

    all_reports = []
    
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
            
        # Filter out private cloud clients since their tenant data cannot be accessed
        if "私有云" in row.get("RPA部署类型", []):
            continue
            
        if org_uuid not in seen_org_uuids:
            seen_org_uuids.add(org_uuid)
            unique_clients.append({
                "custom_no": custom_no,
                "client_name": client_name,
                "org_uuid": org_uuid
            })

    if random_select:
        import random
        random.shuffle(unique_clients)

    if limit > 0:
        unique_clients = unique_clients[:limit]

    delay = float(config.get("network", {}).get("request_delay_seconds", 0.5))
    print(f"Found {len(unique_clients)} unique clients. Fetching reports...", file=sys.stderr)
    
    def fetch_single_client(client_info, idx, total_len):
        client_reports = []
        cname = client_info["client_name"]
        org_uuid = client_info["org_uuid"]
        custom_no = client_info["custom_no"]
        
        # Resolve tenantUuid (falls back to org_uuid if no merge record exists)
        tenant_uuid = get_tenant_uuid(session, config, boss_access_token, org_uuid) or org_uuid
        
        if delay > 0:
            time.sleep(delay)
            
        print(f"[{idx}/{total_len}] Fetching reports for client: {cname} (Tenant: {tenant_uuid})", file=sys.stderr)
        
        retries = 3
        while retries > 0:
            try:
                reports = get_tenant_reports(session, config, boss_access_token, tenant_uuid, start_date, end_date)
                # Inject tracking metadata
                for r in reports:
                    r["_customNo"] = custom_no
                    r["_organizationUuid"] = org_uuid
                    r["_organizationName"] = cname
                    
                client_reports.extend(reports)
                break
            except Exception as e:
                retries -= 1
                if retries == 0:
                    print(f"[{idx}/{total_len}] Error fetching reports for {cname} after retries: {e}", file=sys.stderr)
                    return client_reports
                time.sleep(1)
                
        if delay > 0:
            time.sleep(delay)
            
        return client_reports

    # Use ThreadPoolExecutor to fetch clients concurrently
    max_workers = int(config.get("network", {}).get("max_threads", 2))
    print(f"Starting fetch using max_threads={max_workers}, throttling={delay}s...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_single_client, c, i, len(unique_clients)) for i, c in enumerate(unique_clients, 1)]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                all_reports.extend(result)
            except Exception as e:
                print(f"Error executing fetch task: {e}", file=sys.stderr)

    return all_reports


def build_output_document(config: dict[str, Any], bg: str, start_date: str, end_date: str, all_reports: list[dict[str, Any]]) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat()
    return {
        "schema": "yingdao-boss-data-hub-tenant-reports.v1",
        "meta": {
            "fetched_at": fetched_at,
            "business_group": bg,
            "start_date": start_date,
            "end_date": end_date,
            "total_records": len(all_reports),
        },
        "rows": all_reports,
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

    bg = clients_doc.get("meta", {}).get("business_group", config.get("defaults", {}).get("default_business_group", ""))

    try:
        start_date, end_date = compute_date_range(args.start_date, args.end_date)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Querying daily reports from {start_date} to {end_date}", file=sys.stderr)

    try:
        all_reports = fetch_reports_for_clients(
            config, 
            clients, 
            start_date,
            end_date,
            target_client_no=args.client_no, 
            target_client_name=args.client_name,
            limit=args.limit,
            random_select=args.random_select
        )
    except ApiError as e:
        print(f"API Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    out_doc = build_output_document(config, bg, start_date, end_date, all_reports)

    # Determine output path
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        project_root = Path(__file__).parent.parent.parent.parent  # up to Z7Z8/skills
        runtime_dir = project_root / "runtime" / "yingdao-boss"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        
        if args.client_name:
            out_path = runtime_dir / f"reports-{args.client_name}.json"
        elif args.client_no:
            # Try to get actual name
            cname = args.client_no
            for c in clients:
                if c.get("客户编号") == args.client_no:
                    cname = c.get("组织名称", args.client_no)
                    break
            out_path = runtime_dir / f"reports-{cname}.json"
        else:
            out_path = runtime_dir / "latest-reports.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_doc, f, indent=2, ensure_ascii=False)
        print(f"Successfully saved {len(all_reports)} daily report records to {out_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output {out_path}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
