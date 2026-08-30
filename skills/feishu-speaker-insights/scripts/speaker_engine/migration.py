from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from .storage import DataStore
from .util import atomic_write_json, ensure_private_dir, sha256_file


def _source_customer_rows(store: DataStore) -> list[dict[str, Any]]:
    with store.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM customers ORDER BY customer_id")]


def _directory_name(row: dict[str, Any]) -> str:
    # The requested migration deliberately uses an exact customer name, not a
    # fuzzy match.  DataStore validates that it remains beneath the root.
    return str(row["name"]).strip()


def layout_migration_plan(old_data_dir: Path, customers_root: Path) -> dict[str, Any]:
    source_root = old_data_dir.expanduser().resolve()
    if not (source_root / "registry.sqlite3").is_file():
        raise FileNotFoundError(f"Legacy registry was not found: {source_root / 'registry.sqlite3'}")
    source = DataStore(source_root)
    rows = _source_customer_rows(source)
    target_root = customers_root.expanduser().resolve()
    customer_items: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for row in rows:
        target = target_root / _directory_name(row) / "声纹数据"
        source_path = source.customer_dir(str(row["customer_id"]))
        if target.exists() and any(target.iterdir()):
            conflicts.append(str(target))
        customer_items.append(
            {
                "customer_id": row["customer_id"],
                "customer_name": row["name"],
                "source": str(source_path),
                "target": str(target),
                "file_count": sum(1 for item in source_path.rglob("*") if item.is_file())
                if source_path.exists()
                else 0,
            }
        )
    shared = target_root / "共享数据" / "声纹数据"
    registry_conflict = (shared / "registry.sqlite3").exists()
    if registry_conflict:
        conflicts.append(str(shared / "registry.sqlite3"))
    with source.connect() as db:
        counts = {
            table: int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("customers", "people", "profile_versions", "runs", "candidates")
        }
    return {
        "from_data_dir": str(source.root),
        "customers_root": str(target_root),
        "shared_target": str(shared),
        "customers": customer_items,
        "staff_source": str(source.staff_dir()),
        "staff_target": str(shared / "staff"),
        "counts": counts,
        "conflicts": conflicts,
        "can_apply": not conflicts,
        "copy_only": True,
        "old_data_retention": "The old directory is never removed by this command; retain it for at least 30 days.",
    }


def _copy_sqlite(source_path: Path, target_path: Path) -> None:
    ensure_private_dir(target_path.parent)
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _map_legacy_path(source: DataStore, target: DataStore, value: str, customer_id: str | None) -> str:
    old_path = Path(value).expanduser().resolve()
    staff = source.staff_dir().resolve()
    if old_path == staff or staff in old_path.parents:
        return target.storage_uri(target.staff_dir() / old_path.relative_to(staff))
    if customer_id:
        old_customer = source.customer_dir(customer_id).resolve()
        if old_path == old_customer or old_customer in old_path.parents:
            return target.storage_uri(target.customer_dir(customer_id) / old_path.relative_to(old_customer), customer_id)
    raise ValueError(f"Cannot migrate unmanaged legacy path: {old_path}")


def _validate_target(target: DataStore) -> dict[str, Any]:
    profile_hashes: list[dict[str, Any]] = []
    with target.connect() as db:
        profiles = db.execute("SELECT * FROM profile_versions ORDER BY person_id, version").fetchall()
        foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
    for row in profiles:
        person = target.get_person(str(row["person_id"]))
        npz_path = target.resolve_storage_path(str(row["npz_path"]), person.get("customer_id"))
        manifest_path = target.resolve_storage_path(str(row["manifest_path"]), person.get("customer_id"))
        if not npz_path.is_file() or not manifest_path.is_file():
            raise FileNotFoundError(f"Missing migrated profile file for {row['person_id']} v{row['version']}")
        with np.load(npz_path, allow_pickle=False) as arrays:
            for key in ("references", "heldouts", "center"):
                if key not in arrays:
                    raise ValueError(f"Missing {key} in {npz_path}")
            if arrays["references"].ndim != 2 or arrays["references"].shape[1] != 192:
                raise ValueError(f"Invalid profile vector dimensions in {npz_path}")
            if arrays["heldouts"].ndim != 2 or arrays["heldouts"].shape[1] != 192:
                raise ValueError(f"Invalid heldout dimensions in {npz_path}")
            if arrays["center"].shape != (192,):
                raise ValueError(f"Invalid center dimensions in {npz_path}")
        json.loads(manifest_path.read_text(encoding="utf-8"))
        profile_hashes.append(
            {"person_id": row["person_id"], "version": row["version"], "sha256": sha256_file(npz_path)}
        )
    if foreign_key_errors:
        raise RuntimeError(f"Foreign-key validation failed: {foreign_key_errors}")
    return {"profile_sha256": profile_hashes, "profile_count": len(profile_hashes)}


def apply_layout_migration(old_data_dir: Path, customers_root: Path) -> dict[str, Any]:
    plan = layout_migration_plan(old_data_dir, customers_root)
    if plan["conflicts"]:
        raise FileExistsError(
            "Migration would overwrite existing data; resolve these conflicts first: "
            + ", ".join(plan["conflicts"])
        )
    source = DataStore(old_data_dir.expanduser().resolve())
    target_root = customers_root.expanduser().resolve()
    shared = ensure_private_dir(target_root / "共享数据" / "声纹数据")
    _copy_sqlite(source.db_path, shared / "registry.sqlite3")

    for item in plan["customers"]:
        source_dir = Path(item["source"])
        target_dir = Path(item["target"])
        if source_dir.exists():
            ensure_private_dir(target_dir.parent)
            shutil.copytree(source_dir, target_dir)
    staff_source = source.staff_dir()
    if staff_source.exists():
        shutil.copytree(staff_source, shared / "staff")

    target = DataStore(customers_root_path=target_root)
    with target.connect() as db:
        for item in plan["customers"]:
            db.execute(
                "UPDATE customers SET directory_relpath = ? WHERE customer_id = ?",
                (item["customer_name"], item["customer_id"]),
            )
    # Commit directory bindings before URI conversion.  ``customer_dir`` opens
    # a separate short-lived connection by design, so it must observe them.
    with target.connect() as db:
        profile_rows = db.execute("SELECT * FROM profile_versions").fetchall()
        for row in profile_rows:
            person = target.get_person(str(row["person_id"]))
            db.execute(
                "UPDATE profile_versions SET npz_path = ?, manifest_path = ? WHERE person_id = ? AND version = ?",
                (
                    _map_legacy_path(source, target, str(row["npz_path"]), person.get("customer_id")),
                    _map_legacy_path(source, target, str(row["manifest_path"]), person.get("customer_id")),
                    row["person_id"],
                    row["version"],
                ),
            )
        for row in db.execute("SELECT * FROM runs").fetchall():
            db.execute(
                "UPDATE runs SET run_path = ? WHERE run_id = ?",
                (_map_legacy_path(source, target, str(row["run_path"]), str(row["customer_id"])), row["run_id"]),
            )
        for row in db.execute("SELECT * FROM candidates").fetchall():
            db.execute(
                "UPDATE candidates SET metadata_path = ?, npz_path = ? WHERE candidate_id = ?",
                (
                    _map_legacy_path(source, target, str(row["metadata_path"]), str(row["customer_id"])),
                    _map_legacy_path(source, target, str(row["npz_path"]), str(row["customer_id"])),
                    row["candidate_id"],
                ),
            )

    # Candidate metadata is an artifact as well as an index; rewrite only its
    # stored vector URI so it remains portable after the old directory is gone.
    with target.connect() as db:
        candidate_rows = db.execute("SELECT * FROM candidates").fetchall()
    for row in candidate_rows:
        metadata_path = target.resolve_storage_path(str(row["metadata_path"]), str(row["customer_id"]))
        if not metadata_path.is_file():
            continue
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload["npz_path"] = str(row["npz_path"])
        atomic_write_json(metadata_path, payload)

    validation = _validate_target(target)
    result = {**plan, "applied": True, "validation": validation}
    # An audit document next to the copied registry gives admins a direct
    # record even if the source directory is later archived elsewhere.
    atomic_write_json(shared / "layout_migration.json", result)
    return result
