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
    resolve_results,
    validate_context,
    validate_viewpoints,
)
from speaker_engine.storage import DataStore
from speaker_engine.transcript import format_timestamp, parse_timestamp, parse_transcript
from speaker_engine.util import atomic_save_npz, atomic_write_json
from speaker_engine.workflow import enrollment_prepare, promote_candidate


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
        self.assertEqual(rows[0].end, 4)


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

    def test_viewpoint_must_match_label_timestamp_and_excerpt(self) -> None:
        index = {
            "utterances": [
                {"index": 0, "label": "说话人 1", "timestamp": "00:01", "text": "先做小范围试点"}
            ],
            "labels": {"说话人 1": []},
        }
        valid, rejected = validate_viewpoints(
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
        self.assertEqual(len(rejected), 1)


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
