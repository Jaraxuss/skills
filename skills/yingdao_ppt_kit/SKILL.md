---
name: yingdao-ppt-kit
description: Create high-quality Yingdao-style customer-facing PowerPoint decks from a Markdown creative brief. Use when Codex needs to make customer training, sales, delivery, project recap, or scenario co-creation PPTs for Yingdao/RPA topics, especially when the user provides or asks for a brief.md, wants AI-led visual judgment, asks to avoid fixed script/template output, or references Yingdao-style PPT aesthetics. Prefer this workflow over the legacy JSON/python-pptx generator for final customer decks.
---

# Yingdao PPT Kit

Use this skill to create polished Yingdao-style customer PPTs from a Markdown creative brief. The brief is the content and intent contract; the model must make page-level visual decisions instead of filling a fixed template.

## Default Workflow

1. Read `brief.md` first. If the user provides another Markdown file, treat it as the brief.
2. Read only the reference files needed for the task:
   - `references/visual-style.md` for Yingdao visual language.
   - `references/slide-patterns.md` for page types, rhythm, and anti-patterns.
   - `references/customer-copy.md` for customer-facing wording rules.
   - `references/qa-checklist.md` before final delivery.
3. Use the system `presentations` skill for PowerPoint creation, rendering, and QA. Follow its current requirements, including artifact-tool usage and rendered slide inspection.
4. Create a slide plan from the brief before authoring. The plan should decide the purpose, layout family, visual asset, content density, and speaker-facing notes for each slide.
5. Build the deck with AI-led design judgment:
   - Vary layout rhythm every 3-5 slides.
   - Use visual assets, screenshots, generated images, or meaningful diagrams where they clarify the business story.
   - Keep code slides sparse and legible; show only key snippets.
   - Do not use the legacy fixed script for final customer decks.
6. Render all slides, inspect the contact sheet and full-size previews, then revise before delivery.

## Inputs

The preferred input is `brief.md` at the skill root or a user-provided Markdown brief. If missing, create one from the user's request before generating the PPT.

The brief must capture:

- PPT title, customer, audience, duration, and use case.
- Business context and expected outcome.
- Content scope and source material.
- Visual references, brand assets, and useful image ideas.
- Page-level goals when known.
- Forbidden internal wording and visual anti-patterns.
- Acceptance criteria.

Use `brief.md` as a template. For a filled regression sample, see `examples/brief_lianbao_python_excel.md`.

## Assets

- `assets/yingdao_logo.png` is the default logo.
- Put reference decks, exported slide images, screenshots, and reusable illustrations under `assets/`.
- `assets/reference/` may include bad or good examples. Treat bad examples as anti-patterns, not as design templates.

## Legacy Tools

`yingdao_ppt_builder.py`, `postprocess_yingdao_ppt.py`, and `deck_config_*.json` are legacy helpers. They may be used only for quick structural drafts, format experiments, or compatibility checks. They must not be the default route for final customer-facing PPTs because they produce repetitive fixed layouts and weak visual judgment.

If a user explicitly asks to use the legacy generator, state that it is lower fidelity and proceed only for draft output.

## Delivery Requirements

- Final output must be a `.pptx`.
- Include the final PPTX path in the response.
- Mention any reference deck, image asset, generated visual, or source material used.
- Do not deliver before rendered-slide QA passes or known issues are disclosed.
