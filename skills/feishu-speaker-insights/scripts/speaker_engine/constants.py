from __future__ import annotations

MODEL_CONFIG = {
    "id": "iic/speech_eres2netv2_sv_zh-cn_16k-common",
    "revision": "v1.0.1",
    "checkpoint": "pretrained_eres2netv2.ckpt",
    "embedding_size": 192,
    "source_revision": "065629c313eaf1a01c65c640c46d77e61e9607b4",
    "source_url": "https://github.com/modelscope/3D-Speaker.git",
}

PIPELINE_CONFIG = {
    "sample_rate": 16000,
    "boundary_guard_seconds": 0.20,
    "min_window_seconds": 2.0,
    "max_window_seconds": 8.0,
    "estimated_chars_per_second": 4.2,
    "estimated_utterance_padding_seconds": 1.0,
    "max_start_only_span_seconds": 30.0,
    "vad_frame_seconds": 0.025,
    "vad_hop_seconds": 0.010,
    "vad_noise_quantile": 0.20,
    "vad_reference_quantile": 0.80,
    "vad_min_snr_db": 6.0,
    "vad_absolute_floor_dbfs": -48.0,
    "vad_reference_margin_db": 1.5,
    "vad_min_region_seconds": 0.18,
    "vad_merge_gap_seconds": 0.60,
    "vad_padding_seconds": 0.15,
    "min_rms_dbfs": -50.0,
    "min_voiced_fraction": 0.25,
    "max_clipping_ratio": 0.05,
    "max_enrollment_candidates_per_person": 42,
    "max_profile_windows_per_person": 30,
    # Browser review starts with a bounded but time-diverse sample for each
    # source recording and transcript label.  The audio-quality pass still
    # examines every candidate window; only expensive embedding is capped.
    "review_initial_min_windows_per_label": 8,
    "review_initial_seconds_per_window": 30.0,
    "review_initial_max_windows_per_label": 24,
    "review_mixed_expansion_windows": 8,
    "review_max_windows_per_label": 42,
    "max_test_windows_per_label": 40,
    "holdout_fraction": 0.25,
    "minimum_profile_windows": 6,
    "minimum_profile_seconds": 12.0,
    "top_reference_count": 3,
    "minimum_accept_seconds": 6.0,
    "minimum_accept_windows": 2,
    "minimum_margin_floor": 0.03,
    "default_accept_threshold": 0.58,
    "default_margin_threshold": 0.10,
    "high_confidence_score_surplus": 0.08,
    "high_confidence_margin_surplus": 0.05,
    "high_confidence_seconds": 12.0,
    "uncertain_score_tolerance": 0.03,
    "mixed_minority_fraction": 0.25,
    "mixed_minority_windows": 2,
    "candidate_minimum_seconds": 12.0,
    "max_promoted_references": 60,
}

SCHEMA_VERSION = 1
