---
name: feishu-speaker-insights
description: Identify anonymous speakers in local Feishu Minutes audio and transcripts with customer-scoped voiceprints, then produce auditable confidence evidence and per-person viewpoints. Use for enrollment, cross-meeting speaker matching, profile review, or voiceprint-backed meeting insights; do not use for ordinary summaries without speaker identification.
---

# Feishu Speaker Insights

Use the deterministic CLI in `scripts/speaker_insights.py` for audio processing, voiceprint storage, matching, review sessions, conflict resolution, and report rendering. Keep semantic inference limited to evidence extraction and viewpoint wording.

## Route the request

- For a new customer or new person, read [references/review-console.md](references/review-console.md) and [references/schemas.md](references/schemas.md). Create an `enroll review-create` session and return its review URL. Do not conduct per-label confirmation in chat or run `enroll commit` unless an administrator explicitly requests the legacy CLI path.
- For a later recording, run `analyze acoustic`, read the generated transcript index, autonomously extract anchored context evidence and per-label viewpoints, then run `analyze finalize`. Do not pause for threshold selection or ask the user to fill semantic JSON.
- For profile maintenance, list candidates first. Create `profile review-create` for a pending candidate; the browser confirmation authorizes promotion. `profile rollback` and `profile quarantine` remain explicit administrator actions.
- For setup, migration, the review service, or failures, read [references/deployment.md](references/deployment.md) and run `doctor`.
- For confidence and conflict handling, read [references/identity-resolution.md](references/identity-resolution.md).

## Invariants

- Voiceprint evidence outranks contextual inference. Context may explain, corroborate, downgrade, or produce a clearly labeled context-assisted inference; it must never rewrite acoustic scores.
- A browser click on “确认建库” is the required user confirmation. Before that click, keep vectors only under the expiring review session and never create a usable profile version.
- Match customer people only within their customer. Load global Yingdao staff only when listed as attendees or named exactly in the transcript.
- Preserve unknown, mixed, low-audio, and review-required outcomes. Do not force every label onto a known person.
- Always show acoustic Top-1 and Top-2 identities and similarity scores when profiles exist, even when the final identity remains unknown. Internal thresholds are automatic safety gates, not user settings.
- A strongly and explicitly grounded name may identify a speaker who is outside the current voiceprint cohort. Label this `上下文识别（声纹库外）`, preserve the acoustic ranking, and never create a profile automatically.
- Treat similarity as candidate-set evidence, not an identity probability. Report level, score, threshold, margin, and usable speech instead of a percentage.
- Anchor every context item and viewpoint to an existing transcript label and timestamp. If validation fails, repair it from the transcript or report the failure; never invent evidence.
- Cover every transcript label with at least one grounded core viewpoint or `发言摘要`, whether the label is known, unknown, mixed, or outside the voiceprint cohort. The only exception is grounded background/noise/incidental speech recorded in `non_substantive_labels`. Never finalize an empty viewpoint artifact.
- Do not retain cropped WAV files. Keep original audio unchanged and store only hashes, timestamps, embeddings, metadata, and reports.
- The review HTTP service is LAN-local only. Do not expose it to the public Internet or add an unauthorised remote proxy.

## Normal workflow

1. Run `paths` so the user can see where biometric files and outputs will be stored. In the production layout, set `FEISHU_SPEAKER_CUSTOMERS_ROOT`; customer profiles live under `<客户>/声纹数据` and staff profiles plus SQLite live under `<客户根>/共享数据/声纹数据`.
2. Run `doctor`; stop on missing FFmpeg, unsupported platform, missing model source, or unwritable data paths.
3. Use an absolute-path meeting manifest that follows `references/schemas.md`.
4. Execute the relevant command through the `voiceprint-poc` Conda environment:

   `conda run -n voiceprint-poc python scripts/speaker_insights.py ...`

5. For a new enrollment, create the review session, return the link, and end the interaction. The Worker prepares audio evidence once; the browser reuses it for clustering, playback, editing, and validation. Never reload the model merely because a user edits selections.
6. For semantic artifacts, write only the JSON shapes documented in `references/schemas.md`. Inspect every label in `transcript_index.json`, create both artifacts in the same run, and pass them to `analyze finalize` for deterministic validation and rendering. If finalization reports missing labels, complete those labels from the indexed transcript and retry without asking the user.
7. Return links to the Markdown report and JSON result, plus the exact profile or candidate paths when a write occurred.

## Safety boundaries

- This workflow performs local meeting analysis, not biometric authentication or access control.
- Do not upload audio, transcripts, embeddings, or customer metadata to external services unless the user separately authorizes it.
- Do not broaden a customer candidate set based on fuzzy name similarity.
- If a customer name resolves ambiguously, use its stable customer ID.
