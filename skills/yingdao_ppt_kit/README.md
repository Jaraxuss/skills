# Yingdao PPT Kit

This skill now uses a Markdown creative brief as the primary input for high-quality Yingdao-style customer PPT generation.

## Recommended Workflow

1. Copy `brief.md` and fill in the customer, audience, content scope, visual direction, page intent, and acceptance criteria.
2. Ask the agent to use this skill and the filled brief to create a `.pptx`.
3. The agent should use the system `pptx` skill plus `references/design-tokens.md` to plan, design, build, render, inspect, revise, and add direct-readable speaker notes by default.
4. Final decks should use AI-led layout and visual judgment, not fixed Python layouts. NotebookLM is used only when the user explicitly asks for it.

## Reference Files

- `references/design-tokens.md`: numeric design spec (palette, type scale, furniture, components, QA hard gates). Read before authoring.
- `references/visual-style.md`: Yingdao visual language.
- `references/slide-patterns.md`: page patterns, rhythm rules, and anti-patterns.
- `references/customer-copy.md`: customer-facing copy rules.
- `references/speaker-notes.md`: default talk-track format, 120-second pacing, next-slide bridges, and notes-only PPTX patching.
- `references/qa-checklist.md`: rendering and quality checks.
- `examples/brief_lianbao_python_excel.md`: filled regression brief for the 合肥联宝 Python/Excel training deck.

## Assets

- `assets/yingdao_logo.png`: default logo.
- `assets/manifest.json`: image index — tier, target slide roles, recommended scrim, industry fit, safe text zone, reuse cap. Read it before picking images.
- `assets/atmosphere/`, `assets/hero/`, `assets/concept/`: three-tier image library (background wash / cover hero / concept illustration).
- `scripts/duotone.js`: map any source image onto the Yingdao red/white/pink palette before adding it to the manifest.
- `scripts/patch_speaker_notes.mjs`: add or replace speaker notes in an existing PPTX while preserving embedded media and OLE package members.
- `assets/reference/good/`: four approved sample slides (cover / divider / case / summary), PNG + HTML source.
- `assets/reference/bad/`: real anti-pattern renders from the legacy fixed-script route.

## Legacy Tools

The original files remain for compatibility:

- `yingdao_ppt_builder.py`
- `postprocess_yingdao_ppt.py`
- `deck_config_*.json`

These are draft/legacy helpers only. They are acceptable for quick structure experiments or compatibility checks, but not for final customer-facing PPT quality.
