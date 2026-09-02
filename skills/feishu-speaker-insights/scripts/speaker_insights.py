#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from speaker_engine.embedding import doctor as embedding_doctor
from speaker_engine.util import cache_root, customers_root, data_root
from speaker_engine.storage import DataStore
from speaker_engine.migration import apply_layout_migration, layout_migration_plan
from speaker_engine.review import (
    cleanup_review_artifacts,
    commit_review_session,
    create_enrollment_review,
    create_profile_revision_review,
    create_profile_review,
    restart_cancelled_enrollment_review,
    run_next_review_job,
    save_review_decision,
    validate_review_decision,
)
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
    if args.data_dir and args.customers_root:
        raise ValueError("--data-dir and --customers-root cannot be used together")
    if args.customers_root:
        return DataStore(customers_root_path=args.customers_root.expanduser().resolve())
    if not args.data_dir and customers_root() is not None:
        return DataStore()
    return DataStore(selected_data_root(args))


def paths_command(args: argparse.Namespace) -> dict[str, Any]:
    store = make_store(args)
    return {
        "skill": str(Path(__file__).resolve().parent.parent),
        "layout": store.layout,
        "data_root": str(store.root),
        "customers_root": str(store.customers_root) if store.customers_root else None,
        "registry": str(store.db_path),
        "staff_profiles": str(store.staff_dir()),
        "customer_profiles": (
            str(store.customers_root) if store.customers_root else str(store.root / "customers")
        ),
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
    store = make_store(args)
    writable, checked = writable_parent(store.root)
    result["paths"] = paths_command(args)
    result["checks"]["data_root"] = {
        "ok": writable,
        "value": str(store.root),
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
    parser.add_argument(
        "--customers-root",
        type=Path,
        help="Use the customer-root layout (or FEISHU_SPEAKER_CUSTOMERS_ROOT)",
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
    enroll_review_create = enroll_commands.add_parser("review-create")
    enroll_review_create.add_argument("--manifest", type=Path, required=True)
    enroll_review_create.add_argument("--base-url")
    enroll_review_create.add_argument("--expires-days", type=int, default=7)
    enroll_review_status = enroll_commands.add_parser("review-status")
    enroll_review_status.add_argument("--session", required=True)
    enroll_review_cancel = enroll_commands.add_parser("review-cancel")
    enroll_review_cancel.add_argument("--session", required=True)
    enroll_review_cancel.add_argument("--confirmed-by")
    enroll_review_restart = enroll_commands.add_parser("review-restart")
    enroll_review_restart.add_argument("--session", required=True)
    enroll_review_restart.add_argument("--base-url")
    enroll_review_restart.add_argument("--confirmed-by")

    analyze = commands.add_parser("analyze", help="Run acoustic analysis or finalize a run")
    analyze_commands = analyze.add_subparsers(dest="analyze_command", required=True)
    acoustic = analyze_commands.add_parser("acoustic")
    acoustic.add_argument("--manifest", type=Path, required=True)
    acoustic.add_argument("--download", action="store_true")
    finalize = analyze_commands.add_parser("finalize")
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--context", type=Path)
    finalize.add_argument(
        "--viewpoints",
        type=Path,
        required=True,
        help="Grounded viewpoints covering every label, with explicit background exceptions",
    )

    profile = commands.add_parser("profile", help="Review, version, enable, or disable profiles")
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
    quarantine = profile_commands.add_parser("quarantine")
    quarantine.add_argument("--person", required=True)
    quarantine.add_argument("--confirmed-by", required=True)
    versions = profile_commands.add_parser("versions")
    versions.add_argument("--person", required=True)
    set_current = profile_commands.add_parser("set-current")
    set_current.add_argument("--person", required=True)
    set_current.add_argument("--version", type=int, required=True)
    disable = profile_commands.add_parser("disable")
    disable.add_argument("--person", required=True)
    enable = profile_commands.add_parser("enable")
    enable.add_argument("--person", required=True)
    fork = profile_commands.add_parser("fork")
    fork.add_argument("--person", required=True)
    fork.add_argument("--base-version", type=int, required=True)
    fork.add_argument("--window-ids", type=Path, help="Optional JSON array of retained window IDs")
    fork.add_argument("--keep-current", action="store_true", help="Create the new version without making it current")
    profile_review_create = profile_commands.add_parser("review-create")
    profile_review_create.add_argument("--candidate", type=Path, required=True)
    profile_review_create.add_argument("--base-url")
    revision_review_create = profile_commands.add_parser("revision-review-create")
    revision_review_create.add_argument("--person", required=True)
    revision_review_create.add_argument("--base-version", type=int, required=True)
    revision_review_create.add_argument("--base-url")

    review = commands.add_parser("review", help="Run or inspect the browser enrollment review service")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    serve = review_commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--base-url")
    serve.add_argument("--download", action="store_true")
    worker = review_commands.add_parser("work-once")
    worker.add_argument("--download", action="store_true")
    review_status = review_commands.add_parser("status")
    review_status.add_argument("--session")
    review_validate = review_commands.add_parser("validate")
    review_validate.add_argument("--session", required=True)
    review_validate.add_argument("--decision", type=Path, required=True)
    review_commit = review_commands.add_parser("commit")
    review_commit.add_argument("--session", required=True)
    review_commit.add_argument("--revision", type=int, required=True)
    review_commit.add_argument("--confirmed-by")

    migrate = commands.add_parser("migrate", help="Copy legacy speaker data into the customer-root layout")
    migrate_commands = migrate.add_subparsers(dest="migrate_command", required=True)
    layout = migrate_commands.add_parser("layout")
    layout.add_argument("--from-data-dir", type=Path, required=True)
    layout.add_argument("--customers-root", type=Path, required=True)
    action = layout.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "paths":
        return paths_command(args)
    if args.command == "doctor":
        return doctor_command(args)
    if args.command == "migrate" and args.migrate_command == "layout":
        return (
            apply_layout_migration(args.from_data_dir, args.customers_root)
            if args.apply
            else layout_migration_plan(args.from_data_dir, args.customers_root)
        )
    store = make_store(args)
    if args.command == "customer" and args.customer_command == "upsert":
        return customer_upsert(args.manifest, store)
    if args.command == "enroll" and args.enroll_command == "prepare":
        return enrollment_prepare(args.manifest, store)
    if args.command == "enroll" and args.enroll_command == "commit":
        return enrollment_commit(args.draft, args.confirmation, store, args.download)
    if args.command == "enroll" and args.enroll_command == "review-create":
        return create_enrollment_review(
            args.manifest, store, base_url=args.base_url, expires_days=args.expires_days
        )
    if args.command == "enroll" and args.enroll_command == "review-status":
        return store.get_review_session(args.session)
    if args.command == "enroll" and args.enroll_command == "review-cancel":
        return store.cancel_review_session(args.session, args.confirmed_by)
    if args.command == "enroll" and args.enroll_command == "review-restart":
        return restart_cancelled_enrollment_review(
            args.session,
            store,
            base_url=args.base_url,
            actor=args.confirmed_by,
        )
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
    if args.command == "profile" and args.profile_command == "quarantine":
        return store.quarantine_profile(args.person, args.confirmed_by)
    if args.command == "profile" and args.profile_command == "versions":
        return {"person": store.get_person(args.person), "versions": store.list_profile_versions(args.person)}
    if args.command == "profile" and args.profile_command == "set-current":
        return store.set_current_profile_version(args.person, args.version)
    if args.command == "profile" and args.profile_command == "disable":
        return store.set_profile_enabled(args.person, False)
    if args.command == "profile" and args.profile_command == "enable":
        return store.set_profile_enabled(args.person, True)
    if args.command == "profile" and args.profile_command == "fork":
        window_ids = None
        if args.window_ids:
            window_ids = json.loads(args.window_ids.read_text(encoding="utf-8-sig"))
            if not isinstance(window_ids, list):
                raise ValueError("--window-ids must contain a JSON array")
        return store.fork_profile_version(
            args.person,
            args.base_version,
            [str(item) for item in window_ids] if window_ids is not None else None,
            make_current=not args.keep_current,
        )
    if args.command == "profile" and args.profile_command == "review-create":
        return create_profile_review(args.candidate, store, base_url=args.base_url)
    if args.command == "profile" and args.profile_command == "revision-review-create":
        return create_profile_revision_review(
            args.person,
            args.base_version,
            store,
            base_url=args.base_url,
        )
    if args.command == "review" and args.review_command == "work-once":
        result = run_next_review_job(store, download=args.download)
        cleanup_review_artifacts(store)
        return result or {"status": "idle"}
    if args.command == "review" and args.review_command == "status":
        cleanup_review_artifacts(store)
        return (
            store.get_review_session(args.session)
            if args.session
            else {"sessions": store.list_review_sessions()}
        )
    if args.command == "review" and args.review_command == "validate":
        return validate_review_decision(
            args.session, json.loads(args.decision.read_text(encoding="utf-8-sig")), store
        )
    if args.command == "review" and args.review_command == "commit":
        return commit_review_session(
            args.session, args.revision, store, actor=args.confirmed_by
        )
    if args.command == "review" and args.review_command == "serve":
        from review_server import run_server

        return run_server(
            store,
            host=args.host,
            port=args.port,
            base_url=args.base_url or f"http://{args.host}:{args.port}",
            download=args.download,
        )
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
