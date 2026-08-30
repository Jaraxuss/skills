from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable
from typing import Any

import numpy as np
import soundfile as sf
import torch

from .constants import MODEL_CONFIG, PIPELINE_CONFIG
from .transcript import Candidate, read_window
from .util import cache_root, ensure_private_dir, sha256_file


def normalize(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(norm) or norm <= 1e-8:
        raise ValueError("Invalid zero or non-finite embedding")
    return value / norm


def supported_platform() -> tuple[bool, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return True, "macos-arm64"
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return True, "ubuntu-x86_64-cpu"
    return False, f"{system.lower()}-{machine}"


def source_dir() -> Path:
    configured = os.environ.get("FEISHU_SPEAKER_3D_SPEAKER_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return cache_root() / "source" / "3D-Speaker"


def modelscope_cache_dir() -> Path:
    configured = os.environ.get("MODELSCOPE_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return cache_root() / "modelscope"


def source_revision(path: Path) -> str | None:
    if not path.exists() or not (path / ".git").exists():
        return None
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def prepare_source(download: bool) -> Path:
    path = source_dir()
    expected = str(MODEL_CONFIG["source_revision"])
    if path.exists():
        actual = source_revision(path)
        if actual != expected:
            raise RuntimeError(f"3D-Speaker revision mismatch: {actual} != {expected}")
        return path
    if not download:
        raise FileNotFoundError(
            f"3D-Speaker source missing at {path}; run doctor --download or set "
            "FEISHU_SPEAKER_3D_SPEAKER_DIR"
        )
    ensure_private_dir(path.parent)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", str(MODEL_CONFIG["source_url"]), str(path)],
        check=True,
    )
    subprocess.run(["git", "checkout", expected], cwd=path, check=True)
    actual = source_revision(path)
    if actual != expected:
        raise RuntimeError(f"3D-Speaker checkout failed: {actual} != {expected}")
    return path


def find_checkpoint(cache: Path) -> Path | None:
    if not cache.exists():
        return None
    matches = sorted(cache.rglob(str(MODEL_CONFIG["checkpoint"])))
    return matches[0] if matches else None


def prepare_checkpoint(download: bool) -> Path:
    cache = modelscope_cache_dir()
    checkpoint = find_checkpoint(cache)
    if checkpoint:
        return checkpoint
    if not download:
        raise FileNotFoundError(
            f"Model checkpoint missing below {cache}; run doctor --download"
        )
    ensure_private_dir(cache)
    os.environ["MODELSCOPE_CACHE"] = str(cache)
    from modelscope.hub.snapshot_download import snapshot_download

    model_dir = Path(
        snapshot_download(
            str(MODEL_CONFIG["id"]),
            revision=str(MODEL_CONFIG["revision"]),
        )
    )
    checkpoint = model_dir / str(MODEL_CONFIG["checkpoint"])
    if not checkpoint.exists():
        raise FileNotFoundError(checkpoint)
    return checkpoint


class EmbeddingEngine:
    def __init__(self, download: bool = False, threads: int | None = None):
        source = prepare_source(download)
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from speakerlab.models.eres2net.ERes2NetV2 import ERes2NetV2
        from speakerlab.process.processor import FBank

        self.sample_rate = int(PIPELINE_CONFIG["sample_rate"])
        self.feature_extractor = FBank(80, sample_rate=self.sample_rate, mean_nor=True)
        self.device = torch.device("cpu")
        selected_threads = threads or int(os.environ.get("FEISHU_SPEAKER_CPU_THREADS", "0") or 0)
        if selected_threads <= 0:
            selected_threads = max(1, min(4, os.cpu_count() or 1))
        torch.set_num_threads(selected_threads)

        checkpoint = prepare_checkpoint(download)
        self.model = ERes2NetV2(
            feat_dim=80,
            embedding_size=int(MODEL_CONFIG["embedding_size"]),
            baseWidth=26,
            scale=2,
            expansion=2,
        )
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state)
        self.model.to(self.device)
        self.model.eval()
        self.checkpoint_path = checkpoint
        self.checkpoint_sha256 = sha256_file(checkpoint)
        self.threads = selected_threads

    def embed(self, wave: np.ndarray) -> np.ndarray:
        tensor = torch.from_numpy(np.asarray(wave, dtype=np.float32)).unsqueeze(0)
        feature = self.feature_extractor(tensor).unsqueeze(0).to(self.device)
        with torch.no_grad():
            embedding = self.model(feature).detach().squeeze(0).cpu().numpy()
        result = normalize(embedding)
        expected = int(MODEL_CONFIG["embedding_size"])
        if result.shape != (expected,):
            raise RuntimeError(f"Unexpected embedding shape: {result.shape}")
        return result

    def embed_candidates(
        self,
        wav_path: Path,
        candidates: list[Candidate],
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> np.ndarray:
        vectors: list[np.ndarray] = []
        with sf.SoundFile(wav_path) as audio:
            for index, candidate in enumerate(candidates, start=1):
                if should_cancel and should_cancel():
                    raise InterruptedError("review_cancelled")
                wave = read_window(audio, candidate.start, candidate.end, self.sample_rate)
                vectors.append(self.embed(wave))
                if on_progress:
                    on_progress(index, len(candidates))
        if not vectors:
            return np.empty((0, int(MODEL_CONFIG["embedding_size"])), dtype=np.float32)
        return np.stack(vectors).astype(np.float32)


def doctor(download: bool = False) -> dict[str, Any]:
    ok, platform_name = supported_platform()
    checks: dict[str, Any] = {
        "platform": {"ok": ok, "value": platform_name},
        "python": {"ok": sys.version_info[:2] == (3, 10), "value": platform.python_version()},
        "cpu_only": {"ok": True, "value": "cpu"},
        "conda_environment": {
            "ok": os.environ.get("CONDA_DEFAULT_ENV") == "voiceprint-poc",
            "value": os.environ.get("CONDA_DEFAULT_ENV"),
        },
        "ffmpeg": {"ok": shutil.which("ffmpeg") is not None, "value": shutil.which("ffmpeg")},
    }
    if not ok:
        return {"ok": False, "checks": checks}
    try:
        source = prepare_source(download)
        checks["3d_speaker"] = {"ok": True, "path": str(source), "revision": source_revision(source)}
    except Exception as exc:
        checks["3d_speaker"] = {"ok": False, "error": str(exc)}
    try:
        checkpoint = prepare_checkpoint(download)
        checks["checkpoint"] = {
            "ok": True,
            "path": str(checkpoint),
            "sha256": sha256_file(checkpoint),
        }
    except Exception as exc:
        checks["checkpoint"] = {"ok": False, "error": str(exc)}

    dependencies: dict[str, Any] = {}
    for name in ["numpy", "soundfile", "yaml", "torch", "torchaudio", "modelscope"]:
        try:
            module = __import__(name)
            dependencies[name] = {"ok": True, "version": getattr(module, "__version__", None)}
        except Exception as exc:
            dependencies[name] = {"ok": False, "error": str(exc)}
    checks["dependencies"] = dependencies

    prerequisites_ok = all(
        item.get("ok", False)
        for key, item in checks.items()
        if key not in {"conda_environment", "dependencies"}
    ) and all(item.get("ok", False) for item in dependencies.values())
    if prerequisites_ok:
        try:
            engine = EmbeddingEngine(download=False)
            wave = np.random.default_rng(0).normal(0.0, 0.001, engine.sample_rate * 3).astype(
                np.float32
            )
            vector = engine.embed(wave)
            checks["model_probe"] = {
                "ok": bool(np.isfinite(vector).all()),
                "shape": list(vector.shape),
                "norm": float(np.linalg.norm(vector)),
                "threads": engine.threads,
            }
        except Exception as exc:
            checks["model_probe"] = {"ok": False, "error": str(exc)}
    checks_ok = all(
        value.get("ok", False)
        for key, value in checks.items()
        if key != "conda_environment" and key != "dependencies"
    ) and all(value.get("ok", False) for value in dependencies.values())
    return {"ok": checks_ok, "checks": checks}
