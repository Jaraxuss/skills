from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .util import (
    atomic_save_npz,
    atomic_write_json,
    customers_root,
    data_root,
    ensure_private_dir,
    file_lock,
    now_iso,
    stable_id,
)


class DataStore:
    """File-backed profiles with a small global SQLite registry.

    Supplying ``customers_root`` (or ``FEISHU_SPEAKER_CUSTOMERS_ROOT``) enables
    the review-console layout.  The old ``root`` argument intentionally keeps
    the original layout for backward compatibility and isolated tests.
    """

    def __init__(self, root: Path | None = None, customers_root_path: Path | None = None):
        configured_customers_root = customers_root_path or (None if root else customers_root())
        self.customers_root: Path | None = None
        self.layout = "legacy"
        if configured_customers_root is not None:
            self.customers_root = ensure_private_dir(configured_customers_root.expanduser().resolve())
            self.root = ensure_private_dir(self.customers_root / "共享数据" / "声纹数据")
            self.layout = "customer-root-v1"
        else:
            self.root = ensure_private_dir((root or data_root()).expanduser().resolve())
        self.db_path = self.root / "registry.sqlite3"
        self.locks_dir = ensure_private_dir(self.root / ".locks")
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    directory_relpath TEXT,
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
                    status TEXT NOT NULL DEFAULT 'active',
                    review_session_id TEXT,
                    confirmation_mode TEXT,
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
                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    package_path TEXT,
                    result_path TEXT,
                    source_audio_sha256 TEXT,
                    source_transcript_sha256 TEXT,
                    revision INTEGER NOT NULL DEFAULT 0,
                    decision_json TEXT,
                    reviewed_by TEXT,
                    expires_at TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
                );
                CREATE TABLE IF NOT EXISTS review_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress_json TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES review_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    actor TEXT,
                    old_value_json TEXT,
                    new_value_json TEXT,
                    client_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES review_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS review_sessions_customer_status
                    ON review_sessions(customer_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS review_jobs_status_created
                    ON review_jobs(status, created_at);
                """
            )
            self._add_column(db, "customers", "directory_relpath TEXT")
            self._add_column(db, "profile_versions", "status TEXT NOT NULL DEFAULT 'active'")
            self._add_column(db, "profile_versions", "review_session_id TEXT")
            self._add_column(db, "profile_versions", "confirmation_mode TEXT")
        with np.errstate(all="ignore"):
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass

    @staticmethod
    def _add_column(db: sqlite3.Connection, table: str, declaration: str) -> None:
        column = declaration.split()[0]
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {declaration}")

    @staticmethod
    def _safe_relative_path(value: str) -> Path:
        candidate = Path(value)
        if not value or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError(f"Unsafe customer directory path: {value!r}")
        return candidate

    def _customer_dir_from_relpath(self, relpath: str) -> Path:
        if self.customers_root is None:
            raise RuntimeError("Customer-root layout is not active")
        target = (self.customers_root / self._safe_relative_path(relpath) / "声纹数据").resolve()
        root = self.customers_root.resolve()
        if root not in target.parents:
            raise RuntimeError("Customer directory escaped FEISHU_SPEAKER_CUSTOMERS_ROOT")
        # A symlink in the customer path could otherwise redirect biometric data.
        current = root
        for part in target.relative_to(root).parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise RuntimeError(f"Customer directory contains a symlink: {current}")
        return ensure_private_dir(target)

    def customer_dir(self, customer_id: str) -> Path:
        if self.layout == "legacy":
            return ensure_private_dir(self.root / "customers" / customer_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT directory_relpath FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
        if row is None or not row["directory_relpath"]:
            raise KeyError(f"Customer {customer_id} has no bound directory")
        return self._customer_dir_from_relpath(str(row["directory_relpath"]))

    def staff_dir(self) -> Path:
        return ensure_private_dir(self.root / "staff")

    def storage_uri(self, path: Path, customer_id: str | None = None) -> str:
        """Persist new locations as relocatable URIs; retain legacy absolute paths."""
        resolved = path.expanduser().resolve()
        if self.layout == "legacy":
            return str(resolved)
        staff = self.staff_dir().resolve()
        if resolved == staff or staff in resolved.parents:
            return "shared://staff/" + str(resolved.relative_to(staff)).replace(os.sep, "/")
        if customer_id:
            customer = self.customer_dir(customer_id).resolve()
            if resolved == customer or customer in resolved.parents:
                return f"customer://{customer_id}/" + str(resolved.relative_to(customer)).replace(os.sep, "/")
        raise ValueError(f"Path is outside the managed speaker roots: {resolved}")

    def resolve_storage_path(self, value: str, customer_id: str | None = None) -> Path:
        if value.startswith("shared://staff/"):
            suffix = self._safe_relative_path(value.removeprefix("shared://staff/"))
            target = (self.staff_dir() / suffix).resolve()
            if self.staff_dir().resolve() not in target.parents and target != self.staff_dir().resolve():
                raise RuntimeError("Shared storage URI escaped the staff root")
            return target
        if value.startswith("customer://"):
            _, rest = value.split("customer://", 1)
            stored_id, separator, suffix_text = rest.partition("/")
            if not separator or not stored_id:
                raise ValueError(f"Invalid customer storage URI: {value}")
            if customer_id and stored_id != customer_id:
                raise RuntimeError("Cross-customer storage URI was blocked")
            suffix = self._safe_relative_path(suffix_text)
            base = self.customer_dir(stored_id).resolve()
            target = (base / suffix).resolve()
            if base not in target.parents and target != base:
                raise RuntimeError("Customer storage URI escaped the customer root")
            return target
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(f"Legacy path must be absolute: {value}")
        return path.resolve()

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
            existing = db.execute(
                "SELECT directory_relpath FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            directory_relpath: str | None = None
            if self.layout == "customer-root-v1":
                requested = str(customer.get("directory_relpath") or customer_name).strip()
                directory_relpath = (
                    str(existing["directory_relpath"])
                    if existing and existing["directory_relpath"]
                    else str(self._safe_relative_path(requested))
                )
            db.execute(
                """
                INSERT INTO customers(customer_id, name, directory_relpath, metadata_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    name=excluded.name,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    customer_id,
                    customer_name,
                    directory_relpath,
                    json.dumps(customer, ensure_ascii=False),
                    now,
                    now,
                ),
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

    def list_customers(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM customers ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]

    def console_summary(self) -> dict[str, Any]:
        """Return operational counts for the local review console only."""
        with self.connect() as db:
            customer_total = len(self.discover_customers())
            task_rows = db.execute(
                "SELECT status, COUNT(*) AS count FROM review_sessions GROUP BY status"
            ).fetchall()
            profile_people = int(
                db.execute(
                    "SELECT COUNT(*) FROM people WHERE active = 1 AND current_version IS NOT NULL"
                ).fetchone()[0]
            )
            profile_versions = int(db.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0])
            pending_candidates = int(
                db.execute(
                    "SELECT COUNT(*) FROM candidates WHERE status = 'pending_confirmation'"
                ).fetchone()[0]
            )
        return {
            "customers_total": customer_total,
            "tasks": {str(row["status"]): int(row["count"]) for row in task_rows},
            "active_profile_people": profile_people,
            "profile_versions_total": profile_versions,
            "pending_candidates": pending_candidates,
        }

    def _customer_directory_entries(self) -> list[Path]:
        if self.layout != "customer-root-v1" or self.customers_root is None:
            return []
        root = self.customers_root.resolve()
        return sorted(
            [
                item
                for item in root.iterdir()
                if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")
                and item.name != "共享数据"
            ],
            key=lambda item: item.name.casefold(),
        )

    def discover_customers(self) -> list[dict[str, Any]]:
        """List customer directories without creating data or registry rows.

        A directory becomes a registered customer only after the user submits
        a build task.  This keeps the customer picker a side-effect-free view
        of the existing customer filesystem and removes any OpenClaw setup
        dependency.
        """
        if self.layout != "customer-root-v1" or self.customers_root is None:
            return self.list_customers()
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM customers").fetchall()]
        by_relpath = {
            str(row["directory_relpath"]): row
            for row in rows
            if row.get("directory_relpath")
        }
        by_name = {str(row["name"]): row for row in rows}
        discovered: list[dict[str, Any]] = []
        for directory in self._customer_directory_entries():
            relative = str(self._safe_relative_path(directory.name))
            row = by_relpath.get(relative) or by_name.get(directory.name)
            if row is None:
                discovered.append(
                    {
                        "customer_id": stable_id("customer", "directory", directory.name),
                        "name": directory.name,
                        "directory_relpath": relative,
                        "metadata_json": json.dumps(
                            {"name": directory.name, "directory_relpath": relative}, ensure_ascii=False
                        ),
                        "registered": False,
                    }
                )
            else:
                discovered.append({**row, "registered": True})
        return discovered

    def customer_source_dir(self, customer_id: str) -> Path:
        """Resolve a visible customer's raw-file directory without writing it."""
        if self.layout != "customer-root-v1" or self.customers_root is None:
            return self.customer_dir(customer_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT directory_relpath, name FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
        requested_relpath = str(row["directory_relpath"]) if row and row["directory_relpath"] else None
        requested_name = str(row["name"]) if row else None
        for directory in self._customer_directory_entries():
            relative = str(self._safe_relative_path(directory.name))
            if (
                relative == requested_relpath
                or directory.name == requested_name
                or stable_id("customer", "directory", directory.name) == customer_id
            ):
                return directory.resolve()
        raise KeyError(f"Customer directory does not exist: {customer_id}")

    def list_people(self, customer_id: str | None = None, include_staff: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM people WHERE active = 1"
        parameters: list[Any] = []
        if customer_id:
            query += " AND (scope = 'customer' AND customer_id = ?"
            parameters.append(customer_id)
            if include_staff:
                query += " OR scope = 'staff'"
            query += ")"
        query += " ORDER BY scope, name COLLATE NOCASE"
        with self.connect() as db:
            rows = db.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

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
                    INSERT INTO profile_versions(
                        person_id, version, npz_path, manifest_path, status,
                        review_session_id, confirmation_mode, created_at
                    ) VALUES(?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        person["person_id"],
                        next_version,
                        self.storage_uri(npz_path, person.get("customer_id")),
                        self.storage_uri(manifest_path, person.get("customer_id")),
                        str(manifest.get("review_session_id") or "") or None,
                        str(manifest.get("confirmation_mode") or "") or None,
                        now_iso(),
                    ),
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
        npz_path = self.resolve_storage_path(str(row["npz_path"]), person.get("customer_id"))
        manifest_path = self.resolve_storage_path(str(row["manifest_path"]), person.get("customer_id"))
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
                (run_id, customer_id, meeting_id, kind, self.storage_uri(run_dir, customer_id), now, now),
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
            "npz_path": self.storage_uri(npz_path, customer_id),
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
                    self.storage_uri(metadata_path, customer_id),
                    self.storage_uri(npz_path, customer_id),
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
            path = self.resolve_storage_path(str(row["metadata_path"]), customer_id)
            if path.exists():
                values.append(json.loads(path.read_text(encoding="utf-8")))
        return values

    def get_candidate(self, candidate_id: str) -> tuple[dict[str, Any], Path]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        path = self.resolve_storage_path(str(row["metadata_path"]), str(row["customer_id"]))
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8")), path

    def mark_candidate(self, candidate_id: str, status: str, details: dict[str, Any]) -> None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            path = self.resolve_storage_path(str(row["metadata_path"]), str(row["customer_id"]))
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
                db.execute(
                    "UPDATE profile_versions SET status = 'active' WHERE person_id = ? AND version = ?",
                    (person_id, selected),
                )
        return {
            "person_id": person_id,
            "name": person["name"],
            "from_version": int(current),
            "to_version": selected,
        }

    def list_profile_versions(self, person_id: str) -> list[dict[str, Any]]:
        person = self.get_person(person_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM profile_versions WHERE person_id = ? ORDER BY version DESC", (person_id,)
            ).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            value["npz_path"] = str(
                self.resolve_storage_path(str(value["npz_path"]), person.get("customer_id"))
            )
            value["manifest_path"] = str(
                self.resolve_storage_path(str(value["manifest_path"]), person.get("customer_id"))
            )
            value["is_current"] = int(value["version"]) == person.get("current_version")
            values.append(value)
        return values

    def quarantine_profile(self, person_id: str, actor: str | None = None) -> dict[str, Any]:
        person = self.get_person(person_id)
        previous = person.get("current_version")
        with file_lock(self.person_lock(person)):
            atomic_write_json(
                self.profile_dir(person) / "current.json",
                {
                    "schema_version": 1,
                    "person_id": person_id,
                    "version": None,
                    "updated_at": now_iso(),
                    "status": "quarantined",
                    "quarantined_by": actor,
                },
            )
            with self.connect() as db:
                db.execute(
                    "UPDATE people SET current_version = NULL, updated_at = ? WHERE person_id = ?",
                    (now_iso(), person_id),
                )
                if previous is not None:
                    db.execute(
                        "UPDATE profile_versions SET status = 'quarantined' WHERE person_id = ? AND version = ?",
                        (person_id, int(previous)),
                    )
        return {
            "person_id": person_id,
            "name": person["name"],
            "quarantined_version": previous,
            "status": "quarantined",
        }

    def restore_profile_pointer(self, person_id: str, version: int | None) -> None:
        """Recovery primitive used by a failed multi-person review commit.

        Version files are immutable.  Restoring only the current pointer keeps
        a partially written version unreachable by analysis and makes retries
        safe without deleting audit material.
        """
        person = self.get_person(person_id)
        with file_lock(self.person_lock(person)):
            payload: dict[str, Any] = {
                "schema_version": 1,
                "person_id": person_id,
                "version": version,
                "updated_at": now_iso(),
                "restored_after_failed_review": True,
            }
            if version is not None:
                profile = self.load_profile(person_id, version)
                payload.update({"npz": profile["npz_path"].name, "manifest": profile["manifest_path"].name})
            atomic_write_json(self.profile_dir(person) / "current.json", payload)
            with self.connect() as db:
                db.execute(
                    "UPDATE people SET current_version = ?, updated_at = ? WHERE person_id = ?",
                    (version, now_iso(), person_id),
                )

    def session_dir(self, customer_id: str, session_id: str) -> Path:
        return ensure_private_dir(self.customer_dir(customer_id) / "enrollments" / session_id)

    @staticmethod
    def _expiry(days: int = 7) -> str:
        return (
            datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=days)
        ).isoformat()

    def _audit(
        self,
        db: sqlite3.Connection,
        event_type: str,
        session_id: str | None = None,
        actor: str | None = None,
        old_value: Any | None = None,
        new_value: Any | None = None,
        client: Any | None = None,
    ) -> None:
        db.execute(
            """
            INSERT INTO audit_events(
                session_id, event_type, actor, old_value_json, new_value_json, client_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event_type,
                actor,
                json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
                json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
                json.dumps(client, ensure_ascii=False) if client is not None else None,
                now_iso(),
            ),
        )

    def audit_event(
        self,
        event_type: str,
        *,
        session_id: str | None = None,
        actor: str | None = None,
        value: Any | None = None,
        client: Any | None = None,
    ) -> None:
        with self.connect() as db:
            self._audit(db, event_type, session_id, actor, new_value=value, client=client)

    def audit_count(self, session_id: str, event_type: str) -> int:
        with self.connect() as db:
            return int(
                db.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE session_id = ? AND event_type = ?",
                    (session_id, event_type),
                ).fetchone()[0]
            )

    def create_review_session(
        self,
        customer_id: str,
        session_id: str,
        kind: str,
        manifest_path: Path,
        source_audio_sha256: str | None,
        source_transcript_sha256: str | None,
        expires_days: int = 7,
    ) -> dict[str, Any]:
        self.get_customer(customer_id)
        now = now_iso()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO review_sessions(
                    session_id, customer_id, kind, status, manifest_path, package_path, result_path,
                    source_audio_sha256, source_transcript_sha256, revision, expires_at, created_at, updated_at
                ) VALUES(?, ?, ?, 'queued', ?, NULL, NULL, ?, ?, 0, ?, ?, ?)
                """,
                (
                    session_id,
                    customer_id,
                    kind,
                    self.storage_uri(manifest_path, customer_id),
                    source_audio_sha256,
                    source_transcript_sha256,
                    self._expiry(expires_days),
                    now,
                    now,
                ),
            )
            db.execute(
                """
                INSERT INTO review_jobs(job_id, session_id, job_type, status, created_at, updated_at)
                VALUES(?, ?, 'prepare', 'queued', ?, ?)
                """,
                (f"job-{session_id}", session_id, now, now),
            )
            self._audit(db, "review_session_created", session_id, new_value={"kind": kind})
        return self.get_review_session(session_id)

    def _hydrate_review_session(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        customer_id = value["customer_id"]
        for key in ("manifest_path", "package_path", "result_path"):
            if value.get(key):
                value[key] = str(self.resolve_storage_path(str(value[key]), customer_id))
        if value.get("decision_json"):
            value["decision"] = json.loads(value["decision_json"])
        else:
            value["decision"] = None
        value.pop("decision_json", None)
        return value

    @staticmethod
    def _hydrate_review_job(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        try:
            value["progress"] = json.loads(value.pop("progress_json") or "null")
        except json.JSONDecodeError:
            value["progress"] = None
            value.pop("progress_json", None)
        return value

    def _attach_review_job(self, session: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM review_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session["session_id"],),
            ).fetchone()
        session["job"] = self._hydrate_review_job(row) if row is not None else None
        return session

    def get_review_session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM review_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._attach_review_job(self._hydrate_review_session(row))

    def list_review_sessions(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_sessions"
        parameters: tuple[Any, ...] = ()
        if customer_id:
            query += " WHERE customer_id = ?"
            parameters = (customer_id,)
        query += " ORDER BY updated_at DESC"
        with self.connect() as db:
            rows = db.execute(query, parameters).fetchall()
        return [self._attach_review_job(self._hydrate_review_session(row)) for row in rows]

    def set_review_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        package_path: Path | None = None,
        result_path: Path | None = None,
        error_message: str | None = None,
        reviewed_by: str | None = None,
        decision: dict[str, Any] | None = None,
        expected_revision: int | None = None,
        actor: str | None = None,
        client: dict[str, Any] | None = None,
        event_type: str = "review_session_updated",
    ) -> dict[str, Any]:
        with self.connect() as db:
            before_row = db.execute(
                "SELECT * FROM review_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if before_row is None:
                raise KeyError(session_id)
            before = self._hydrate_review_session(before_row)
            if expected_revision is not None and int(before["revision"]) != int(expected_revision):
                raise RuntimeError("review_revision_conflict")
            fields: dict[str, Any] = {"updated_at": now_iso()}
            if status is not None:
                fields["status"] = status
            if package_path is not None:
                fields["package_path"] = self.storage_uri(package_path, before["customer_id"])
            if result_path is not None:
                fields["result_path"] = self.storage_uri(result_path, before["customer_id"])
            if error_message is not None:
                fields["error_message"] = error_message
            if reviewed_by is not None:
                fields["reviewed_by"] = reviewed_by
            if decision is not None:
                fields["decision_json"] = json.dumps(decision, ensure_ascii=False)
                fields["revision"] = int(before["revision"]) + 1
            assignments = ", ".join(f"{key} = ?" for key in fields)
            db.execute(
                f"UPDATE review_sessions SET {assignments} WHERE session_id = ?",
                (*fields.values(), session_id),
            )
            self._audit(db, event_type, session_id, actor, before, fields, client)
        return self.get_review_session(session_id)

    def claim_review_job(self) -> dict[str, Any] | None:
        """Atomically claim one preparation job; one process can own it at a time."""
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM review_jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                db.commit()
                return None
            now = now_iso()
            changed = db.execute(
                """
                UPDATE review_jobs
                SET status = 'running', started_at = ?, updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (now, now, row["job_id"]),
            ).rowcount
            if changed != 1:
                db.rollback()
                return None
            db.execute(
                "UPDATE review_sessions SET status = 'preparing', updated_at = ? WHERE session_id = ?", (now, row["session_id"])
            )
            db.execute(
                "UPDATE review_jobs SET progress_json = ? WHERE job_id = ?",
                (json.dumps({"phase": "starting", "message": "正在启动本地声纹处理…"}, ensure_ascii=False), row["job_id"]),
            )
            self._audit(db, "review_job_claimed", row["session_id"], new_value={"job_id": row["job_id"]})
            db.commit()
            return dict(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def finish_review_job(
        self, job_id: str, status: str, progress: dict[str, Any] | None = None, error: str | None = None
    ) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError(f"Invalid final review job status: {status}")
        with self.connect() as db:
            db.execute(
                """
                UPDATE review_jobs SET status = ?, progress_json = ?, error_message = ?,
                    finished_at = ?, updated_at = ? WHERE job_id = ?
                """,
                (status, json.dumps(progress, ensure_ascii=False) if progress else None, error, now_iso(), now_iso(), job_id),
            )

    def update_review_job_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        """Persist lightweight, user-visible progress without changing session state."""
        with self.connect() as db:
            db.execute(
                "UPDATE review_jobs SET progress_json = ?, updated_at = ? WHERE job_id = ? AND status = 'running'",
                (json.dumps(progress, ensure_ascii=False), now_iso(), job_id),
            )

    def cancel_review_session(
        self,
        session_id: str,
        actor: str | None = None,
        client: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.get_review_session(session_id)
        if session["status"] in {"committed", "cancelled", "expired"}:
            return session
        with self.connect() as db:
            db.execute(
                "UPDATE review_jobs SET status = 'cancelled', finished_at = ?, updated_at = ? "
                "WHERE session_id = ? AND status IN ('queued', 'running')",
                (now_iso(), now_iso(), session_id),
            )
        return self.set_review_session(
            session_id,
            status="cancelled",
            actor=actor,
            client=client,
            event_type="review_cancelled",
        )

    def expire_review_sessions(self) -> list[str]:
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for session in self.list_review_sessions():
            if session["status"] not in {"queued", "preparing", "review_required", "approved"}:
                continue
            try:
                expiry = datetime.fromisoformat(str(session["expires_at"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            if expiry <= now:
                self.set_review_session(session["session_id"], status="expired", event_type="review_expired")
                expired.append(session["session_id"])
        return expired
