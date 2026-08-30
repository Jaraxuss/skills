#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from speaker_engine.embedding import doctor as embedding_doctor
from speaker_engine.util import cache_root, data_root
from speaker_engine.storage import DataStore
from speaker_engine.workflow import (
    analyze_acoustic,
    analyze_finalize,
    customer_upsert,
    enrollment_commit,
    enrollment_prepare,
    list_profile_candidates,
    promote_candidate,
)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def selected_data_root(args: argparse.Namespace) -> Path:
    return args.data_dir.expanduser().resolve() if args.data_dir else data_root()


def make_store(args: argparse.Namespace) -> DataStore:
    return DataStore(selected_data_root(args))


def paths_command(args: argparse.Namespace) -> dict[str, Any]:
    root = selected_data_root(args)
    return {
        "skill": str(Path(__file__).resolve().parent.parent),
        "data_root": str(root),
        "registry": str(root / "registry.sqlite3"),
        "staff_profiles": str(root / "staff"),
        "customer_profiles": str(root / "customers"),
        "cache_root": str(cache_root()),
        "overrides": {
            "FEISHU_SPEAKER_DATA_DIR": os.environ.get("FEISHU_SPEAKER_DATA_DIR"),
            "FEISHU_SPEAKER_CACHE_DIR": os.environ.get("FEISHU_SPEAKER_CACHE_DIR"),
            "FEISHU_SPEAKER_3D_SPEAKER_DIR": os.environ.get(
                "FEISHU_SPEAKER_3D_SPEAKER_DIR"
            ),
            "MODELSCOPE_CACHE": os.environ.get("MODELSCOPE_CACHE"),
        },
    }


def writable_parent(path: Path) -> tuple[bool, Path]:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return os.access(candidate, os.W_OK), candidate


def doctor_command(args: argparse.Namespace) -> dict[str, Any]:
    result = embedding_doctor(download=args.download)
    root = selected_data_root(args)
    writable, checked = writable_parent(root)
    result["paths"] = paths_command(args)
    result["checks"]["data_root"] = {
        "ok": writable,
        "value": str(root),
        "checked_parent": str(checked),
    }
    result["ok"] = bool(result["ok"] and writable)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local customer-scoped voiceprint matching for Feishu Minutes recordings"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override FEISHU_SPEAKER_DATA_DIR for this command",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("paths", help="Show resolved skill, data, and cache paths")
    doctor = commands.add_parser("doctor", help="Check the CPU runtime and pinned model")
    doctor.add_argument(
        "--download",
        action="store_true",
        help="Download the pinned 3D-Speaker source and checkpoint when missing",
    )

    customer = commands.add_parser("customer", help="Manage customer metadata")
    customer_commands = customer.add_subparsers(dest="customer_command", required=True)
    customer_upsert_parser = customer_commands.add_parser("upsert")
    customer_upsert_parser.add_argument("--manifest", type=Path, required=True)

    enroll = commands.add_parser("enroll", help="Prepare or commit confirmed enrollment")
    enroll_commands = enroll.add_subparsers(dest="enroll_command", required=True)
    enroll_prepare_parser = enroll_commands.add_parser("prepare")
    enroll_prepare_parser.add_argument("--manifest", type=Path, required=True)
    enroll_commit_parser = enroll_commands.add_parser("commit")
    enroll_commit_parser.add_argument("--draft", type=Path, required=True)
    enroll_commit_parser.add_argument("--confirmation", type=Path, required=True)
    enroll_commit_parser.add_argument("--download", action="store_true")

    analyze = commands.add_parser("analyze", help="Run acoustic analysis or finalize a run")
    analyze_commands = analyze.add_subparsers(dest="analyze_command", required=True)
    acoustic = analyze_commands.add_parser("acoustic")
    acoustic.add_argument("--manifest", type=Path, required=True)
    acoustic.add_argument("--download", action="store_true")
    finalize = analyze_commands.add_parser("finalize")
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--context", type=Path)
    finalize.add_argument("--viewpoints", type=Path)

    profile = commands.add_parser("profile", help="Review, promote, or roll back profiles")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    candidates = profile_commands.add_parser("candidates")
    candidates.add_argument("--customer", required=True)
    promote = profile_commands.add_parser("promote")
    promote.add_argument("--candidate", type=Path, required=True)
    promote.add_argument("--person", required=True)
    promote.add_argument("--confirmed-by", required=True)
    rollback = profile_commands.add_parser("rollback")
    rollback.add_argument("--person", required=True)
    rollback.add_argument("--customer")
    rollback.add_argument("--to-version", type=int)
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "paths":
        return paths_command(args)
    if args.command == "doctor":
        return doctor_command(args)
    store = make_store(args)
    if args.command == "customer" and args.customer_command == "upsert":
        return customer_upsert(args.manifest, store)
    if args.command == "enroll" and args.enroll_command == "prepare":
        return enrollment_prepare(args.manifest, store)
    if args.command == "enroll" and args.enroll_command == "commit":
        return enrollment_commit(args.draft, args.confirmation, store, args.download)
    if args.command == "analyze" and args.analyze_command == "acoustic":
        return analyze_acoustic(args.manifest, store, args.download)
    if args.command == "analyze" and args.analyze_command == "finalize":
        return analyze_finalize(args.run_dir, args.context, args.viewpoints, store)
    if args.command == "profile" and args.profile_command == "candidates":
        return list_profile_candidates(args.customer, store)
    if args.command == "profile" and args.profile_command == "promote":
        return promote_candidate(args.candidate, args.person, args.confirmed_by, store)
    if args.command == "profile" and args.profile_command == "rollback":
        person = store.get_person(args.person)
        if args.customer and person["scope"] == "customer" and person["customer_id"] != args.customer:
            raise RuntimeError("Cross-customer rollback was blocked")
        return {"status": "rolled_back", **store.rollback_profile(args.person, args.to_version)}
    raise RuntimeError("Unhandled command")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        emit(dispatch(args))
    except Exception as exc:
        emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
