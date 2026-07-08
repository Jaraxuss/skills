# 「运行洞察」进一步优化方案

> 优化范围仅限「运行洞察」板块，不改动数据层（`latest-app-run-insights.json`）和现有抽屉/看板其他模块。
> 本次改动聚焦两个真实可观察的体验问题。

---

## 一、本次改动范围

### 改动 1：当前时间段活跃账号板块过长 + 活跃定义不清

**问题**：

- 板块默认渲染 50 行全字段表格，垂直占用高，需要下拉很久。
- 「活跃」口径未显式标注，CSM 不知道哪些账号被算成活跃。

**方案**：

1. 标题区追加「活跃」定义徽标
   - 标题右侧加 `?` 图标，hover 展示完整定义：
     > 「活跃」= 当前时间范围内（核心/全部 应用范围内）运行次数 ≥ 1 的账号
   - 标题文案改为：`当前时间段活跃账号 · N 个`，旁边追加灰色小标签：`活跃 = 运行次数 ≥ 1`
2. 默认收起列表，仅保留前 8 行精简表
   - 列精简为：`账号 / 运行次数 / 活跃天数 / 最近运行`（去掉运行应用数、核心应用运行次数，避免列过宽）
   - 下方加 `展开全部 N 个活跃账号` 按钮（默认收起）
   - 展开后展示全量（最多 50 行；超出显示 `+N 更多，去 BOSS 查完整明细`）
3. 摘要卡保持不变
   - 已有 5 张摘要卡（真实运行账号 / 日均活跃 / 连续活跃 / 新增沉默 / Top3 占比）已经覆盖 CSM 关心的口径，不再叠加。

**业务价值**：

- 解决滚动疲劳：首屏只看到 8 行最常用信息
- 解决定义困惑：徽标让「活跃」标准显式可见
- 保留下钻：需要全部数据时一键展开

---

### 改动 2：核心应用 x 运行者矩阵单元格点击弹层位置错乱

**问题**：

- 点击矩阵单元格后，弹窗没有出现在鼠标旁边，而是出现在视口上方好几页之外。

**根因**：

- `.drawer` 使用 `transform: translateX(0)` 控制抽屉滑入滑出动画（line 335）。
- 任何非 `none` 的 transform 都会为后代 `position: fixed` 建立新的包含块（containing block）。
- 弹层 `.heatmap-popover` 虽然声明 `position: fixed`，但实际是相对 `.drawer` 内容区定位，不是相对视口。
- 用户滚动到矩阵底部后点击单元格，`rect.top` 返回视口 Y（例如 500），写入 `top: 500px`。
- 因为 containing block 切换，500px 被解释为抽屉内容区相对 Y。当 `drawer.scrollTop > 0` 时，弹层视觉位置 = 500 − scrollTop，可能跑到视口上方数屏外。

**方案**：

1. 改用鼠标事件坐标作为定位基准
   - 在点击回调里直接读 `event.clientX`、`event.clientY`
   - 弹层左上 = `(clientX + 12, clientY + 8)`
   - 边界保护：弹层宽度 280、高度估 200；超出视口右/下边时自动翻转到鼠标左/上
   - 不再依赖 `cell.getBoundingClientRect()`，不再依赖 drawer 滚动位置
2. CSS 微调
   - `.heatmap-popover` 加 `pointer-events: auto`，确保点击弹层内部不被外层 drawer 的点击监听吃掉

**业务价值**：

- 弹层始终出现在用户视线内，符合点击即查看的直觉
- 不依赖任何复杂的坐标换算，跨浏览器 / 缩放一致
- 关闭策略（点同一格关闭 / 点其他格切换 / 点空白关闭 / Esc 关闭）保持不变

---

## 二、实施细节

涉及函数：

| 函数 | 改动 |
|---|---|
| `runInsightPeriodRunnerListHtml` | 增加 `runInsightRunnerListExpanded` 状态、Top 8 精简列、问号徽标 + tooltip |
| `runInsightRunnerActivityHtml` | 在末尾插入 `runInsightPeriodRunnerListHtml`（已存在，保持结构） |
| `runInsightsHtml` | 顺序保持（核心应用概览 → 运行账号 x 日期活跃图 → 核心应用 x 运行者矩阵） |
| 热力图 cell 点击回调 | 把 `rect = cell.getBoundingClientRect()` 改成读 `event.clientX/clientY` |
| CSS | 补 `.info-pill`（活跃=…徽标）、`.info-tip`（hover tooltip） |

新增前端状态：

- `runInsightRunnerListExpanded`（默认 `false`）
- `runInsightRunnerListLimit`：默认 `8`，展开后切到 `50`

不改动：

- `latest-app-run-insights.json` 数据层
- ECharts、抽屉宽度、CSM 诊断等无关模块

---

## 三、验证计划

### 功能验证

- **活跃账号板块**
  - 切换时间范围（7d / 30d / 全部），列表数和「活跃」定义保持一致
  - hover 问号徽标，显示完整定义文案
  - 默认只看到 8 行精简表，点击「展开全部」看到完整列表
  - 切回核心/全部应用范围，列表数和定义解释同步变化
- **弹层定位**
  - 切到运行洞察，向上/向下滚动到不同位置点击矩阵单元格，弹层稳定出现在鼠标附近
  - 切换整体图模式点击，弹层位置仍正确
  - 抽屉全屏模式下点击，弹层仍在视口内
  - 单元格紧贴视口右/下边缘时，弹层自动翻转到鼠标左/上
  - Esc / 点空白 / 点同一格 / 点其他格的关闭行为不变

### 回归验证

- 「核心应用概览」、「核心应用 x 运行者矩阵」表格、整体图、单元格点击 popover 内容、抽屉宽度 / 全屏 / 关闭按钮行为不变
- 现有指标观察、CSM 诊断、Top 10、合同明细、9 指标趋势图不受影响

### 构建检查

- `conda run -n llm python skills/yingdao-boss-data-hub/dashboard/build_data.py`
- `conda run -n llm python -m py_compile ...`
- 生成 HTML 内联 JS `node --check`
- `git diff --check`

---

## 四、假设与边界

- 弹层位置改用鼠标坐标而不是格子坐标，是这次唯一能彻底解决 transform containing block 的简单方案
- 活跃账号精简到 8 行后，Top 8 已经能覆盖绝大多数 CSM 想要的「先看谁」信息；全量列表保留为可展开项
- 「活跃」的口径沿用现有聚合逻辑（`runCnt >= 1`），不引入更复杂的「高频活跃」、「连续活跃」等口径，避免与上方摘要卡重复
- 弹层在单元格右侧紧贴呈现与鼠标右下呈现，从交互上等价，因为弹层尺寸已知（280×~200）
- 不改动数据层、不引入新依赖、不重构运行洞察整体结构