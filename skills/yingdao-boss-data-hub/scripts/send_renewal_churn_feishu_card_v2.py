#!/usr/bin/env python3
"""Fetch data, build, and send the renewal/churn Feishu card.

This is the deterministic entrypoint used by the 09:00 workday cron job.
It keeps data refresh, analysis, card building, and native Feishu card delivery
inside scripts so the agent does not need to re-render JSON as text.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE_DIR = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
TASK_CENTER_CARD_SDK_DIR = WORKSPACE_DIR / "task_center" / "backend" / "scripts" / "sdk" / "feishu-card-v2"
DEFAULT_CONFIG = WORKSPACE_DIR / "runtime" / "yingdao-boss-client-fetch" / "config.local.json"
DEFAULT_CLIENTS = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "latest-clients.json"
DEFAULT_CONTRACTS_SUMMARY = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "contracts-expiration-summary.json"
DEFAULT_APPS = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "latest-apps.json"
DEFAULT_OUTPUT = WORKSPACE_DIR / "runtime" / "yingdao-boss" / "renewal-churn-card-preview.json"
DEFAULT_RECEIVE_ID = "ou_8ca37a28527b51fdad39a83998c37625"
DEFAULT_RECEIVE_ID_TYPE = "open_id"
DEFAULT_BUSINESS_GROUP = "江苏业务组"


def run_step(cmd: list[str], *, cwd: Path | None = None, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd or WORKSPACE_DIR),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-1200:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{tail}")
    if not quiet and result.stdout.strip():
        print(result.stdout.strip())
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send daily renewal/churn Feishu Card V2 report")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Yingdao Boss runtime config path")
    parser.add_argument("--business-group", default=DEFAULT_BUSINESS_GROUP, help="Business group for client fetch")
    parser.add_argument("--receive-id", default=DEFAULT_RECEIVE_ID, help="Feishu receive id")
    parser.add_argument("--receive-id-type", default=DEFAULT_RECEIVE_ID_TYPE, choices=["open_id", "user_id", "union_id", "email", "chat_id"])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Where to write the generated Card JSON")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Report timezone")
    parser.add_argument("--skip-fetch", action="store_true", help="Use existing latest data without refreshing from Boss")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate card only; do not send")
    parser.add_argument("--uuid", default="", help="Optional Feishu de-duplication UUID")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python_bin = sys.executable
    config_path = str(Path(args.config).expanduser().resolve())
    output_path = str(Path(args.output).expanduser().resolve())

    try:
        if not args.skip_fetch:
            run_step([
                python_bin,
                str(SCRIPTS_DIR / "fetch_clients.py"),
                "--config",
                config_path,
                "--business-group",
                args.business_group,
            ], quiet=True)
            run_step([
                python_bin,
                str(SCRIPTS_DIR / "fetch_contracts.py"),
                "--config",
                config_path,
            ], quiet=True)
            run_step([
                python_bin,
                str(SCRIPTS_DIR / "fetch_apps.py"),
                "--config",
                config_path,
                "--clients-input",
                str(DEFAULT_CLIENTS),
            ], quiet=True)

        run_step([python_bin, str(SCRIPTS_DIR / "analyze_expiring_orders.py")], quiet=True)
        run_step([
            python_bin,
            str(SCRIPTS_DIR / "build_renewal_churn_feishu_card.py"),
            "--clients",
            str(DEFAULT_CLIENTS),
            "--contracts-summary",
            str(DEFAULT_CONTRACTS_SUMMARY),
            "--apps",
            str(DEFAULT_APPS),
            "--tz",
            args.tz,
            "--output",
            output_path,
        ], quiet=True)

        card = json.loads(Path(output_path).read_text(encoding="utf-8"))
        row_count = 0
        try:
            row_count = len(card["body"]["elements"][-1].get("rows") or [])
        except Exception:
            row_count = 0

        if args.dry_run:
            print(json.dumps({"status": "dry_run_ok", "card": output_path, "low_activity_rows": row_count}, ensure_ascii=False, indent=2))
            return 0

        request_uuid = args.uuid or f"renewal-churn-{datetime.now(ZoneInfo(args.tz)).date().isoformat()}-{uuid.uuid4().hex[:8]}"
        send_result = run_step([
            python_bin,
            str(TASK_CENTER_CARD_SDK_DIR / "send_card_v2.py"),
            "--card",
            output_path,
            "--to",
            args.receive_id,
            "--type",
            args.receive_id_type,
            "--uuid",
            request_uuid,
        ], quiet=True)
        sent = json.loads(send_result.stdout)
        message_id = (((sent.get("data") or {}).get("message_id")) or "")
        print(json.dumps({"status": "sent", "message_id": message_id, "card": output_path, "request_uuid": request_uuid}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"【续费日报发送失败】{exc}；请检查 yingdao 抓取配置或 Feishu 卡片投递链路", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
