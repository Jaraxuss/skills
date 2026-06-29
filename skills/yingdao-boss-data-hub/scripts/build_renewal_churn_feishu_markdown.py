#!/usr/bin/env python3
"""Build markdown content for Feishu-rendered daily renewal/churn card.

This intentionally outputs markdown instead of raw interactive-card JSON,
so OpenClaw/Feishu can render it via the normal assistant card path.
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


def customer_key(row: dict) -> str:
    return (
        row.get("组织UUID")
        or str(row.get("客户编号") or "")
        or str(row.get("组织名称") or "")
        or str(row.get("组织简称") or "")
    )


def customer_name(row: dict) -> str:
    return (
        row.get("组织名称")
        or row.get("组织简称")
        or row.get("客户编号")
        or "(未命名客户)"
    )


def pick_low_activity(rows: list[dict]) -> list[dict]:
    low_activity_candidates = []
    seen = set()
    sorted_rows = sorted(
        rows,
        key=lambda x: (
            to_float(x.get("账号饱和度")) if to_float(x.get("账号饱和度")) is not None else 999999
        ),
    )
    for r in sorted_rows:
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
        if len(low_activity_candidates) >= 5:
            break
    return low_activity_candidates


def fmt_amount(v) -> str:
    try:
        return f"¥{float(v):,.0f}"
    except Exception:
        return str(v)


def fmt_ratio_2(v) -> str:
    n = to_float(v)
    if n is None:
        return "未知"
    return f"{n:.2f}"


def fmt_beijing_time(ts: str | None) -> str:
    if not ts:
        return "未知"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        bj = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        return bj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def build_markdown(clients_data: dict, contract_summary: dict, tz_name: str, as_of: date | None) -> str:
    rows = clients_data.get("rows") or []
    low_activity = pick_low_activity(rows)
    now_date = as_of or datetime.now(ZoneInfo(tz_name)).date()
    client_meta = clients_data.get("meta") or {}

    bucket_30 = contract_summary.get("0-30 Days") or []
    bucket_60 = contract_summary.get("31-60 Days") or []

    lines: list[str] = []
    lines.append("**续费与流失防范（日常自动版）**")
    lines.append("")
    lines.append(f"**分析日期**：{now_date.isoformat()}（{tz_name}）")
    lines.append(f"**客户数据时间**：{fmt_beijing_time(client_meta.get('fetched_at'))}（北京时间）")
    lines.append(f"**业务组**：{client_meta.get('business_group') or '未知'}")
    lines.append(f"**客户数量**：{client_meta.get('row_count') if client_meta.get('row_count') is not None else '未知'}")
    lines.append("")
    lines.append("---")
    lines.append("**1）待续费客户**")
    lines.append(f"**30天内（{len(bucket_30)}家）**")
    if bucket_30:
        for item in bucket_30:
            details = "；".join(
                part.strip().replace("\r", "")
                for detail in item.get("order_details", [])
                for part in str(detail).split("\n")
                if part.strip()
            )
            order_types = " / ".join(item.get("order_types", []) or []) or "未标注"
            lines.append(f"- **{item.get('client_name', '(未命名客户)')}**｜剩余 **{item.get('days_remaining', '?')} 天**")
            lines.append(f"  合同编号：`{item.get('latest_contract_no', '未知')}`")
            lines.append(f"  订单起止：`{item.get('min_start_date', '未知')}` 至 `{item.get('max_end_date', '未知')}`")
            lines.append(f"  金额：**{fmt_amount(item.get('total_amount'))}**｜类型：**{order_types}**")
            lines.append(f"  详情：{details or '暂无'}")
    else:
        lines.append("- 暂无")

    lines.append("")
    lines.append("")
    lines.append(f"**31-60天（{len(bucket_60)}家）**")
    if bucket_60:
        for item in bucket_60:
            details = "；".join(
                part.strip().replace("\r", "")
                for detail in item.get("order_details", [])
                for part in str(detail).split("\n")
                if part.strip()
            )
            order_types = " / ".join(item.get("order_types", []) or []) or "未标注"
            lines.append(f"- **{item.get('client_name', '(未命名客户)')}**｜剩余 **{item.get('days_remaining', '?')} 天**")
            lines.append(f"  合同编号：`{item.get('latest_contract_no', '未知')}`")
            lines.append(f"  订单起止：`{item.get('min_start_date', '未知')}` 至 `{item.get('max_end_date', '未知')}`")
            lines.append(f"  金额：**{fmt_amount(item.get('total_amount'))}**｜类型：**{order_types}**")
            lines.append(f"  详情：{details or '暂无'}")
    else:
        lines.append("- 暂无")

    lines.append("")
    lines.append("---")
    lines.append("**2）活跃低客户**")
    lines.append("")
    lines.append("| 客户 | 账号饱和度 | 7日活跃 | 15天活跃账号 | 服务阶段 | 部署类型 |")
    lines.append("| --- | ---: | ---: | ---: | --- | --- |")
    for r in low_activity:
        lines.append(
            f"| {customer_name(r)} | {fmt_ratio_2(r.get('账号饱和度'))} | {r.get('7日活跃应用数') or 0} | {r.get('近15天活跃账号数') or 0} | {first(r.get('RPA服务阶段')) or '未填写'} | {first(r.get('RPA部署类型')) or '未填写'} |"
        )
    if not low_activity:
        lines.append("| 暂无 | - | - | - | - | - |")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build markdown for daily renewal/churn report")
    parser.add_argument("--clients", default=str(DEFAULT_CLIENTS), help="Path to latest-clients.json")
    parser.add_argument("--contracts-summary", default=str(DEFAULT_CONTRACT_SUMMARY), help="Path to contracts-expiration-summary.json")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Timezone for report date")
    parser.add_argument("--as-of", default="", help="Override analysis date (YYYY-MM-DD)")
    parser.add_argument("--output", default="", help="Optional output file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    clients_path = Path(args.clients).expanduser().resolve()
    contracts_path = Path(args.contracts_summary).expanduser().resolve()

    clients_data = json.loads(clients_path.read_text(encoding="utf-8"))
    contract_summary = json.loads(contracts_path.read_text(encoding="utf-8"))
    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    content = build_markdown(clients_data, contract_summary, tz_name=args.tz, as_of=as_of)

    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
