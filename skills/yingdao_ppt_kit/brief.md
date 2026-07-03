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

## Page-Level Intent

If known, list target pages. The agent may adjust sequence and count when it improves the story.

| Slide | Purpose | Must Say | Suggested Visual |
| --- | --- | --- | --- |
| 1 | Cover | [literal customer-facing title] | [hero image / product screenshot / brand image] |
| 2 | Narrative setup | [why this matters] | [simple statement or visual contrast] |
| 3 | Map | [modules / route] | [timeline or structured map] |
| ... | ... | ... | ... |

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

## Acceptance Criteria

- First slide looks like a formal customer-facing presentation.
- Every case slide has business context and outcome, not just code.
- Layout rhythm changes across the deck.
- At least some slides use real or generated visual assets when appropriate.
- Rendered preview has no obvious overlap, clipping, unreadable text, or broken images.
