---
name: yingdao-ppt-kit
description: Create high-quality Yingdao-style customer-facing PowerPoint decks from Markdown creative briefs, using AI-led slide planning, visual judgment, assets, rendering, and QA instead of fixed script templates. Use when Codex needs to make customer training, sales, delivery, project recap, or scenario co-creation PPTs for Yingdao/RPA topics, especially when the user provides Markdown source material, asks for a brief.md workflow, wants AI-led aesthetics, references Yingdao-style PPTs, or wants to avoid repetitive JSON/python-pptx output. / 基于 Markdown 创意简报生成高质量影刀风格对客 PPT，通过 AI 逐页规划版式、视觉资产、信息密度、渲染和 QA，而不是套固定脚本模板。适用于影刀/RPA 相关的客户培训、售前汇报、交付复盘、项目总结和场景共创材料，尤其是用户提供 Markdown 资料、要求 brief.md 工作流、希望 AI 做审美判断、参考影刀风格样张，或明确不想要重复的 JSON/python-pptx 脚本产物时。
---

# Yingdao PPT Kit

Use this skill to create polished Yingdao-style customer PPTs from a Markdown creative brief.

用这个 Skill 生成影刀风格的对客 PPT。`brief.md` 是内容与意图契约；AI 必须做 slide-level 视觉判断，而不是把文字填进固定模板。

## Trigger / When to Use

Use this skill when the task is to create or improve a customer-facing Yingdao/RPA PowerPoint deck from Markdown, a course outline, project notes, or a creative brief.

当用户要基于 Markdown、课程大纲、项目资料或创意简报生成/优化影刀或 RPA 相关对客 PPT 时，使用本 Skill。

Typical triggers:

- English: "Use the Yingdao PPT kit to create a customer training deck from this Markdown."
- English: "Make this RPA deck more polished and less template-like."
- 中文：使用这个 Skill，帮我基于上传的培训规划生成 PPT。
- 中文：不要固定脚本那种重复卡片风格，按影刀对客材料的审美重新做。

## Steps

1. 先读取 `brief.md`。如果用户提供了其他 Markdown 文件，把它当作 brief 使用；如果没有 brief，先从用户需求整理出一份临时 brief。
2. 按任务需要读取 reference files，不要一次性加载无关资料：
   - `references/visual-style.md` for Yingdao visual language.
   - `references/slide-patterns.md` for page types, rhythm, and anti-patterns.
   - `references/customer-copy.md` for customer-facing wording rules.
   - `references/qa-checklist.md` before final delivery.
3. 使用系统 `presentations` skill 创建 PowerPoint，并遵守其当前要求，包括 `artifact-tool`、rendered slide inspection 和 QA。
4. 先输出内部 slide plan，再开始制作。每页都要明确：
   - 页面目标：cover、chapter、case、process、comparison、table、code、summary 等。
   - layout family：图文页、流程页、矩阵页、案例页、代码页、信息图等。
   - visual asset：logo、截图、生成图片、业务流程图、表格或图标。
   - information density：客户现场可读，不要把讲稿塞进页面。
   - speaker notes：只放讲解辅助，不把内部提示写到画面上。
5. 用 AI-led design judgment 制作 deck：
   - 每 3-5 页改变一次视觉节奏。
   - 主动使用 visual assets、screenshots、generated images、diagrams 或 infographic。
   - 代码页只展示关键片段，保证字号和业务解释层级。
   - 业务案例页要先讲业务问题，再讲处理规则和输出结果。
6. 生成后必须 render all slides，查看 contact sheet 和 full-size previews；发现重叠、越界、文字过小、图片缺失或页面重复感时，先返修再交付。

## Inputs / 输入

首选输入是 skill 根目录的 `brief.md`，或用户提供的 Markdown brief。缺失时，先根据用户请求整理 brief，再生成 PPT。

The brief must capture:

- PPT title, customer, audience, duration, and use case.
- Business context and expected outcome.
- Content scope and source material.
- Visual references, brand assets, and useful image ideas.
- Page-level goals when known.
- Forbidden internal wording and visual anti-patterns.
- Acceptance criteria.

Use `brief.md` as a template. For a filled regression sample, see `examples/brief_lianbao_python_excel.md`.

## Rules

- MUST 优先使用 Markdown creative brief + AI-led slide planning 路线。
- MUST 使用系统 `presentations` skill 生成、渲染并检查最终 `.pptx`。
- MUST 让页面文字面向客户可直接展示，避免内部备课语、提示语和 AI 味说明。
- MUST 让每个核心知识点对应业务例子、业务流程或输出结果。
- REQUIRED 在交付前完成 rendered-slide QA；若仍有问题，必须明确披露。
- NEVER 把 `yingdao_ppt_builder.py` 作为客户版最终 PPT 的默认生成路线。
- NEVER 让整套 deck 都是重复卡片、重复代码框或单一配色节奏。
- NEVER 在代码页堆满完整脚本；只展示关键 snippet，并配业务解释。
- NEVER 把 source material 原文大段搬到页面上。

## Assets / 资产

- `assets/yingdao_logo.png` 是默认 logo。
- 把 reference decks、exported slide images、screenshots、reusable illustrations 放在 `assets/`。
- `assets/reference/` 可以存放 good / bad examples。Bad examples 只作为 anti-patterns，不作为设计模板。

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
4. Build with `presentations` and `artifact-tool`, using visual assets or generated images where useful.
5. Render, inspect, revise, then deliver `.pptx`.

### 中文示例

用户请求：

```text
使用这个 Skill，帮我基于合肥联宝第二天 Python 数据处理培训规划生成一份对客 PPT。受众是供应链业务人员，风格要比固定脚本生成的版本更完整、更有图片和业务感。
```

处理方式：

1. 将培训规划 Markdown 作为 brief。
2. 先规划 12-18 页 slide plan，覆盖定位、能力分工、数据结构、Pandas / NumPy、业务案例和闭环总结。
3. 每页选择合适的 layout family，不套同一种卡片模板。
4. 案例页突出业务问题、处理规则、输出结果；代码页只放关键 snippet。
5. 渲染检查后再交付 `.pptx`。

## Delivery Requirements / 交付要求

- Final output must be a `.pptx`.
- Include the final PPTX path in the response.
- Mention any reference deck, image asset, generated visual, or source material used.
- Do not deliver before rendered-slide QA passes or known issues are disclosed.
