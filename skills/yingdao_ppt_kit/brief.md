# Yingdao Customer PPT Creative Brief

Use this file as the standard input contract for customer-facing Yingdao-style PPT generation. Replace bracketed text before generation.

## Basic Info

- Title: [PPT title]
- Customer: [customer name and department]
- Audience: [roles and knowledge level]
- Duration: [training/report duration]
- Use case: [customer training / sales presentation / delivery plan / project recap / scenario co-creation]
- Output filename: [desired .pptx filename]

## Business Context

- [What has already happened?]
- [Why does this deck exist now?]
- [What should the audience understand or decide after the deck?]
- [What customer-specific industry/process context matters?]

## Deck Context

Use this section to make cross-slide context explicit. Do not rely on later slides understanding "the previous framework" or "the above example" without restating the needed facts.

- Source summary: [one-paragraph summary of the source material]
- Core claim: [the central message this deck should keep reinforcing]
- Canonical terms: [approved Chinese/English terms, product names, process names, field names]
- Audience assumptions: [what the audience already knows and what must be explained]
- Reusable business frame: [input / rule / output / owner / workflow closure, or another frame used across slides]

## Goals

1. [Goal 1]
2. [Goal 2]
3. [Goal 3]

## Content Scope

Use these modules as the content boundary:

- [Module 1]
- [Module 2]
- [Module 3]
- [Module 4]
- [Module 5]

Source material:

- [Paste or link source notes, Markdown outline, meeting notes, reference docs, or prior deck paths.]

## Visual Direction

- Brand feel: clean, confident, customer-facing, business-practical.
- Palette: white canvas, Yingdao red accents, soft pink atmosphere, restrained gray/black text.
- Logo: use `assets/yingdao_logo.png` unless another logo is supplied.
- Visual assets to consider: [screenshots / generated illustrations / process diagrams / reference deck pages / product UI].
- Reference deck or images: [paths, if any].
- Style identity rule: keep one Yingdao visual identity across the deck, but vary composition by slide role.
- Optional sample gate: [not needed / generate and render one representative sample slide before full deck].

## Asset Map

Classify supplied or generated assets before production.

| Asset | Type | Role | Fidelity Requirement | Target Slide |
| --- | --- | --- | --- | --- |
| [path or description] | strict input asset | [must appear as evidence/content] | [preserve labels/data/UI/business meaning] | [slide number or purpose] |
| [path or description] | style reference | [visual inspiration only] | [match palette/composition mood; do not copy content] | [deck-level or slide-specific] |
| [image idea] | generated visual | [business scene / process metaphor / hero visual] | [must match Yingdao palette and customer-facing tone] | [slide number or purpose] |

## Structured Slide Plan

If known, list target pages. The agent may adjust sequence and count when it improves the story. Each page should be self-contained enough for another agent to implement without guessing the hidden context.

| Slide | Role | Intent | Key Points | Layout Family | Visual Asset | Density | Local Context / Speaker Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cover | [open the customer story] | [literal customer-facing title; customer context] | title + hero visual | [hero image / product screenshot / brand image] | low | [opening talk track or source reminder] |
| 2 | setup | [explain why this matters now] | [business tension; expected outcome] | statement or contrast | [business scene / process contrast] | low-medium | [customer-specific context] |
| 3 | map | [show route and modules] | [modules; business outcomes] | timeline / route map | [icons / step map] | medium | [how to introduce the route] |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Customer-Facing Copy Rules

- Visible slide text must be suitable for direct customer display.
- Prefer short business sentences over internal teaching notes.
- Avoid these phrases unless the user explicitly asks for speaker notes:
  - "不要讲成纯编程课"
  - "这里只讲基础认知"
  - "业务人员只需要知道"
  - "这页给讲师提示"
  - "先把学员预期摆正"
  - "AI味道很重的说明性措辞"

## Visual Anti-Patterns

- Do not repeat the same card layout across most slides.
- Do not make code blocks dominate the deck.
- Do not use tiny code or dense tables that cannot be read in slideshow mode.
- Do not rely only on text boxes; add meaningful visuals where they help.
- Do not leave large empty containers with one short sentence.
- Do not default to full-slide image PPT unless the user explicitly accepts non-editable slides.
- Do not copy the color systems from external style libraries if they weaken the Yingdao red/white/pink identity.

## Acceptance Criteria

- First slide looks like a formal customer-facing presentation.
- Every case slide has business context and outcome, not just code.
- Layout rhythm changes across the deck.
- At least some slides use real or generated visual assets when appropriate.
- Rendered preview has no obvious overlap, clipping, unreadable text, or broken images.
- Slide content matches the structured slide plan, or deviations are intentional and improve the story.
- Required `strict input asset` items are visibly preserved and not replaced by approximate redraws.
- Final response reports source material, visual assets, rendered QA result, and known limitations.
