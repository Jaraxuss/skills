# Slide Patterns and Anti-Patterns

Use this reference when planning page-level layouts.

## Structured Slide Plan

Before authoring, create a slide plan where every page has these fields:

| Field | Requirement |
| --- | --- |
| `role` | cover, setup, map, chapter, concept, case, process, comparison, table, code, summary, Q&A |
| `intent` | what the customer should understand, decide, or do after this slide |
| `key_points` | 3-5 concise customer-facing points |
| `layout_family` | title + hero, statement, visual process, comparison, case story, code + explanation, matrix, checklist |
| `visual_asset` | logo, screenshot, strict input asset, style reference, generated visual, diagram, table, icon |
| `density` | low, medium, or high; high must still be readable in slideshow mode |
| `local_context` | facts, fields, rules, terms, or examples this slide needs so it does not rely on hidden cross-slide context |
| `speaker_notes` | talk-track support only; never visible internal coaching language |

Use `deck_context` for concepts that multiple slides need: source summary, core claim, canonical terms, recurring business frame, and customer assumptions.

## Asset Roles

- `strict input asset`: must be visibly represented and preserve its labels, data, UI content, arrows, relationships, or business meaning.
- `style reference`: use only for palette, composition mood, density, texture, or visual hierarchy; do not copy private content.
- `generated visual`: create or source a business-relevant visual when no real screenshot exists; it must match the Yingdao red/white/pink identity.

## Recommended Patterns

- Cover: strong title, customer context, logo, one meaningful hero visual.
- Setup: one clear business tension or opportunity, minimal copy.
- Course map: structured route with 4-6 modules and business outcomes.
- Role split: compare Yingdao, Python/AI/API, and combined value with different visual weights.
- Case story: business problem, data action, output result, then workflow connection.
- Process: show flow from trigger to data processing to notification/archive.
- Code: show only core lines, with business interpretation beside it.
- Summary: decision guidance or action checklist.

## Rhythm Rules

- Change layout family every 3-5 slides.
- Avoid long runs of three-card slides.
- Avoid stacking table slides back to back unless they serve different purposes.
- Use section transitions for long decks.
- Alternate dense explanation slides with visual or statement slides.
- Keep one visual identity, but do not repeat one composition unless it is a deliberate sequence.
- If two adjacent pages share the same layout family, make the content relationship explicit in the slide plan.

## Lightweight Sample Gate

Default behavior is direct `.pptx` production after planning. Use a one-slide sample gate when:

- the deck is a high-value customer-facing deliverable;
- the requested style is ambiguous or depends on a reference deck/image;
- the user explicitly asks for polishing, premium output, or a less template-like result;
- the first generated/rendered pass shows a high risk of repeated composition.

The sample should be a representative content slide, not always the cover. Render and inspect it before using the same visual identity across the deck. Do not turn this into a hard approval chain unless the user asks for that workflow.

## Code Slides

- Show only the minimum snippet needed to explain the method.
- Make code secondary to the business point.
- Use callouts for inputs, rule, and output.
- If a code block becomes more than one-third of the slide, split it or simplify it.

## Bad Output Anti-Patterns

The screenshot in `assets/reference/bad_fixed_script_output.png` is an anti-pattern example:

- repeated card/code page structure
- code too small and not visually important
- missing business imagery
- weak hierarchy between business problem, result, and code
- mostly static white slides with repeated pale ring decoration
- low sense of customer-facing polish

Do not imitate that screenshot. Use it to identify what to avoid.
