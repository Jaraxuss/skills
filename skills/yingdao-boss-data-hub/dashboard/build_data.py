#!/usr/bin/env python3
"""Build a self-contained customer-success dashboard HTML."""
import json
import os
import sys
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(SCRIPT_DIR, "../../../runtime/yingdao-boss")
DEFAULT_INPUT = os.path.join(RUNTIME_DIR, "latest-reports.json")
DEFAULT_CLIENTS_INPUT = os.path.join(RUNTIME_DIR, "latest-clients.json")
DEFAULT_EXPIRATION_INPUT = os.path.join(RUNTIME_DIR, "contracts-expiration-summary.json")
DEFAULT_APP_RUN_INSIGHTS_INPUT = os.path.join(RUNTIME_DIR, "latest-app-run-insights.json")
DEFAULT_TEMPLATE = os.path.join(SCRIPT_DIR, "_template.html")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "dashboard.html")
PLACEHOLDER = '"__REPORT_DATA_PLACEHOLDER__"'


def read_json(path, required=False, label="data"):
    if not os.path.exists(path):
        if required:
            print(f"❌ Error: {label} not found: {path}")
            sys.exit(1)
        print(f"⚠️  Optional {label} not found, continuing without it: {path}")
        return None

    print(f"📖 Reading {label} from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value if value is not None else ""


def build_client_profiles(data):
    profiles = {}
    rows = (data or {}).get("rows", [])

    for row in rows:
        name = first(row.get("组织名称")) or first(row.get("组织简称"))
        if not name:
            continue

        profile = {
            "name": name,
            "shortName": first(row.get("组织简称")),
            "uuid": first(row.get("组织UUID")),
            "organizationUuid": first(row.get("组织UUID")),
            "customNo": first(row.get("客户编号")),
            "csOwner": first(row.get("客户成功")) or "未填写",
            "coach": first(row.get("RPA教练")),
            "sales": first(row.get("销售人员")),
            "serviceStage": first(row.get("RPA服务阶段")) or "未填写",
            "cooperationStatus": first(row.get("RPA合作状态")) or "未填写",
            "deploymentType": first(row.get("RPA部署类型")) or "未填写",
            "daysRemaining": row.get("RPA剩余天数"),
            "expirationDate": first(row.get("RPA到期日期")),
            "renewalStatus": first(row.get("RPA续费状态")),
            "accountSaturation": row.get("账号饱和度"),
            "health": row.get("健康度"),
            "lastFollowUp": first(row.get("最近跟进时间")),
            "customerTier": first(row.get("客户分层")),
            "renewalQuarter": first(row.get("本年度续费季度")),
            "estimatedRenewalType": first(row.get("预估续费类型")),
            "contractSeniorQuota": row.get("合同高级账号额度"),
            "seniorQuota": row.get("高级账号额度"),
            "openedSeniorAccountCount": row.get("已开通高级账号数量"),
            "usesPersonalEdition": first(row.get("是否使用个人版")),
            "personalUserCount": row.get("个人版用户数量"),
            "personalDeepUserCount": row.get("个人版深度使用用户数量"),
        }

        profiles[name] = profile
        uuid = profile.get("uuid")
        if uuid:
            profiles[uuid] = profile
        custom_no = profile.get("customNo")
        if custom_no:
            profiles[custom_no] = profile

    return profiles


def build_expiration_profiles(data):
    profiles = {}

    for bucket, items in (data or {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            name = item.get("client_name")
            if not name:
                continue

            contract = {
                "bucket": bucket,
                "latestContractNo": item.get("latest_contract_no"),
                "startDate": item.get("min_start_date"),
                "endDate": item.get("max_end_date"),
                "daysRemaining": item.get("days_remaining"),
                "totalAmount": item.get("total_amount"),
                "orderTypes": item.get("order_types") or [],
                "orderDetails": item.get("order_details") or [],
            }
            if name not in profiles:
                profiles[name] = dict(contract)
                profiles[name]["contracts"] = []
            profiles[name]["contracts"].append(contract)

    return profiles


def main():
    parser = argparse.ArgumentParser(description="Generate self-contained customer-success dashboard HTML")
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help="Path to latest-reports.json")
    parser.add_argument("--clients-input", default=DEFAULT_CLIENTS_INPUT, help="Optional path to latest-clients.json")
    parser.add_argument("--expiration-input", default=DEFAULT_EXPIRATION_INPUT, help="Optional path to contracts-expiration-summary.json")
    parser.add_argument("--app-run-insights-input", default=DEFAULT_APP_RUN_INSIGHTS_INPUT, help="Optional path to latest-app-run-insights.json")
    parser.add_argument("--template", "-t", default=DEFAULT_TEMPLATE, help="Path to _template.html")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output dashboard.html path")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    clients_input_path = os.path.abspath(args.clients_input)
    expiration_input_path = os.path.abspath(args.expiration_input)
    app_run_insights_input_path = os.path.abspath(args.app_run_insights_input)
    template_path = os.path.abspath(args.template)
    output_path = os.path.abspath(args.output)

    reports = read_json(input_path, required=True, label="tenant reports")
    clients_data = read_json(clients_input_path, required=False, label="client profiles")
    expiration_data = read_json(expiration_input_path, required=False, label="expiration summary")
    app_run_insights_data = read_json(app_run_insights_input_path, required=False, label="app run insights")

    payload = dict(reports)
    payload["clientProfiles"] = build_client_profiles(clients_data)
    payload["expirationProfiles"] = build_expiration_profiles(expiration_data)
    payload["appRunInsights"] = app_run_insights_data or {}
    payload["dashboardMeta"] = {
        "client_profile_count": len({v.get("name") for v in payload["clientProfiles"].values()}),
        "expiration_profile_count": len(payload["expirationProfiles"]),
        "app_run_insights_available": bool(app_run_insights_data),
        "clients_input": clients_input_path if clients_data else "",
        "expiration_input": expiration_input_path if expiration_data else "",
        "app_run_insights_input": app_run_insights_input_path if app_run_insights_data else "",
    }

    total_rows = len(payload.get("rows", []))
    clients = len(set(r.get("_organizationName", "") for r in payload.get("rows", [])))
    print(f"   → {total_rows} report records, {clients} report clients")
    print(f"   → {payload['dashboardMeta']['client_profile_count']} client profiles")
    print(f"   → {payload['dashboardMeta']['expiration_profile_count']} expiration profiles")
    print(f"   → app run insights: {'available' if app_run_insights_data else 'not available'}")

    if not os.path.exists(template_path):
        print(f"❌ Error: Template not found: {template_path}")
        sys.exit(1)
    print(f"📄 Reading template from: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    if PLACEHOLDER not in template:
        print(f"❌ Error: Placeholder {PLACEHOLDER} not found in template")
        sys.exit(1)

    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = template.replace(PLACEHOLDER, data_js)

    print(f"✅ Writing dashboard to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    file_size = os.path.getsize(output_path)
    if file_size > 1024 * 1024:
        print(f"   → File size: {file_size / (1024*1024):.1f} MB")
    else:
        print(f"   → File size: {file_size / 1024:.0f} KB")
    print("🎉 Done! You can now open dashboard.html directly in any browser.")


if __name__ == "__main__":
    main()
