#!/usr/bin/env python3
"""Benchmark equal-length ERes2NetV2 batches against saved sequential embeddings."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--acoustic-json", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--batch-sizes", default="2,4,8")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scripts_dir = args.skill_root.resolve() / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from speaker_engine.embedding import EmbeddingEngine, normalize
    from speaker_engine.transcript import Candidate, convert_to_wav, read_window

    payload = json.loads(args.acoustic_json.read_text(encoding="utf-8"))
    candidates: list[Candidate] = []
    expected_rows: list[np.ndarray] = []
    for result in payload["results"]:
        rows = [Candidate(**value) for value in result["candidate_windows"]]
        with np.load(result["candidate_vector_path"], allow_pickle=False) as arrays:
            expected = np.asarray(arrays["embeddings"], dtype=np.float32)
        if len(rows) != len(expected):
            raise RuntimeError("Candidate/vector count mismatch")
        candidates.extend(rows)
        expected_rows.extend(expected)
    expected_matrix = np.stack(expected_rows).astype(np.float32)

    batch_sizes = [int(value) for value in args.batch_sizes.split(",") if value.strip()]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="speaker-batch-benchmark-") as temporary:
        wav_path = Path(temporary) / "meeting.wav"
        convert_to_wav(args.audio.resolve(), wav_path, 16000)
        engine = EmbeddingEngine(download=False, threads=args.threads)
        features: list[torch.Tensor] = []
        with sf.SoundFile(wav_path) as audio:
            for candidate in candidates:
                wave = read_window(audio, candidate.start, candidate.end, engine.sample_rate)
                tensor = torch.from_numpy(np.asarray(wave, dtype=np.float32)).unsqueeze(0)
                features.append(engine.feature_extractor(tensor))

        groups: dict[int, list[int]] = defaultdict(list)
        for index, feature in enumerate(features):
            groups[int(feature.shape[0])].append(index)

        with torch.inference_mode():
            engine.model(features[0].unsqueeze(0))

        for batch_size in batch_sizes:
            actual_rows: list[np.ndarray | None] = [None] * len(features)
            started = time.perf_counter()
            with torch.inference_mode():
                for indices in groups.values():
                    for offset in range(0, len(indices), batch_size):
                        selected = indices[offset : offset + batch_size]
                        batch = torch.stack([features[index] for index in selected])
                        vectors = engine.model(batch).detach().cpu().numpy()
                        for index, vector in zip(selected, vectors, strict=True):
                            actual_rows[index] = normalize(vector)
            elapsed = time.perf_counter() - started
            actual_matrix = np.stack(actual_rows).astype(np.float32)
            cosine = np.sum(actual_matrix * expected_matrix, axis=1)
            results.append(
                {
                    "batch_size": batch_size,
                    "embedding_seconds": elapsed,
                    "windows": len(features),
                    "length_groups": len(groups),
                    "max_absolute_difference": float(
                        np.max(np.abs(actual_matrix - expected_matrix))
                    ),
                    "minimum_cosine_to_sequential": float(np.min(cosine)),
                    "mean_cosine_to_sequential": float(np.mean(cosine)),
                }
            )

    report = {
        "threads": args.threads,
        "audio": str(args.audio.resolve()),
        "acoustic_json": str(args.acoustic_json.resolve()),
        "sequential_reference_windows": len(candidates),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
