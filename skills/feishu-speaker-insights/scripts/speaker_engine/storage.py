from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .util import (
    atomic_save_npz,
    atomic_write_json,
    data_root,
    ensure_private_dir,
    file_lock,
    now_iso,
    stable_id,
)


class DataStore:
    def __init__(self, root: Path | None = None):
        self.root = ensure_private_dir((root or data_root()).expanduser().resolve())
        self.db_path = self.root / "registry.sqlite3"
        self.locks_dir = ensure_private_dir(self.root / ".locks")
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS people (
                    person_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL CHECK(scope IN ('customer', 'staff')),
                    customer_id TEXT,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    organization TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    current_version INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS people_customer_name
                    ON people(customer_id, name) WHERE scope = 'customer';
                CREATE UNIQUE INDEX IF NOT EXISTS people_staff_name
                    ON people(name) WHERE scope = 'staff';
                CREATE TABLE IF NOT EXISTS profile_versions (
                    person_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    npz_path TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(person_id, version),
                    FOREIGN KEY(person_id) REFERENCES people(person_id)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    run_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    npz_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
                    FOREIGN KEY(person_id) REFERENCES people(person_id)
                );
                """
            )
        with np.errstate(all="ignore"):
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass

    def customer_dir(self, customer_id: str) -> Path:
        return ensure_private_dir(self.root / "customers" / customer_id)

    def staff_dir(self) -> Path:
        return ensure_private_dir(self.root / "staff")

    def upsert_manifest(self, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        customer = manifest.get("customer") or {}
        customer_id = str(customer.get("id", "")).strip()
        customer_name = str(customer.get("name", "")).strip()
        if not customer_id or not customer_name:
            raise ValueError("manifest.customer.id and manifest.customer.name are required")
        if any(char in customer_id for char in "/\\") or customer_id in {".", ".."}:
            raise ValueError(f"Unsafe customer id: {customer_id}")
        now = now_iso()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO customers(customer_id, name, metadata_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    name=excluded.name,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (customer_id, customer_name, json.dumps(customer, ensure_ascii=False), now, now),
            )
        customer_dir = self.customer_dir(customer_id)
        atomic_write_json(customer_dir / "customer.json", customer)

        people: dict[str, dict[str, Any]] = {}
        for attendee in manifest.get("attendees", []):
            if not isinstance(attendee, dict):
                raise ValueError("Each attendee must be an object")
            name = str(attendee.get("name", "")).strip()
            role = str(attendee.get("role", "")).strip()
            organization = str(attendee.get("organization", "")).strip().lower()
            if not name or organization not in {"customer", "yingdao", "external"}:
                raise ValueError(f"Invalid attendee: {attendee}")
            if name in people:
                raise ValueError(f"Duplicate attendee name is ambiguous: {name}")
            if organization == "external":
                people[name] = {
                    "person_id": None,
                    "name": name,
                    "role": role,
                    "organization": organization,
                    "scope": "external",
                    "customer_id": customer_id,
                }
                continue
            scope = "staff" if organization == "yingdao" else "customer"
            scoped_customer = None if scope == "staff" else customer_id
            person_id = str(attendee.get("id") or "").strip()
            if not person_id:
                person_id = stable_id(
                    "staff" if scope == "staff" else "person",
                    "global" if scope == "staff" else customer_id,
                    name,
                )
            with self.connect() as db:
                db.execute(
                    """
                    INSERT INTO people(
                        person_id, scope, customer_id, name, role, organization,
                        active, current_version, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
                    ON CONFLICT(person_id) DO UPDATE SET
                        name=excluded.name,
                        role=excluded.role,
                        organization=excluded.organization,
                        active=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        person_id,
                        scope,
                        scoped_customer,
                        name,
                        role,
                        organization,
                        now,
                        now,
                    ),
                )
            people[name] = self.get_person(person_id)
        return people

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown customer: {customer_id}")
        return dict(row)

    def get_person(self, person_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM people WHERE person_id = ?", (person_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown person: {person_id}")
        return dict(row)

    def resolve_attendee_name(
        self, customer_id: str, attendees: dict[str, dict[str, Any]], name: str
    ) -> dict[str, Any]:
        value = attendees.get(name)
        if not value or not value.get("person_id"):
            raise KeyError(f"Mapped name is not an enrollable attendee: {name}")
        if value["scope"] == "customer" and value["customer_id"] != customer_id:
            raise RuntimeError("Cross-customer attendee resolution was blocked")
        return value

    def profile_dir(self, person: dict[str, Any]) -> Path:
        if person["scope"] == "staff":
            base = self.staff_dir() / person["person_id"]
        else:
            base = self.customer_dir(person["customer_id"]) / "people" / person["person_id"]
        return ensure_private_dir(base / "profiles")

    def person_lock(self, person: dict[str, Any]) -> Path:
        scope = "staff" if person["scope"] == "staff" else person["customer_id"]
        return self.locks_dir / f"{scope}-{person['person_id']}.lock"

    def save_profile(
        self,
        person: dict[str, Any],
        arrays: dict[str, np.ndarray],
        manifest: dict[str, Any],
        version: int | None = None,
    ) -> dict[str, Any]:
        references = np.asarray(arrays["references"], dtype=np.float32)
        heldouts = np.asarray(arrays["heldouts"], dtype=np.float32)
        center = np.asarray(arrays["center"], dtype=np.float32)
        weights = np.asarray(arrays.get("quality_weights", np.ones(len(references))), dtype=np.float32)
        if references.ndim != 2 or references.shape[1] != 192:
            raise ValueError(f"Invalid reference shape: {references.shape}")
        if heldouts.ndim != 2 or heldouts.shape[1] != 192:
            raise ValueError(f"Invalid holdout shape: {heldouts.shape}")
        if center.shape != (192,) or not np.isfinite(references).all() or not np.isfinite(center).all():
            raise ValueError("Invalid profile arrays")

        profile_dir = self.profile_dir(person)
        with file_lock(self.person_lock(person)):
            current = person.get("current_version")
            next_version = version if version is not None else int(current or 0) + 1
            npz_path = profile_dir / f"v{next_version:04d}.npz"
            manifest_path = profile_dir / f"v{next_version:04d}.json"
            if npz_path.exists() or manifest_path.exists():
                raise FileExistsError(f"Profile version already exists: {person['person_id']} v{next_version}")
            enriched = {
                **manifest,
                "schema_version": 1,
                "person": {
                    "person_id": person["person_id"],
                    "name": person["name"],
                    "role": person["role"],
                    "scope": person["scope"],
                    "customer_id": person["customer_id"],
                },
                "version": next_version,
                "created_at": now_iso(),
                "array_file": npz_path.name,
            }
            atomic_save_npz(
                npz_path,
                references=references,
                heldouts=heldouts,
                center=center,
                quality_weights=weights,
            )
            atomic_write_json(manifest_path, enriched)
            atomic_write_json(
                profile_dir / "current.json",
                {
                    "schema_version": 1,
                    "person_id": person["person_id"],
                    "version": next_version,
                    "npz": npz_path.name,
                    "manifest": manifest_path.name,
                    "updated_at": now_iso(),
                },
            )
            with self.connect() as db:
                db.execute(
                    """
                    INSERT INTO profile_versions(person_id, version, npz_path, manifest_path, created_at)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (person["person_id"], next_version, str(npz_path), str(manifest_path), now_iso()),
                )
                db.execute(
                    "UPDATE people SET current_version = ?, updated_at = ? WHERE person_id = ?",
                    (next_version, now_iso(), person["person_id"]),
                )
        return {
            "person_id": person["person_id"],
            "name": person["name"],
            "version": next_version,
            "npz_path": str(npz_path),
            "manifest_path": str(manifest_path),
        }

    def load_profile(self, person_id: str, version: int | None = None) -> dict[str, Any]:
        person = self.get_person(person_id)
        selected = version if version is not None else person.get("current_version")
        if selected is None:
            raise FileNotFoundError(f"No active profile for {person['name']}")
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM profile_versions WHERE person_id = ? AND version = ?",
                (person_id, int(selected)),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Profile not found: {person_id} v{selected}")
        npz_path = Path(row["npz_path"])
        manifest_path = Path(row["manifest_path"])
        with np.load(npz_path, allow_pickle=False) as arrays:
            values = {key: np.asarray(arrays[key], dtype=np.float32) for key in arrays.files}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "person": person,
            "version": int(selected),
            "arrays": values,
            "manifest": manifest,
            "npz_path": npz_path,
            "manifest_path": manifest_path,
        }

    def analysis_profiles(
        self,
        customer_id: str,
        attendees: Iterable[dict[str, Any]],
        transcript_labels: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            customer_rows = db.execute(
                """
                SELECT * FROM people
                WHERE scope = 'customer' AND customer_id = ? AND active = 1
                      AND current_version IS NOT NULL
                """,
                (customer_id,),
            ).fetchall()
            staff_rows = db.execute(
                """
                SELECT * FROM people
                WHERE scope = 'staff' AND active = 1 AND current_version IS NOT NULL
                """
            ).fetchall()
        selected: dict[str, dict[str, Any]] = {row["person_id"]: dict(row) for row in customer_rows}
        requested_staff = {
            str(item.get("name", "")).strip()
            for item in attendees
            if str(item.get("organization", "")).lower() == "yingdao"
        }
        label_names = set(transcript_labels)
        for row in staff_rows:
            if row["name"] in requested_staff or row["name"] in label_names:
                selected[row["person_id"]] = dict(row)
        return {person_id: self.load_profile(person_id) for person_id in selected}

    def create_run(
        self, customer_id: str, meeting_id: str, run_id: str, kind: str
    ) -> Path:
        run_dir = ensure_private_dir(self.customer_dir(customer_id) / "runs" / run_id)
        now = now_iso()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO runs(run_id, customer_id, meeting_id, kind, status, run_path, created_at, updated_at)
                VALUES(?, ?, ?, ?, 'created', ?, ?, ?)
                """,
                (run_id, customer_id, meeting_id, kind, str(run_dir), now, now),
            )
        return run_dir

    def update_run(self, run_id: str, status: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now_iso(), run_id),
            )

    def enrollment_dir(self, customer_id: str, enrollment_id: str) -> Path:
        return ensure_private_dir(
            self.customer_dir(customer_id) / "enrollments" / enrollment_id
        )

    def save_candidate(
        self,
        customer_id: str,
        person_id: str,
        run_id: str,
        candidate_id: str,
        vectors: np.ndarray,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_dir = ensure_private_dir(self.customer_dir(customer_id) / "candidates")
        npz_path = candidate_dir / f"{candidate_id}.npz"
        metadata_path = candidate_dir / f"{candidate_id}.json"
        atomic_save_npz(npz_path, embeddings=np.asarray(vectors, dtype=np.float32))
        payload = {
            **metadata,
            "schema_version": 1,
            "candidate_id": candidate_id,
            "customer_id": customer_id,
            "person_id": person_id,
            "run_id": run_id,
            "status": "pending_confirmation",
            "npz_path": str(npz_path),
            "created_at": now_iso(),
        }
        atomic_write_json(metadata_path, payload)
        with self.connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO candidates(
                    candidate_id, customer_id, person_id, run_id, status,
                    metadata_path, npz_path, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    customer_id,
                    person_id,
                    run_id,
                    "pending_confirmation",
                    str(metadata_path),
                    str(npz_path),
                    now_iso(),
                    now_iso(),
                ),
            )
        return payload

    def list_candidates(self, customer_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM candidates WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            path = Path(row["metadata_path"])
            if path.exists():
                values.append(json.loads(path.read_text(encoding="utf-8")))
        return values

    def mark_candidate(self, candidate_id: str, status: str, details: dict[str, Any]) -> None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            path = Path(row["metadata_path"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["status"] = status
            payload["status_details"] = details
            payload["updated_at"] = now_iso()
            atomic_write_json(path, payload)
            db.execute(
                "UPDATE candidates SET status = ?, updated_at = ? WHERE candidate_id = ?",
                (status, now_iso(), candidate_id),
            )

    def rollback_profile(
        self, person_id: str, to_version: int | None = None
    ) -> dict[str, Any]:
        person = self.get_person(person_id)
        current = person.get("current_version")
        if current is None:
            raise FileNotFoundError(f"No profile for {person['name']}")
        selected = int(current) - 1 if to_version is None else int(to_version)
        if selected < 1:
            raise ValueError("No earlier profile version exists")
        profile = self.load_profile(person_id, selected)
        with file_lock(self.person_lock(person)):
            atomic_write_json(
                self.profile_dir(person) / "current.json",
                {
                    "schema_version": 1,
                    "person_id": person_id,
                    "version": selected,
                    "npz": profile["npz_path"].name,
                    "manifest": profile["manifest_path"].name,
                    "updated_at": now_iso(),
                    "rollback_from": int(current),
                },
            )
            with self.connect() as db:
                db.execute(
                    "UPDATE people SET current_version = ?, updated_at = ? WHERE person_id = ?",
                    (selected, now_iso(), person_id),
                )
        return {
            "person_id": person_id,
            "name": person["name"],
            "from_version": int(current),
            "to_version": selected,
        }
