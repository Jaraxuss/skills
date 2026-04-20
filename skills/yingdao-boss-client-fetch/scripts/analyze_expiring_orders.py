#!/usr/bin/env python3
"""
analyze_expiring_orders.py

Reads the latest contracts JSON export and categorizes clients based on the maximum 
expiration date (endDate) found within their MOST RECENT contract.
Grouping: Expired, <= 30 Days, 31-60 Days, 61-90 Days, > 90 Days.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Adjust path to find the default location if running from root relative
SHARED_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "yingdao-boss"
DEFAULT_INPUT = SHARED_RUNTIME_DIR / "latest-contracts.json"

class ClientRecord:
    def __init__(self, custom_no, custom_name):
        self.custom_no = custom_no
        self.custom_name = custom_name
        self.contracts = []
        self.max_end_date = None
        self.latest_contract_no = None
        self.min_start_date = None
        self.total_amount = 0.0
        self.order_types = []
        self.order_details = []

def get_datetime(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def main():
    parser = argparse.ArgumentParser(description="Analyze and group expiring contracts.")
    args = parser.parse_args()

    input_path = DEFAULT_INPUT
    if not input_path.exists():
        print(f"Error: Could not find contracts data at {input_path}")
        print("Please run fetch_contracts.py first.")
        sys.exit(1)
        
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_path}: {e}")
        sys.exit(1)

    rows = data.get("rows", [])
    if not rows:
        print("No contracts found to analyze.")
        sys.exit(0)

    # 1. Group contracts by Client ID (customNo)
    clients_map = {}
    for r in rows:
        # customNo can be in _customNo or customIdExtra.no
        custom_no = r.get("_customNo")
        if not custom_no:
            custom_extra = r.get("customIdExtra") or {}
            custom_no = custom_extra.get("no")
            
        if not custom_no:
            continue
            
        custom_name = r.get("customIdExtra", {}).get("name", "Unknown Client")
        
        if custom_no not in clients_map:
            clients_map[custom_no] = ClientRecord(custom_no, custom_name)
            
        clients_map[custom_no].contracts.append(r)

    # 2. Extract Max End Date from the MOST RECENT contract per client
    clients_with_valid_dates = []
    
    for custom_no, record in clients_map.items():
        # Find latest contract based on createTime
        valid_contracts = [c for c in record.contracts if c.get("createTime")]
        if not valid_contracts:
            continue
            
        latest_contract = max(valid_contracts, key=lambda c: get_datetime(c["createTime"]) or datetime.min)
        record.latest_contract_no = latest_contract.get("contractNo", "Unknown")
        
        # Check orders inside latest contract
        orders = latest_contract.get("contractOrderDTOList2", [])
        end_dates = []
        start_dates = []
        total_amount = 0.0
        order_types_set = set()
        order_details = []
        
        for o in orders:
            # We only track expiration dates for subscription-like order types
            order_type = o.get("orderType")
            if order_type not in ("new", "renew", "add"):
                continue
            
            end_date_dt = get_datetime(o.get("endDate"))
            start_date_dt = get_datetime(o.get("startDate"))
            if end_date_dt:
                end_dates.append(end_date_dt)
            if start_date_dt:
                start_dates.append(start_date_dt)
                
            total_amount += float(o.get("actualAmount") or 0.0)
            
            type_mapping = {"new": "新购/新签", "renew": "续费", "add": "增购"}
            mapped_type = type_mapping.get(order_type, order_type)
            if mapped_type:
                order_types_set.add(mapped_type)
                
            details = o.get("itemsDetailDesc", "").strip()
            if details:
                order_details.append(details)
                
        if end_dates:
            record.max_end_date = max(end_dates)
            record.min_start_date = min(start_dates) if start_dates else None
            record.total_amount = total_amount
            record.order_types = list(order_types_set)
            record.order_details = order_details
            
            clients_with_valid_dates.append(record)

    # 3. Categorize and bucket
    today = datetime.now()
    
    categories = {
        "Expired (已过期)": [],
        "0-30 Days": [],
        "31-60 Days": [],
    }
    
    for rec in clients_with_valid_dates:
        days_diff = (rec.max_end_date - today).days
        
        if -30 <= days_diff < 0:
            categories["Expired (已过期)"].append((days_diff, rec))
        elif 0 <= days_diff <= 30:
            categories["0-30 Days"].append((days_diff, rec))
        elif 31 <= days_diff <= 60:
            categories["31-60 Days"].append((days_diff, rec))
            
    # 4. Sort internally from near to far, and output
    # print(f"\n======== Contract Expiration Analysis ========\n")
    print(f"Total Unique Clients Analyzed: {len(clients_with_valid_dates)}\n")
    
    display_order = [
         "Expired (已过期)",
         "0-30 Days",
         "31-60 Days",
    ]
    
    # Pre-format to a nice dictionary/array so we can also dump to JSON if needed
    report_data = {}
    
    for cat in display_order:
        items = categories[cat]
        if not items:
            continue
            
        # Sort ascending by days remaining
        items.sort(key=lambda x: x[0])
        print(f"## {cat} ({len(items)} clients)")
        
        cat_array = []
        for days, rec in items:
            end_date_str = rec.max_end_date.strftime('%Y-%m-%d')
            start_date_str = rec.min_start_date.strftime('%Y-%m-%d') if rec.min_start_date else "未知"
            order_types_str = "、".join(rec.order_types) if rec.order_types else "未知"
            amount_str = f"¥{rec.total_amount:,.2f}"
            
            print(f"  - {rec.custom_name}")
            print(f"    合同编号: {rec.latest_contract_no}")
            print(f"    订单起止: {start_date_str} 至 {end_date_str} (剩余 {days} 天)")
            print(f"    总金额:   {amount_str}")
            print(f"    订单类型: {order_types_str}")
            
            if rec.order_details:
                print(f"    详情:")
                for i, detail in enumerate(set(rec.order_details)):
                    lines = [line.strip() for line in detail.split('\n') if line.strip()]
                    for line in lines:
                        print(f"      {line}")
                    if i < len(set(rec.order_details)) - 1:
                        print(f"      ---")
            print("")
            
            cat_array.append({
                "client_name": rec.custom_name,
                "latest_contract_no": rec.latest_contract_no,
                "min_start_date": start_date_str,
                "max_end_date": end_date_str,
                "days_remaining": days,
                "total_amount": rec.total_amount,
                "order_types": rec.order_types,
                "order_details": list(set(rec.order_details))
            })
            
        report_data[cat] = cat_array

    # Automatically save a JSON output of the parsed summary
    output_summary = SHARED_RUNTIME_DIR / "contracts-expiration-summary.json"
    with open(output_summary, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
        
    print(f"Summary JSON saved to: {output_summary}")

if __name__ == "__main__":
    main()
