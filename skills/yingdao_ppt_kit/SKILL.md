---
name: yingdao-ppt-kit
description: Create or improve high-quality Yingdao-style customer-facing PowerPoint decks from creative briefs, project materials, or existing PPTX files. Use for Yingdao/RPA customer training, sales, delivery, project recaps, and scenario co-creation when polished AI-led visuals, editable slides, rendered QA, or direct-readable presenter notes are needed. By default add approximately two-minute speaker notes for every main slide with a natural next-slide transition; disable talk tracks only when the user explicitly asks for no notes. Use NotebookLM only when the user explicitly requests it. / 基于创意简报、项目资料或现有 PPTX 创建或优化影刀风格对客 PPT；默认给每个主汇报页添加约两分钟、可直接朗读并带下一页衔接的讲解备注，除非用户明确不要备注。NotebookLM 仅在用户主动要求时使用。
---

# Yingdao PPT Kit

Use this skill to create polished Yingdao-style customer PPTs from a Markdown creative brief.

用这个 Skill 生成影刀风格的对客 PPT。`brief.md` 是内容与意图契约；AI 必须做 slide-level 视觉判断，而不是把文字填进固定模板。

## Trigger / When to Use

Use this skill when the task is to create or improve a customer-facing Yingdao/RPA PowerPoint deck from Markdown, a course outline, project notes, a creative brief, or an existing PPTX. Generate direct-readable speaker notes by default.

当用户要基于 Markdown、课程大纲、项目资料或创意简报生成/优化影刀或 RPA 相关对客 PPT 时，使用本 Skill。

Typical triggers:

- English: "Use the Yingdao PPT kit to create a customer training deck from this Markdown."
- English: "Make this RPA deck more polished and less template-like."
- 中文：使用这个 Skill，帮我基于上传的培训规划生成 PPT。
- 中文：不要固定脚本那种重复卡片风格，按影刀对客材料的审美重新做。

## Steps

1. 先读取 `brief.md`。如果用户提供了其他 Markdown 文件，把它当作 brief 使用；如果没有 brief，先从用户需求整理出一份临时 brief。
2. 按任务需要读取 reference files，不要一次性加载无关资料：
   - `references/design-tokens.md` REQUIRED before authoring any slide: numeric spec for palette, type scale, furniture, components, page compositions, and QA hard gates. 样张见 `assets/reference/good/`（PNG 看效果，HTML 抄结构数值）。
   - `references/visual-style.md` for Yingdao visual language.
   - `references/slide-patterns.md` for page types, rhythm, and anti-patterns.
   - `references/customer-copy.md` for customer-facing wording rules.
   - `references/speaker-notes.md` REQUIRED unless the user explicitly requests no talk track: note schema, pacing, transition rules, context policy, and PPTX write routes.
   - `references/qa-checklist.md` before final delivery.
3. 使用系统 `pptx` skill（PowerPoint 系统技能，pptxgenjs 生成路线；旧版文档称 `presentations`）创建 PowerPoint，并遵守其要求，包括 rendered slide inspection 和 QA。本 skill 的 design tokens 与系统 skill 的通用设计建议冲突时，以 design tokens 为准（影刀品牌语言允许红竖条标题、卡片左色条等元素）。
4. 先输出内部 structured slide plan，再开始制作。每页都要明确：
   - `role`：cover、chapter、case、process、comparison、table、code、summary 等。
   - `intent`：这页帮助客户理解、判断或行动什么。
   - `key points`：3-5 条客户可见信息，不写内部备课话术。
   - `layout family`：图文页、流程页、矩阵页、案例页、代码页、信息图等。
   - `visual asset`：logo、截图、generated image、业务流程图、表格、图标；标注 `strict input asset` 或 `style reference`。
   - `density`：low / medium / high，客户现场可读，不把讲稿塞进页面。
   - `note_role`：opening、explanation、case、decision、closing 或 appendix。
   - `note_context`：本页需要解释的背景、事实、限制和客户关注点。
   - `target_seconds`：主汇报页默认 120 秒；附录按需讲解。
   - `transition_intent`：下一页衔接要完成的逻辑动作；最终主汇报页写收束或请示。
   - `sources`：本页使用的事实与资产来源。
   - `is_appendix`：是否属于按需讲解页面。
   - `local_context`：把本页需要的字段、规则、案例背景写清楚，避免引用“上页/上面那个框架”这类隐式上下文。
5. 生成备注，默认让每张主汇报页具备可直接朗读的正文和下一页衔接。只在用户明确说“不需要备注”“不要讲稿”或“只制作页面”时关闭讲稿与衔接；外部来源的 `[Sources]` 仍按系统 `pptx` skill 要求保留。未被用户主动提及的 NotebookLM 不得查询、引用或列为缺失项。
6. 用 AI-led design judgment 制作 deck：
   - 所有数值（字号、边距、圆角、投影、色值、家具位置）按 `references/design-tokens.md` 执行；judgment 用在构图选择、密度分配和资产选择上。
   - 每 3-5 页改变一次视觉节奏；超过 10 页的 deck 每 4-5 个内容页插一张章节页。章节页有 `divider-split`（左文右图，样张 `slide_b_divider`）和 `divider-halfbleed`（右侧图三边出血 + 左侧 atmosphere 底纹）两种变体，多于两张时交替使用。
   - 主动使用 `assets/atmosphere/` 铺底图、`assets/concept/` 示意图、screenshots、generated images、diagrams 或 infographic；封面必须有 hero 视觉。
   - 代码页只展示关键片段（≤12 行），保证字号和业务解释层级。
   - 业务案例页要先讲业务问题，再讲处理规则和输出结果，并带"运行结果示意"证据区（见样张 `slide_c_case`）。
7. 用系统 `pptx` skill 的 Artifact Tool 写入新建或正常导入 deck 的 `slide.speakerNotes`，再通过 `presentation.inspect({ kind: "notes" })` 回读。对于必须原样保留视频、音频、OLE 或其他嵌入对象的现有 PPTX，改用 `scripts/patch_speaker_notes.mjs` 做 notes-only OOXML patch；该路径不依赖 AppleScript。
8. 按需使用 lightweight sample gate：默认可直接生成 `.pptx`；当材料是高价值客户交付、风格方向不明确，或用户明确要求精修时，先生成并渲染 1 页代表性样张确认视觉身份，再扩展到全 deck。
9. 生成后必须 render all slides，查看 contact sheet 和 full-size previews；发现重叠、越界、中文乱码、文字过小、图片缺失、strict input asset 未正确使用或页面重复感时，先返修再交付。完成 `references/qa-checklist.md` 的 notes checks，并回读每页备注。

## Inputs / 输入

首选输入是 skill 根目录的 `brief.md`，或用户提供的 Markdown brief。缺失时，先根据用户请求整理 brief，再生成 PPT。

The brief must capture:

- PPT title, customer, audience, duration, and use case.
- Business context and expected outcome.
- Deck-level context: source summary, core claim, canonical terms, and constraints that multiple slides need.
- Content scope and source material.
- Visual references, brand assets, useful image ideas, and asset roles (`strict input asset` vs `style reference`).
- Page-level goals and structured slide plan fields when known.
- Optional `speaker_notes` configuration. If omitted, use the defaults in `references/speaker-notes.md`.
- Forbidden internal wording and visual anti-patterns.
- Acceptance criteria.

Use `brief.md` as a template. For a filled regression sample, see `examples/brief_lianbao_python_excel.md`.

## Rules

- MUST 优先使用 Markdown creative brief + AI-led slide planning 路线。
- MUST 使用系统 `pptx` skill 生成、渲染并检查最终 `.pptx`。
- MUST 遵守 `references/design-tokens.md` 的数值规范与 QA 硬门槛：无文字截断、可见文字 ≥9pt、内容页底部 1/3 不整体留白、圆角 ≤14px、无默认灰投影、装饰不压内容、家具位置逐页一致。
- MUST 默认生成可编辑 PowerPoint 页面，保留文本、表格、代码、流程图等对象的可维护性。
- MUST 保持影刀主视觉身份：白底、影刀红、柔粉氛围、深灰/黑文字；外部风格只借鉴结构，不迁移主色。
- MUST 让同一 deck 拥有一致 visual identity，但按页面语义改变 composition。
- MUST 在 slide plan 中显式写出 `deck_context` 和必要的 `local_context`。
- MUST 区分 `strict input asset` 和 `style reference`；严格输入资产需要保留内容、标签、数据关系或业务含义。
- MUST 让页面文字面向客户可直接展示，避免内部备课语、提示语和 AI 味说明。
- MUST 让每个核心知识点对应业务例子、业务流程或输出结果。
- MUST 默认生成每个主汇报页的 direct-readable speaker notes，目标约 120 秒，并使用空行、`----`、空行分隔正文与下一页衔接话术；最后一个主汇报页改用会议收束或领导请示。
- MUST 让备注补充页面未呈现的背景、价值、边界和决策信息，而不是逐字朗读页面；不得把内部制作提示写入讲稿。
- MUST 只在用户明确请求时使用 NotebookLM；默认上下文是用户提供的 brief、PPT、附件、需求表和会议材料。
- MUST 对已有严格媒体资产的 PPTX 使用 `scripts/patch_speaker_notes.mjs`，并检查媒体、嵌入对象与备注映射。
- REQUIRED 在交付前完成 rendered-slide QA；若仍有问题，必须明确披露。
- NEVER 把 `yingdao_ppt_builder.py` 作为客户版最终 PPT 的默认生成路线。
- NEVER 默认制作 full-slide image PPT，除非用户明确接受不可编辑图片页。
- NEVER 引入硬性 outline approval、sample approval 或 mandatory subagent 流水线；样张确认只作为增强流程。
- NEVER 让整套 deck 都是重复卡片、重复代码框或单一配色节奏。
- NEVER 在代码页堆满完整脚本；只展示关键 snippet，并配业务解释。
- NEVER 把 source material 原文大段搬到页面上。
- NEVER 因为备注信息不足而补造客户事实、运行成果、量化收益、领导观点或项目承诺。

## Assets / 资产

- `assets/yingdao_logo.png` 是默认 logo。
- `assets/manifest.json` 是图库索引，**选图前先读它**：每张图记录了 tier、适用页型、推荐蒙版、行业倾向、安全文字区（文字该放哪一侧）、复用上限。文件末尾的 `gaps` 字段列出已知缺口。
- 图库按用途分三层，不按行业铺矩阵：
  - `assets/atmosphere/` 氛围底图（4 张，行业中性）：halfbleed 章节页的左侧底纹、声明页、收尾。均为人工筛选的生成图，构图语义见 manifest；本身很淡，只配轻蒙版。
  - `assets/hero/` 封面主视觉、halfbleed 出血主图：行业相关，目前只有行业中性的 `hero_office_generic`。
  - `assets/concept/` 概念示意图（4 张）：案例页配图、流程页示意、halfbleed 出血主图。**不能当文字背景**，且带制造/物流道具，跨行业前查 manifest。
- `assets/reference/good/` 是四张定稿样张（封面/章节/案例/总结，PNG+HTML）。制作前先看，风格对齐它们。
- `assets/reference/bad/` 是固定脚本产物的反例截图（文字截断、药丸圆角、空白失衡）。只作为 anti-patterns，不作为设计模板。

### 工具脚本

- `scripts/duotone.js`：把任意来源的图片映射成红白粉调，入库前跑一遍。图源因此不必自带品牌配色。
- `scripts/patch_speaker_notes.mjs`：对现有 `.pptx` 进行跨平台 notes-only OOXML 更新，适用于需严格保留媒体或嵌入对象的 deck。格式、JSON 契约和验证要求见 `references/speaker-notes.md`。

```bash
node scripts/duotone.js <输入图> <输出图> --tier atmosphere|hero|concept

node scripts/patch_speaker_notes.mjs --input <source.pptx> --output <target.pptx> --notes <notes.json> --verify
```

## Legacy Tools

`yingdao_ppt_builder.py`, `postprocess_yingdao_ppt.py`, and `deck_config_*.json` are legacy helpers.

它们只适合 quick structural drafts、format experiments 或 compatibility checks。不得作为 final customer-facing PPT 的默认路线，因为固定脚本容易生成重复布局、弱视觉判断和过密文字。

如果用户明确要求使用 legacy generator，先说明它的 fidelity 较低，再只按 draft output 处理。

## Examples

### English Example

User request:

```text
Use the Yingdao PPT kit to create a polished customer training deck from this Markdown outline. The audience is supply chain business users, and the deck should avoid repetitive template cards.
```

Expected approach:

1. Treat the Markdown outline as the brief.
2. Read relevant reference files, especially `visual-style.md`, `slide-patterns.md`, and `customer-copy.md`.
3. Create a slide plan before authoring.
4. Build with the system `pptx` skill, following `references/design-tokens.md`, picking images from `assets/manifest.json` by tier, or generating new ones.
5. Render, inspect, revise, then deliver `.pptx`.

### 中文示例

用户请求：

```text
使用这个 Skill，帮我基于合肥联宝第二天 Python 数据处理培训规划生成一份对客 PPT。受众是供应链业务人员，风格要比固定脚本生成的版本更完整、更有图片和业务感。
```

处理方式：

1. 将培训规划 Markdown 作为 brief。
2. 先规划 12-18 页 slide plan，覆盖定位、能力分工、数据结构、Pandas / NumPy、业务案例和闭环总结。
3. 每页写明 `role / intent / key points / layout family / visual asset / density / local_context`，不套同一种卡片模板。
4. 案例页突出业务问题、处理规则、输出结果；代码页只放关键 snippet。
5. 渲染检查后再交付 `.pptx`。

## Delivery Requirements / 交付要求

- Final output must be a `.pptx`.
- Include the final PPTX path in the response.
- Mention source material, reference deck, image asset, generated visual, rendered QA result, and known limitations if any.
- State that direct-readable speaker notes were added by default, or that the user explicitly opted out. When an OOXML patch route is used, report the media-preservation verification result.
- Do not deliver before rendered-slide QA passes or known issues are disclosed.
