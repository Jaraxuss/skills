#!/usr/bin/env python3
"""Refresh dashboard inputs only when today's JSON outputs are missing or stale."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPT_DIR.parents[2]
RUNTIME_DIR = WORKSPACE_DIR / "runtime" / "yingdao-boss"
SKILL_DIR = WORKSPACE_DIR / "skills" / "yingdao-boss-data-hub"


@dataclass(frozen=True)
class Step:
    label: str
    output: Path
    command: list[str]


def normalize_tz_suffix(value: str) -> str:
    return re.sub(r"([+-]\d{2})$", r"\1:00", value.strip())


def parse_fetched_at(value: object, tz: ZoneInfo) -> date | None:
    if not value:
        return None
    text = normalize_tz_suffix(str(value)).replace("Z", "+00:00").replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz).date()


def json_data_date(path: Path, tz: ZoneInfo) -> date | None:
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None

    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            meta_date = parse_fetched_at(meta.get("fetched_at"), tz)
            if meta_date:
                return meta_date

    return datetime.fromtimestamp(path.stat().st_mtime, tz).date()


def is_fresh_today(path: Path, today: date, tz: ZoneInfo) -> bool:
    data_date = json_data_date(path, tz)
    return data_date == today


def run_step(step: Step, today: date, tz: ZoneInfo, *, force: bool, dry_run: bool) -> None:
    data_date = json_data_date(step.output, tz)
    if not force and data_date == today:
        print(f"✅ Skip {step.label}: {step.output} is already from {today.isoformat()}")
        return

    reason = "forced" if force else ("missing" if data_date is None else f"stale ({data_date.isoformat()})")
    print(f"▶️  Run {step.label}: {reason}")
    print("   " + " ".join(step.command))

    if dry_run:
        return

    subprocess.run(step.command, cwd=WORKSPACE_DIR, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh dashboard data only when JSON files are not from today.")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Timezone used for freshness checks")
    parser.add_argument("--as-of", default="", help="Override today's date for checks (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Run every data step even if today's JSON exists")
    parser.add_argument("--dry-run", action="store_true", help="Print planned steps without running fetch/build commands")
    parser.add_argument("--reports-start-date", default="", help="Optional YYYYMMDD start date for fetch_tenant_reports.py")
    parser.add_argument("--reports-end-date", default="", help="Optional YYYYMMDD end date for fetch_tenant_reports.py")
    parser.add_argument("--output", default=str(SKILL_DIR / "dashboard" / "dashboard.html"), help="Dashboard HTML output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tz = ZoneInfo(args.tz)
    today = date.fromisoformat(args.as_of) if args.as_of else datetime.now(tz).date()

    reports_cmd = [sys.executable, "skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py"]
    if args.reports_start_date:
        reports_cmd.extend(["--start-date", args.reports_start_date])
    if args.reports_end_date:
        reports_cmd.extend(["--end-date", args.reports_end_date])

    steps = [
        Step(
            label="fetch clients",
            output=RUNTIME_DIR / "latest-clients.json",
            command=[sys.executable, "skills/yingdao-boss-data-hub/scripts/fetch_clients.py"],
        ),
        Step(
            label="fetch contracts",
            output=RUNTIME_DIR / "latest-contracts.json",
            command=[sys.executable, "skills/yingdao-boss-data-hub/scripts/fetch_contracts.py"],
        ),
        Step(
            label="analyze expiring orders",
            output=RUNTIME_DIR / "contracts-expiration-summary.json",
            command=[sys.executable, "skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py"],
        ),
        Step(
            label="fetch tenant reports",
            output=RUNTIME_DIR / "latest-reports.json",
            command=reports_cmd,
        ),
    ]

    print(f"Freshness date: {today.isoformat()} ({args.tz})")
    for step in steps:
        run_step(step, today, tz, force=args.force, dry_run=args.dry_run)

    build_cmd = [
        sys.executable,
        "skills/yingdao-boss-data-hub/dashboard/build_data.py",
        "--output",
        args.output,
    ]
    print("🧱 Build dashboard")
    print("   " + " ".join(build_cmd))
    if not args.dry_run:
        subprocess.run(build_cmd, cwd=WORKSPACE_DIR, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
