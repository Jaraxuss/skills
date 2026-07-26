# QA Checklist

Use this checklist before delivering a PPT.

## Hard Gates（任一不过即返修，标准来自 `design-tokens.md`）

1. 无文字截断/溢出：卡片长句、表格单元格、流程 pill 逐个看；生成文本框必须开启 word wrap。
2. 可见文字 ≥ 9pt（12px@720p）；正文 ≥ 10pt。
3. 内容页底部 1/3 不得整体留白（封面/章节/大字页除外）。
4. 圆角 ≤ 14px；无默认灰投影（只允许 tokens 里的卡片/图像规范投影）。
5. 背景装饰不压任何内容；logo/标题系/页脚/页码位置逐页一致。
6. 色板合规：无蓝色主视觉图像、无大粉底表头、红色只做强调。
7. 同构版式不连续 ≥ 3 页；案例页有"运行结果"证据区；>10 页的 deck 有章节页。

## Required Checks

- Render every slide to PNG.
- Inspect a montage/contact sheet for repeated layouts, missing images, and obvious hierarchy problems.
- Inspect full-size previews for code, tables, and dense slides.
- Run overflow/bounds checks when tooling is available.
- Fix unintended overlap, clipping, broken image links, and unreadable text.
- Compare rendered slides against the structured slide plan: role, intent, key points, layout family, visual asset, and density should match or intentionally improve the plan.
- Check Chinese text for garbled characters, awkward line breaks, and unreadable small labels.
- Verify any `strict input asset` remains visibly represented and preserves required labels, data, UI content, arrows, or business meaning.

## Visual Quality Checks

- The first slide should look like a formal customer presentation, not a generated worksheet.
- The deck should include meaningful visual assets when the topic benefits from them.
- Card grids should not dominate the deck.
- Code slides should be legible and sparse.
- Tables should be readable and not overused.
- Page rhythm should change across the deck.
- The deck should keep one Yingdao visual identity while varying composition by slide role.
- White, Yingdao red, soft pink, dark gray, and black should remain the main palette.
- Full-slide image pages should not be used by default; editable text, tables, code, and diagrams should remain editable unless the user explicitly accepted image-only slides.

## Content Checks

- The story should connect business context, method, and workflow closure.
- Each case should include business problem, data action, and output result.
- Visible slide text should be customer-facing.
- Any source material or generated image usage should be reflected in the final response.
- Deck-level terms, field names, customer names, and recurring frameworks should stay consistent with `deck_context`.
- Slide-specific examples should be self-contained through `local_context`, not hidden assumptions from previous pages.
- Speaker notes may contain delivery cues, but visible pages must not contain internal coaching language.

## Delivery Evidence

Final response should report:

- source material used;
- reference deck/image or style reference used, if any;
- generated visuals or major assets used;
- rendered QA result, including overflow/bounds status when available;
- known limitations or disclosed issues, if any.

## Legacy Warning

If the deck was produced by `yingdao_ppt_builder.py`, treat it as draft quality unless the user explicitly asked for the fixed generator. For final customer decks, use the system `pptx` skill workflow and revise from rendered previews.
