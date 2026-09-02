from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_server import create_app
from speaker_engine.api_client import agent_api_command
from speaker_engine.errors import StructuredError
from speaker_engine.service import (
    ServiceWorker,
    enqueue_analysis,
    enrollment_request,
    submit_semantic_result,
)
from speaker_engine.storage import DataStore
from speaker_engine.util import atomic_write_json


class ServiceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "客户"
        self.source = self.root / "客户甲" / "录音"
        self.source.mkdir(parents=True)
        self.audio = self.source / "会议.wav"
        self.transcript = self.source / "会议.md"
        sf.write(self.audio, np.zeros(16000 * 20, dtype=np.float32), 16000)
        self.transcript.write_text(
            "说话人 1 00:00\n我们需要确认项目范围。\n", encoding="utf-8"
        )
        self.store = DataStore(customers_root_path=self.root)
        self.customer_id = str(self.store.discover_customers()[0]["customer_id"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, external_request_id: str = "message-1") -> dict:
        return {
            "schema_version": 1,
            "external_request_id": external_request_id,
            "conversation": {
                "channel": "feishu",
                "chat_id": "chat-1",
                "user_id": "user-1",
                "trigger_message_id": external_request_id,
            },
            "customer_id": self.customer_id,
            "meeting": {
                "audio_relpath": "录音/会议.wav",
                "transcript_relpath": "录音/会议.md",
            },
            "attendees": [],
            "known_label_map": {},
            "excluded_labels": [],
        }

    def test_enqueue_uses_customer_relative_paths_and_is_idempotent(self) -> None:
        first, reused = enqueue_analysis(self.request(), self.store)
        self.assertFalse(reused)
        self.assertEqual(first["status"], "queued")
        second, reused = enqueue_analysis(self.request(), self.store)
        self.assertTrue(reused)
        self.assertEqual(first["task_id"], second["task_id"])
        manifest = json.loads(
            (Path(first["artifact_dir"]) / "request.json").read_text(encoding="utf-8")
        )["manifest"]
        self.assertTrue(Path(manifest["meeting"]["audio"]).is_absolute())
        self.assertEqual(manifest["meeting"]["title"], "会议")

    def test_absolute_and_protected_paths_are_rejected(self) -> None:
        invalid = self.request()
        invalid["meeting"]["audio_relpath"] = str(self.audio)
        with self.assertRaises(StructuredError) as caught:
            enqueue_analysis(invalid, self.store)
        self.assertEqual(caught.exception.code, "INVALID_SOURCE_PATH")

        protected = self.root / "客户甲" / "声纹数据" / "fake.md"
        protected.parent.mkdir(parents=True, exist_ok=True)
        protected.write_text("secret", encoding="utf-8")
        invalid = self.request("message-2")
        invalid["meeting"]["transcript_relpath"] = "声纹数据/fake.md"
        with self.assertRaises(StructuredError) as caught:
            enqueue_analysis(invalid, self.store)
        self.assertEqual(caught.exception.code, "INVALID_SOURCE_PATH")

    def test_external_request_id_conflict_is_machine_readable(self) -> None:
        enqueue_analysis(self.request(), self.store)
        transcript = self.source / "另一场.md"
        transcript.write_text("说话人 1 00:00\n另一份内容。\n", encoding="utf-8")
        changed = self.request()
        changed["meeting"]["transcript_relpath"] = "录音/另一场.md"
        with self.assertRaises(StructuredError) as caught:
            enqueue_analysis(changed, self.store)
        self.assertEqual(caught.exception.code, "EXTERNAL_REQUEST_CONFLICT")

    def test_enrollment_normalizes_staff_alias_for_target_person(self) -> None:
        payload = {
            "schema_version": 1,
            "customer_id": self.customer_id,
            "meetings": [
                {
                    "audio_relpath": "录音/会议.wav",
                    "transcript_relpath": "录音/会议.md",
                }
            ],
            "attendees": [],
            "target_person": {
                "name": "图南",
                "role": "CSM",
                "organization": "staff",
            },
        }
        normalized = enrollment_request(payload, self.store)
        self.assertEqual(normalized["target_person"]["organization"], "yingdao")
        self.assertEqual(
            normalized["manifest"]["attendees"][0]["organization"], "yingdao"
        )

    def test_http_lifecycle_exposes_semantic_request_and_queues_finalize(self) -> None:
        with patch("speaker_engine.service.ServiceWorker.run_once", return_value=None):
            with TestClient(create_app(self.store, base_url="http://testserver")) as client:
                capabilities = client.get("/api/v1/capabilities")
                self.assertEqual(capabilities.status_code, 200)
                self.assertEqual(capabilities.json()["service_api"], 1)
                customers = client.get("/api/v1/customers").json()["customers"]
                self.assertEqual(customers[0]["customer_id"], self.customer_id)
                self.assertNotIn("metadata_json", customers[0])
                self.assertNotIn("directory_relpath", customers[0])
                created = client.post("/api/v1/analysis-tasks", json=self.request())
                self.assertEqual(created.status_code, 202)
                task_id = created.json()["task_id"]
                task = self.store.get_task(task_id)
                semantic_path = Path(task["artifact_dir"]) / "semantic_request.json"
                transcript_index_path = Path(task["artifact_dir"]) / "transcript_index.json"
                atomic_write_json(
                    transcript_index_path,
                    {"labels": {"说话人 1": [0]}, "utterances": [{"label": "说话人 1"}]},
                )
                atomic_write_json(
                    semantic_path,
                    {
                        "schema_version": 1,
                        "required_labels": ["说话人 1"],
                        "transcript_index": str(transcript_index_path),
                    },
                )
                self.store.update_task(
                    task_id,
                    status="awaiting_semantic",
                    phase="awaiting_semantic",
                    checkpoint={
                        **(task.get("checkpoint") or {}),
                        "semantic_request": str(semantic_path),
                        "acoustic": {"run_dir": str(Path(task["artifact_dir"]) / "run")},
                    },
                )
                semantic = client.get(
                    f"/api/v1/analysis-tasks/{task_id}/semantic-request"
                )
                self.assertEqual(semantic.status_code, 200)
                self.assertIsInstance(semantic.json()["transcript_index"], dict)
                self.assertNotIn(str(self.root), semantic.text)
                payload = {
                    "context": {"schema_version": 1, "items": []},
                    "viewpoints": {
                        "schema_version": 1,
                        "items": [],
                        "non_substantive_labels": [
                            {
                                "transcript_label": "说话人 1",
                                "timestamp": "00:00",
                                "quote": "我们需要确认项目范围。",
                                "reason": "测试",
                            }
                        ],
                    },
                }
                submitted = client.post(
                    f"/api/v1/analysis-tasks/{task_id}/semantic-result", json=payload
                )
                self.assertEqual(submitted.status_code, 202)
                self.assertEqual(submitted.json()["phase"], "queued_finalize")
                repeated = client.post(
                    f"/api/v1/analysis-tasks/{task_id}/semantic-result", json=payload
                )
                self.assertTrue(repeated.json()["reused"])

    def test_http_cancel_retry_and_machine_error_shape(self) -> None:
        with patch("speaker_engine.service.ServiceWorker.run_once", return_value=None):
            with TestClient(create_app(self.store, base_url="http://testserver")) as client:
                created = client.post("/api/v1/analysis-tasks", json=self.request())
                task_id = created.json()["task_id"]
                cancelled = client.post(
                    f"/api/v1/analysis-tasks/{task_id}/cancel", json={}
                )
                self.assertEqual(cancelled.json()["status"], "cancelled")
                retried = client.post(
                    f"/api/v1/analysis-tasks/{task_id}/retry", json={}
                )
                self.assertEqual(retried.status_code, 202)
                self.assertEqual(retried.json()["phase"], "queued_acoustic")

                invalid = self.request("message-invalid")
                invalid["meeting"]["audio_relpath"] = str(self.audio)
                rejected = client.post("/api/v1/analysis-tasks", json=invalid)
                self.assertEqual(rejected.status_code, 400)
                self.assertEqual(rejected.json()["error_code"], "INVALID_SOURCE_PATH")
                self.assertIn("retryable", rejected.json())

    def test_http_enrollment_task_accepts_relative_multi_meeting_request(self) -> None:
        payload = {
            "schema_version": 1,
            "external_request_id": "enrollment-message-1",
            "customer_id": self.customer_id,
            "meetings": [
                {
                    "audio_relpath": "录音/会议.wav",
                    "transcript_relpath": "录音/会议.md",
                }
            ],
            "attendees": [
                {"name": "客户负责人", "role": "负责人", "organization": "customer"}
            ],
            "target_person": {"name": "客户负责人"},
            "review_mode": "auto",
        }
        with patch("speaker_engine.service.ServiceWorker.run_once", return_value=None):
            with TestClient(create_app(self.store, base_url="http://testserver")) as client:
                created = client.post("/api/v1/enrollment-tasks", json=payload)
                self.assertEqual(created.status_code, 202)
                self.assertEqual(created.json()["phase"], "queued_enrollment")
                self.assertNotIn(str(self.root), created.text)

    def test_reports_are_served_without_exposing_server_paths(self) -> None:
        task, _ = enqueue_analysis(self.request(), self.store)
        task_dir = Path(task["artifact_dir"])
        final_path = task_dir / "final_results.json"
        feishu_path = task_dir / "feishu_summary.json"
        markdown_path = task_dir / "report.md"
        atomic_write_json(
            final_path,
            {
                "schema_version": 1,
                "meeting": {"title": "会议", "audio": str(self.audio)},
                "calibration": {"cache_path": str(task_dir / "calibration.json")},
                "results": [],
            },
        )
        atomic_write_json(
            feishu_path,
            {
                "schema_version": 1,
                "message_markdown": "完成",
                "detailed_report": str(markdown_path),
            },
        )
        markdown_path.write_text("# 报告\n", encoding="utf-8")
        self.store.update_task(
            task["task_id"],
            status="completed",
            phase="completed",
            checkpoint={
                "result": {
                    "outputs": {
                        "json": str(final_path),
                        "feishu_summary": str(feishu_path),
                        "report": str(markdown_path),
                    }
                }
            },
            result_path=final_path,
            completed=True,
        )
        with patch("speaker_engine.service.ServiceWorker.run_once", return_value=None):
            with TestClient(create_app(self.store, base_url="http://testserver")) as client:
                summary = client.get(
                    f"/api/v1/analysis-tasks/{task['task_id']}/report?format=feishu"
                )
                self.assertEqual(summary.json()["message_markdown"], "完成")
                self.assertIn("markdown", summary.json()["report_urls"])
                self.assertNotIn(str(self.root), summary.text)
                complete = client.get(
                    f"/api/v1/analysis-tasks/{task['task_id']}/report?format=json"
                )
                self.assertNotIn(str(self.root), complete.text)
                markdown = client.get(
                    f"/api/v1/analysis-tasks/{task['task_id']}/report?format=markdown"
                )
                self.assertIn("# 报告", markdown.text)

    def test_service_restart_recovers_owned_running_task(self) -> None:
        task, _ = enqueue_analysis(self.request(), self.store)
        self.store.claim_task(task["task_id"], "old-service", lease_seconds=900)
        recovered = self.store.recover_expired_tasks(force=True)
        self.assertEqual(recovered, [task["task_id"]])
        self.assertEqual(self.store.get_task(task["task_id"])["phase"], "queued_acoustic")

    def test_single_worker_runs_acoustic_then_finalize_queue(self) -> None:
        task, _ = enqueue_analysis(self.request(), self.store)
        run_dir = self.store.create_run(self.customer_id, "meeting-test", "run-test", "analysis")
        bundle_path = run_dir / "acoustic_bundle.json"
        index_path = run_dir / "transcript_index.json"
        atomic_write_json(bundle_path, {"candidate_people": []})
        atomic_write_json(index_path, {"labels": {"说话人 1": [0]}})
        acoustic = {
            "run_dir": str(run_dir),
            "acoustic_bundle": str(bundle_path),
            "transcript_index": str(index_path),
        }
        worker = ServiceWorker(
            self.store,
            base_url="http://testserver",
            engine_factory=lambda: object(),
        )
        with patch("speaker_engine.agent.analyze_acoustic", return_value=acoustic):
            worker.run_once()
        waiting = self.store.get_task(task["task_id"])
        self.assertEqual(waiting["status"], "awaiting_semantic")
        semantic = {
            "context": {"schema_version": 1, "items": []},
            "viewpoints": {"schema_version": 1, "items": [], "non_substantive_labels": []},
        }
        submit_semantic_result(task["task_id"], semantic, self.store)
        final_path = run_dir / "final_results.json"
        feishu_path = run_dir / "feishu_summary.json"
        report_path = run_dir / "report.md"
        atomic_write_json(final_path, {"results": []})
        atomic_write_json(feishu_path, {"message_markdown": "完成"})
        report_path.write_text("# 完成\n", encoding="utf-8")
        result = {
            "status": "completed",
            "outputs": {
                "json": str(final_path),
                "feishu_summary": str(feishu_path),
                "report": str(report_path),
            },
        }
        with patch("speaker_engine.agent.analyze_finalize", return_value=result):
            worker.run_once()
        self.assertEqual(self.store.get_task(task["task_id"])["status"], "completed")

    def test_business_cli_never_falls_back_when_backend_is_down(self) -> None:
        request_path = Path(self.temporary.name) / "request.json"
        atomic_write_json(request_path, self.request())
        with self.assertRaises(StructuredError) as caught:
            agent_api_command(
                "analyze-start",
                api_url="http://127.0.0.1:9",
                request_path=request_path,
            )
        self.assertEqual(caught.exception.code, "BACKEND_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
