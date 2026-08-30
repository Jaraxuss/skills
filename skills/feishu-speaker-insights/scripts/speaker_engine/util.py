from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import platform
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import yaml


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def data_root() -> Path:
    configured = os.environ.get("FEISHU_SPEAKER_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "feishu-speaker-insights"
    xdg = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return xdg / "feishu-speaker-insights"


def customers_root() -> Path | None:
    """Return the configured customer root for the review-console layout.

    ``None`` deliberately preserves the original single-data-root layout.  This
    lets an existing deployment remain readable until the explicit copy-based
    migration has completed.
    """
    configured = os.environ.get("FEISHU_SPEAKER_CUSTOMERS_ROOT")
    if not configured:
        return None
    return Path(configured).expanduser().resolve()


def cache_root() -> Path:
    configured = os.environ.get("FEISHU_SPEAKER_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Caches" / "feishu-speaker-insights"
    xdg = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    return xdg / "feishu-speaker-insights"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def load_structured(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def json_default(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def atomic_write_json(path: Path, value: Any) -> None:
    ensure_private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, default=json_default)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def atomic_save_npz(path: Path, **arrays: np.ndarray) -> None:
    ensure_private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        with np.load(temporary, allow_pickle=False) as check:
            if not check.files:
                raise RuntimeError(f"NPZ validation failed for {path}")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_private_dir(path.parent)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(kind: str, scope: str, name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:24]
    digest = hashlib.sha256(f"{kind}\0{scope}\0{name}".encode("utf-8")).hexdigest()[:12]
    return f"{slug + '-' if slug else ''}{digest}"


def safe_component(value: str, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:48]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{slug or fallback}-{digest}"


def require_absolute_file(value: str, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} must be an absolute path: {value}")
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{field}: {path}")
    return path


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).strip()


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    import fcntl

    ensure_private_dir(path.parent)
    with path.open("a+", encoding="utf-8") as handle:
        with contextlib.suppress(OSError):
            path.chmod(0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
