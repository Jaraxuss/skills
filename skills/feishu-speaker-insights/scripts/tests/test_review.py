from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_server import create_app
from speaker_engine.migration import apply_layout_migration, layout_migration_plan
from speaker_engine.review import (
    _review_initial_sample_count,
    _verify_source,
    create_enrollment_review,
    create_profile_revision_review,
    normalize_review_manifest,
    prepare_review_session,
    restart_cancelled_enrollment_review,
    retry_failed_review_session,
    save_review_decision,
    commit_review_session,
    validate_review_decision,
)
from speaker_engine.storage import DataStore
from speaker_engine.transcript import Candidate, Utterance
from speaker_engine.util import atomic_save_npz, atomic_write_json, sha256_file


def unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


def arrays(seed: int = 0) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    center = np.zeros(192, dtype=np.float32)
    center[0] = 1
    references = np.stack([unit(center + rng.normal(0, 0.01, 192)) for _ in range(8)])
    heldouts = np.stack([unit(center + rng.normal(0, 0.01, 192)) for _ in range(3)])
    return {"references": references, "heldouts": heldouts, "center": unit(references.mean(axis=0)), "quality_weights": np.ones(8, dtype=np.float32)}


def profile_manifest_with_windows(audio: Path, transcript: Path) -> dict:
    windows = []
    for index in range(11):
        start = float(index * 2)
        windows.append({
            "label": "说话人 1", "utterance_index": index, "start": start, "end": start + 2.0,
            "timestamp": f"00:{index * 2:02d}", "text": f"测试发言 {index}", "duration": 2.0,
            "rms_dbfs": -20.0, "voiced_fraction": 0.9, "clipping_ratio": 0.0, "quality": 0.9,
            "source_id": "source-1", "meeting_title": "测试会议",
        })
    source = {
        "source_id": "source-1", "customer_id": "customer-a", "meeting_id": "meeting-a",
        "title": "测试会议", "audio_path": str(audio), "transcript_path": str(transcript),
        "audio_sha256": sha256_file(audio), "transcript_sha256": sha256_file(transcript),
        "selected_window_count": len(windows),
    }
    return {
        "model": {"id": "test"}, "creation_mode": "enrollment",
        "registration": {"source_recordings": [source], "source_windows": windows},
        "statistics": {
            "reference_count": 8, "holdout_count": 3,
            "reference_seconds": 16.0, "holdout_seconds": 6.0,
            "reference_windows": windows[:8], "holdout_windows": windows[8:],
        },
    }


def manifest(audio: Path, transcript: Path, customer: str = "客户甲") -> dict:
    return {
        "schema_version": 1,
        "customer": {"id": "customer-a", "name": customer},
        "meeting": {"id": "meeting-a", "title": "测试会议", "audio": str(audio), "transcript": str(transcript)},
        "attendees": [{"name": "张总", "role": "老板", "organization": "customer"}],
        "known_label_map": {},
        "excluded_labels": [],
    }


class ReviewFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.customer_root = self.root / "客户"
        self.store = DataStore(customers_root_path=self.customer_root)
        self.audio = self.root / "source.wav"
        self.transcript = self.root / "source.txt"
        sf.write(self.audio, np.zeros(16000 * 30, dtype=np.float32), 16000)
        self.transcript.write_text("说话人 1 00:00\n测试发言\n", encoding="utf-8")
        self.raw_manifest = manifest(self.audio, self.transcript)
        self.people = self.store.upsert_manifest(self.raw_manifest)
        self.person = self.people["张总"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_review_session(self) -> str:
        session_id = "review-unit"
        session_dir = self.store.session_dir("customer-a", session_id)
        manifest_path = session_dir / "manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        self.store.create_review_session(
            "customer-a", session_id, "enrollment", manifest_path, sha256_file(self.audio), sha256_file(self.transcript)
        )
        rng = np.random.default_rng(10)
        base = np.zeros(192, dtype=np.float32)
        base[0] = 1
        vectors = np.stack([unit(base + rng.normal(0, 0.01, 192)) for _ in range(6)])
        segments = []
        for index in range(6):
            start = float(index * 2)
            segments.append({
                "segment_id": f"seg-{index}", "vector_index": index, "label": "说话人 1", "utterance_index": index,
                "timestamp": f"00:{index * 2:02d}", "start": start, "end": start + 2.0, "duration": 2.0,
                "quality": 0.9, "rms_dbfs": -20.0, "voiced_fraction": 0.9, "clipping_ratio": 0.0, "text": "这是有效测试发言",
            })
        pending = session_dir / "pending_vectors.npz"
        atomic_save_npz(pending, embeddings=vectors)
        package = {
            "schema_version": 1, "session_id": session_id, "kind": "enrollment", "manifest": self.raw_manifest,
            "source": {"audio_path": str(self.audio), "audio_sha256": sha256_file(self.audio), "transcript_path": str(self.transcript), "transcript_sha256": sha256_file(self.transcript)},
            "model": {"id": "test", "revision": "test"}, "people": [self.person], "segments": segments,
            "pending_vector_file": pending.name, "selection_requirements": {"minimum_windows": 6, "minimum_seconds": 12.0},
            "labels": [], "transcript_index": {}, "calibration": {"accept_threshold": 0.58},
        }
        package_path = session_dir / "review_package.json"
        atomic_write_json(package_path, package)
        self.store.set_review_session(session_id, status="review_required", package_path=package_path)
        return session_id

    def test_customer_root_layout_and_uri(self) -> None:
        directory = self.store.customer_dir("customer-a")
        self.assertEqual(directory, (self.customer_root / "客户甲" / "声纹数据").resolve())
        saved = self.store.save_profile(self.person, arrays(), {"model": {}})
        with self.store.connect() as db:
            row = db.execute("SELECT npz_path FROM profile_versions").fetchone()
        self.assertTrue(row["npz_path"].startswith("customer://customer-a/"))
        self.assertTrue(Path(saved["npz_path"]).is_file())

    def test_customer_directories_are_discovered_without_openclaw(self) -> None:
        (self.customer_root / "目录客户").mkdir(parents=True)
        (self.customer_root / "共享数据").mkdir(parents=True, exist_ok=True)
        customers = self.store.discover_customers()
        self.assertEqual({item["name"] for item in customers}, {"客户甲", "目录客户"})
        customer = next(item for item in customers if item["name"] == "目录客户")
        self.assertEqual(customer["directory_relpath"], "目录客户")
        self.assertFalse(customer["registered"])
        self.assertEqual(
            self.store.customer_source_dir(customer["customer_id"]),
            (self.customer_root / "目录客户").resolve(),
        )
        self.assertFalse((self.customer_root / "目录客户" / "声纹数据").exists())

    def test_batch_manifest_derives_recording_names_and_snapshots_each_source(self) -> None:
        second_audio = self.root / "第二场.wav"
        second_transcript = self.root / "第二场.txt"
        sf.write(second_audio, np.zeros(16000, dtype=np.float32), 16000)
        second_transcript.write_text("说话人 2 00:00\n第二场测试\n", encoding="utf-8")
        raw = {
            "schema_version": 1,
            "customer": {"id": "customer-a", "name": "客户甲"},
            "meetings": [
                {"audio": str(self.audio), "transcript": str(self.transcript)},
                {"audio": str(second_audio), "transcript": str(second_transcript)},
            ],
            "attendees": [{"name": "张总", "role": "老板", "organization": "customer"}],
        }
        normalized = normalize_review_manifest(raw)
        self.assertEqual([item["title"] for item in normalized["meetings"]], ["source", "第二场"])
        manifest_path = self.root / "batch.json"
        atomic_write_json(manifest_path, raw)
        created = create_enrollment_review(manifest_path, self.store)
        session = self.store.get_review_session(created["session_id"])
        saved_manifest = json.loads(Path(session["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(saved_manifest["meetings"]), 2)
        self.assertEqual(saved_manifest["meetings"][1]["audio_sha256"], sha256_file(second_audio))

    def test_batch_source_verification_checks_every_recording(self) -> None:
        second_audio = self.root / "second.wav"
        second_transcript = self.root / "second.txt"
        sf.write(second_audio, np.zeros(16000, dtype=np.float32), 16000)
        second_transcript.write_text("说话人 2 00:00\n测试\n", encoding="utf-8")
        package = {
            "sources": [
                {"title": "第一场", "audio_path": str(self.audio), "audio_sha256": sha256_file(self.audio), "transcript_path": str(self.transcript), "transcript_sha256": sha256_file(self.transcript)},
                {"title": "第二场", "audio_path": str(second_audio), "audio_sha256": sha256_file(second_audio), "transcript_path": str(second_transcript), "transcript_sha256": sha256_file(second_transcript)},
            ]
        }
        _verify_source({"source_audio_sha256": "unused", "source_transcript_sha256": "unused"}, package, self.store)
        second_transcript.write_text("内容已变化", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "第二场"):
            _verify_source({"source_audio_sha256": "unused", "source_transcript_sha256": "unused"}, package, self.store)

    def test_profile_revision_reuses_review_flow_and_preserves_version_history(self) -> None:
        base_manifest = profile_manifest_with_windows(self.audio, self.transcript)
        self.store.save_profile(self.person, arrays(1), base_manifest)
        self.store.save_profile(
            self.store.get_person(self.person["person_id"]),
            arrays(2),
            {**base_manifest, "parent_version": 1},
        )
        created = create_profile_revision_review(
            self.person["person_id"], 1, self.store, base_url="http://testserver"
        )
        session = self.store.get_review_session(created["session_id"])
        self.assertEqual(session["kind"], "profile_revision")
        self.assertEqual(session["status"], "review_required")
        self.assertEqual(session["job"]["status"], "completed")
        package = json.loads(Path(session["package_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(package["segments"]), 11)
        self.assertTrue(all(item["playable"] for item in package["segments"]))

        assignments = {
            item["segment_id"]: self.person["person_id"] if index < 6 else "skip"
            for index, item in enumerate(package["segments"])
        }
        saved = save_review_decision(
            created["session_id"],
            {"assignments": assignments, "new_people": [], "make_current": False},
            session["revision"],
            self.store,
        )
        result = commit_review_session(
            created["session_id"], saved["revision"], self.store
        )
        self.assertEqual(result["profile_revision"]["new_version"], 3)
        self.assertFalse(result["profile_revision"]["made_current"])
        self.assertEqual(self.store.get_person(self.person["person_id"])["current_version"], 2)
        versions = self.store.list_profile_versions(self.person["person_id"])
        self.assertEqual([item["version"] for item in versions], [3, 2, 1])
        self.assertEqual(versions[0]["parent_version"], 1)
        self.assertEqual(versions[0]["review_session_id"], created["session_id"])

    def test_legacy_profile_revision_reports_missing_auditable_sources(self) -> None:
        self.store.save_profile(self.person, arrays(1), {"model": {"id": "legacy"}})
        with self.assertRaisesRegex(ValueError, "缺少可回查的窗口来源"):
            create_profile_revision_review(self.person["person_id"], 1, self.store)

    def test_staff_profile_revision_uses_hidden_shared_review_owner(self) -> None:
        raw = manifest(self.audio, self.transcript)
        raw["attendees"].append({"name": "图南", "role": "CSM", "organization": "yingdao"})
        staff = self.store.upsert_manifest(raw)["图南"]
        self.store.save_profile(staff, arrays(4), profile_manifest_with_windows(self.audio, self.transcript))
        created = create_profile_revision_review(staff["person_id"], 1, self.store)
        session = self.store.get_review_session(created["session_id"])
        self.assertEqual(session["customer_id"], "__shared_staff__")
        self.assertEqual(self.store.get_customer("__shared_staff__")["name"], "我方共享")
        self.assertNotIn("我方共享", {item["name"] for item in self.store.discover_customers()})

    def test_batch_prepare_and_commit_aggregate_two_recordings(self) -> None:
        second_audio = self.root / "第二场.wav"
        second_transcript = self.root / "第二场.txt"
        sf.write(second_audio, np.zeros(16000, dtype=np.float32), 16000)
        second_transcript.write_text("说话人 1 00:00\n测试\n", encoding="utf-8")
        raw = {
            "schema_version": 1,
            "customer": {"id": "customer-a", "name": "客户甲"},
            "meetings": [
                {"audio": str(self.audio), "transcript": str(self.transcript)},
                {"audio": str(second_audio), "transcript": str(second_transcript)},
            ],
            "attendees": [{"name": "张总", "role": "老板", "organization": "customer"}],
        }
        manifest_path = self.root / "batch-prepare.json"
        atomic_write_json(manifest_path, raw)
        created = create_enrollment_review(manifest_path, self.store)

        class FakeEngine:
            checkpoint_sha256 = "test-checkpoint"

            def __init__(self, **_: object) -> None:
                pass

            def embed_candidates(self, _: Path, values: list[Candidate], **__: object) -> np.ndarray:
                base = np.zeros(192, dtype=np.float32)
                base[0] = 1.0
                return np.stack([unit(base + index * 0.0001) for index, _ in enumerate(values)])

        utterance = Utterance(
            index=0, label="说话人 1", start=0.0, end=18.0, timestamp="00:00", text="测试", end_source="test"
        )
        candidates = [
            Candidate(
                label="说话人 1", utterance_index=0, start=float(index * 2), end=float(index * 2 + 2),
                timestamp=f"00:{index * 2:02d}", text="测试", duration=2.0, rms_dbfs=-20.0,
                voiced_fraction=0.9, clipping_ratio=0.0, quality=0.9,
            )
            for index in range(6)
        ]
        with patch("speaker_engine.review.convert_to_wav"), patch(
            "speaker_engine.review.audio_duration", return_value=20.0
        ), patch("speaker_engine.review.parse_transcript", return_value=[utterance]), patch(
            "speaker_engine.review.build_candidates", return_value=candidates
        ), patch("speaker_engine.review.EmbeddingEngine", FakeEngine):
            prepared = prepare_review_session(created["session_id"], self.store)
        self.assertEqual(prepared["status"], "review_required")
        session = self.store.get_review_session(created["session_id"])
        package = json.loads(Path(session["package_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(package["sources"]), 2)
        self.assertEqual(len(package["segments"]), 12)
        decision = {"assignments": {item["segment_id"]: self.person["person_id"] for item in package["segments"]}, "new_people": []}
        saved = save_review_decision(created["session_id"], decision, 0, self.store, actor="审核人")
        result = commit_review_session(created["session_id"], saved["revision"], self.store, actor="审核人")
        self.assertEqual(result["status"], "committed")
        profile = self.store.load_profile(self.person["person_id"])
        self.assertEqual(len(profile["manifest"]["registration"]["source_recordings"]), 2)

    def test_review_sampling_count_uses_usable_speech_and_cap(self) -> None:
        def candidates(count: int, duration: float) -> list[Candidate]:
            return [
                Candidate(
                    label="说话人 1", utterance_index=index, start=float(index * 10), end=float(index * 10 + duration),
                    timestamp=f"00:{index:02d}", text="测试", duration=duration, rms_dbfs=-20.0,
                    voiced_fraction=0.9, clipping_ratio=0.0, quality=0.9,
                )
                for index in range(count)
            ]

        self.assertEqual(_review_initial_sample_count(candidates(4, 4.0)), 4)
        self.assertEqual(_review_initial_sample_count(candidates(50, 4.0)), 8)
        self.assertEqual(_review_initial_sample_count(candidates(50, 16.0)), 24)

    def test_running_job_progress_is_exposed_on_session(self) -> None:
        manifest_path = self.root / "progress-manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)
        job = self.store.claim_review_job()
        self.assertIsNotNone(job)
        self.store.update_review_job_progress(
            str(job["job_id"]),
            {"phase": "embedding", "message": "正在提取声纹：3 / 8 个窗口", "embedding_completed": 3, "embedding_total": 8},
        )
        session = self.store.get_review_session(created["session_id"])
        self.assertEqual(session["job"]["status"], "running")
        self.assertEqual(session["job"]["progress"]["embedding_completed"], 3)

    def test_cancelled_enrollment_can_restart_with_new_session(self) -> None:
        manifest_path = self.root / "restart-manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)
        self.store.cancel_review_session(created["session_id"], "审核人")
        restarted = restart_cancelled_enrollment_review(
            created["session_id"], self.store, base_url="http://testserver", actor="审核人"
        )
        self.assertEqual(restarted["status"], "queued")
        self.assertNotEqual(restarted["session_id"], created["session_id"])
        self.assertEqual(restarted["restarted_from"], created["session_id"])
        self.assertEqual(self.store.get_review_session(created["session_id"])["status"], "cancelled")
        self.assertEqual(self.store.get_review_session(restarted["session_id"])["status"], "queued")

    def test_failed_commit_can_resume_same_review_with_decision_intact(self) -> None:
        session_id = self.make_review_session()
        decision = {
            "assignments": {f"seg-{index}": self.person["person_id"] for index in range(6)},
            "new_people": [],
        }
        saved = save_review_decision(session_id, decision, 0, self.store)
        self.store.set_review_session(
            session_id,
            status="failed",
            error_message="IndexError: list index out of range",
            event_type="review_commit_failed",
        )
        recovered = retry_failed_review_session(
            session_id, saved["revision"], self.store, actor="测试用户"
        )
        self.assertEqual(recovered["session_id"], session_id)
        self.assertEqual(recovered["status"], "review_required")
        self.assertEqual(recovered["revision"], saved["revision"] + 1)
        self.assertEqual(recovered["decision"], decision)
        self.assertEqual(recovered["error_message"], "")
        # Repeated clicks are idempotent and do not advance the revision again.
        repeated = retry_failed_review_session(
            session_id, saved["revision"], self.store, actor="测试用户"
        )
        self.assertEqual(repeated["revision"], recovered["revision"])

    def test_failed_prepare_without_review_package_cannot_resume_editing(self) -> None:
        manifest_path = self.root / "failed-prepare-manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)
        self.store.set_review_session(
            created["session_id"], status="failed", error_message="准备失败"
        )
        with self.assertRaisesRegex(RuntimeError, "审核包生成前失败"):
            retry_failed_review_session(created["session_id"], 0, self.store)

    def test_prepare_embeds_bounded_sample_and_expands_mixed_label(self) -> None:
        manifest_path = self.root / "manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)

        class FakeEngine:
            checkpoint_sha256 = "test-checkpoint"

            def __init__(self, **_: object) -> None:
                self.calls: list[int] = []

            def embed_candidates(self, _: Path, values: list[Candidate], **__: object) -> np.ndarray:
                self.calls.append(len(values))
                first = np.zeros(192, dtype=np.float32)
                first[0] = 1.0
                second = np.zeros(192, dtype=np.float32)
                second[1] = 1.0
                return np.stack([first if item.utterance_index < 25 else second for item in values])

        utterance = Utterance(index=0, label="说话人 1", start=0.0, end=500.0, timestamp="00:00", text="测试", end_source="test")
        candidate_values = [
            Candidate(
                label="说话人 1", utterance_index=index, start=float(index * 4), end=float(index * 4 + 4),
                timestamp=f"00:{index:02d}", text="测试", duration=4.0, rms_dbfs=-20.0,
                voiced_fraction=0.9, clipping_ratio=0.0, quality=0.9,
            )
            for index in range(50)
        ]
        engine = FakeEngine()
        with patch("speaker_engine.review.convert_to_wav"), patch(
            "speaker_engine.review.audio_duration", return_value=210.0
        ), patch("speaker_engine.review.parse_transcript", return_value=[utterance]), patch(
            "speaker_engine.review.build_candidates", return_value=candidate_values
        ), patch("speaker_engine.review.EmbeddingEngine", return_value=engine):
            prepared = prepare_review_session(created["session_id"], self.store)
        self.assertEqual(prepared["status"], "review_required")
        self.assertEqual(engine.calls, [8, 8])
        package = json.loads(Path(self.store.get_review_session(created["session_id"])["package_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(package["segments"]), 16)
        quality = package["labels"][0]["quality"]
        self.assertEqual(quality["candidate_window_count"], 50)
        self.assertEqual(quality["embedded_window_count"], 16)
        self.assertTrue(quality["expanded_for_mixture"])

    def test_review_does_not_write_profile_until_commit(self) -> None:
        session_id = self.make_review_session()
        decision = {"assignments": {f"seg-{index}": self.person["person_id"] for index in range(6)}, "new_people": []}
        validated = validate_review_decision(session_id, decision, self.store)
        self.assertTrue(validated["valid"], validated)
        self.assertIsNone(self.store.get_person(self.person["person_id"])["current_version"])
        saved = save_review_decision(session_id, decision, 0, self.store, actor="审核人")
        result = commit_review_session(session_id, saved["revision"], self.store, actor="审核人")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.store.get_person(self.person["person_id"])["current_version"], 1)
        self.assertFalse((self.store.session_dir("customer-a", session_id) / "pending_vectors.npz").exists())

    def test_web_commit_without_reviewer_creates_global_our_side_profile(self) -> None:
        session_id = self.make_review_session()
        draft_id = "draft-our-side"
        decision = {
            "assignments": {f"seg-{index}": draft_id for index in range(6)},
            "new_people": [{
                "draft_id": draft_id,
                "name": "图南",
                "role": "CSM",
                "organization": "yingdao",
            }],
        }
        validated = validate_review_decision(session_id, decision, self.store)
        self.assertTrue(validated["valid"], validated)
        saved = save_review_decision(session_id, decision, 0, self.store)
        result = commit_review_session(session_id, saved["revision"], self.store)
        self.assertEqual(result["status"], "committed")
        profile = result["created_profiles"][0]
        person = self.store.get_person(profile["person_id"])
        self.assertEqual(person["name"], "图南")
        self.assertEqual(person["scope"], "staff")
        self.assertIsNone(person["customer_id"])
        with self.store.connect() as db:
            stored = db.execute(
                "SELECT npz_path FROM profile_versions WHERE person_id = ?", (person["person_id"],)
            ).fetchone()
        self.assertTrue(stored["npz_path"].startswith("shared://staff/"))

    def test_source_change_blocks_commit(self) -> None:
        session_id = self.make_review_session()
        decision = {"assignments": {f"seg-{index}": self.person["person_id"] for index in range(6)}, "new_people": []}
        self.transcript.write_text("说话人 1 00:00\n内容已经变更\n", encoding="utf-8")
        result = validate_review_decision(session_id, decision, self.store)
        self.assertFalse(result["valid"])
        self.assertIn("source_changed", result["errors"][0])
        self.assertEqual(self.store.get_review_session(session_id)["status"], "source_changed")

    def test_api_requires_csrf_for_mutations(self) -> None:
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            self.assertEqual(client.get("/api/v1/customers").status_code, 200)
            self.assertEqual(client.post("/api/v1/enrollment-sessions", json={}).status_code, 403)

    def test_console_summary_and_session_list_use_readable_metadata(self) -> None:
        self.make_review_session()
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            summary = client.get("/api/v1/console/summary")
            sessions = client.get("/api/v1/enrollment-sessions")
        self.assertEqual(summary.status_code, 200)
        payload = summary.json()
        self.assertEqual(payload["customers_total"], 1)
        self.assertEqual(sum(payload["tasks"].values()), 1)
        self.assertEqual(payload["recent_sessions"][0]["customer_name"], "客户甲")
        self.assertEqual(payload["recent_sessions"][0]["display_title"], "测试会议")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(sessions.json()["sessions"][0]["recording_count"], 1)

    def test_profile_api_paginates_switches_and_disables_without_deleting_versions(self) -> None:
        self.store.save_profile(self.person, arrays(1), {"model": {}, "sources": []})
        self.store.save_profile(self.store.get_person(self.person["person_id"]), arrays(2), {"model": {}, "sources": [], "parent_version": 1})
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            listed = client.get("/api/v1/profiles?page=1&page_size=1")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["total"], 1)
            versions = client.get(f"/api/v1/profiles/{self.person['person_id']}/versions")
            self.assertEqual([item["version"] for item in versions.json()["versions"]], [2, 1])
            csrf = client.get("/api/v1/csrf").json()["token"]
            switched = client.post(
                f"/api/v1/profiles/{self.person['person_id']}/current-version",
                headers={"X-CSRF-Token": csrf},
                json={"version": 1},
            )
            disabled = client.post(
                f"/api/v1/profiles/{self.person['person_id']}/disable",
                headers={"X-CSRF-Token": csrf},
                json={},
            )
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["to_version"], 1)
        self.assertEqual(disabled.status_code, 200)
        person = self.store.get_person(self.person["person_id"])
        self.assertEqual(person["current_version"], 1)
        self.assertEqual(person["voiceprint_enabled"], 0)
        self.assertEqual(len(self.store.list_profile_versions(self.person["person_id"])), 2)

    def test_profile_revision_api_opens_sanitized_full_review_task(self) -> None:
        self.store.save_profile(
            self.person,
            arrays(1),
            profile_manifest_with_windows(self.audio, self.transcript),
        )
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            csrf = client.get("/api/v1/csrf").json()["token"]
            created = client.post(
                f"/api/v1/profiles/{self.person['person_id']}/versions/1/review",
                headers={"X-CSRF-Token": csrf},
                json={},
            )
            self.assertEqual(created.status_code, 200)
            session = client.get(
                f"/api/v1/enrollment-sessions/{created.json()['session_id']}"
            )
        self.assertEqual(session.status_code, 200)
        payload = session.json()
        self.assertEqual(payload["kind"], "profile_revision")
        self.assertEqual(payload["task_type"], "profile_revision")
        self.assertEqual(payload["package"]["profile_revision"]["base_version"], 1)
        self.assertNotIn("base_npz_path", payload["package"]["profile_revision"])
        self.assertNotIn("audio_path", payload["package"]["sources"][0])

    def test_customer_file_listing_does_not_duplicate_a_source_file(self) -> None:
        source_dir = self.customer_root / "客户甲" / "会议素材"
        source_dir.mkdir(parents=True)
        source = source_dir / "唯一录音.ogg"
        source.write_bytes(b"not-an-audio-fixture")
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            response = client.get("/api/v1/customers/customer-a/files")
        self.assertEqual(response.status_code, 200)
        paths = [item["path"] for item in response.json()["files"]]
        self.assertEqual(paths.count("会议素材/唯一录音.ogg"), 1)
        self.assertNotIn(str(self.customer_root), response.text)

    def test_api_cancels_running_review_session(self) -> None:
        manifest_path = self.root / "manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)
        claimed = self.store.claim_review_job()
        self.assertIsNotNone(claimed)
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            csrf = client.get("/api/v1/csrf").json()["token"]
            response = client.post(
                f"/api/v1/enrollment-sessions/{created['session_id']}/cancel",
                headers={"X-CSRF-Token": csrf},
                json={"reviewer": "审核人"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        with self.store.connect() as db:
            job = db.execute("SELECT status FROM review_jobs WHERE session_id = ?", (created["session_id"],)).fetchone()
        self.assertEqual(job["status"], "cancelled")

    def test_api_restarts_cancelled_enrollment_session(self) -> None:
        manifest_path = self.root / "restart-api-manifest.json"
        atomic_write_json(manifest_path, self.raw_manifest)
        created = create_enrollment_review(manifest_path, self.store)
        self.store.cancel_review_session(created["session_id"], "审核人")
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            csrf = client.get("/api/v1/csrf").json()["token"]
            response = client.post(
                f"/api/v1/enrollment-sessions/{created['session_id']}/restart",
                headers={"X-CSRF-Token": csrf},
                json={"reviewer": "审核人"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["restarted_from"], created["session_id"])
        self.assertEqual(response.json()["status"], "queued")

    def test_api_retries_failed_commit_into_original_editor(self) -> None:
        session_id = self.make_review_session()
        decision = {
            "assignments": {f"seg-{index}": self.person["person_id"] for index in range(6)},
            "new_people": [],
        }
        saved = save_review_decision(session_id, decision, 0, self.store)
        self.store.set_review_session(
            session_id, status="failed", error_message="提交失败"
        )
        self.store.finish_review_job(f"job-{session_id}", "failed", error="提交失败")
        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            before = client.get(f"/api/v1/enrollment-sessions/{session_id}").json()
            self.assertTrue(before["can_retry_edit"])
            csrf = client.get("/api/v1/csrf").json()["token"]
            response = client.post(
                f"/api/v1/enrollment-sessions/{session_id}/retry-edit",
                headers={"X-CSRF-Token": csrf},
                json={"revision": saved["revision"]},
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["session_id"], session_id)
        self.assertEqual(payload["status"], "review_required")
        self.assertEqual(payload["decision"], decision)
        self.assertIn("package", payload)

    def test_transcript_preview_is_bounded_and_cannot_escape_customer_directory(self) -> None:
        source_dir = self.customer_root / "客户甲" / "会议素材"
        source_dir.mkdir(parents=True)
        source = source_dir / "会议.txt"
        source.write_text("可预览的转写内容\n" * 3, encoding="utf-8")
        outside = self.root / "outside.txt"
        outside.write_text("不得读取", encoding="utf-8")

        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            response = client.get(
                "/api/v1/customers/customer-a/transcript-preview",
                params={"path": "会议素材/会议.txt"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["relative_path"], "会议素材/会议.txt")
            self.assertIn("可预览的转写内容", response.json()["content"])
            rejected = client.get(
                "/api/v1/customers/customer-a/transcript-preview",
                params={"path": str(outside)},
            )
            self.assertEqual(rejected.status_code, 400)

    def test_transcript_speakers_scans_full_selected_customer_transcripts(self) -> None:
        source_dir = self.customer_root / "客户甲" / "会议素材"
        source_dir.mkdir(parents=True)
        first = source_dir / "第一场.txt"
        second = source_dir / "第二场.txt"
        first.write_text("说话人 1 00:00\n发言\n说话人 2 01:02\n发言\n", encoding="utf-8")
        second.write_text("说话人 2 00:00:00\n发言\n说话人 3 00:03\n发言\n", encoding="utf-8")

        from fastapi.testclient import TestClient

        with TestClient(create_app(self.store, base_url="http://testserver")) as client:
            csrf = client.get("/api/v1/csrf").json()["token"]
            response = client.post(
                "/api/v1/customers/customer-a/transcript-speakers",
                headers={"X-CSRF-Token": csrf},
                json={"paths": ["会议素材/第一场.txt", "会议素材/第二场.txt"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["labels"], ["说话人 1", "说话人 2", "说话人 3"])
            self.assertEqual(response.json()["transcripts"][1]["labels"], ["说话人 2", "说话人 3"])


class MigrationTests(unittest.TestCase):
    def test_copy_migration_keeps_old_layout_and_writes_uris(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = DataStore(root / "old")
            audio = root / "a.wav"
            transcript = root / "a.txt"
            sf.write(audio, np.zeros(16000, dtype=np.float32), 16000)
            transcript.write_text("说话人 1 00:00\n测试\n", encoding="utf-8")
            people = old.upsert_manifest(manifest(audio, transcript, "迁移客户"))
            old.save_profile(people["张总"], arrays(), {"model": {}})
            plan = layout_migration_plan(old.root, root / "客户")
            self.assertTrue(plan["can_apply"])
            result = apply_layout_migration(old.root, root / "客户")
            self.assertTrue(result["applied"])
            self.assertTrue((old.root / "registry.sqlite3").exists())
            target = DataStore(customers_root_path=root / "客户")
            loaded = target.load_profile(people["张总"]["person_id"])
            self.assertEqual(loaded["arrays"]["center"].shape, (192,))


if __name__ == "__main__":
    unittest.main()
