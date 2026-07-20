#!/usr/bin/env python3
"""Build a Feishu card JSON for the daily renewal/churn report.

The structure intentionally follows the proven-good sample card shape
(including schema 2.0 body/table/column_set layout) so the Feishu channel
can render the orange standalone card consistently.

Inputs:
- latest-clients.json
- contracts-expiration-summary.json

Output:
- Prints a complete Feishu card JSON string to stdout.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_CLIENTS = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "latest-clients.json"
DEFAULT_CONTRACT_SUMMARY = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "contracts-expiration-summary.json"
DEFAULT_APPS = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "latest-apps.json"
BOSS_ENTERPRISE_DETAIL_BASE = "https://boss.shadow-rpa.net/simple/manage/microApp/boss/busi/enterpriseDetail?organizationUuid="
RUIXIANG_OLD_KEYS = {
    "江苏瑞祥科技集团有限公司",
    "20230722-021117",
    "891c7f79-1856-4af4-b3cf-c4b49e05af5d",
}
RUIXIANG_GLOBAL_BUY = {
    "name": "瑞祥全球购超市有限公司",
    "custom_no": "20230116-017676",
    "organization_uuid": "7c156ae7-7c00-40bb-9ff9-645acaf83443",
}

# 来自用户确认“效果正确”的样例卡片。当前作为稳定样式模板使用。
DEFAULT_HEADER_IMG_KEY = "img_v3_0210v_67c70217-d281-4280-af53-0e26741af92g"


def first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def to_float(v):
    try:
        if v in (None, ""):
            return None
        return float(v)
    except Exception:
        return None


def to_int_like(v):
    n = to_float(v)
    if n is None:
        return 0
    return int(n) if float(n).is_integer() else n


def customer_key(row: dict) -> str:
    return (
        row.get("组织UUID")
        or str(row.get("客户编号") or "")
        or str(row.get("组织名称") or "")
        or str(row.get("组织简称") or "")
    )


def is_ruixiang_old_subject(row: dict) -> bool:
    values = {
        str(row.get("组织名称") or ""),
        str(row.get("客户编号") or ""),
        str(row.get("组织UUID") or ""),
    }
    return bool(values & RUIXIANG_OLD_KEYS)


def boss_url(organization_uuid: str | None) -> str:
    if not organization_uuid:
        return ""
    return f"{BOSS_ENTERPRISE_DETAIL_BASE}{organization_uuid}"


def boss_markdown_link(organization_uuid: str | None) -> str:
    url = boss_url(organization_uuid)
    return f"[点击跳转]({url})" if url else "暂无"


def parse_history_names(row: dict) -> list[str]:
    raw = row.get("历史名称")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw if v]
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v]
    except Exception:
        pass
    return [str(raw)]


def build_client_index(rows: list[dict]) -> dict[str, dict]:
    index = {}
    for row in rows:
        keys = [
            row.get("组织UUID"),
            row.get("客户编号"),
            row.get("组织名称"),
            row.get("组织简称"),
            *parse_history_names(row),
        ]
        for key in keys:
            if key:
                index.setdefault(str(key), row)
    return index


def find_client_row(item: dict, client_index: dict[str, dict]) -> dict | None:
    for key in (
        item.get("organization_uuid"),
        item.get("custom_no"),
        item.get("client_name"),
    ):
        if key and str(key) in client_index:
            return client_index[str(key)]
    return None


def collect_ruixiang_global_buy_activity(apps_data: dict | None) -> dict[str, int]:
    rows = (apps_data or {}).get("rows") or []
    matched = [r for r in rows if r.get("_organizationUuid") == RUIXIANG_GLOBAL_BUY["organization_uuid"]]
    return {
        "app_count": len(matched),
        "week_active_apps": sum(1 for r in matched if (to_float(r.get("weekRunCnt")) or 0) > 0),
        "month_active_apps": sum(1 for r in matched if (to_float(r.get("monthRunCnt")) or 0) > 0),
        "week_active_owners": len({r.get("ownerUuid") for r in matched if (to_float(r.get("weekRunCnt")) or 0) > 0 and r.get("ownerUuid")}),
        "month_active_owners": len({r.get("ownerUuid") for r in matched if (to_float(r.get("monthRunCnt")) or 0) > 0 and r.get("ownerUuid")}),
    }


def customer_name(row: dict) -> str:
    if is_ruixiang_old_subject(row):
        return RUIXIANG_GLOBAL_BUY["name"]
    return (
        row.get("组织名称")
        or row.get("组织简称")
        or row.get("客户编号")
        or "(未命名客户)"
    )


def organization_uuid(row: dict) -> str | None:
    if is_ruixiang_old_subject(row):
        return RUIXIANG_GLOBAL_BUY["organization_uuid"]
    return row.get("组织UUID")


def pick_low_activity(rows: list[dict], apps_data: dict | None = None) -> list[dict]:
    low_activity_candidates = []
    seen = set()
    ruixiang_activity = collect_ruixiang_global_buy_activity(apps_data)
    sorted_rows = sorted(
        rows,
        key=lambda x: (
            to_float(x.get("账号饱和度")) if to_float(x.get("账号饱和度")) is not None else 999999
        ),
    )
    for r in sorted_rows:
        if is_ruixiang_old_subject(r) and ruixiang_activity.get("week_active_apps", 0) > 0:
            continue
        stage = first(r.get("RPA服务阶段"))
        deploy = first(r.get("RPA部署类型"))
        coop = first(r.get("RPA合作状态"))
        if stage in {"已流失", "售前阶段"}:
            continue
        if coop in {"已过期", "已流失"}:
            continue
        if deploy != "公有云":
            continue
        key = customer_key(r)
        if key in seen:
            continue
        seen.add(key)
        low_activity_candidates.append(r)
        if len(low_activity_candidates) >= 10:
            break
    return low_activity_candidates


def fmt_amount(v) -> str:
    try:
        return f"¥{float(v):,.0f}"
    except Exception:
        return str(v)


def fmt_days(v) -> str:
    n = to_float(v)
    if n is None:
        return "?"
    return str(int(n) if float(n).is_integer() else n)


def fmt_beijing_time(ts: str | None) -> str:
    if not ts:
        return "未知"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        bj = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        return bj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def format_detail_lines(order_details: list[str]) -> str:
    parts: list[str] = []
    for detail in order_details or []:
        for piece in str(detail).replace("\r", "").split("\n"):
            piece = piece.strip()
            if piece:
                parts.append(f"- {piece}；")
    return "\n".join(parts) if parts else "- 暂无；"


def build_client_detail_markdown(item: dict, client_index: dict[str, dict]) -> str:
    order_types = " / ".join(item.get("order_types", []) or []) or "未标注"
    details = format_detail_lines(item.get("order_details", []))
    row = find_client_row(item, client_index)
    link = boss_markdown_link(organization_uuid(row)) if row else boss_markdown_link(item.get("organization_uuid"))
    return "\n".join(
        [
            f"**{item.get('client_name', '(未命名客户)')}** | 剩余 {fmt_days(item.get('days_remaining'))} 天",
            f"合同编号：`{item.get('latest_contract_no', '未知')}`",
            f"订单起止：`{item.get('min_start_date', '未知')}` 至 `{item.get('max_end_date', '未知')}`",
            f"金额：{fmt_amount(item.get('total_amount'))} | 类型：{order_types}",
            "详情：",
            details,
            f"BOSS链接：{link}",
        ]
    )


def build_bucket_column(title: str, title_color: str, background_style: str, items: list[dict], client_index: dict[str, dict]) -> dict:
    elements = [
        {"tag": "markdown", "content": f"**<font color='{title_color}'>{title}（{len(items)}家）</font>**"}
    ]
    if items:
        for item in items:
            elements.append(
                {
                    "tag": "markdown",
                    "content": build_client_detail_markdown(item, client_index),
                    "text_align": "left",
                    "text_size": "normal_v2",
                }
            )
    else:
        elements.append(
            {
                "tag": "markdown",
                "content": "暂无",
                "text_align": "left",
                "text_size": "normal_v2",
            }
        )

    return {
        "tag": "column_set",
        "flex_mode": "stretch",
        "horizontal_spacing": "12px",
        "horizontal_align": "left",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "background_style": background_style,
                "elements": elements,
                "padding": "12px 12px 12px 12px",
                "vertical_spacing": "4px",
                "horizontal_align": "left",
                "vertical_align": "top",
                "weight": 1,
            }
        ],
        "margin": "0px 0px 0px 0px",
    }


def build_low_activity_table(rows: list[dict]) -> dict:
    return {
        "tag": "table",
        "columns": [
            {"data_type": "text", "name": "customer", "display_name": "客户", "horizontal_align": "left", "width": "auto"},
            {
                "data_type": "number",
                "name": "saturation",
                "display_name": "账号饱和度",
                "horizontal_align": "right",
                "width": "auto",
                "format": {"precision": 2},
            },
            {
                "data_type": "number",
                "name": "seven_active",
                "display_name": "7日活跃",
                "horizontal_align": "right",
                "width": "auto",
                "format": {"precision": 0},
            },
            {
                "data_type": "number",
                "name": "fifteen_active",
                "display_name": "15天活跃账号",
                "horizontal_align": "right",
                "width": "auto",
                "format": {"precision": 0},
            },
            {"data_type": "text", "name": "service_stage", "display_name": "服务阶段", "horizontal_align": "right", "width": "auto"},
            {"data_type": "text", "name": "deploy_type", "display_name": "部署类型", "horizontal_align": "center", "width": "auto"},
            {"data_type": "markdown", "name": "boss_link", "display_name": "BOSS链接", "horizontal_align": "center", "width": "auto"},
        ],
        "rows": [
            {
                "customer": customer_name(r),
                "saturation": round(to_float(r.get("账号饱和度")) or 0, 2),
                "seven_active": to_int_like(r.get("7日活跃应用数")),
                "fifteen_active": to_int_like(r.get("近15天活跃账号数")),
                "service_stage": first(r.get("RPA服务阶段")) or "未填写",
                "deploy_type": first(r.get("RPA部署类型")) or "未填写",
                "boss_link": boss_markdown_link(organization_uuid(r)),
            }
            for r in rows
        ],
        "row_height": "low",
        "header_style": {"text_align": "left", "background_style": "grey", "bold": True},
        "page_size": max(len(rows), 1),
        "margin": "0px 0px 0px 0px",
        "element_id": "renewal-low-activity-table",
    }


def build_card(clients_data: dict, contract_summary: dict, tz_name: str, as_of: date | None, header_img_key: str, apps_data: dict | None = None) -> dict:
    rows = clients_data.get("rows") or []
    low_activity = pick_low_activity(rows, apps_data=apps_data)
    client_index = build_client_index(rows)
    now_date = as_of or datetime.now(ZoneInfo(tz_name)).date()
    client_meta = clients_data.get("meta") or {}

    bucket_30 = contract_summary.get("0-30 Days") or []
    bucket_60 = contract_summary.get("31-60 Days") or []
    bucket_90 = contract_summary.get("61-90 Days") or []

    meta_md = "\n".join(
        [
            f"**分析日期** ：{now_date.isoformat()}（{tz_name}）",
            f"**客户数据时间** ：{fmt_beijing_time(client_meta.get('fetched_at'))}（北京时间）",
            f"**业务组** ：{client_meta.get('business_group') or '未知'} | **客户数量** ：{client_meta.get('row_count') if client_meta.get('row_count') is not None else '未知'}",
        ]
    )

    card = {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "style": {
                "text_size": {
                    "normal_v2": {"default": "normal", "pc": "normal", "mobile": "heading"}
                }
            },
        },
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "img",
                    "img_key": header_img_key,
                    "scale_type": "fit_horizontal",
                    "corner_radius": "8px",
                    "margin": "0px 0px 0px 0px",
                },
                {"tag": "markdown", "content": meta_md, "margin": "0px 0px 0px 0px", "element_id": "renewal-meta"},
                {"tag": "markdown", "content": "### <font color='blue'>1）待续费客户</font>", "margin": "0px 0px 0px 0px", "element_id": "renewal-title"},
                build_bucket_column("30天内", "blue", "blue-50", bucket_30, client_index),
                build_bucket_column("31-60天", "violet", "purple-50", bucket_60, client_index),
                build_bucket_column("61-90天", "orange", "orange-50", bucket_90, client_index),
                {
                    "tag": "markdown",
                    "content": "### <font color='purple'>2）活跃低客户</font>\n> 筛选条件：按账号饱和度升序 Top 10；RPA服务阶段 ≠ 已流失/售前阶段；RPA合作状态 ≠ 已过期/已流失；RPA部署类型 = 公有云。江苏瑞祥科技集团有限公司按瑞祥全球购超市有限公司主体活跃数据处理。",
                    "margin": "0px 0px 0px 0px",
                    "element_id": "low-activity-title",
                },
                build_low_activity_table(low_activity),
            ],
        },
    }
    return card


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Feishu card JSON for daily renewal/churn report")
    parser.add_argument("--clients", default=str(DEFAULT_CLIENTS), help="Path to latest-clients.json")
    parser.add_argument("--contracts-summary", default=str(DEFAULT_CONTRACT_SUMMARY), help="Path to contracts-expiration-summary.json")
    parser.add_argument("--apps", default=str(DEFAULT_APPS), help="Optional path to latest-apps.json for customer subject aliases")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Timezone for report date")
    parser.add_argument("--as-of", default="", help="Override analysis date (YYYY-MM-DD)")
    parser.add_argument("--header-img-key", default=DEFAULT_HEADER_IMG_KEY, help="Feishu image key for card header banner")
    parser.add_argument("--output", default="", help="Optional output file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    clients_path = Path(args.clients).expanduser().resolve()
    contracts_path = Path(args.contracts_summary).expanduser().resolve()

    clients_data = json.loads(clients_path.read_text(encoding="utf-8"))
    contract_summary = json.loads(contracts_path.read_text(encoding="utf-8"))
    apps_path = Path(args.apps).expanduser().resolve() if args.apps else None
    apps_data = json.loads(apps_path.read_text(encoding="utf-8")) if apps_path and apps_path.exists() else None
    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    card = build_card(
        clients_data,
        contract_summary,
        tz_name=args.tz,
        as_of=as_of,
        header_img_key=args.header_img_key,
        apps_data=apps_data,
    )
    payload = json.dumps(card, ensure_ascii=False, indent=4)

    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
