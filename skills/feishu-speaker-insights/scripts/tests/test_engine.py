from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from speaker_engine.matching import calibrate_profiles
from speaker_engine.resolution import (
    deterministic_named_label_context,
    ensure_viewpoint_coverage,
    resolve_results,
    validate_context,
    validate_viewpoints,
)
from speaker_engine.storage import DataStore
from speaker_engine.transcript import (
    Candidate,
    build_candidates,
    format_timestamp,
    parse_timestamp,
    parse_transcript,
)
from speaker_engine.constants import PIPELINE_CONFIG
from speaker_engine.util import atomic_save_npz, atomic_write_json
from speaker_engine.workflow import (
    _group_enrollment_candidates,
    enrollment_prepare,
    promote_candidate,
)


def unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


def profile_arrays(seed: int, center_axis: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    center = np.zeros(192, dtype=np.float32)
    center[center_axis] = 1.0
    references = np.stack([unit(center + rng.normal(0, 0.02, 192)) for _ in range(8)])
    heldouts = np.stack([unit(center + rng.normal(0, 0.02, 192)) for _ in range(3)])
    return {
        "references": references,
        "heldouts": heldouts,
        "center": unit(np.mean(references, axis=0)),
        "quality_weights": np.ones(8, dtype=np.float32),
    }


def profile_manifest_with_windows() -> dict:
    windows = []
    for index in range(11):
        start = float(index * 2)
        windows.append(
            {
                "label": "说话人 1",
                "utterance_index": index,
                "start": start,
                "end": start + 2.0,
                "timestamp": f"00:{index * 2:02d}",
                "text": f"测试发言 {index}",
                "duration": 2.0,
                "rms_dbfs": -20.0,
                "voiced_fraction": 0.9,
                "clipping_ratio": 0.0,
                "quality": 0.9,
                "source_id": "source-1",
                "meeting_title": "测试会议",
            }
        )
    return {
        "model": {"id": "test"},
        "creation_mode": "enrollment",
        "sources": [{"source_id": "source-1", "meeting_id": "m1", "title": "测试会议"}],
        "registration": {"source_recordings": [{"source_id": "source-1", "meeting_id": "m1", "title": "测试会议"}], "source_windows": windows},
        "statistics": {
            "reference_count": 8,
            "holdout_count": 3,
            "reference_seconds": 16.0,
            "holdout_seconds": 6.0,
            "reference_windows": windows[:8],
            "holdout_windows": windows[8:],
        },
    }


def manifest(customer_id: str, customer_name: str, audio: str = "/tmp/a.wav", transcript: str = "/tmp/a.txt") -> dict:
    return {
        "schema_version": 1,
        "customer": {"id": customer_id, "name": customer_name},
        "meeting": {
            "id": "m1",
            "title": "测试会议",
            "audio": audio,
            "transcript": transcript,
        },
        "attendees": [
            {"name": "客户甲", "role": "老板", "organization": "customer"},
            {"name": "内部CSM", "role": "CSM", "organization": "yingdao"},
        ],
    }


class TranscriptTests(unittest.TestCase):
    def test_timestamp_and_generic_named_label(self) -> None:
        self.assertEqual(parse_timestamp("01:01:19"), 3679)
        self.assertEqual(format_timestamp(3679), "01:01:19")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "中文 转写.txt"
            path.write_text(
                "客户负责人 00:01\n第一句\n\n说话人 1 00:04\n第二句\n",
                encoding="utf-8-sig",
            )
            rows = parse_transcript(path, 8)
        self.assertEqual([row.label for row in rows], ["客户负责人", "说话人 1"])
        self.assertLess(rows[0].end, 4)
        self.assertEqual(rows[0].end_source, "estimated_text_duration")

    def test_start_only_rows_do_not_fill_long_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sparse.txt"
            path.write_text(
                "说话人 1 00:00\n简短答复\n\n说话人 2 00:40\n下一句\n",
                encoding="utf-8",
            )
            rows = parse_transcript(path, 60)
        self.assertLessEqual(rows[0].end, 5)
        self.assertEqual(rows[0].end_source, "estimated_text_duration")

    def test_explicit_range_is_supported_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ranged.txt"
            path.write_text(
                "[00:01 - 00:04] 客户负责人\n完整句子\n",
                encoding="utf-8",
            )
            rows = parse_transcript(path, 10)
        self.assertEqual((rows[0].start, rows[0].end), (1, 4))
        self.assertEqual(rows[0].end_source, "explicit_stop")

    def test_adaptive_vad_keeps_speech_and_rejects_long_silence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio_path = root / "speech.wav"
            transcript_path = root / "speech.txt"
            sample_rate = 16000
            wave = np.zeros(sample_rate * 20, dtype=np.float32)
            time = np.arange(int(sample_rate * 2.4)) / sample_rate
            wave[int(sample_rate * 0.3) : int(sample_rate * 2.7)] = (
                0.08 * np.sin(2 * math.pi * 220 * time)
            )
            sf.write(audio_path, wave, sample_rate)
            transcript_path.write_text(
                "说话人 1 00:00\n这是一个简短答复\n\n说话人 2 00:18\n嗯\n",
                encoding="utf-8",
            )
            rows = parse_transcript(transcript_path, 20)
            candidates = build_candidates(audio_path, rows, PIPELINE_CONFIG)
        first = [item for item in candidates if item.label == "说话人 1"]
        second = [item for item in candidates if item.label == "说话人 2"]
        self.assertTrue(first)
        self.assertLess(max(item.end for item in first), 6)
        self.assertFalse(second)


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = DataStore(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_staff_is_global_and_customers_are_isolated(self) -> None:
        people_a = self.store.upsert_manifest(manifest("a", "客户A"))
        people_b = self.store.upsert_manifest(manifest("b", "客户B"))
        self.assertEqual(people_a["内部CSM"]["person_id"], people_b["内部CSM"]["person_id"])
        self.assertNotEqual(people_a["客户甲"]["person_id"], people_b["客户甲"]["person_id"])
        self.store.save_profile(people_a["客户甲"], profile_arrays(1, 0), {"model": {}})
        self.store.save_profile(people_b["客户甲"], profile_arrays(2, 1), {"model": {}})
        self.store.save_profile(people_a["内部CSM"], profile_arrays(3, 2), {"model": {}})
        selected = self.store.analysis_profiles(
            "a", manifest("a", "客户A")["attendees"], ["说话人 1"]
        )
        names = {item["person"]["name"] for item in selected.values()}
        self.assertEqual(names, {"客户甲", "内部CSM"})

    def test_profile_versions_and_rollback(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        first = self.store.save_profile(person, profile_arrays(1, 0), {"model": {}})
        person = self.store.get_person(person["person_id"])
        second = self.store.save_profile(person, profile_arrays(2, 0), {"model": {}})
        self.assertEqual((first["version"], second["version"]), (1, 2))
        result = self.store.rollback_profile(person["person_id"])
        self.assertEqual(result["to_version"], 1)
        self.assertEqual(self.store.get_person(person["person_id"])["current_version"], 1)

    def test_profile_allocation_skips_orphaned_immutable_files(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        self.store.save_profile(person, profile_arrays(1, 0), {"model": {}})
        profile_dir = self.store.profile_dir(person)
        (profile_dir / "v0002.npz").write_bytes(b"failed-commit-evidence")
        (profile_dir / "v0002.json").write_text("{}", encoding="utf-8")
        created = self.store.save_profile(
            self.store.get_person(person["person_id"]),
            profile_arrays(2, 0),
            {"model": {}},
        )
        self.assertEqual(created["version"], 3)

    def test_disable_preserves_current_version_and_matching_excludes_profile(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        self.store.save_profile(person, profile_arrays(1, 0), profile_manifest_with_windows())
        result = self.store.set_profile_enabled(person["person_id"], False)
        self.assertEqual(result["status"], "disabled")
        disabled = self.store.get_person(person["person_id"])
        self.assertEqual(disabled["current_version"], 1)
        self.assertEqual(disabled["voiceprint_enabled"], 0)
        selected = self.store.analysis_profiles("a", manifest("a", "客户A")["attendees"], [])
        self.assertNotIn(person["person_id"], selected)
        self.store.set_profile_enabled(person["person_id"], True)
        selected = self.store.analysis_profiles("a", manifest("a", "客户A")["attendees"], [])
        self.assertIn(person["person_id"], selected)

    def test_switch_then_fork_allocates_after_highest_immutable_version(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        base_manifest = profile_manifest_with_windows()
        self.store.save_profile(person, profile_arrays(1, 0), base_manifest)
        self.store.save_profile(self.store.get_person(person["person_id"]), profile_arrays(2, 0), {**base_manifest, "parent_version": 1})
        self.store.save_profile(self.store.get_person(person["person_id"]), profile_arrays(3, 0), {**base_manifest, "parent_version": 2})
        switched = self.store.set_current_profile_version(person["person_id"], 1)
        self.assertEqual(switched["to_version"], 1)
        detail = self.store.profile_version_detail(person["person_id"], 1)
        forked = self.store.fork_profile_version(
            person["person_id"],
            1,
            [item["window_id"] for item in detail["windows"]],
            make_current=True,
        )
        self.assertEqual(forked["new_version"], 4)
        self.assertEqual(self.store.get_person(person["person_id"])["current_version"], 4)
        versions = self.store.list_profile_versions(person["person_id"])
        self.assertEqual([item["version"] for item in versions], [4, 3, 2, 1])
        self.assertEqual(versions[0]["parent_version"], 1)
        self.assertTrue(self.store.load_profile(person["person_id"], 2)["npz_path"].is_file())
        self.assertTrue(self.store.load_profile(person["person_id"], 3)["npz_path"].is_file())

    def test_profile_catalogue_is_paginated_and_filters_scope(self) -> None:
        people_a = self.store.upsert_manifest(manifest("a", "客户A"))
        people_b = self.store.upsert_manifest(manifest("b", "客户B"))
        self.store.save_profile(people_a["客户甲"], profile_arrays(1, 0), profile_manifest_with_windows())
        self.store.save_profile(people_b["客户甲"], profile_arrays(2, 1), profile_manifest_with_windows())
        self.store.save_profile(people_a["内部CSM"], profile_arrays(3, 2), profile_manifest_with_windows())
        first_page = self.store.list_profiles(page=1, page_size=2)
        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["items"]), 2)
        self.assertEqual(first_page["pages"], 2)
        staff = self.store.list_profiles(scope="staff")
        self.assertEqual(staff["total"], 1)
        self.assertEqual(staff["items"][0]["name"], "内部CSM")
        customer = self.store.list_profiles(customer_id="a")
        self.assertEqual(customer["total"], 1)
        self.assertEqual(customer["items"][0]["customer_name"], "客户A")

    def test_candidate_requires_explicit_promotion(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        arrays = profile_arrays(1, 0)
        self.store.save_profile(person, arrays, {"model": {}, "sources": []})
        rng = np.random.default_rng(10)
        vectors = np.stack(
            [unit(arrays["center"] + rng.normal(0, 0.02, 192)) for _ in range(8)]
        )
        candidate = self.store.save_candidate(
            "a",
            person["person_id"],
            "run-1",
            "candidate-1",
            vectors,
            {
                "predicted_identity": "客户甲",
                "usable_seconds": 20,
                "voiceprint": {"accept_threshold": 0.58},
                "source": {},
            },
        )
        self.assertEqual(self.store.get_person(person["person_id"])["current_version"], 1)
        result = promote_candidate(
            Path(self.root / "customers/a/candidates/candidate-1.json"),
            person["person_id"],
            "测试确认人",
            self.store,
        )
        self.assertEqual(result["profile"]["version"], 2)
        listed = self.store.list_candidates("a")
        self.assertEqual(listed[0]["status"], "promoted")

    def test_large_legacy_profile_without_provenance_can_be_promoted(self) -> None:
        person = self.store.upsert_manifest(manifest("a", "客户A"))["客户甲"]
        rng = np.random.default_rng(19)
        center = np.zeros(192, dtype=np.float32)
        center[0] = 1.0
        references = np.stack(
            [unit(center + rng.normal(0, 0.01, 192)) for _ in range(49)]
        )
        heldouts = np.stack(
            [unit(center + rng.normal(0, 0.01, 192)) for _ in range(16)]
        )
        self.store.save_profile(
            person,
            {
                "references": references,
                "heldouts": heldouts,
                "center": unit(references.mean(axis=0)),
                "quality_weights": np.ones(len(references), dtype=np.float32),
            },
            {"model": {"id": "legacy"}, "sources": []},
        )
        current = self.store.load_profile(person["person_id"])
        provenance = self.store._profile_provenance(current)
        self.assertEqual(len(provenance["references"]), 49)
        self.assertEqual(len(provenance["heldouts"]), 16)
        self.assertTrue(
            all(
                item["provenance_status"] == "legacy_source_unavailable"
                for item in provenance["references"] + provenance["heldouts"]
            )
        )

        vectors = np.stack(
            [unit(current["arrays"]["center"] + rng.normal(0, 0.01, 192)) for _ in range(24)]
        )
        windows = [
            {
                "source_id": "source-new",
                "label": "说话人 1",
                "utterance_index": index,
                "start": float(index * 2),
                "end": float(index * 2 + 2),
                "timestamp": f"00:{index * 2:02d}",
                "text": f"新候选发言 {index}",
                "duration": 2.0,
                "quality": 0.9,
            }
            for index in range(24)
        ]
        self.store.save_candidate(
            "a",
            person["person_id"],
            "run-legacy",
            "candidate-legacy",
            vectors,
            {
                "predicted_identity": "客户甲",
                "usable_seconds": 48.0,
                "voiceprint": {"accept_threshold": 0.58},
                "windows": windows,
                "source": {},
            },
        )
        result = promote_candidate(
            self.root / "customers" / "a" / "candidates" / "candidate-legacy.json",
            person["person_id"],
            "测试确认人",
            self.store,
        )
        self.assertEqual(result["profile"]["version"], 2)
        promoted = self.store.load_profile(person["person_id"])
        promoted_provenance = promoted["manifest"]["vector_provenance"]
        self.assertEqual(
            len(promoted_provenance["references"]),
            len(promoted["arrays"]["references"]),
        )
        self.assertEqual(
            len(promoted_provenance["heldouts"]),
            len(promoted["arrays"]["heldouts"]),
        )
        compatibility = promoted["manifest"]["compatibility"]["legacy_source_provenance"]
        self.assertEqual(compatibility["base_version"], 1)
        self.assertEqual(compatibility["reference_placeholders"], 49)
        self.assertEqual(compatibility["holdout_placeholders"], 16)


class CalibrationAndResolutionTests(unittest.TestCase):
    def test_dynamic_calibration(self) -> None:
        profiles = {
            "p1": {"arrays": profile_arrays(1, 0)},
            "p2": {"arrays": profile_arrays(2, 1)},
        }
        calibration = calibrate_profiles(profiles)
        self.assertEqual(calibration["source"], "dynamic_candidate_cohort")
        self.assertEqual(calibration["holdout_top1_accuracy"], 1.0)
        self.assertGreater(calibration["accept_threshold"], 0)

    def test_context_is_grounded_and_voiceprint_wins_conflict(self) -> None:
        index = {
            "utterances": [
                {
                    "index": 0,
                    "label": "内部CSM",
                    "timestamp": "00:01",
                    "text": "负责人，您怎么看？",
                },
                {
                    "index": 1,
                    "label": "说话人 1",
                    "timestamp": "00:03",
                    "text": "我认为要先试点。",
                },
            ],
            "labels": {"内部CSM": [], "说话人 1": []},
        }
        people = [
            {"person_id": "p1", "name": "客户开发者", "role": "开发者"},
            {"person_id": "p2", "name": "客户负责人", "role": "负责人"},
        ]
        context, rejected = validate_context(
            {
                "items": [
                    {
                        "target_label": "说话人 1",
                        "supported_person": "客户负责人",
                        "strength": "strong",
                        "type": "direct_address_response",
                        "source_label": "内部CSM",
                        "timestamp": "00:01",
                        "excerpt": "负责人，您怎么看",
                    }
                ]
            },
            index,
            people,
        )
        self.assertFalse(rejected)
        acoustic = [
            {
                "transcript_label": "说话人 1",
                "acoustic_status": "matched",
                "acoustic_confidence": "高",
                "matched_person_id": "p1",
                "top1_person_id": "p1",
                "top1_score": 0.8,
                "top2_person_id": "p2",
                "top2_score": 0.5,
                "score_margin": 0.3,
                "usable_windows": 5,
                "usable_seconds": 20,
                "notes": [],
            }
        ]
        resolved = resolve_results(acoustic, context, people)[0]
        self.assertEqual(resolved["final_identity"], "客户开发者")
        self.assertEqual(resolved["final_status"], "声纹已匹配，需复核")
        self.assertTrue(resolved["voice_context_conflict"])

    def test_role_semantics_cannot_be_strong(self) -> None:
        index = {
            "utterances": [
                {"index": 0, "label": "说话人 1", "timestamp": "00:01", "text": "我负责开发"}
            ],
            "labels": {"说话人 1": []},
        }
        evidence, _ = validate_context(
            {
                "items": [
                    {
                        "target_label": "说话人 1",
                        "supported_person": "客户开发者",
                        "strength": "strong",
                        "type": "role_semantics",
                        "source_label": "说话人 1",
                        "timestamp": "00:01",
                        "excerpt": "负责开发",
                    }
                ]
            },
            index,
            [{"person_id": "p1", "name": "客户开发者", "role": "开发者"}],
        )
        self.assertEqual(evidence[0]["strength"], "weak")

    def test_exact_named_label_generates_strong_context(self) -> None:
        index = {
            "utterances": [
                {"index": 0, "label": "图南", "timestamp": "00:00", "text": "我们开始吧"}
            ],
            "labels": {
                "图南": [
                    {"index": 0, "label": "图南", "timestamp": "00:00", "text": "我们开始吧"}
                ]
            },
        }
        evidence = deterministic_named_label_context(
            index, [{"person_id": "p1", "name": "图南", "role": "CSM"}]
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["strength"], "strong")
        self.assertEqual(evidence[0]["supported_person_id"], "p1")

    def test_explicit_outside_cohort_identity_can_resolve(self) -> None:
        index = {
            "utterances": [
                {
                    "index": 0,
                    "label": "说话人 1",
                    "timestamp": "00:18",
                    "text": "我姓吴，叫我吴老师就可以。",
                }
            ],
            "labels": {"说话人 1": []},
        }
        evidence, rejected = validate_context(
            {
                "items": [
                    {
                        "target_label": "说话人 1",
                        "supported_person": "吴老师",
                        "strength": "strong",
                        "type": "self_identification",
                        "source_label": "说话人 1",
                        "timestamp": "00:18",
                        "excerpt": "我姓吴",
                    }
                ]
            },
            index,
            [{"person_id": "p1", "name": "已知客户", "role": "老板"}],
        )
        self.assertFalse(rejected)
        acoustic = [
            {
                "transcript_label": "说话人 1",
                "acoustic_status": "unknown",
                "acoustic_confidence": "低",
                "matched_person_id": None,
                "top1_person_id": "p1",
                "top1_score": 0.41,
                "top2_person_id": None,
                "top2_score": None,
                "score_margin": None,
                "usable_windows": 3,
                "usable_seconds": 9,
                "notes": [],
            }
        ]
        resolved = resolve_results(
            acoustic,
            evidence,
            [{"person_id": "p1", "name": "已知客户", "role": "老板"}],
        )[0]
        self.assertEqual(resolved["final_identity"], "吴老师")
        self.assertEqual(resolved["final_status"], "上下文识别（声纹库外）")
        self.assertEqual(resolved["top1_person_id"], "p1")

    def test_viewpoint_must_match_label_timestamp_and_excerpt(self) -> None:
        index = {
            "utterances": [
                {"index": 0, "label": "说话人 1", "timestamp": "00:01", "text": "先做小范围试点"}
            ],
            "labels": {"说话人 1": []},
        }
        valid, non_substantive, rejected = validate_viewpoints(
            {
                "items": [
                    {
                        "transcript_label": "说话人 1",
                        "timestamp": "00:01",
                        "category": "主张",
                        "point": "建议先做小范围试点。",
                        "source_excerpt": "小范围试点",
                    },
                    {
                        "transcript_label": "说话人 1",
                        "timestamp": "00:02",
                        "category": "主张",
                        "point": "不存在的观点。",
                        "source_excerpt": "不存在",
                    },
                ]
            },
            index,
        )
        self.assertEqual(len(valid), 1)
        self.assertFalse(non_substantive)
        self.assertEqual(len(rejected), 1)
        ensure_viewpoint_coverage(index, valid, non_substantive)

    def test_empty_viewpoints_fail_and_grounded_background_is_allowed(self) -> None:
        index = {
            "utterances": [
                {"index": 0, "label": "说话人 4", "timestamp": "00:02", "text": "喂喂"}
            ],
            "labels": {"说话人 4": []},
        }
        with self.assertRaises(ValueError):
            ensure_viewpoint_coverage(index, [], [])
        valid, background, rejected = validate_viewpoints(
            {
                "items": [],
                "non_substantive_labels": [
                    {
                        "transcript_label": "说话人 4",
                        "classification": "background_or_incidental",
                        "reason": "只有设备试音，没有会议观点。",
                        "timestamp": "00:02",
                        "source_excerpt": "喂喂",
                    }
                ],
            },
            index,
        )
        self.assertFalse(valid)
        self.assertFalse(rejected)
        ensure_viewpoint_coverage(index, valid, background)


class EnrollmentGroupingTests(unittest.TestCase):
    def test_multiple_labels_for_one_person_are_built_together(self) -> None:
        person = {"person_id": "p1", "name": "姚总"}
        candidates = [
            Candidate(
                label=label,
                utterance_index=index,
                start=float(index * 3),
                end=float(index * 3 + 2),
                timestamp=f"00:0{index}",
                text="测试",
                duration=2,
                rms_dbfs=-20,
                voiced_fraction=0.9,
                clipping_ratio=0,
                quality=0.9,
            )
            for index, label in enumerate(["说话人 1", "说话人 2"])
        ]
        grouped = _group_enrollment_candidates(
            {"说话人 1": person, "说话人 2": person}, candidates
        )
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["labels"], ["说话人 1", "说话人 2"])
        self.assertEqual(len(grouped[0]["candidates"]), 2)


class EnrollmentGuardTests(unittest.TestCase):
    def test_prepare_creates_no_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "测试 录音.wav"
            transcript = root / "测试 录音.txt"
            sample_rate = 16000
            seconds = 7
            time = np.arange(sample_rate * seconds) / sample_rate
            wave = (0.1 * np.sin(2 * math.pi * 220 * time)).astype(np.float32)
            sf.write(audio, wave, sample_rate)
            transcript.write_text("说话人 1 00:00\n测试语音\n", encoding="utf-8")
            meeting = manifest("a", "客户A", str(audio), str(transcript))
            manifest_path = root / "manifest.yaml"
            import yaml

            manifest_path.write_text(yaml.safe_dump(meeting, allow_unicode=True), encoding="utf-8")
            store = DataStore(root / "data")
            result = enrollment_prepare(manifest_path, store)
            self.assertEqual(result["status"], "awaiting_confirmation")
            for person in result["labels"]:
                self.assertIn("candidate_windows", person)
            people = store.upsert_manifest(meeting)
            self.assertIsNone(store.get_person(people["客户甲"]["person_id"])["current_version"])
            self.assertFalse(list((root / "data").rglob("v0001.npz")))


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_json_and_npz(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            atomic_write_json(root / "含 空格.json", {"中文": "值"})
            atomic_save_npz(root / "voice.npz", vector=np.ones(192, dtype=np.float32))
            self.assertEqual(json.loads((root / "含 空格.json").read_text())["中文"], "值")
            with np.load(root / "voice.npz", allow_pickle=False) as arrays:
                self.assertEqual(arrays["vector"].shape, (192,))


if __name__ == "__main__":
    unittest.main()
