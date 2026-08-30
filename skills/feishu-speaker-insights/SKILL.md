---
name: feishu-speaker-insights
description: Identify anonymous speakers in local Feishu Minutes audio and transcripts with customer-scoped voiceprints, then produce auditable confidence evidence and per-person viewpoints. Use for enrollment, cross-meeting speaker matching, profile review, or voiceprint-backed meeting insights; do not use for ordinary summaries without speaker identification.
---

# Feishu Speaker Insights

Use the deterministic CLI in `scripts/speaker_insights.py` for audio processing, voiceprint storage, matching, conflict resolution, and report rendering. Keep semantic inference limited to evidence extraction and viewpoint wording.

## Route the request

- For a new customer or new person, read [references/schemas.md](references/schemas.md), run `enroll prepare`, infer a draft label mapping from the transcript, obtain one consolidated user confirmation, then run `enroll commit`.
- For a later recording, run `analyze acoustic`, extract anchored context evidence and per-label viewpoints, then run `analyze finalize`.
- For profile maintenance, list candidates first. Run `profile promote` or `profile rollback` only after explicit confirmation.
- For setup, migration, or failures, read [references/deployment.md](references/deployment.md) and run `doctor`.
- For confidence and conflict handling, read [references/identity-resolution.md](references/identity-resolution.md).

## Invariants

- Voiceprint evidence outranks contextual inference. Context may explain, corroborate, downgrade, or produce a clearly labeled context-assisted inference; it must never rewrite acoustic scores.
- Never commit an initial label mapping or promote a candidate without user confirmation.
- Match customer people only within their customer. Load global Yingdao staff only when listed as attendees or named exactly in the transcript.
- Preserve unknown, mixed, low-audio, and review-required outcomes. Do not force every label onto a known person.
- Treat similarity as candidate-set evidence, not an identity probability. Report level, score, threshold, margin, and usable speech instead of a percentage.
- Anchor every context item and viewpoint to an existing transcript label and timestamp. If validation fails, remove the item instead of inventing a replacement.
- Do not retain cropped WAV files. Keep original audio unchanged and store only hashes, timestamps, embeddings, metadata, and reports.

## Normal workflow

1. Run `paths` so the user can see where biometric files and outputs will be stored.
2. Run `doctor`; stop on missing FFmpeg, unsupported platform, missing model source, or unwritable data paths.
3. Use an absolute-path meeting manifest that follows `references/schemas.md`.
4. Execute the relevant command through the `voiceprint-poc` Conda environment:

   `conda run -n voiceprint-poc python scripts/speaker_insights.py ...`

5. For semantic artifacts, write only the JSON shapes documented in `references/schemas.md`; pass them to `analyze finalize` for deterministic validation and rendering.
6. Return links to the Markdown report and JSON result, plus the exact profile or candidate paths when a write occurred.

## Safety boundaries

- This workflow performs local meeting analysis, not biometric authentication or access control.
- Do not upload audio, transcripts, embeddings, or customer metadata to external services unless the user separately authorizes it.
- Do not broaden a customer candidate set based on fuzzy name similarity.
- If a customer name resolves ambiguously, use its stable customer ID.
