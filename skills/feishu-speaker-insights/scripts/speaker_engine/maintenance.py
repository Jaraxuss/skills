from __future__ import annotations

import contextlib
import fcntl
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from .errors import StructuredError
from .storage import DataStore


@contextlib.contextmanager
def runtime_lock_file(path: Path) -> Iterator[None]:
    """Acquire the process-wide backend/maintenance lock without opening SQLite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StructuredError(
                "SERVICE_ALREADY_RUNNING",
                "声纹后端正在运行；写入型维护操作必须先停止服务。",
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def service_runtime_lock(store: DataStore) -> Iterator[None]:
    """Prevent two backends or an online repair from sharing one registry."""
    with runtime_lock_file(store.locks_dir / "service-runtime.lock"):
        yield


def database_check(store: DataStore) -> dict[str, Any]:
    with store.connect() as db:
        integrity = [str(row[0]) for row in db.execute("PRAGMA integrity_check").fetchall()]
        foreign_keys = [dict(row) for row in db.execute("PRAGMA foreign_key_check").fetchall()]
        people = [
            dict(row)
            for row in db.execute(
                """
                SELECT person_id, name, customer_id, current_version
                FROM people WHERE current_version IS NOT NULL
                ORDER BY person_id
                """
            ).fetchall()
        ]
    profile_errors: list[dict[str, Any]] = []
    checked = 0
    for person in people:
        try:
            profile = store.load_profile(
                str(person["person_id"]), int(person["current_version"])
            )
            center = np.asarray(profile["arrays"].get("center"), dtype=np.float32)
            if center.shape != (192,) or not np.isfinite(center).all():
                raise ValueError(f"invalid center shape or values: {center.shape}")
            if not Path(profile["manifest_path"]).is_file():
                raise FileNotFoundError(profile["manifest_path"])
            checked += 1
        except Exception as exc:
            profile_errors.append(
                {
                    "person_id": person["person_id"],
                    "name": person["name"],
                    "version": person["current_version"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    ok = integrity == ["ok"] and not foreign_keys and not profile_errors
    return {
        "ok": ok,
        "registry": str(store.db_path),
        "integrity": integrity,
        "foreign_key_errors": foreign_keys,
        "current_profiles_checked": checked,
        "profile_errors": profile_errors,
    }


def repair_tasks(store: DataStore) -> dict[str, Any]:
    with service_runtime_lock(store):
        recovered = store.recover_expired_tasks(force=True)
    return {"ok": True, "recovered_tasks": recovered, "count": len(recovered)}


def inspect_task(store: DataStore, task_id: str) -> dict[str, Any]:
    return {"ok": True, "task": store.get_task(task_id)}
