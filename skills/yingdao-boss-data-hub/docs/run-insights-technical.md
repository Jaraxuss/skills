# 运行洞察技术说明

## 1. 目标

运行洞察用于把客户详细 Excel 运行明细聚合成看板可渲染的数据，注入客户成功行动看板的客户详情页。

V1 只做聚合洞察，不做运行明细下钻：

- 核心应用概览
- 运行账号 x 日期活跃图
- 核心应用 x 运行者矩阵

## 2. 数据输入与输出

### 2.1 输入

运行洞察依赖 BOSS 导出的详细 Excel 看板文件，核心 sheet 为：

```text
运行明细数据
```

解析脚本：

```text
skills/yingdao-boss-data-hub/scripts/build_app_run_insights.py
```

默认输出：

```text
runtime/yingdao-boss/latest-app-run-insights.json
```

### 2.2 单客户 JSON 结构

单客户输出 schema：

```json
{
  "schema": "yingdao-boss-app-run-insights.v1",
  "meta": {
    "client_name": "...",
    "organization_uuid": "...",
    "custom_no": "...",
    "range_start": "20260101",
    "range_end": "20260705",
    "run_detail_available": true
  },
  "apps": [],
  "runners": [],
  "app_runner_matrix": [],
  "runner_daily_activity": [],
  "app_daily_summary": []
}
```

### 2.3 多客户 bundle 结构

当多个客户都有详细运行明细时，`latest-app-run-insights.json` 可以是 bundle：

```json
{
  "schema": "yingdao-boss-app-run-insights.bundle.v1",
  "clients": []
}
```

`dashboard/build_data.py` 会按客户的 `organizationUuid`、`customNo`、客户名称进行匹配，并把对应文档注入到：

```text
reportData.appRunInsights
```

## 3. 字段口径

| 口径 | 说明 |
|---|---|
| 应用主键 | `应用uuid` |
| 运行者主键 | `运行者uuid` |
| 展示字段 | 应用名称、运行者账号、运行者名称 |
| 运行次数 | 按 `运行开始时间` 计数 |
| 运行时长 | 按明细中的运行时长字段累计，前端展示为小时 |
| 活跃天数 | 在当前时间范围内有至少一次运行的自然日数量 |
| 真实运行账号 | 当前时间范围内至少运行过一次的 `运行者uuid` |
| 最近运行 | 当前时间范围内最大 `运行开始时间` |

V1 不使用以下字段做判断：

- 运行状态
- 启动方式
- 运行方式

## 4. 核心应用标记

核心应用是唯一保留的人工标签。

前端使用浏览器 `localStorage` 保存：

```json
{
  "dashboard_core_apps_v1": {
    "{organizationUuid}": {
      "{appUuid}": {
        "core": true,
        "appName": "...",
        "updatedAt": "2026-07-06T..."
      }
    }
  }
}
```

设计约束：

- 标记只影响当前浏览器。
- 不做团队共享。
- 不写回 BOSS。
- 不改变 JSON 数据源。
- 不引入“候选”“观察”“忽略”等额外标签，避免消耗 CSM 注意力。

## 5. 构建流程

### 5.1 从 Excel 生成运行洞察 JSON

建议在本机使用 `llm` conda 环境：

```bash
conda run -n llm python skills/yingdao-boss-data-hub/scripts/build_app_run_insights.py \
  runtime/yingdao-boss/客户数据看板.xlsx \
  --output runtime/yingdao-boss/latest-app-run-insights.json \
  --client-name "客户名称" \
  --organization-uuid "客户 organizationUuid" \
  --custom-no "客户编号"
```

如果只是临时解析单个客户，可以先输出到 `/tmp`，确认后再合并到 bundle。

### 5.2 生成客户成功行动看板

```bash
conda run -n llm python skills/yingdao-boss-data-hub/dashboard/build_data.py
```

`build_data.py` 默认读取：

- `runtime/yingdao-boss/latest-reports.json`
- `runtime/yingdao-boss/latest-clients.json`
- `runtime/yingdao-boss/contracts-expiration-summary.json`
- `runtime/yingdao-boss/latest-app-run-insights.json`

其中 `latest-app-run-insights.json` 是可选文件。缺少时，看板仍正常生成，客户详情页中的运行洞察会展示空态或隐藏数据。

## 6. 多客户明细合并建议

当新增一个客户的详细 Excel 运行明细时：

1. 使用 `build_app_run_insights.py` 解析成单客户 JSON。
2. 检查输出中的 `meta.client_name`、`meta.organization_uuid`、`meta.custom_no` 是否正确。
3. 如果当前 `latest-app-run-insights.json` 是单客户文档，先转换为 bundle。
4. 按 `organization_uuid` 或 `custom_no` 替换同一客户的旧文档，避免重复。
5. 重新执行 `dashboard/build_data.py`。

## 7. 前端状态

运行洞察相关状态主要在 `dashboard/_template.html` 中维护。

关键状态包括：

| 状态 | 用途 |
|---|---|
| `runInsightPeriod` | 时间范围：最近 7 天、最近 30 天、导出周期 |
| `runInsightAppScope` | 热力图共享应用范围：核心应用 / 全部应用 |
| `runInsightAppSearch` | 应用搜索 |
| `runInsightRunnerSearch` | 运行账号搜索 |
| `runInsightRunnerRowSort` | 运行账号 x 日期活跃图的行排序 |
| `runInsightRowSort` | 核心应用 x 运行者矩阵的行排序 |
| `runInsightColSort` | 核心应用 x 运行者矩阵的列排序 |
| `runInsightMatrixFit` | 应用矩阵整体图模式 |
| `runInsightRunnerFit` | 账号日期热力图整体图模式 |
| `runInsightActiveCell` | 当前点击打开的热力图弹层 |

## 8. 弹层定位

热力图单元格详情弹层使用 body 级 portal：

```html
<div id="heatmap-popover-root"></div>
```

原因是 `.drawer` 使用 `transform` 实现抽屉动画，会让后代 `position: fixed` 不再按视口定位。弹层必须渲染到抽屉外，再使用单元格的 `getBoundingClientRect()` 计算视口坐标。

交互规则：

- 点击有数据色块打开弹层。
- 点击同一色块关闭。
- 点击其他色块切换。
- 点击空白处或按 `Esc` 关闭。
- 抽屉或热力图滚动时关闭，避免弹层停留在旧坐标。

## 9. 性能边界

V1 不做虚拟滚动，依赖 Top N 限制控制复杂度：

- 应用矩阵默认最多展示 50 行应用 x 30 列账号。
- 账号日期图默认最多展示 80 行账号 x 31 列日期。
- 整体图模式会压缩单元格展示，保留色块深浅，隐藏部分文本。

如果后续单客户数据规模明显增大，再考虑虚拟滚动或 canvas 渲染。

## 10. 验证清单

修改运行洞察后，建议执行：

```bash
conda run -n llm python skills/yingdao-boss-data-hub/dashboard/build_data.py
conda run -n llm python -m py_compile \
  skills/yingdao-boss-data-hub/dashboard/build_data.py \
  skills/yingdao-boss-data-hub/scripts/build_app_run_insights.py
git diff --check
```

前端人工验证：

- 缺少 `latest-app-run-insights.json` 时看板不报错。
- 未标记核心应用且选择核心应用范围时，两个热力图展示空态。
- 标记核心应用后，两个热力图按核心应用范围过滤。
- 时间范围切换后，概览、账号热力图、应用矩阵同步变化。
- 整体图模式下热力图能一屏快速观察整体分布。
- 点击热力图色块，弹层贴近单元格且不被抽屉滚动影响。
