# QA Checklist

Use this checklist before delivering a PPT.

## Required Checks

- Render every slide to PNG.
- Inspect a montage/contact sheet for repeated layouts, missing images, and obvious hierarchy problems.
- Inspect full-size previews for code, tables, and dense slides.
- Run overflow/bounds checks when tooling is available.
- Fix unintended overlap, clipping, broken image links, and unreadable text.

## Visual Quality Checks

- The first slide should look like a formal customer presentation, not a generated worksheet.
- The deck should include meaningful visual assets when the topic benefits from them.
- Card grids should not dominate the deck.
- Code slides should be legible and sparse.
- Tables should be readable and not overused.
- Page rhythm should change across the deck.

## Content Checks

- The story should connect business context, method, and workflow closure.
- Each case should include business problem, data action, and output result.
- Visible slide text should be customer-facing.
- Any source material or generated image usage should be reflected in the final response.

## Legacy Warning

If the deck was produced by `yingdao_ppt_builder.py`, treat it as draft quality unless the user explicitly asked for the fixed generator. For final customer decks, use the presentations workflow and revise from rendered previews.
