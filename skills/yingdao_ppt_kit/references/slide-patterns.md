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

## Asset Tiers

图库按用途分三层，选图先定层。数值规范和复用上限见 `references/design-tokens.md`，逐图索引见 `assets/manifest.json`。

| Tier | 用途 | 行业相关性 | 能否铺底 |
| --- | --- | --- | --- |
| `atmosphere` | halfbleed 章节页的左侧底纹、声明页、收尾 | 无 | 是（配 `scrim-wash`，勿重压） |
| `hero` | 封面主视觉、halfbleed 出血主图 | 强 | 是（`scrim-left`） |
| `concept` | 案例页配图、流程页示意、halfbleed 出血主图 | 中 | **否**（不能当文字背景） |

选图时问三个问题：这页需要氛围还是需要信息？（氛围 → atmosphere，信息 → concept）文字压在图上吗？（是 → 查 manifest 的 `safe_text_zone` 决定文字放哪侧）这张图这个 deck 用过几次了？（查 tier 的复用上限）

`concept` 层不能当文字背景：这几张是信息量大的插画，靠小元素承载意义，压上蒙版会糊成色块。它们可以独占图区（案例页右侧、`divider-halfbleed` 的出血主图）。它们也带行业道具（仓储、叉车），跨行业复用前先查 manifest 的 `industry` 字段。

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
- 章节页有两种变体（`divider-split` 左文 + 右侧圆角卡片图 / `divider-halfbleed` 右侧图三边出血），多于两张章节页时交替使用。
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

`assets/reference/bad/` 里是固定脚本产物的真实反例：

- `builder_cards_truncated-04.png`：卡片文字被截断、药丸式巨圆角、卡片下半截空白、默认灰投影。
- `builder_codecase_unbalanced-08.png`：代码面板下半截全空、左轻右重、裸文字流程收尾、粉色圆环带阴影压在内容后面。

共性问题：repeated card/code page structure、missing business imagery、weak hierarchy、repeated pale ring decoration、low customer-facing polish。

Do not imitate these screenshots. Use them to identify what to avoid; the positive baseline is `assets/reference/good/`.
