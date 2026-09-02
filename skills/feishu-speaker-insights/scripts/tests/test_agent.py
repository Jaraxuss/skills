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

from speaker_engine.agent import (
    _audition_bundle,
    agent_analysis_correct,
    agent_analyze_complete,
    agent_analyze_start,
    agent_enroll_confirm,
)
from speaker_engine.reporting import build_feishu_summary, write_outputs
from speaker_engine.storage import DataStore
from speaker_engine.util import atomic_save_npz, atomic_write_json, sha256_file
from speaker_engine.workflow import _calibration_for_profiles


def unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


class AgentWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = DataStore(customers_root_path=self.root / "客户")
        self.audio = self.root / "会议.wav"
        self.transcript = self.root / "会议.txt"
        sf.write(self.audio, np.zeros(16000 * 20, dtype=np.float32), 16000)
        self.transcript.write_text(
            "说话人 1 00:00\n我们需要先确认项目范围。\n", encoding="utf-8"
        )
        self.manifest = {
            "schema_version": 1,
            "customer": {"id": "customer-a", "name": "客户甲"},
            "meeting": {
                "id": "meeting-a",
                "title": "会议",
                "audio": str(self.audio),
                "transcript": str(self.transcript),
            },
            "attendees": [
                {"name": "张总", "role": "老板", "organization": "customer"}
            ],
            "known_label_map": {},
            "excluded_labels": [],
        }
        self.people = self.store.upsert_manifest(self.manifest)
        self.person = self.people["张总"]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_task(self, operation: str, request_hash: str) -> dict:
        return self.store.create_or_reuse_task(
            task_id=f"task-{operation}-{request_hash}",
            operation=operation,
            customer_id="customer-a",
            request_hash=request_hash,
            source_hash="source-hash",
            pipeline_hash="pipeline-hash",
            cohort_hash="cohort-hash",
        )[0]

    def test_task_hash_reuses_work_and_waiting_state_releases_lease(self) -> None:
        first, reused = self.store.create_or_reuse_task(
            task_id="task-analyze-one",
            operation="analyze",
            customer_id="customer-a",
            request_hash="same-request",
            source_hash="source-hash",
            pipeline_hash="pipeline-hash",
            cohort_hash="cohort-hash",
        )
        self.assertFalse(reused)
        second, reused = self.store.create_or_reuse_task(
            task_id="task-analyze-two",
            operation="analyze",
            customer_id="customer-a",
            request_hash="same-request",
            source_hash="source-hash",
            pipeline_hash="pipeline-hash",
            cohort_hash="cohort-hash",
        )
        self.assertTrue(reused)
        self.assertEqual(first["task_id"], second["task_id"])
        self.store.claim_task(first["task_id"], "worker-a")
        with self.assertRaisesRegex(RuntimeError, "task_already_running"):
            self.store.claim_task(first["task_id"], "worker-b")
        waiting = self.store.update_task(
            first["task_id"], status="awaiting_semantic", phase="awaiting_semantic"
        )
        self.assertIsNone(waiting["lease_owner"])
        claimed = self.store.claim_task(first["task_id"], "worker-b")
        self.assertEqual(claimed["lease_owner"], "worker-b")
        revision = self.store.update_task(
            first["task_id"],
            status="awaiting_semantic",
            phase="semantic_revision_required",
            error_code="MISSING_VIEWPOINT_LABELS",
            error_details={"missing_labels": ["说话人 1"]},
        )
        self.assertEqual(revision["error_code"], "MISSING_VIEWPOINT_LABELS")
        resumed = self.store.update_task(
            first["task_id"], status="running", phase="semantic_validation"
        )
        self.assertIsNone(resumed["error_code"])

    def test_calibration_cache_is_read_instead_of_recomputed(self) -> None:
        profile_path = self.root / "profile.npz"
        atomic_save_npz(profile_path, center=np.eye(1, 192, dtype=np.float32)[0])
        profiles = {
            self.person["person_id"]: {
                "version": 1,
                "npz_path": profile_path,
                "arrays": {"center": np.eye(1, 192, dtype=np.float32)[0]},
            }
        }
        calibration = {
            "accept_threshold": 0.58,
            "margin_threshold": 0.10,
            "source": "unit",
        }
        with patch(
            "speaker_engine.workflow.calibrate_profiles", return_value=calibration
        ) as mocked:
            first = _calibration_for_profiles(self.store, "customer-a", profiles)
            second = _calibration_for_profiles(self.store, "customer-a", profiles)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        mocked.assert_called_once()

    def test_feishu_summary_keeps_rankings_and_viewpoints(self) -> None:
        bundle = self.bundle()
        row = self.resolved_row()
        grouped = [
            {
                "identity": "张总",
                "person_id": self.person["person_id"],
                "labels": ["说话人 1"],
                "items": [
                    {
                        "timestamp": "00:00",
                        "category": "需求",
                        "point": "需要先确认项目范围。",
                    }
                ],
                "non_substantive": [],
            }
        ]
        summary = build_feishu_summary(bundle, [row], grouped)
        self.assertEqual(summary["speakers"][0]["matches"][0]["top1"]["name"], "张总")
        self.assertIn("核心观点", summary["message_markdown"])
        self.assertIn("声纹排序", summary["message_markdown"])

    def test_combined_audition_audio_is_a_single_playable_ogg(self) -> None:
        package = {
            "source": {
                "source_id": "source-1",
                "audio_path": str(self.audio),
            },
            "segments": [
                {
                    "segment_id": "segment-a",
                    "source_id": "source-1",
                    "start": 0.0,
                    "end": 2.0,
                }
            ],
        }
        destination = self.root / "试听合并.ogg"
        result = _audition_bundle(
            package,
            [{"representative_segment_id": "segment-a"}],
            destination,
        )
        info = sf.info(result)
        self.assertEqual(info.samplerate, 16000)
        self.assertGreater(info.frames, 16000)

    def test_quick_confirmation_is_idempotent_and_records_feishu_mode(self) -> None:
        session_id = "review-agent-unit"
        session_dir = self.store.session_dir("customer-a", session_id)
        manifest_path = session_dir / "manifest.json"
        atomic_write_json(manifest_path, self.manifest)
        self.store.create_review_session(
            "customer-a",
            session_id,
            "enrollment",
            manifest_path,
            sha256_file(self.audio),
            sha256_file(self.transcript),
        )
        rng = np.random.default_rng(2)
        center = np.eye(1, 192, dtype=np.float32)[0]
        vectors = np.stack([unit(center + rng.normal(0, 0.01, 192)) for _ in range(6)])
        segments = []
        for index in range(6):
            start = float(index * 2)
            segments.append(
                {
                    "segment_id": f"seg-{index}",
                    "vector_index": index,
                    "source_id": "source-1",
                    "meeting_title": "会议",
                    "label": "说话人 1",
                    "utterance_index": index,
                    "timestamp": f"00:{index * 2:02d}",
                    "start": start,
                    "end": start + 2.0,
                    "duration": 2.0,
                    "quality": 0.9,
                    "rms_dbfs": -20.0,
                    "voiced_fraction": 0.9,
                    "clipping_ratio": 0.0,
                    "text": "这是有效测试发言",
                }
            )
        pending_path = session_dir / "pending_vectors.npz"
        atomic_save_npz(pending_path, embeddings=vectors)
        source = {
            "source_id": "source-1",
            "customer_id": "customer-a",
            "meeting_id": "meeting-a",
            "title": "会议",
            "audio_path": str(self.audio),
            "transcript_path": str(self.transcript),
            "audio_sha256": sha256_file(self.audio),
            "transcript_sha256": sha256_file(self.transcript),
        }
        package = {
            "schema_version": 1,
            "session_id": session_id,
            "kind": "enrollment",
            "manifest": self.manifest,
            "source": source,
            "sources": [source],
            "model": {"id": "test", "revision": "test"},
            "people": [self.person],
            "segments": segments,
            "pending_vector_file": pending_path.name,
            "selection_requirements": {"minimum_windows": 6, "minimum_seconds": 12.0},
            "labels": [],
            "transcript_index": {},
            "calibration": {"accept_threshold": 0.58},
        }
        package_path = session_dir / "review_package.json"
        atomic_write_json(package_path, package)
        self.store.set_review_session(
            session_id, status="review_required", package_path=package_path
        )
        agent_payload = {
            "review_mode": "feishu_quick",
            "target_person": self.person,
            "candidates": [
                {
                    "code": "A",
                    "candidate_id": "cluster-a",
                    "segment_ids": [item["segment_id"] for item in segments],
                }
            ],
        }
        agent_path = session_dir / "agent_enrollment.json"
        atomic_write_json(agent_path, agent_payload)
        task = self.create_task("enroll", "enroll-confirmation")
        self.store.update_task(
            task["task_id"],
            status="waiting_confirmation",
            phase="waiting_chat_confirmation",
            checkpoint={
                "session_id": session_id,
                "agent_enrollment": str(agent_path),
                "conversation": {
                    "channel": "feishu",
                    "chat_id": "chat-1",
                    "user_id": "user-1",
                },
            },
        )
        confirmation = self.root / "confirmation.json"
        atomic_write_json(
            confirmation,
            {
                "task_id": task["task_id"],
                "confirmation_text": "确认建库",
                "confirmation_message_id": "message-1",
                "channel": "feishu",
                "chat_id": "chat-1",
                "user_id": "user-1",
            },
        )
        first = agent_enroll_confirm(confirmation, self.store)
        second = agent_enroll_confirm(confirmation, self.store)
        self.assertEqual(first["status"], "completed")
        self.assertTrue(second["reused"])
        profile = self.store.load_profile(self.person["person_id"])
        self.assertEqual(profile["manifest"]["confirmation_mode"], "feishu_message_confirmed")
        self.assertTrue(first["commit_hash"])

    def test_analysis_stages_resume_and_correction_does_not_change_voiceprint(self) -> None:
        request_path = self.root / "analysis-request.json"
        atomic_write_json(request_path, {"manifest": self.manifest})
        fake_run = self.store.create_run("customer-a", "meeting-a", "run-agent", "analysis")
        bundle_path = fake_run / "acoustic_bundle.json"
        transcript_index_path = fake_run / "transcript_index.json"
        atomic_write_json(bundle_path, self.bundle())
        atomic_write_json(
            transcript_index_path,
            {
                "labels": {"说话人 1": [0]},
                "utterances": [
                    {
                        "index": 0,
                        "label": "说话人 1",
                        "timestamp": "00:00",
                        "text": "我们需要先确认项目范围。",
                    }
                ],
            },
        )
        acoustic = {
            "run_dir": str(fake_run),
            "acoustic_bundle": str(bundle_path),
            "transcript_index": str(transcript_index_path),
        }
        with patch("speaker_engine.agent.analyze_acoustic", return_value=acoustic) as analyze:
            started = agent_analyze_start(request_path, self.store)
            resumed = agent_analyze_start(request_path, self.store)
        analyze.assert_called_once()
        self.assertEqual(started["status"], "awaiting_semantic")
        self.assertTrue(resumed["reused"])
        semantic_path = self.root / "semantic.json"
        semantic = {
            "context": {"schema_version": 1, "items": []},
            "viewpoints": {
                "schema_version": 1,
                "items": [
                    {
                        "transcript_label": "说话人 1",
                        "timestamp": "00:00",
                        "category": "需求",
                        "point": "需要先确认项目范围。",
                        "source_excerpt": "我们需要先确认项目范围。",
                    }
                ],
                "non_substantive_labels": [],
            },
        }
        atomic_write_json(semantic_path, semantic)
        atomic_write_json(fake_run / "validated_context.json", semantic["context"])
        atomic_write_json(
            fake_run / "validated_viewpoints.json", semantic["viewpoints"]
        )
        outputs = write_outputs(
            fake_run,
            self.bundle(),
            [self.resolved_row()],
            [],
            [],
            semantic["viewpoints"]["items"],
            [],
            [],
            [],
        )
        finalize_result = {"status": "completed", "outputs": outputs}
        with patch(
            "speaker_engine.agent.analyze_finalize", return_value=finalize_result
        ) as finalize:
            completed = agent_analyze_complete(started["task_id"], semantic_path, self.store)
            repeated = agent_analyze_complete(started["task_id"], semantic_path, self.store)
        finalize.assert_called_once()
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(repeated["reused"])
        corrections = self.root / "corrections.json"
        atomic_write_json(
            corrections,
            {
                "confirmation_message_id": "correction-message",
                "corrections": [
                    {"transcript_label": "说话人 1", "identity": "现场专家"}
                ],
            },
        )
        with self.store.connect() as db:
            before = db.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0]
        corrected = agent_analysis_correct(started["task_id"], corrections, self.store)
        corrected_again = agent_analysis_correct(started["task_id"], corrections, self.store)
        with self.store.connect() as db:
            after = db.execute("SELECT COUNT(*) FROM profile_versions").fetchone()[0]
        self.assertFalse(corrected["voiceprint_changed"])
        self.assertTrue(corrected_again["reused"])
        self.assertEqual(before, after)

    def bundle(self) -> dict:
        return {
            "run_id": "run-agent",
            "customer": self.manifest["customer"],
            "meeting": self.manifest["meeting"],
            "model": {"id": "test", "revision": "test"},
            "calibration": {
                "accept_threshold": 0.58,
                "margin_threshold": 0.10,
                "source": "unit",
            },
            "candidate_people": [
                {
                    "person_id": self.person["person_id"],
                    "name": "张总",
                    "role": "老板",
                }
            ],
        }

    def resolved_row(self) -> dict:
        return {
            "transcript_label": "说话人 1",
            "final_identity_key": f"person:{self.person['person_id']}",
            "final_person_id": self.person["person_id"],
            "final_identity": "张总",
            "final_status": "声纹已匹配",
            "final_confidence": "高",
            "acoustic_confidence": "高",
            "top1_person_id": self.person["person_id"],
            "top1_score": 0.82,
            "top2_person_id": None,
            "top2_score": None,
            "score_margin": None,
            "usable_windows": 6,
            "usable_seconds": 18.0,
            "context_person": None,
            "context_strength": None,
            "voice_context_conflict": False,
            "needs_review": False,
            "decision_basis": "voiceprint",
            "notes": [],
        }


if __name__ == "__main__":
    unittest.main()
