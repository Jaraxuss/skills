#!/usr/bin/env python3
"""Build a self-contained renewal performance dashboard from local BOSS data."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
RESOLVED_SCRIPT = Path(__file__).resolve()
WORKSPACE_DIR = RESOLVED_SCRIPT.parents[3] if len(RESOLVED_SCRIPT.parents) > 3 else Path.cwd()
RUNTIME_DIR = WORKSPACE_DIR / "runtime" / "yingdao-boss"
DEFAULT_CLIENTS_INPUT = RUNTIME_DIR / "latest-clients.json"
DEFAULT_CONTRACTS_INPUT = RUNTIME_DIR / "latest-contracts.json"
DEFAULT_TEMPLATE = SCRIPT_DIR / "_renewal_performance_template.html"
DEFAULT_OUTPUT = SCRIPT_DIR / "renewal_performance.html"
PLACEHOLDER = '"__RENEWAL_DATA_PLACEHOLDER__"'

BOSS_CONTRACT_BASE = "https://boss.shadow-rpa.net/simple/manage/microApp/boss/oms/contractDetail?contractNo="
BOSS_ENTERPRISE_BASE = "https://boss.shadow-rpa.net/simple/manage/microApp/boss/busi/enterpriseDetail?organizationUuid="
DELTA_TOLERANCE = 10.0
PRE_RENEWAL_ADD_END_TOLERANCE_DAYS = 7

PRODUCT_LABELS = {
    "rpa": "RPA",
    "business_connector": "数据连接器",
    "ap": "AI power",
}
PERIODIC_PRODUCTS = set(PRODUCT_LABELS.values())
BASE_ORDER_TYPES = {"new", "renew"}
ADD_ORDER_TYPE = "add"
RPA_PRODUCT_LINE = "rpa"


def read_json(path: Path, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required input not found: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:10], text.replace(" ", "T")):
        try:
            if len(candidate) == 10:
                return date.fromisoformat(candidate)
            return datetime.fromisoformat(candidate).date()
        except Exception:
            continue
    return None


def iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def quarter_for(d: date) -> str:
    return f"q{((d.month - 1) // 3) + 1}"


def service_days(start: date | None, end: date | None) -> int:
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def annualize(amount: float, days: int) -> float:
    if not days:
        return amount
    return amount / days * 365


def normalize_delta(value: float) -> float:
    return 0.0 if abs(value) < DELTA_TOLERANCE else value


def as_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def normalize_product_line(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip().lower()]


def product_label(order: dict[str, Any]) -> str:
    items = order.get("items") or {}
    commodity = order.get("commodityIdExtra") or {}
    code = items.get("productCode") or commodity.get("product") or ""
    if str(code) in PRODUCT_LABELS:
        return PRODUCT_LABELS[str(code)]
    product_line = normalize_product_line(commodity.get("productLine") or order.get("productLine"))
    is_period = as_bool(commodity.get("isPeriod"))
    if RPA_PRODUCT_LINE in product_line and is_period:
        return "RPA"
    return ""


def product_name(order: dict[str, Any]) -> str:
    items = order.get("items") or {}
    commodity = order.get("commodityIdExtra") or {}
    return (
        str(commodity.get("name") or "").strip()
        or str(items.get("productName") or "").strip()
        or str(order.get("commodityName") or "").strip()
        or product_label(order)
    )


def product_code(order: dict[str, Any]) -> str:
    items = order.get("items") or {}
    commodity = order.get("commodityIdExtra") or {}
    return str(items.get("productCode") or commodity.get("product") or "").strip()


def contract_total_amount(contract: dict[str, Any]) -> float:
    total = as_float(contract.get("totalAmount"))
    if total:
        return total
    payment = as_float(contract.get("paymentAmount"))
    if payment:
        return payment
    return sum(as_float(order.get("actualAmount")) for order in contract.get("contractOrderDTOList2") or [])


def is_buyout(order: dict[str, Any]) -> bool:
    items = order.get("items") or {}
    commodity = order.get("commodityIdExtra") or {}
    return bool(
        order.get("isBuyout")
        or commodity.get("isBuyout")
        or items.get("productIsBuyOut")
    )


def order_qty(order: dict[str, Any], product: str) -> Any:
    items = order.get("items") or {}
    if product == "RPA":
        return items.get("rpaAccountNum") or items.get("skuBuyNum") or items.get("buyNum")
    if product == "数据连接器":
        return {
            "apps": items.get("contentBusinessAppNum") or 0,
            "robots": items.get("contentBusinessRobotNum") or 0,
        }
    if product == "AI power":
        return items.get("buyNum") or items.get("skuBuyNum") or 1
    return items.get("skuBuyNum") or items.get("buyNum")


def format_qty(qty: Any, product: str) -> str:
    if product == "数据连接器" and isinstance(qty, dict):
        parts = []
        if qty.get("apps"):
            parts.append(f"应用{qty['apps']}")
        if qty.get("robots"):
            parts.append(f"机器人{qty['robots']}")
        return "、".join(parts) or "基础服务"
    if qty in (None, ""):
        return "-"
    return str(qty)


def numeric_qty(qty: Any) -> float | None:
    if isinstance(qty, (int, float)):
        return float(qty)
    return None


def order_type_label(order_type: str) -> str:
    return {
        "new": "新购",
        "renew": "续费",
        "add": "增购",
        "gift": "赠送",
        "charge": "收费",
    }.get(order_type, order_type or "-")


def details_text(order: dict[str, Any]) -> str:
    return "\n".join(
        line.strip()
        for line in str(order.get("itemsDetailDesc") or "").replace("\r", "").split("\n")
        if line.strip()
    )


def build_client_profiles(clients_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for row in clients_data.get("rows") or []:
        custom_no = str(first(row.get("客户编号")) or "").strip()
        name = str(first(row.get("组织名称")) or first(row.get("组织简称")) or custom_no).strip()
        if not custom_no:
            continue
        organization_uuid = str(first(row.get("组织UUID")) or "").strip()
        profiles[custom_no] = {
            "customNo": custom_no,
            "name": name,
            "shortName": first(row.get("组织简称")) or "",
            "organizationUuid": organization_uuid,
            "enterpriseUrl": f"{BOSS_ENTERPRISE_BASE}{organization_uuid}" if organization_uuid else "",
            "csOwner": first(row.get("客户成功")) or "未填写",
            "sales": first(row.get("销售人员")) or "",
            "serviceStage": first(row.get("RPA服务阶段")) or "",
            "cooperationStatus": first(row.get("RPA合作状态")) or "",
        }
    return profiles


def collect_orders(contracts_data: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for contract in contracts_data.get("rows") or []:
        custom_extra = contract.get("customIdExtra") or {}
        custom_no = str(contract.get("_customNo") or custom_extra.get("no") or "").strip()
        if not custom_no:
            continue
        profile = profiles.get(custom_no) or {}
        client_name = profile.get("name") or custom_extra.get("name") or custom_no
        contract_no = contract.get("contractNo") or ""
        contract_amount = contract_total_amount(contract)
        contract_url = (
            (contract.get("contractIdExtra") or {}).get("link")
            or f"{BOSS_CONTRACT_BASE}{contract_no}"
            if contract_no
            else ""
        )
        for index, raw in enumerate(contract.get("contractOrderDTOList2") or []):
            product = product_label(raw)
            if product not in PERIODIC_PRODUCTS:
                continue
            if is_buyout(raw):
                continue
            order_type = str(raw.get("orderType") or "")
            start = parse_date(raw.get("startDate"))
            end = parse_date(raw.get("endDate"))
            amount = as_float(raw.get("actualAmount"))
            qty = order_qty(raw, product)
            order_no = raw.get("contractOrderNo") or raw.get("id") or str(index)
            order_id = "|".join(
                [
                    custom_no,
                    product,
                    contract_no,
                    str(order_no),
                    order_type,
                    iso(start),
                    iso(end),
                    f"{amount:.2f}",
                ]
            )
            organization_uuid = profile.get("organizationUuid") or ""
            orders.append(
                {
                    "id": order_id,
                    "clientName": client_name,
                    "customNo": custom_no,
                    "organizationUuid": organization_uuid,
                    "enterpriseUrl": profile.get("enterpriseUrl") or (
                        f"{BOSS_ENTERPRISE_BASE}{organization_uuid}" if organization_uuid else ""
                    ),
                    "csOwner": profile.get("csOwner") or "未填写",
                    "sales": profile.get("sales") or "",
                    "serviceStage": profile.get("serviceStage") or "",
                    "cooperationStatus": profile.get("cooperationStatus") or "",
                    "contractNo": contract_no,
                    "contractUrl": contract_url,
                    "contractTotalAmount": contract_amount,
                    "orderNo": str(order_no),
                    "orderType": order_type,
                    "orderTypeLabel": order_type_label(order_type),
                    "productCode": product_code(raw),
                    "productName": product_name(raw),
                    "isBuyout": is_buyout(raw),
                    "isGift": as_bool(raw.get("isGift")),
                    "createDate": iso(parse_date(raw.get("createTime") or contract.get("createTime"))),
                    "startDate": iso(start),
                    "endDate": iso(end),
                    "start": start,
                    "end": end,
                    "amount": amount,
                    "product": product,
                    "qty": qty,
                    "qtyNumber": numeric_qty(qty),
                    "qtyText": format_qty(qty, product),
                    "serviceDays": service_days(start, end),
                    "details": details_text(raw),
                }
            )
    return orders


def serialize_order(order: dict[str, Any] | None) -> dict[str, Any] | None:
    if not order:
        return None
    return {
        "id": order.get("id") or "",
        "contractNo": order.get("contractNo") or "",
        "contractUrl": order.get("contractUrl") or "",
        "contractTotalAmount": order.get("contractTotalAmount") or 0.0,
        "orderNo": order.get("orderNo") or "",
        "orderType": order.get("orderType") or "",
        "orderTypeLabel": order.get("orderTypeLabel") or order_type_label(order.get("orderType") or ""),
        "productCode": order.get("productCode") or "",
        "productName": order.get("productName") or order.get("product") or "",
        "isBuyout": bool(order.get("isBuyout")),
        "isGift": bool(order.get("isGift")),
        "createDate": order.get("createDate") or "",
        "startDate": order.get("startDate") or "",
        "endDate": order.get("endDate") or "",
        "amount": order.get("amount") or 0.0,
        "product": order.get("product") or "",
        "qtyText": order.get("qtyText") or "",
        "qtyNumber": order.get("qtyNumber"),
        "serviceDays": order.get("serviceDays") or 0,
        "details": order.get("details") or "",
    }


def add_with_arr(order: dict[str, Any]) -> dict[str, Any]:
    doc = serialize_order(order) or {}
    doc["arrAmount"] = annualize(order["amount"], order["serviceDays"])
    return doc


def same_customer_product(order: dict[str, Any], custom_no: str, product: str) -> bool:
    return order["customNo"] == custom_no and order["product"] == product


def find_renewal(base: dict[str, Any], orders: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        o
        for o in orders
        if same_customer_product(o, base["customNo"], base["product"])
        and o["orderType"] == "renew"
        and o.get("end")
        and o["end"] > base["end"]
        and o["id"] != base["id"]
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda x: (
            x["start"] or date.max,
            x["end"] or date.max,
            x["createDate"],
            x["contractNo"],
            x["orderNo"],
        ),
    )


def pre_renewal_adds(base: dict[str, Any], orders: list[dict[str, Any]], renew: dict[str, Any] | None) -> list[dict[str, Any]]:
    baseline_end_limit = base["end"] + timedelta(days=PRE_RENEWAL_ADD_END_TOLERANCE_DAYS)
    return sorted(
        [
            o
            for o in orders
            if same_customer_product(o, base["customNo"], base["product"])
            and o["orderType"] == ADD_ORDER_TYPE
            and o.get("start")
            and o.get("end")
            and o["start"] <= base["end"]
            and o["end"] >= base["end"]
            and o["end"] <= baseline_end_limit
            and (not renew or o["contractNo"] != renew["contractNo"])
        ],
        key=lambda x: (x["start"], x["end"], x["contractNo"], x["orderNo"]),
    )


def renewal_status(renew: dict[str, Any] | None, delta_arr: float) -> tuple[str, str]:
    if not renew:
        return "未续/断约", "churn"
    if delta_arr > 0:
        return "续费增购", "renew_up"
    if delta_arr < 0:
        return "续费减购", "renew_down"
    return "续费无变化", "renew_flat"


def build_due_rows(orders: list[dict[str, Any]], as_of_date: date) -> list[dict[str, Any]]:
    base_orders = [o for o in orders if o["orderType"] in BASE_ORDER_TYPES and o.get("end")]
    by_key: dict[tuple[str, str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for order in base_orders:
        assessment_start = order["end"] + timedelta(days=1)
        by_key[(order["customNo"], order["product"], assessment_start.year, quarter_for(assessment_start))].append(order)

    rows: list[dict[str, Any]] = []
    for (custom_no, product, year, quarter), candidates in by_key.items():
        base = max(candidates, key=lambda x: (x["end"], x["start"] or date.min, x["createDate"], x["contractNo"], x["orderNo"]))
        assessment_start = base["end"] + timedelta(days=1)
        renew = find_renewal(base, orders)
        baseline_adds = pre_renewal_adds(base, orders, renew)
        baseline_add_docs = [add_with_arr(add) for add in baseline_adds]

        baseline_amount = base["amount"] + sum(add["amount"] for add in baseline_adds)
        baseline_arr = base["amount"] + sum(add["arrAmount"] for add in baseline_add_docs)
        renewal_raw_delta_arr = (renew["amount"] - baseline_arr) if renew else 0.0
        renewal_delta_arr = normalize_delta(renewal_raw_delta_arr) if renew else 0.0
        status, status_group = renewal_status(renew, renewal_delta_arr)
        if not renew and base["end"] >= as_of_date:
            status = "待续/未到期"
            status_group = "pending"

        qty_delta = None
        if renew and base.get("qtyNumber") is not None and renew.get("qtyNumber") is not None:
            qty_delta = renew["qtyNumber"] - base["qtyNumber"]

        churn_amount = 0.0
        churn_arr = 0.0
        if not renew and status_group == "churn":
            churn_amount = -baseline_amount
            churn_arr = -baseline_arr

        row_id = f"{custom_no}|{product}|{year}|{quarter}|{base['contractNo']}|{base['orderNo']}"
        rows.append(
            {
                "id": row_id,
                "clientName": base["clientName"],
                "customNo": custom_no,
                "organizationUuid": base.get("organizationUuid") or "",
                "enterpriseUrl": base.get("enterpriseUrl") or "",
                "csOwner": base.get("csOwner") or "未填写",
                "sales": base.get("sales") or "",
                "serviceStage": base.get("serviceStage") or "",
                "cooperationStatus": base.get("cooperationStatus") or "",
                "year": year,
                "quarter": quarter,
                "period": f"{year} {quarter.upper()}",
                "assessmentStart": iso(assessment_start),
                "product": product,
                "base": serialize_order(base),
                "renewal": serialize_order(renew) if renew else None,
                "preRenewalAdds": baseline_add_docs,
                "status": status,
                "statusGroup": status_group,
                "qtyDelta": qty_delta,
                "baselineAmount": baseline_amount,
                "baselineArr": baseline_arr,
                "baseAmount": base["amount"],
                "preRenewalAddAmount": sum(add["amount"] for add in baseline_adds),
                "preRenewalAddArr": sum(add["arrAmount"] for add in baseline_add_docs),
                "renewalRawDeltaArr": renewal_raw_delta_arr,
                "renewalDeltaAmount": renewal_delta_arr,
                "renewalDeltaArr": renewal_delta_arr,
                "churnAmount": churn_amount,
                "churnArr": churn_arr,
                "changeAmount": renewal_delta_arr + churn_amount,
                "changeArr": renewal_delta_arr + churn_arr,
            }
        )

    rows.sort(key=lambda x: (x["year"], x["quarter"], x["clientName"], x["product"]))
    return rows


def build_add_rows(orders: list[dict[str, Any]], due_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_map: dict[str, list[str]] = defaultdict(list)
    for row in due_rows:
        for add in row.get("preRenewalAdds") or []:
            if add.get("id"):
                baseline_map[add["id"]].append(row["id"])

    rows: list[dict[str, Any]] = []
    for order in orders:
        if order["orderType"] != ADD_ORDER_TYPE or not order.get("start"):
            continue
        year = order["start"].year
        quarter = quarter_for(order["start"])
        arr_amount = annualize(order["amount"], order["serviceDays"])
        doc = serialize_order(order) or {}
        rows.append(
            {
                "id": f"add|{order['id']}",
                "orderId": order["id"],
                "clientName": order["clientName"],
                "customNo": order["customNo"],
                "organizationUuid": order.get("organizationUuid") or "",
                "enterpriseUrl": order.get("enterpriseUrl") or "",
                "csOwner": order.get("csOwner") or "未填写",
                "sales": order.get("sales") or "",
                "serviceStage": order.get("serviceStage") or "",
                "cooperationStatus": order.get("cooperationStatus") or "",
                "year": year,
                "quarter": quarter,
                "period": f"{year} {quarter.upper()}",
                "product": order["product"],
                "contract": doc,
                "amount": order["amount"],
                "arrAmount": arr_amount,
                "serviceDays": order["serviceDays"],
                "baselineForDueIds": sorted(baseline_map.get(order["id"], [])),
            }
        )
    rows.sort(key=lambda x: (x["year"], x["quarter"], x["clientName"], x["product"], x["contract"]["startDate"]))
    return rows


def build_payload(clients_data: dict[str, Any], contracts_data: dict[str, Any], as_of_date: date | None = None) -> dict[str, Any]:
    as_of_date = as_of_date or datetime.now().astimezone().date()
    profiles = build_client_profiles(clients_data)
    orders = collect_orders(contracts_data, profiles)
    due_rows = build_due_rows(orders, as_of_date)
    add_rows = build_add_rows(orders, due_rows)
    years = sorted({row["year"] for row in due_rows} | {row["year"] for row in add_rows})
    return {
        "schema": "yingdao-boss-renewal-performance.v2",
        "meta": {
            "generatedAt": datetime.now().astimezone().isoformat(),
            "asOfDate": iso(as_of_date),
            "clientsInputRows": len(clients_data.get("rows") or []),
            "contractsInputRows": len(contracts_data.get("rows") or []),
            "orderCount": len(orders),
            "dueRowCount": len(due_rows),
            "addRowCount": len(add_rows),
            "availableYears": years,
            "deltaTolerance": DELTA_TOLERANCE,
            "preRenewalAddEndToleranceDays": PRE_RENEWAL_ADD_END_TOLERANCE_DAYS,
            "businessGroup": (clients_data.get("meta") or {}).get("business_group")
            or (contracts_data.get("meta") or {}).get("business_group")
            or "",
        },
        "dueRows": due_rows,
        "addRows": add_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build renewal performance dashboard HTML")
    parser.add_argument("--clients-input", default=str(DEFAULT_CLIENTS_INPUT), help="Path to latest-clients.json")
    parser.add_argument("--contracts-input", default=str(DEFAULT_CONTRACTS_INPUT), help="Path to latest-contracts.json")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Path to HTML template")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output HTML path")
    parser.add_argument("--as-of-date", default="", help="Date used to decide pending vs churn, YYYY-MM-DD")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    clients_path = Path(args.clients_input).expanduser().resolve()
    contracts_path = Path(args.contracts_input).expanduser().resolve()
    template_path = Path(args.template).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    try:
        clients_data = read_json(clients_path, required=True)
        contracts_data = read_json(contracts_path, required=True)
        as_of_date = parse_date(args.as_of_date) if args.as_of_date else None
        payload = build_payload(clients_data, contracts_data, as_of_date=as_of_date)
        template = template_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if PLACEHOLDER not in template:
        print(f"Error: placeholder {PLACEHOLDER} not found in {template_path}", file=sys.stderr)
        return 1

    data_js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template.replace(PLACEHOLDER, data_js), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output_path),
                "due_rows": payload["meta"]["dueRowCount"],
                "add_rows": payload["meta"]["addRowCount"],
                "available_years": payload["meta"]["availableYears"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
