# Speaker Notes

Read this file whenever a deck needs presenter notes, including the default case. Use it with the system `pptx` skill's `[Sources]` requirement.

## Defaults

```yaml
speaker_notes:
  enabled: true
  mode: direct_readable
  target_seconds_per_main_slide: 120
  appendix_mode: on_demand
  include_sources: true
  presenter_identity: auto
  audience_address: auto
  context_policy:
    default: user_provided_materials
    notebooklm: explicit_request_only
```

Treat explicit requests such as “不需要备注”, “不要讲稿”, or “只制作页面” as `enabled: false`. Keep source-only notes when required for external claims or assets.

Use this context order:

1. Current user instructions.
2. User-provided brief, current deck, attachments, requirements, meeting notes, and reference materials.
3. NotebookLM only when the user explicitly asks for it.
4. External research only when the user requests it or the task requires it under system rules.

Do not query, cite, or flag NotebookLM when the user has not mentioned it.

## Writing Contract

Write notes in this exact order:

```text
可直接朗读的本页讲稿。

----

可直接朗读的下一页衔接话术。

[Sources]
来源一
来源二
```

- Use one separator only. Preserve a blank line on both sides of `----`.
- Make the transition a spoken bridge, not a click instruction.
- For the final main slide, replace the bridge with a spoken wrap-up, leadership ask, or question invitation.
- For an appendix, explain its on-demand purpose, whether to play a video, and which main-story point to return to afterward.
- Keep `[Sources]` last. It is provenance, not spoken content.
- Use natural customer-facing business language. Infer the appropriate form of address from the brief; do not hard-code a customer name when it is absent.
- Add background, value, trade-offs, boundaries, and decisions that are useful in speech but not suitable as visible slide density.
- Do not invent facts, completed outcomes, savings, stakeholder views, or commitments. Use careful wording if evidence is incomplete.

## Pacing

- Main slides target approximately 120 seconds. Aim for 360-480 Chinese characters excluding `[Sources]`, then adjust for live demos, pauses, and dense evidence.
- Cover, chapter, and closing slides still need coherent spoken material but must not be padded with repetition.
- Appendix, video, and evidence slides are on-demand and do not count toward a fixed presentation duration.

## Write Routes

Use Artifact Tool for new decks and ordinary imported decks:

```js
slide.speakerNotes.textFrame.setText(notesText);
slide.speakerNotes.setVisible(true);
```

Inspect `kind: "notes"` before export to validate slide mapping and source blocks.

Use `scripts/patch_speaker_notes.mjs` when an existing PPTX must retain embedded video, audio, OLE, or other package members exactly as content:

```bash
node scripts/patch_speaker_notes.mjs \
  --input source.pptx \
  --output target.pptx \
  --notes notes.json \
  --verify
```

Use 1-based visual slide order in `notes.json`:

```json
{
  "version": 1,
  "slides": [
    {
      "slide": 1,
      "kind": "main",
      "body": "本页讲稿",
      "transition": "下一页衔接话术",
      "sources": ["用户提供的项目会议纪要"]
    },
    {
      "slide": 2,
      "kind": "closing",
      "body": "本页讲稿",
      "closing": "以上是本次建议的协同动作。",
      "sources": []
    }
  ]
}
```

The patcher updates only the supplied slide notes. It replaces their note body rather than appending content, so reruns are idempotent. It creates missing notes parts and verifies preserved media and embedding content with SHA-256.
