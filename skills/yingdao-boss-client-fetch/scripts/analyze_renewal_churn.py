#!/usr/bin/env python3
"""Renewal + churn focused analysis for yingdao boss latest dataset.

Outputs a markdown report for three scenarios:
1) Pending renewals (deduplicated 30/60 buckets)
2) Low-activity public-cloud customers (top 5 by account saturation)
3) Expired/churned customers in current + previous month
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "latest-clients.json"


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


def normalize_tz_suffix(ts: str) -> str:
    # Convert "+08" -> "+08:00" for fromisoformat compatibility
    return re.sub(r"([+-]\d{2})$", r"\1:00", ts)


def parse_date(v) -> date | None:
    if v in (None, ""):
        return None
    s = str(v).strip()
    if not s:
        return None

    # Common format in source: "2027-01-18 00:00:00+08"
    s = normalize_tz_suffix(s).replace(" ", "T")

    for candidate in (s, s[:10]):
        try:
            if len(candidate) == 10:
                return date.fromisoformat(candidate)
            return datetime.fromisoformat(candidate).date()
        except Exception:
            continue
    return None


def month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def previous_month(d: date) -> tuple[int, int]:
    if d.month == 1:
        return (d.year - 1, 12)
    return (d.year, d.month - 1)


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


def line_for_renewal(row: dict) -> str:
    return (
        f"- {customer_name(row)}｜剩余 {row.get('RPA剩余天数')} 天"
        f"｜7日活跃 {row.get('7日活跃应用数')}"
        f"｜15天活跃账号 {row.get('近15天活跃账号数')}"
        f"｜服务阶段 {first(row.get('RPA服务阶段'))}"
        f"｜CS {first(row.get('客户成功')) or '未填写'}"
    )


def line_for_low_activity(row: dict) -> str:
    return (
        f"- {customer_name(row)}｜账号饱和度 {row.get('账号饱和度')}"
        f"｜7日活跃 {row.get('7日活跃应用数')}"
        f"｜15天活跃账号 {row.get('近15天活跃账号数')}"
        f"｜服务阶段 {first(row.get('RPA服务阶段'))}"
        f"｜部署类型 {first(row.get('RPA部署类型'))}"
        f"｜CS {first(row.get('客户成功')) or '未填写'}"
    )


def line_for_churn(row: dict) -> str:
    return (
        f"- {customer_name(row)}｜状态 {first(row.get('RPA合作状态'))}"
        f"｜到期日期 {row.get('RPA到期日期') or '缺失'}"
        f"｜7日活跃 {row.get('7日活跃应用数')}"
        f"｜CS {first(row.get('客户成功')) or '未填写'}"
    )


def build_report(data: dict, tz_name: str, as_of: date | None) -> str:
    rows = data.get("rows") or []
    now_date = as_of or datetime.now(ZoneInfo(tz_name)).date()
    current_m = month_key(now_date)
    prev_m = previous_month(now_date)

    renewal_pool = []
    for r in rows:
        coop = first(r.get("RPA合作状态"))
        if coop != "合作中(年订阅)":
            continue
        days = to_float(r.get("RPA剩余天数"))
        if days is None or days <= 0 or days > 90:
            continue
        renewal_pool.append(r)

    # Deduplicate + bucket by exclusive range
    seen = set()
    bucket_30, bucket_60 = [], []
    for r in sorted(renewal_pool, key=lambda x: to_float(x.get("RPA剩余天数")) or 99999):
        key = customer_key(r)
        if key in seen:
            continue
        seen.add(key)

        d = to_float(r.get("RPA剩余天数")) or 0
        if d <= 30:
            bucket_30.append(r)
        elif d <= 60:
            bucket_60.append(r)

    # Low-activity customers: public cloud only, exclude lost / presale, top 5 by account saturation asc
    low_activity_candidates = []
    seen_low_activity = set()
    for r in sorted(rows, key=lambda x: (to_float(x.get("账号饱和度")) if to_float(x.get("账号饱和度")) is not None else 999999)):
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
        if key in seen_low_activity:
            continue
        seen_low_activity.add(key)
        low_activity_candidates.append(r)
        if len(low_activity_candidates) >= 5:
            break

    # Expired/churned in current + previous month
    churn_candidates = []
    churn_date_missing = []
    for r in rows:
        coop = first(r.get("RPA合作状态"))
        if coop not in {"已过期", "已流失"}:
            continue
        d = parse_date(r.get("RPA到期日期"))
        if d is None:
            churn_date_missing.append(r)
            continue
        if month_key(d) in {current_m, prev_m}:
            churn_candidates.append(r)

    # Build markdown
    lines = []
    meta = data.get("meta") or {}
    lines.append("## 续费与流失防范（日常自动版）")
    lines.append("")
    lines.append(f"- 分析日期：{now_date.isoformat()} ({tz_name})")
    lines.append(f"- 数据时间：{meta.get('fetched_at')}")
    lines.append(f"- 业务组：{meta.get('business_group')}")
    lines.append(f"- 样本量：{meta.get('row_count')}")
    lines.append("")

    lines.append("### 1) 待续费客户（去重）")
    lines.append(f"- 30天内：{len(bucket_30)}")
    lines.append(f"- 31-60天：{len(bucket_60)}")
    lines.append("")

    lines.append("#### 30天内")
    if bucket_30:
        lines.extend(line_for_renewal(r) for r in bucket_30)
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("#### 31-60天")
    if bucket_60:
        lines.extend(line_for_renewal(r) for r in bucket_60)
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("### 2) 活跃低客户")
    lines.append("- 筛选条件：按账号饱和度升序 Top 5；RPA服务阶段 ≠ 已流失/售前阶段；RPA合作状态 ≠ 已过期/已流失；RPA部署类型 = 公有云")
    if low_activity_candidates:
        lines.extend(line_for_low_activity(r) for r in low_activity_candidates)
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("### 3) 当月 + 前一个月 已过期/已流失")
    if churn_candidates:
        lines.extend(line_for_churn(r) for r in churn_candidates)
    else:
        lines.append("- 暂无")
    lines.append("")

    if churn_date_missing:
        lines.append(f"- 日期缺失待核查：{len(churn_date_missing)}")
        for r in churn_date_missing:
            lines.append(
                f"  - {customer_name(r)}｜状态 {first(r.get('RPA合作状态'))}｜到期日期 缺失｜7日活跃 {r.get('7日活跃应用数')}｜CS {first(r.get('客户成功')) or '未填写'}"
            )
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze renewal/churn scenarios from latest-clients.json")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to latest-clients.json")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Timezone for report date")
    parser.add_argument("--as-of", default="", help="Override analysis date (YYYY-MM-DD)")
    parser.add_argument("--output", default="", help="Optional output markdown file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    in_path = Path(args.input).expanduser().resolve()
    data = json.loads(in_path.read_text(encoding="utf-8"))

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    report = build_report(data, tz_name=args.tz, as_of=as_of)

    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
