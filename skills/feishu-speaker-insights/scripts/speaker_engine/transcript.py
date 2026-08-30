from __future__ import annotations

import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf

from .constants import PIPELINE_CONFIG

TIMESTAMP_PATTERN = r"(?:\d{1,2}:)?\d{2}:\d{2}(?:\.\d{1,3})?"
HEADER_RE = re.compile(
    rf"^(?P<label>[^\r\n]{{1,80}}?)\s+(?P<timestamp>{TIMESTAMP_PATTERN})\s*$"
)
RANGED_HEADER_RE = re.compile(
    rf"^(?:\*\*)?\[(?P<start>{TIMESTAMP_PATTERN})\s*[–—-]\s*"
    rf"(?P<end>{TIMESTAMP_PATTERN})\]\s*(?P<label>[^\r\n*]{{1,80}}?)(?:\*\*)?\s*$"
)


@dataclass
class Utterance:
    index: int
    label: str
    start: float
    end: float
    timestamp: str
    text: str
    end_source: str


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
    parts = value.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return float(int(minutes) * 60 + float(seconds))
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    raise ValueError(f"Unsupported timestamp: {value}")


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def estimate_utterance_duration(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    chinese_units = len(re.findall(r"[\u3400-\u9fff]", compact))
    ascii_units = sum(
        max(1.0, len(token) / 4.0)
        for token in re.findall(r"[A-Za-z0-9]+", compact)
    )
    punctuation = len(re.findall(r"[，。！？；：,.!?;:]", compact))
    spoken_units = chinese_units + ascii_units
    estimated = (
        spoken_units / float(PIPELINE_CONFIG["estimated_chars_per_second"])
        + punctuation * 0.08
        + float(PIPELINE_CONFIG["estimated_utterance_padding_seconds"])
    )
    return float(
        np.clip(
            estimated,
            float(PIPELINE_CONFIG["min_window_seconds"]) + 0.4,
            float(PIPELINE_CONFIG["max_start_only_span_seconds"]),
        )
    )


def parse_transcript(path: Path, audio_duration: float | None = None) -> list[Utterance]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            ranged_match = RANGED_HEADER_RE.match(line.strip())
            match = HEADER_RE.match(line.strip()) if ranged_match is None else None
            if ranged_match:
                if current is not None:
                    rows.append(current)
                start = parse_timestamp(ranged_match.group("start"))
                current = {
                    "label": re.sub(r"\s+", " ", ranged_match.group("label")).strip(),
                    "timestamp": format_timestamp(start),
                    "start": start,
                    "explicit_end": parse_timestamp(ranged_match.group("end")),
                    "text_lines": [],
                }
            if match:
                if current is not None:
                    rows.append(current)
                current = {
                    "label": re.sub(r"\s+", " ", match.group("label")).strip(),
                    "timestamp": match.group("timestamp"),
                    "start": parse_timestamp(match.group("timestamp")),
                    "explicit_end": None,
                    "text_lines": [],
                }
            elif ranged_match is None and current is not None and line.strip():
                current["text_lines"].append(line.strip())
    if current is not None:
        rows.append(current)
    if not rows:
        raise ValueError(f"No timestamped speaker rows found in {path}")

    utterances: list[Utterance] = []
    for index, row in enumerate(rows):
        next_start = rows[index + 1]["start"] if index + 1 < len(rows) else audio_duration
        start = float(row["start"])
        explicit_end = row.get("explicit_end")
        if explicit_end is not None:
            end = float(explicit_end)
            if next_start is not None:
                end = min(end, float(next_start))
            end_source = "explicit_stop"
        else:
            estimated_end = start + estimate_utterance_duration(
                " ".join(row["text_lines"]).strip()
            )
            if next_start is None:
                end = estimated_end
                end_source = "estimated_text_duration"
            else:
                end = min(float(next_start), estimated_end)
                end_source = (
                    "next_label_start"
                    if float(next_start) <= estimated_end
                    else "estimated_text_duration"
                )
        if audio_duration is not None:
            end = min(end, float(audio_duration))
        end = max(start, end)
        utterances.append(
            Utterance(
                index=index,
                label=row["label"],
                start=start,
                end=end,
                timestamp=format_timestamp(start),
                text=" ".join(row["text_lines"]).strip(),
                end_source=end_source,
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


def _activity_levels(
    wave: np.ndarray, sample_rate: int
) -> tuple[np.ndarray, np.ndarray, int, int]:
    frame_size = max(1, int(round(float(PIPELINE_CONFIG["vad_frame_seconds"]) * sample_rate)))
    hop_size = max(1, int(round(float(PIPELINE_CONFIG["vad_hop_seconds"]) * sample_rate)))
    levels = frame_rms(wave, frame_size, hop_size)
    levels_db = 20.0 * np.log10(np.maximum(levels, 1e-8))
    reference_db = float(
        np.quantile(levels_db, float(PIPELINE_CONFIG["vad_reference_quantile"]))
    )
    if reference_db < float(PIPELINE_CONFIG["vad_absolute_floor_dbfs"]):
        reference_db = float(np.quantile(levels_db, 0.95))
    if reference_db < float(PIPELINE_CONFIG["vad_absolute_floor_dbfs"]):
        return levels_db, np.zeros(levels_db.shape, dtype=bool), frame_size, hop_size
    noise_db = float(
        np.quantile(levels_db, float(PIPELINE_CONFIG["vad_noise_quantile"]))
    )
    threshold_db = max(
        float(PIPELINE_CONFIG["vad_absolute_floor_dbfs"]),
        noise_db + float(PIPELINE_CONFIG["vad_min_snr_db"]),
    )
    threshold_db = min(
        threshold_db,
        reference_db - float(PIPELINE_CONFIG["vad_reference_margin_db"]),
    )
    return levels_db, levels_db >= threshold_db, frame_size, hop_size


def speech_regions(wave: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
    if wave.size == 0:
        return []
    _, active, frame_size, hop_size = _activity_levels(wave, sample_rate)
    active_indices = np.flatnonzero(active)
    if active_indices.size == 0:
        return []
    maximum_gap_frames = max(
        0,
        int(round(float(PIPELINE_CONFIG["vad_merge_gap_seconds"]) * sample_rate / hop_size)),
    )
    groups: list[tuple[int, int]] = []
    first = previous = int(active_indices[0])
    for value in active_indices[1:]:
        current = int(value)
        if current - previous - 1 > maximum_gap_frames:
            groups.append((first, previous))
            first = current
        previous = current
    groups.append((first, previous))

    minimum = float(PIPELINE_CONFIG["vad_min_region_seconds"])
    padding = float(PIPELINE_CONFIG["vad_padding_seconds"])
    wave_duration = wave.size / sample_rate
    regions: list[tuple[float, float]] = []
    for first_frame, last_frame in groups:
        start = first_frame * hop_size / sample_rate
        end = (last_frame * hop_size + frame_size) / sample_rate
        if end - start < minimum:
            continue
        regions.append((max(0.0, start - padding), min(wave_duration, end + padding)))
    return regions


def quality_metrics(
    wave: np.ndarray, sample_rate: int = 16000
) -> tuple[float, float, float, float]:
    if wave.size == 0:
        return -120.0, 0.0, 0.0, 0.0
    rms = float(np.sqrt(np.mean(np.square(wave)) + 1e-12))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-8))
    _, active, _, _ = _activity_levels(wave, sample_rate)
    voiced_fraction = float(np.mean(active)) if active.size else 0.0
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
            if end - start < minimum:
                continue
            utterance_wave = read_window(audio, start, end, sample_rate)
            regions = speech_regions(utterance_wave, sample_rate)
            expanded: list[tuple[float, float]] = []
            for relative_start, relative_end in regions:
                region_start = start + relative_start
                region_end = start + relative_end
                if region_end - region_start < minimum:
                    missing = minimum - (region_end - region_start)
                    region_start = max(start, region_start - missing / 2.0)
                    region_end = min(end, region_end + missing / 2.0)
                    if region_end - region_start < minimum:
                        if region_start <= start:
                            region_end = min(end, start + minimum)
                        else:
                            region_start = max(start, end - minimum)
                if region_end - region_start >= minimum:
                    expanded.append((region_start, region_end))

            merged: list[list[float]] = []
            for region_start, region_end in expanded:
                if merged and region_start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], region_end)
                else:
                    merged.append([region_start, region_end])

            windows: list[tuple[float, float]] = []
            for region_start, region_end in merged:
                region_duration = region_end - region_start
                count = max(1, int(math.ceil(region_duration / maximum)))
                window_duration = region_duration / count
                if window_duration < minimum and count > 1:
                    count -= 1
                    window_duration = region_duration / count
                for window_index in range(count):
                    window_start = region_start + window_index * window_duration
                    window_end = (
                        region_end
                        if window_index == count - 1
                        else region_start + (window_index + 1) * window_duration
                    )
                    if window_end - window_start >= minimum:
                        windows.append((window_start, window_end))

            for window_start, window_end in windows:
                wave = read_window(audio, window_start, window_end, sample_rate)
                rms_dbfs, voiced_fraction, clipping_ratio, quality = quality_metrics(
                    wave, sample_rate
                )
                if (
                    rms_dbfs >= float(settings["min_rms_dbfs"])
                    and voiced_fraction >= float(settings["min_voiced_fraction"])
                    and clipping_ratio <= float(settings["max_clipping_ratio"])
                ):
                    candidates.append(
                        Candidate(
                            label=utterance.label,
                            utterance_index=utterance.index,
                            start=window_start,
                            end=window_end,
                            timestamp=format_timestamp(window_start),
                            text=utterance.text,
                            duration=window_end - window_start,
                            rms_dbfs=rms_dbfs,
                            voiced_fraction=voiced_fraction,
                            clipping_ratio=clipping_ratio,
                            quality=quality,
                        )
                    )
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
    end_sources: dict[str, int] = {}
    for row in utterances:
        end_sources[row.end_source] = end_sources.get(row.end_source, 0) + 1
    return {
        "utterances": [asdict(row) for row in utterances],
        "labels": labels,
        "segmentation": {
            "strategy": "explicit stop when present; otherwise text-duration cap plus adaptive energy VAD",
            "end_sources": end_sources,
            "allocated_seconds": float(sum(row.end - row.start for row in utterances)),
        },
    }
