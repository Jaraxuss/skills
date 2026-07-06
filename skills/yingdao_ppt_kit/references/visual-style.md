# Yingdao Visual Style

Use this reference when designing the deck's look and feel.

## Style Brief

```json
{
  "type": "editable 16:9 customer-facing PowerPoint deck",
  "style_name": "Yingdao clean customer deck",
  "visual_direction": "clean, confident, practical customer presentation with warm white canvas, Yingdao red accents, soft pink atmosphere, and clear business hierarchy",
  "canvas": {
    "aspect_ratio": "16:9",
    "background": "white or near-white canvas, occasional soft pink atmosphere, never a heavy full-page red wash",
    "composition": "title zone, main idea zone, evidence/diagram zone, concise takeaway or workflow closure zone",
    "density": "medium by default; low for cover/setup/summary; high only for readable tables or matrices"
  },
  "color_palette": {
    "primary": "Yingdao red for accents, section markers, key arrows, highlights",
    "secondary": "soft pink for atmosphere, light cards, backgrounds, and subtle emphasis",
    "neutral": "black, dark gray, warm light gray, white",
    "semantic": "use green, amber, or blue only for specific meanings such as success, warning, or stages",
    "rule": "maintain the red/white/pink Yingdao identity; do not import external blue/green/retro/handmade palettes as the main theme"
  },
  "typography": {
    "title": "large clear sans-serif, customer-facing, strong hierarchy",
    "body": "readable sans-serif, short business sentences, enough line spacing",
    "labels": "small labels are allowed only when still readable in slideshow mode",
    "code": "large enough to read; only key snippets; business interpretation has higher visual priority than complete scripts"
  },
  "layout_patterns": [
    "cover with hero visual and customer context",
    "business tension statement with minimal copy",
    "course or solution route map",
    "role split comparison with unequal visual weights",
    "case story: problem, rule/action, output, workflow closure",
    "process or automation loop",
    "decision matrix or action checklist"
  ],
  "image_treatment": {
    "generated_visuals": "business-practical illustrations or scenes that match the red/white/pink palette and do not look like generic stock art",
    "screenshots": "use for concrete UI/process inspection; preserve legibility and business meaning",
    "reference_decks": "treat as style references unless the user explicitly asks to reuse content",
    "strict_input_assets": "preserve labels, data, UI, arrows, relationships, and business meaning"
  },
  "rendering_constraints": [
    "The deck should feel like formal customer material, not a worksheet or code notebook.",
    "Use one visual identity across the deck, but vary composition by slide role.",
    "Do not let repeated card grids dominate the deck.",
    "Do not use full-slide image pages by default; keep PPT objects editable unless requested otherwise.",
    "No unrelated logos, watermarks, or off-brand color systems."
  ]
}
```

## Core Feel

- Customer-facing, clean, confident, practical.
- White or near-white canvas with soft red/pink atmosphere.
- Yingdao red is an accent, not a full-page wash.
- Black and dark gray carry most text.
- Use restrained borders, soft shadows, and rounded corners only when they frame useful content.
- Borrow structure from external style systems only; do not borrow their primary palette when it weakens Yingdao identity.

## Composition

- Prefer one strong composition per slide over many equal boxes.
- Use full-slide visual hierarchy: title, main idea, supporting evidence, footer.
- Keep one global visual identity while varying composition by page role.
- Vary silhouettes across the deck:
  - title + hero visual
  - statement slide
  - visual process
  - comparison table
  - case story with screenshot or illustration
  - code snippet with business explanation
  - summary/decision slide
- Keep margins consistent and generous.

## Visual Assets

- Use `assets/yingdao_logo.png` for brand presence.
- Use generated or sourced bitmap images for conceptual business scenes when no product screenshot exists.
- Use screenshots or real UI/process images when the slide needs concrete inspection.
- Classify assets as `strict input asset`, `style reference`, or `generated visual` before production.
- Preserve strict input assets: do not redraw, relabel, invent replacement data, or crop away the required business meaning.
- Treat reference decks/images as visual inspiration unless content reuse is explicitly requested.
- Do not reuse the same non-background image across many slides.
- When adding a code slide, consider pairing a small code snippet with a business-result visual.

## Typography

- Titles should be clear and presentation-scale.
- Body text should be readable in slideshow mode.
- Do not shrink text to fit; shorten copy or split the slide.
- Code must be large enough to read and limited to the essential lines.

## Palette

- Background: white / near-white.
- Accent: Yingdao red and soft pink.
- Support: warm light gray, dark gray, black.
- Use other colors only for semantic meaning, such as success/warning/process stages.
- Never migrate an external style library's blue/green/retro/handmade palette into the main theme.
