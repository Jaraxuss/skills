#!/usr/bin/env python3
"""Benchmark TorchScript inference against saved sequential voice embeddings."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.path.insert(0, str(args.skill_root.resolve() / "scripts"))

    from speaker_engine.embedding import EmbeddingEngine, normalize
    from speaker_engine.transcript import Candidate, convert_to_wav, read_window

    payload = json.loads(args.acoustic_json.read_text(encoding="utf-8"))
    candidates: list[Candidate] = []
    expected_rows: list[np.ndarray] = []
    for result in payload["results"]:
        rows = [Candidate(**value) for value in result["candidate_windows"]]
        with np.load(result["candidate_vector_path"], allow_pickle=False) as arrays:
            expected = np.asarray(arrays["embeddings"], dtype=np.float32)
        candidates.extend(rows)
        expected_rows.extend(expected)
    expected_matrix = np.stack(expected_rows).astype(np.float32)

    with tempfile.TemporaryDirectory(prefix="speaker-torchscript-benchmark-") as temporary:
        wav_path = Path(temporary) / "meeting.wav"
        convert_to_wav(args.audio.resolve(), wav_path, 16000)
        engine = EmbeddingEngine(download=False, threads=args.threads)
        features: list[torch.Tensor] = []
        with sf.SoundFile(wav_path) as audio:
            for candidate in candidates:
                wave = read_window(audio, candidate.start, candidate.end, engine.sample_rate)
                tensor = torch.from_numpy(np.asarray(wave, dtype=np.float32)).unsqueeze(0)
                features.append(engine.feature_extractor(tensor).unsqueeze(0))

        example = max(features, key=lambda value: int(value.shape[1]))
        compile_started = time.perf_counter()
        with torch.inference_mode():
            traced = torch.jit.trace(engine.model, example, check_trace=False)
            optimized = torch.jit.freeze(traced.eval())
            optimization_mode = "trace_freeze"
            optimized(example)
        compile_seconds = time.perf_counter() - compile_started

        actual_rows: list[np.ndarray] = []
        started = time.perf_counter()
        with torch.inference_mode():
            for feature in features:
                vector = optimized(feature).detach().squeeze(0).cpu().numpy()
                actual_rows.append(normalize(vector))
        inference_seconds = time.perf_counter() - started

    actual_matrix = np.stack(actual_rows).astype(np.float32)
    cosine = np.sum(actual_matrix * expected_matrix, axis=1)
    report = {
        "threads": args.threads,
        "windows": len(candidates),
        "compile_and_warmup_seconds": compile_seconds,
        "optimization_mode": optimization_mode,
        "inference_seconds": inference_seconds,
        "max_absolute_difference": float(np.max(np.abs(actual_matrix - expected_matrix))),
        "minimum_cosine_to_sequential": float(np.min(cosine)),
        "mean_cosine_to_sequential": float(np.mean(cosine)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
