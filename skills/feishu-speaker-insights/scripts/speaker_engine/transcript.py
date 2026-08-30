from __future__ import annotations

import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf


HEADER_RE = re.compile(
    r"^(?P<label>[^\r\n]{1,80}?)\s+(?P<timestamp>(?:\d{1,2}:)?\d{2}:\d{2})\s*$"
)


@dataclass
class Utterance:
    index: int
    label: str
    start: float
    end: float
    timestamp: str
    text: str


@dataclass
class Candidate:
    label: str
    utterance_index: int
    start: float
    end: float
    timestamp: str
    text: str
    duration: float
    rms_dbfs: float
    voiced_fraction: float
    clipping_ratio: float
    quality: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_timestamp(value: str) -> float:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours * 3600 + minutes * 60 + seconds)
    raise ValueError(f"Unsupported timestamp: {value}")


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_transcript(path: Path, audio_duration: float | None = None) -> list[Utterance]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            match = HEADER_RE.match(line.strip())
            if match:
                if current is not None:
                    rows.append(current)
                current = {
                    "label": re.sub(r"\s+", " ", match.group("label")).strip(),
                    "timestamp": match.group("timestamp"),
                    "start": parse_timestamp(match.group("timestamp")),
                    "text_lines": [],
                }
            elif current is not None and line.strip():
                current["text_lines"].append(line.strip())
    if current is not None:
        rows.append(current)
    if not rows:
        raise ValueError(f"No timestamped speaker rows found in {path}")

    utterances: list[Utterance] = []
    for index, row in enumerate(rows):
        next_start = rows[index + 1]["start"] if index + 1 < len(rows) else audio_duration
        if next_start is None:
            next_start = row["start"]
        end = max(float(row["start"]), float(next_start))
        utterances.append(
            Utterance(
                index=index,
                label=row["label"],
                start=float(row["start"]),
                end=end,
                timestamp=row["timestamp"],
                text=" ".join(row["text_lines"]).strip(),
            )
        )
    return utterances


def convert_to_wav(input_path: Path, output_path: Path, sample_rate: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
    )


def frame_rms(wave: np.ndarray, frame_size: int = 400, hop_size: int = 160) -> np.ndarray:
    if wave.size < frame_size:
        return np.array([float(np.sqrt(np.mean(np.square(wave)) + 1e-12))])
    count = 1 + (wave.size - frame_size) // hop_size
    shape = (count, frame_size)
    strides = (wave.strides[0] * hop_size, wave.strides[0])
    frames = np.lib.stride_tricks.as_strided(wave, shape=shape, strides=strides)
    return np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)


def quality_metrics(wave: np.ndarray) -> tuple[float, float, float, float]:
    if wave.size == 0:
        return -120.0, 0.0, 0.0, 0.0
    rms = float(np.sqrt(np.mean(np.square(wave)) + 1e-12))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-8))
    levels = frame_rms(wave)
    relative_threshold = float(np.quantile(levels, 0.70)) * 0.25
    threshold = max(0.001, relative_threshold)
    voiced_fraction = float(np.mean(levels > threshold))
    clipping_ratio = float(np.mean(np.abs(wave) >= 0.99))
    volume_score = float(np.clip((rms_dbfs + 55.0) / 35.0, 0.0, 1.0))
    clean_score = float(np.clip(1.0 - clipping_ratio * 20.0, 0.0, 1.0))
    quality = 0.45 * voiced_fraction + 0.35 * volume_score + 0.20 * clean_score
    return rms_dbfs, voiced_fraction, clipping_ratio, quality


def read_window(handle: sf.SoundFile, start: float, end: float, sample_rate: int) -> np.ndarray:
    first = max(0, int(round(start * sample_rate)))
    frames = max(0, int(round((end - start) * sample_rate)))
    handle.seek(first)
    wave = handle.read(frames=frames, dtype="float32", always_2d=False)
    if wave.ndim > 1:
        wave = np.mean(wave, axis=1)
    return np.asarray(wave, dtype=np.float32)


def build_candidates(
    wav_path: Path,
    utterances: Iterable[Utterance],
    settings: dict[str, Any],
) -> list[Candidate]:
    sample_rate = int(settings["sample_rate"])
    guard = float(settings["boundary_guard_seconds"])
    minimum = float(settings["min_window_seconds"])
    maximum = float(settings["max_window_seconds"])
    candidates: list[Candidate] = []
    with sf.SoundFile(wav_path) as audio:
        if audio.samplerate != sample_rate:
            raise ValueError(f"Expected {sample_rate} Hz, got {audio.samplerate} Hz")
        duration = len(audio) / sample_rate
        for utterance in utterances:
            start = min(duration, max(0.0, utterance.start + guard))
            end = min(duration, max(start, utterance.end - guard))
            cursor = start
            while end - cursor >= minimum:
                window_end = min(end, cursor + maximum)
                if window_end - cursor < minimum:
                    break
                wave = read_window(audio, cursor, window_end, sample_rate)
                rms_dbfs, voiced_fraction, clipping_ratio, quality = quality_metrics(wave)
                if (
                    rms_dbfs >= float(settings["min_rms_dbfs"])
                    and voiced_fraction >= float(settings["min_voiced_fraction"])
                    and clipping_ratio <= float(settings["max_clipping_ratio"])
                ):
                    candidates.append(
                        Candidate(
                            label=utterance.label,
                            utterance_index=utterance.index,
                            start=cursor,
                            end=window_end,
                            timestamp=format_timestamp(cursor),
                            text=utterance.text,
                            duration=window_end - cursor,
                            rms_dbfs=rms_dbfs,
                            voiced_fraction=voiced_fraction,
                            clipping_ratio=clipping_ratio,
                            quality=quality,
                        )
                    )
                cursor = window_end
    return candidates


def select_temporally_diverse(candidates: list[Candidate], limit: int) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: (item.start, item.end))
    if len(ordered) <= limit:
        return ordered
    selected: list[Candidate] = []
    for bucket in np.array_split(np.array(ordered, dtype=object), limit):
        choices = list(bucket)
        if choices:
            selected.append(max(choices, key=lambda item: item.quality))
    return sorted(selected, key=lambda item: item.start)


def transcript_index(utterances: list[Utterance]) -> dict[str, Any]:
    labels: dict[str, list[dict[str, Any]]] = {}
    for row in utterances:
        labels.setdefault(row.label, []).append(asdict(row))
    return {"utterances": [asdict(row) for row in utterances], "labels": labels}
