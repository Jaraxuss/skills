from __future__ import annotations

import json
import math
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
                    voiceprint_enabled INTEGER NOT NULL DEFAULT 1,
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
                    parent_version INTEGER,
                    creation_mode TEXT,
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
                CREATE TABLE IF NOT EXISTS task_executions (
                    task_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    external_request_id TEXT,
                    request_hash TEXT NOT NULL UNIQUE,
                    source_hash TEXT NOT NULL,
                    pipeline_hash TEXT NOT NULL,
                    cohort_hash TEXT,
                    semantic_hash TEXT,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    checkpoint_json TEXT,
                    artifact_dir_uri TEXT NOT NULL,
                    result_path TEXT,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    heartbeat_at TEXT,
                    error_code TEXT,
                    error_details_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
                );
                CREATE INDEX IF NOT EXISTS review_sessions_customer_status
                    ON review_sessions(customer_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS review_jobs_status_created
                    ON review_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS task_executions_customer_status
                    ON task_executions(customer_id, status, updated_at DESC);
                """
            )
            self._add_column(db, "customers", "directory_relpath TEXT")
            self._add_column(db, "profile_versions", "status TEXT NOT NULL DEFAULT 'active'")
            self._add_column(db, "profile_versions", "review_session_id TEXT")
            self._add_column(db, "profile_versions", "confirmation_mode TEXT")
            self._add_column(db, "profile_versions", "parent_version INTEGER")
            self._add_column(db, "profile_versions", "creation_mode TEXT")
            self._add_column(db, "people", "voiceprint_enabled INTEGER NOT NULL DEFAULT 1")
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

    def task_dir(self, customer_id: str, task_id: str) -> Path:
        return ensure_private_dir(self.customer_dir(customer_id) / "agent-tasks" / task_id)

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

    def ensure_shared_review_customer(self) -> dict[str, Any]:
        """Create the hidden registry owner used by staff profile reviews.

        Review sessions require a customer-scoped storage directory.  Global
        staff profiles do not belong to a customer, so their revision drafts
        live under the existing shared data directory and remain absent from
        the customer picker.
        """
        customer_id = "__shared_staff__"
        now = now_iso()
        metadata = {
            "id": customer_id,
            "name": "我方共享",
            "directory_relpath": "共享数据",
            "internal": True,
        }
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            if row is None:
                db.execute(
                    """
                    INSERT INTO customers(
                        customer_id, name, directory_relpath, metadata_json,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        customer_id,
                        metadata["name"],
                        "共享数据" if self.layout == "customer-root-v1" else None,
                        json.dumps(metadata, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
        # Resolve once so permissions and the review-session directory parent
        # are guaranteed before the caller writes a package.
        self.customer_dir(customer_id)
        return self.get_customer(customer_id)

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
                    """SELECT COUNT(*) FROM people
                       WHERE active = 1 AND voiceprint_enabled = 1
                             AND current_version IS NOT NULL"""
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

    def list_profiles(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        customer_id: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Return a server-paginated catalogue without duplicating global staff."""
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        clauses = [
            "p.active = 1",
            "EXISTS (SELECT 1 FROM profile_versions x WHERE x.person_id = p.person_id)",
        ]
        parameters: list[Any] = []
        if customer_id:
            clauses.append("p.scope = 'customer' AND p.customer_id = ?")
            parameters.append(customer_id)
        if scope in {"customer", "staff"}:
            clauses.append("p.scope = ?")
            parameters.append(scope)
        if status == "enabled":
            clauses.append("p.voiceprint_enabled = 1 AND p.current_version IS NOT NULL")
        elif status == "disabled":
            clauses.append("(p.voiceprint_enabled = 0 OR p.current_version IS NULL)")
        query_text = str(keyword or "").strip()
        if query_text:
            clauses.append("(p.name LIKE ? ESCAPE '\\' OR p.role LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')")
            escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend([f"%{escaped}%"] * 3)
        where = " AND ".join(f"({item})" for item in clauses)
        with self.connect() as db:
            total = int(
                db.execute(
                    f"SELECT COUNT(*) FROM people p LEFT JOIN customers c ON c.customer_id = p.customer_id WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            rows = db.execute(
                f"""
                SELECT p.*, c.name AS customer_name,
                       (SELECT COUNT(*) FROM profile_versions pv WHERE pv.person_id = p.person_id) AS version_count,
                       (SELECT created_at FROM profile_versions pv
                        WHERE pv.person_id = p.person_id AND pv.version = p.current_version) AS current_version_created_at
                FROM people p
                LEFT JOIN customers c ON c.customer_id = p.customer_id
                WHERE {where}
                ORDER BY p.updated_at DESC, p.name COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["voiceprint_enabled"] = bool(item.get("voiceprint_enabled"))
            item["profile_status"] = (
                "enabled"
                if item["voiceprint_enabled"] and item.get("current_version") is not None
                else "disabled"
            )
            item["current_version_summary"] = (
                self.profile_version_summary(str(item["person_id"]), int(item["current_version"]))
                if item.get("current_version") is not None
                else None
            )
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, int(math.ceil(total / page_size))) if total else 1,
        }

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
        *,
        make_current: bool = True,
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
            with self.connect() as db:
                highest = int(
                    db.execute(
                        "SELECT COALESCE(MAX(version), 0) FROM profile_versions WHERE person_id = ?",
                        (person["person_id"],),
                    ).fetchone()[0]
                )
            next_version = int(version) if version is not None else highest + 1
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
            if make_current:
                atomic_write_json(
                    profile_dir / "current.json",
                    {
                        "schema_version": 1,
                        "person_id": person["person_id"],
                        "version": next_version,
                        "npz": npz_path.name,
                        "manifest": manifest_path.name,
                        "status": "active" if bool(person.get("voiceprint_enabled", 1)) else "disabled",
                        "updated_at": now_iso(),
                    },
                )
            with self.connect() as db:
                db.execute(
                    """
                    INSERT INTO profile_versions(
                        person_id, version, npz_path, manifest_path, status,
                        review_session_id, confirmation_mode, parent_version,
                        creation_mode, created_at
                    ) VALUES(?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        person["person_id"],
                        next_version,
                        self.storage_uri(npz_path, person.get("customer_id")),
                        self.storage_uri(manifest_path, person.get("customer_id")),
                        str(manifest.get("review_session_id") or "") or None,
                        str(manifest.get("confirmation_mode") or "") or None,
                        manifest.get("parent_version") or manifest.get("previous_version"),
                        str(manifest.get("creation_mode") or "") or None,
                        now_iso(),
                    ),
                )
                if make_current:
                    db.execute(
                        "UPDATE people SET current_version = ?, updated_at = ? WHERE person_id = ?",
                        (next_version, now_iso(), person["person_id"]),
                    )
        return {
            "person_id": person["person_id"],
            "name": person["name"],
            "version": next_version,
            "is_current": make_current,
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
                      AND voiceprint_enabled = 1
                      AND current_version IS NOT NULL
                """,
                (customer_id,),
            ).fetchall()
            staff_rows = db.execute(
                """
                SELECT * FROM people
                WHERE scope = 'staff' AND active = 1 AND voiceprint_enabled = 1
                      AND current_version IS NOT NULL
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

    @staticmethod
    def _hydrate_task(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        for source, target in (
            ("checkpoint_json", "checkpoint"),
            ("error_details_json", "error_details"),
        ):
            raw = value.pop(source, None)
            try:
                value[target] = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                value[target] = None
        return value

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM task_executions WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        value = self._hydrate_task(row)
        value["artifact_dir"] = str(
            self.resolve_storage_path(str(value["artifact_dir_uri"]), value["customer_id"])
        )
        if value.get("result_path"):
            value["result_path"] = str(
                self.resolve_storage_path(str(value["result_path"]), value["customer_id"])
            )
        return value

    def find_task_by_request_hash(self, request_hash: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT task_id FROM task_executions WHERE request_hash = ?", (request_hash,)
            ).fetchone()
        return self.get_task(str(row["task_id"])) if row is not None else None

    def create_or_reuse_task(
        self,
        *,
        task_id: str,
        operation: str,
        customer_id: str,
        request_hash: str,
        source_hash: str,
        pipeline_hash: str,
        cohort_hash: str | None,
        external_request_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        existing = self.find_task_by_request_hash(request_hash)
        if existing is not None:
            return existing, True
        artifact_dir = self.task_dir(customer_id, task_id)
        now = now_iso()
        try:
            with self.connect() as db:
                db.execute(
                    """
                    INSERT INTO task_executions(
                        task_id, operation, customer_id, external_request_id,
                        request_hash, source_hash, pipeline_hash, cohort_hash,
                        status, phase, checkpoint_json, artifact_dir_uri,
                        created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'created', 'created', ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        operation,
                        customer_id,
                        external_request_id,
                        request_hash,
                        source_hash,
                        pipeline_hash,
                        cohort_hash,
                        json.dumps({}, ensure_ascii=False),
                        self.storage_uri(artifact_dir, customer_id),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.find_task_by_request_hash(request_hash)
            if existing is None:
                raise
            return existing, True
        return self.get_task(task_id), False

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        checkpoint: dict[str, Any] | None = None,
        result_path: Path | None = None,
        semantic_hash: str | None = None,
        error_code: str | None = None,
        error_details: dict[str, Any] | None = None,
        completed: bool = False,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        fields: dict[str, Any] = {"updated_at": now_iso()}
        if status is not None:
            fields["status"] = status
        if phase is not None:
            fields["phase"] = phase
        if checkpoint is not None:
            fields["checkpoint_json"] = json.dumps(checkpoint, ensure_ascii=False)
        if result_path is not None:
            fields["result_path"] = self.storage_uri(result_path, task["customer_id"])
        if semantic_hash is not None:
            fields["semantic_hash"] = semantic_hash
        if error_code is not None:
            fields["error_code"] = error_code
        if error_details is not None:
            fields["error_details_json"] = json.dumps(error_details, ensure_ascii=False)
        if status in {
            "awaiting_semantic",
            "waiting_worker",
            "waiting_confirmation",
            "completed",
            "failed",
            "cancelled",
        }:
            fields["lease_owner"] = None
            fields["lease_expires_at"] = None
        if completed:
            fields["completed_at"] = now_iso()
        if error_code is None and error_details is None and status in {
            "running",
            "awaiting_semantic",
            "waiting_worker",
            "waiting_confirmation",
            "completed",
        }:
            fields["error_code"] = None
            fields["error_details_json"] = None
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.connect() as db:
            db.execute(
                f"UPDATE task_executions SET {assignments} WHERE task_id = ?",
                (*fields.values(), task_id),
            )
        return self.get_task(task_id)

    def claim_task(self, task_id: str, owner: str, lease_seconds: int = 900) -> dict[str, Any]:
        """Acquire or renew a task lease so retries cannot run duplicate workers."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, int(lease_seconds)))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT lease_owner, lease_expires_at FROM task_executions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            active = False
            if row["lease_owner"] and row["lease_expires_at"]:
                try:
                    active = datetime.fromisoformat(
                        str(row["lease_expires_at"]).replace("Z", "+00:00")
                    ) > now
                except ValueError:
                    active = False
            if active and str(row["lease_owner"]) != owner:
                raise RuntimeError("task_already_running")
            db.execute(
                """
                UPDATE task_executions
                SET lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?,
                    status = 'running', updated_at = ?
                WHERE task_id = ?
                """,
                (owner, expires.isoformat(), now.isoformat(), now.isoformat(), task_id),
            )
            db.commit()
        return self.get_task(task_id)

    def heartbeat_task(self, task_id: str, owner: str, lease_seconds: int = 900) -> None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, int(lease_seconds)))
        with self.connect() as db:
            changed = db.execute(
                """
                UPDATE task_executions SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
                WHERE task_id = ? AND lease_owner = ?
                """,
                (now.isoformat(), expires.isoformat(), now.isoformat(), task_id, owner),
            ).rowcount
        if changed != 1:
            raise RuntimeError("task_lease_lost")

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

    @staticmethod
    def _window_key(window: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(window.get("label") or ""),
            int(window.get("utterance_index") or 0),
            round(float(window.get("start") or 0.0), 3),
            round(float(window.get("end") or 0.0), 3),
            str(window.get("text") or ""),
        )

    @staticmethod
    def _safe_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
        registration = manifest.get("registration") if isinstance(manifest.get("registration"), dict) else {}
        raw_sources = list(registration.get("source_recordings") or []) + list(manifest.get("sources") or [])
        allowed = {
            "source_id", "customer_id", "meeting_id", "title", "audio_relative_path",
            "transcript_relative_path", "audio_sha256", "transcript_sha256",
            "selected_window_count", "kind", "candidate_id", "run_id",
        }
        values: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            value = {key: raw.get(key) for key in allowed if raw.get(key) not in {None, ""}}
            if value.get("meeting_id"):
                identity = ("meeting", str(value["meeting_id"]), str(value.get("title") or ""))
            elif value.get("source_id"):
                identity = ("source", str(value["source_id"]), str(value.get("title") or ""))
            else:
                identity = (
                    "other",
                    str(value.get("candidate_id") or value.get("run_id") or ""),
                    str(value.get("title") or ""),
                )
            if identity in seen:
                continue
            seen.add(identity)
            values.append(value)
        return values

    def _profile_provenance(self, profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        manifest = profile["manifest"]
        stored = manifest.get("vector_provenance")
        if isinstance(stored, dict) and isinstance(stored.get("references"), list):
            raw = {
                "references": list(stored.get("references") or []),
                "heldouts": list(stored.get("heldouts") or []),
            }
        else:
            statistics = manifest.get("statistics") if isinstance(manifest.get("statistics"), dict) else {}
            raw = {
                "references": list(statistics.get("reference_windows") or []),
                "heldouts": list(statistics.get("holdout_windows") or []),
            }
        registration = manifest.get("registration") if isinstance(manifest.get("registration"), dict) else {}
        source_windows = [item for item in registration.get("source_windows") or [] if isinstance(item, dict)]
        source_map: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for item in source_windows:
            source_map.setdefault(self._window_key(item), []).append(item)
        output: dict[str, list[dict[str, Any]]] = {"references": [], "heldouts": []}
        for kind in ("references", "heldouts"):
            for index, item in enumerate(raw[kind]):
                if not isinstance(item, dict):
                    continue
                matches = source_map.get(self._window_key(item)) or []
                source = matches.pop(0) if matches else {}
                prefix = "ref" if kind == "references" else "holdout"
                output[kind].append(
                    {
                        **source,
                        **item,
                        "window_id": str(item.get("window_id") or f"{prefix}-{index:04d}"),
                        "array_kind": kind,
                        "array_index": index,
                    }
                )
        return output

    def profile_version_summary(self, person_id: str, version: int) -> dict[str, Any]:
        person = self.get_person(person_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM profile_versions WHERE person_id = ? AND version = ?",
                (person_id, int(version)),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Profile not found: {person_id} v{version}")
        manifest_path = self.resolve_storage_path(str(row["manifest_path"]), person.get("customer_id"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        statistics = manifest.get("statistics") if isinstance(manifest.get("statistics"), dict) else {}
        sources = self._safe_sources(manifest)
        reference_count = int(statistics.get("reference_count") or 0)
        holdout_count = int(statistics.get("holdout_count") or 0)
        if "reference_seconds" in statistics or "holdout_seconds" in statistics:
            seconds: float | None = float(statistics.get("reference_seconds") or 0.0) + float(
                statistics.get("holdout_seconds") or 0.0
            )
        else:
            provenance = manifest.get("vector_provenance")
            provenance_windows = (
                list(provenance.get("references") or []) + list(provenance.get("heldouts") or [])
                if isinstance(provenance, dict)
                else []
            )
            seconds = (
                float(
                    sum(
                        float(item.get("duration") or 0.0)
                        for item in provenance_windows
                        if isinstance(item, dict)
                    )
                )
                if provenance_windows
                else None
            )
        return {
            "version": int(version),
            "is_current": int(version) == person.get("current_version"),
            "created_at": manifest.get("created_at") or row["created_at"],
            "parent_version": manifest.get("parent_version") or manifest.get("previous_version"),
            "creation_mode": manifest.get("creation_mode") or (
                "fork" if manifest.get("parent_version") else "enrollment"
            ),
            "source_count": len(sources),
            "reference_count": reference_count,
            "holdout_count": holdout_count,
            "usable_seconds": seconds,
            "review_session_id": manifest.get("review_session_id"),
        }

    def list_profile_versions(self, person_id: str) -> list[dict[str, Any]]:
        person = self.get_person(person_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT version, status, review_session_id, confirmation_mode, parent_version, creation_mode, created_at "
                "FROM profile_versions WHERE person_id = ? ORDER BY version DESC",
                (person_id,),
            ).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            summary = self.profile_version_summary(person_id, int(row["version"]))
            values.append({**dict(row), **summary, "is_current": int(row["version"]) == person.get("current_version")})
        return values

    def profile_version_detail(self, person_id: str, version: int) -> dict[str, Any]:
        profile = self.load_profile(person_id, version)
        manifest = profile["manifest"]
        provenance = self._profile_provenance(profile)
        return {
            "person": {
                key: profile["person"].get(key)
                for key in (
                    "person_id", "name", "role", "scope", "organization", "customer_id",
                    "current_version", "voiceprint_enabled",
                )
            },
            "summary": self.profile_version_summary(person_id, version),
            "sources": self._safe_sources(manifest),
            "windows": provenance["references"] + provenance["heldouts"],
            "model": manifest.get("model") or {},
            "statistics": manifest.get("statistics") or {},
        }

    def set_current_profile_version(self, person_id: str, version: int) -> dict[str, Any]:
        person = self.get_person(person_id)
        selected = int(version)
        profile = self.load_profile(person_id, selected)
        previous = person.get("current_version")
        enabled = bool(person.get("voiceprint_enabled", 1))
        with file_lock(self.person_lock(person)):
            atomic_write_json(
                self.profile_dir(person) / "current.json",
                {
                    "schema_version": 1,
                    "person_id": person_id,
                    "version": selected,
                    "npz": profile["npz_path"].name,
                    "manifest": profile["manifest_path"].name,
                    "status": "active" if enabled else "disabled",
                    "updated_at": now_iso(),
                    "switched_from": previous,
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
            "from_version": previous,
            "to_version": selected,
            "voiceprint_enabled": enabled,
        }

    def rollback_profile(self, person_id: str, to_version: int | None = None) -> dict[str, Any]:
        person = self.get_person(person_id)
        current = person.get("current_version")
        if current is None:
            raise FileNotFoundError(f"No profile for {person['name']}")
        selected = int(current) - 1 if to_version is None else int(to_version)
        if selected < 1:
            raise ValueError("No earlier profile version exists")
        return self.set_current_profile_version(person_id, selected)

    def set_profile_enabled(self, person_id: str, enabled: bool) -> dict[str, Any]:
        person = self.get_person(person_id)
        current = person.get("current_version")
        if enabled and current is None:
            raise FileNotFoundError(f"No profile version can be enabled for {person['name']}")
        payload: dict[str, Any] = {
            "schema_version": 1,
            "person_id": person_id,
            "version": current,
            "status": "active" if enabled else "disabled",
            "updated_at": now_iso(),
        }
        if current is not None:
            profile = self.load_profile(person_id, int(current))
            payload.update({"npz": profile["npz_path"].name, "manifest": profile["manifest_path"].name})
        with file_lock(self.person_lock(person)):
            atomic_write_json(self.profile_dir(person) / "current.json", payload)
            with self.connect() as db:
                db.execute(
                    "UPDATE people SET voiceprint_enabled = ?, updated_at = ? WHERE person_id = ?",
                    (1 if enabled else 0, now_iso(), person_id),
                )
        return {
            "person_id": person_id,
            "name": person["name"],
            "current_version": current,
            "status": "enabled" if enabled else "disabled",
        }

    def quarantine_profile(self, person_id: str, actor: str | None = None) -> dict[str, Any]:
        """Compatibility alias for the old CLI; disabling is now non-destructive."""
        result = self.set_profile_enabled(person_id, False)
        return {**result, "disabled_by": actor}

    def fork_profile_version(
        self,
        person_id: str,
        base_version: int,
        included_window_ids: list[str] | None = None,
        *,
        make_current: bool = True,
        review_session_id: str | None = None,
        confirmation_mode: str = "web_version_editor",
    ) -> dict[str, Any]:
        from .matching import build_profile_arrays
        from .transcript import Candidate

        base = self.load_profile(person_id, int(base_version))
        provenance = self._profile_provenance(base)
        available = provenance["references"] + provenance["heldouts"]
        selected_ids = set(included_window_ids or [str(item["window_id"]) for item in available])
        unknown_ids = selected_ids - {str(item["window_id"]) for item in available}
        if unknown_ids:
            raise ValueError(f"Unknown profile windows: {', '.join(sorted(unknown_ids)[:3])}")
        selected = [item for item in available if str(item["window_id"]) in selected_ids]
        vectors: list[np.ndarray] = []
        candidates: list[Candidate] = []
        for item in selected:
            array_kind = str(item["array_kind"])
            array_index = int(item["array_index"])
            vectors.append(np.asarray(base["arrays"][array_kind][array_index], dtype=np.float32))
            candidates.append(
                Candidate(
                    label=str(item.get("label") or "历史声纹"),
                    utterance_index=int(item.get("utterance_index") or array_index),
                    start=float(item.get("start") or 0.0),
                    end=float(item.get("end") or float(item.get("start") or 0.0) + float(item.get("duration") or 0.0)),
                    timestamp=str(item.get("timestamp") or "00:00"),
                    text=str(item.get("text") or ""),
                    duration=float(item.get("duration") or 0.0),
                    rms_dbfs=float(item.get("rms_dbfs") or -30.0),
                    voiced_fraction=float(item.get("voiced_fraction") or 1.0),
                    clipping_ratio=float(item.get("clipping_ratio") or 0.0),
                    quality=float(item.get("quality") or 0.5),
                )
            )
        if not vectors:
            raise ValueError("At least one source window must be retained")
        arrays, statistics = build_profile_arrays(candidates, np.stack(vectors))

        pool: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for item in selected:
            pool.setdefault(self._window_key(item), []).append(item)
        vector_provenance: dict[str, list[dict[str, Any]]] = {"references": [], "heldouts": []}
        for kind, key in (("references", "reference_windows"), ("heldouts", "holdout_windows")):
            for index, window in enumerate(statistics.get(key) or []):
                matches = pool.get(self._window_key(window)) or []
                source = matches.pop(0) if matches else {}
                prefix = "ref" if kind == "references" else "holdout"
                vector_provenance[kind].append(
                    {
                        **source,
                        **window,
                        "window_id": f"{prefix}-{index:04d}",
                        "array_kind": kind,
                        "array_index": index,
                    }
                )
        source_ids = {str(item.get("source_id") or "") for item in selected}
        sources = [
            item for item in self._safe_sources(base["manifest"])
            if not source_ids or not item.get("source_id") or str(item.get("source_id")) in source_ids
        ]
        manifest = {
            "model": base["manifest"].get("model") or {},
            "parent_version": int(base_version),
            "previous_version": int(base_version),
            "creation_mode": "fork",
            "confirmation_mode": confirmation_mode,
            "review_session_id": review_session_id,
            "fork": {
                "base_version": int(base_version),
                "created_at": now_iso(),
                "retained_window_count": len(selected),
            },
            "statistics": statistics,
            "vector_provenance": vector_provenance,
            "registration": {
                "source_recordings": sources,
                "source_windows": selected,
            },
            "sources": sources,
        }
        saved = self.save_profile(
            base["person"], arrays, manifest, make_current=make_current
        )
        return {
            "person_id": person_id,
            "base_version": int(base_version),
            "new_version": int(saved["version"]),
            "made_current": bool(make_current),
            "retained_window_count": len(selected),
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

    def claim_review_job_for_session(self, session_id: str) -> dict[str, Any] | None:
        """Atomically claim the preparation job belonging to one known session."""
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM review_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is None:
                db.commit()
                return None
            if row["status"] == "running":
                db.commit()
                return None
            if row["status"] != "queued":
                db.commit()
                return dict(row)
            now = now_iso()
            changed = db.execute(
                """
                UPDATE review_jobs SET status = 'running', started_at = ?, updated_at = ?,
                    progress_json = ? WHERE job_id = ? AND status = 'queued'
                """,
                (
                    now,
                    now,
                    json.dumps(
                        {"phase": "starting", "message": "正在启动本地声纹处理…"},
                        ensure_ascii=False,
                    ),
                    row["job_id"],
                ),
            ).rowcount
            if changed != 1:
                db.rollback()
                return None
            db.execute(
                "UPDATE review_sessions SET status = 'preparing', updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            self._audit(
                db,
                "review_job_claimed",
                session_id,
                new_value={"job_id": row["job_id"], "agent_direct": True},
            )
            db.commit()
            value = dict(row)
            value["status"] = "running"
            return value
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
