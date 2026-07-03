# Yingdao PPT Kit

This skill now uses a Markdown creative brief as the primary input for high-quality Yingdao-style customer PPT generation.

## Recommended Workflow

1. Copy `brief.md` and fill in the customer, audience, content scope, visual direction, page intent, and acceptance criteria.
2. Ask Codex to use this skill and the filled brief to create a `.pptx`.
3. Codex should use the `presentations` workflow to plan, design, build, render, inspect, and revise the deck.
4. Final decks should use AI-led layout and visual judgment, not fixed Python layouts.

## Reference Files

- `references/visual-style.md`: Yingdao visual language.
- `references/slide-patterns.md`: page patterns, rhythm rules, and anti-patterns.
- `references/customer-copy.md`: customer-facing copy rules.
- `references/qa-checklist.md`: rendering and quality checks.
- `examples/brief_lianbao_python_excel.md`: filled regression brief for the 合肥联宝 Python/Excel training deck.

## Assets

- `assets/yingdao_logo.png`: default logo.
- `assets/reference/bad_fixed_script_output.png`: anti-pattern example showing why the old fixed script route should not be used for final customer decks.

## Legacy Tools

The original files remain for compatibility:

- `yingdao_ppt_builder.py`
- `postprocess_yingdao_ppt.py`
- `deck_config_*.json`

These are draft/legacy helpers only. They are acceptable for quick structure experiments or compatibility checks, but not for final customer-facing PPT quality.
