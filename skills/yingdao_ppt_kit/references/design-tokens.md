# Yingdao Design Tokens（数值规范）

这是影刀对客 PPT 的数值化设计规范。Agent 做逐页构图判断时，所有"多大、多粗、什么色、放哪里"的问题先查这里，不要凭感觉发挥。视觉基准样张见 `assets/reference/good/`（PNG 为效果、同名 HTML 为可抄的结构与数值来源）。

## 基准画布与换算

- 画布：16:9，13.333 × 7.5 in。
- 本文件所有 px 数值基于 1280 × 720 px 画布（96dpi）。
- 换算：`in = px / 96`；`pt = px × 0.75`。
- pptxgenjs 用 in 与 pt：例如 96px 边距 = 1.0 in；31px 标题 ≈ 23pt。

## 色板（唯一允许的主色板）

| Token | Hex | 用途 |
| --- | --- | --- |
| red | `F0263C` | 品牌红：徽章、标题竖条、当前项、页码、强调词 |
| red-deep | `C9202F` | 深红：流程条文字、表格红字、代码关键字 |
| pink-1 | `FFF3F5` | 浅粉：流程 pill 底、结论带底 |
| pink-2 | `FFE4E9` | 粉：图标 chip 底、表头下划线 |
| ink | `17181C` | 标题、卡片标题 |
| body | `565B63` | 正文 |
| muted | `8A8F98` | 次要说明、代码注释 |
| faint | `B7BCC4` | 页脚 slogan、装饰性文字 |
| line | `F2D8DC` | 粉色描边（流程 pill、结论带） |
| card-border | `F1E3E6` | 卡片描边 |
| table-line | `F1F2F4` | 表格行线 |
| code-bg | `FFF9FA` / 头部 `FDEFF1` / 边 `F4DCE0` | 代码面板 |

语义色只在有语义时用：成功 `1E7A44` on `EDF7F0`；Python/深色标签 `2B2D33`。禁止引入蓝色系主视觉（包括生成图里的蓝色机械风）。

## 字体

- Windows 放映环境（客户现场默认）：微软雅黑；macOS：苹方 PingFang SC。pptxgenjs 里写 `Microsoft YaHei`，标题用 bold。
- 代码：Menlo / Consolas；中文注释会回退中文字体，属正常。
- 渲染 QA 时注意 LibreOffice/预览环境的字体替换可能造成宽度偏差，文本容器留 ~10% 余量。

## 字号阶梯（px @1280×720 → pt）

| 元素 | px | ≈pt | 字重 |
| --- | --- | --- | --- |
| 封面主标题 | 50 | 38 | bold |
| 封面 eyebrow | 22 | 16 | semibold |
| 章节页大标题 | 44 | 33 | bold |
| 内容页标题 | 31 | 23 | bold |
| 红色副标题 | 15.5 | 12 | semibold |
| 卡片标题 | 16.5 | 12.5 | semibold |
| 正文/卡片正文 | 13.5–14.5 | 10.5–11 | regular |
| 表格正文 | 14.5 | 11 | regular |
| 流程 pill | 14–14.5 | 10.5–11 | semibold |
| 代码 | 12.5 | 9.5 | regular（行距 1.6） |
| 页脚 slogan | 11–12 | 8.5–9 | regular |
| 页码 | 12.5 | 9.5 | semibold |

硬下限：任何可见文字 ≥ 12px（9pt）；正文 ≥ 13.5px（10pt）。到不了就删文案或拆页，不准缩字号。

## 版面家具（每页固定，位置不许漂移）

- logo：右上，`top:38px, right:48px, height:26px`（封面 30px）。用 `assets/yingdao_logo.png`。
- 标题块：`left:96px, top:64px`；红竖条 `6×34px, radius:3px`，在标题左侧 22px 处；红副标题在标题下 9px。
- 页脚 slogan：`left:96px, bottom:22–34px`，faint 色，"From human doing to human being."
- 页码：`right:52px, bottom:28px`，red 色 semibold。
- 页边距：内容主区左右 96px；图像/装饰允许到 72px；内容底界 ≈ 620px（流程条区之上）。

## 背景（每个内容页都要有，禁止纯白裸奔）

- 棱镜纹理：1–2 条大三角描边，`#17181C` @ 2.5–3.5% 不透明度，stroke 1.5px。
- 品牌圆环：右上角描边圆，`F0263C` @ 4.5–5%，stroke 22–26px，允许出血到画布外。
- 粉晕：`radial-gradient(560–620px at 94% 6–8%, rgba(240,38,60,.05–.07), transparent 70%)`。
- 装饰永远压在内容层之下，禁止投影，禁止盖住任何文字或表格。

## 组件规格

### 卡片
圆角 12px；描边 1px card-border；投影 `0 6px 18px rgba(23,24,28,.05)`（≈ pptxgenjs `shadow:{type:"outer", angle:90, offset:3, blur:9, color:"17181C", opacity:0.08}`，注意 shadow 对象不能复用，每次新建）；内边距 16–18px。卡片高度按内容定，禁止拉高卡片留大片空底。

### 流程条（pill 链）
pill：`radius:999px, padding:9–10px 20–22px`，底 pink-1、描边 1px line、文字 red-deep semibold；当前/收尾项：底 red、文字白。连接符用 `›`（色 `E3A9B2`），不用大块箭头形状。整条居左对齐，放底部 `bottom:56–74px`。

### 代码面板
底 code-bg、描边 1px `F4DCE0`、圆角 12px；顶部头条 `FDEFF1`：三个 9px 圆点（`F4B4BC/F8CDD3/FBE3E7`）+ 文件名（Menlo 12px `A9727B`）。语法色：keyword `C9202F` bold、string `B45909`、函数/方法 `7E3F98`、注释 muted。代码 ≤ 12 行，面板高度贴内容，不许下半截空白。

### 表格
不用大粉底表头：表头文字 ink semibold + 2px red 底线；行线 1px table-line；偶数行底 `FFFBFB`；行高 ≈ 50–52px。方案/状态列用 pill 标签：影刀=red 实底白字，Python=`2B2D33` 实底白字，组合=白底 red 描边红字。

### 图像容器
内容页图像：圆角 18px，投影 `0 18px 44px rgba(23,24,28,.12)`，内侧 1px 半透明描边（`rgba(23,24,28,.06)`），`object-fit: cover`。封面 hero 全幅铺底 + 左侧白色渐变压字层：`linear-gradient(90deg, rgba(255,255,255,.94) 0%, .86 34%, 0 58%)`。

### 徽章
red 实底白字，`radius:6–7px, padding:6–7px 14–16px`，14–15px semibold。

## 页型构图规范（对照样张）

1. **封面**（`slide_a_cover`）：全幅 hero（`assets/brand/cover_hero_office.png` 或新生成的红白粉场景图）+ 渐变压字层；左列 = 徽章 → eyebrow → 两行大标题 → 一句副题 → 红短横线 + 主讲/客户 meta。
2. **章节页**（`slide_b_divider`）：左列 = 红 chip「第 N 部分」+ `PART 0N / 0M` → 大标题 → 一句副题 → 五模块进度列表（当前项 ink+红点，其余 muted）；右侧圆角大图；底部框架流程条。**超过 10 页的 deck，每 4–5 个内容页必须插一张。**
3. **案例页**（`slide_c_case`）：左列三张语义卡（业务问题⚠ / 处理规则⚙ / 输出结果✓，图标 chip 30px 圆角 9px）；右列代码面板 + **运行结果示意表（证据区，必须有）**；底部四步闭环流程条（末步实底）。
4. **总结/矩阵页**（`slide_d_summary`）：干净表格 + pill 标签 + 底部结论带（浅粉渐变底 `linear-gradient(90deg,#FFF1F3,#FFF9FA)`、左侧 5×40px 红条、18px 结论句，关键词标红）。

## 图像资产使用

- `assets/brand/` 现有：`cover_hero_office`（封面/收尾）、`workflow_loop_scene`（流程环）、`data_cleaning_before_after`（清洗案例）、`table_matching_scene`（匹配案例）、`data_pipeline_scene`（链路页）。同一张图一个 deck 最多用两次（封面+收尾算一次复用）。
- 新生成图像的 prompt 必须锁：红白粉主色、商务办公/供应链场景、画面内不出现文字、不要蓝色机械风。生成后不合色板就弃用。

## QA 硬门槛（渲染后逐页核对，任一不过即返修）

1. 无文字截断/溢出（重点：卡片内长句、表格单元格、流程 pill）。
2. 可见文字全部 ≥ 12px（9pt）。
3. 内容页底部 1/3 不得整体留白（封面/章节/大字页除外）。
4. 圆角 ≤ 14px；除卡片/图像的规范投影外无默认灰投影。
5. 装饰不压内容；每页家具四件套（logo/标题系/页脚/页码）位置一致。
6. 色板合规：无蓝色主视觉、无大粉底表头、红色只用于强调而非大面积铺底。
7. 同构版式不得连续 ≥ 3 页；案例页必须有证据区。
