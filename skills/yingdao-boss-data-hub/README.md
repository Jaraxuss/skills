# yingdao-boss-data-hub

一个用于 **OpenClaw / Agent Skill** 的内部数据抓取技能。

该技能用于从 **影刀 Boss 平台** 拉取指定业务组的客户数据，完成认证链路转换后，自动抓取分页数据，并将结果写入一个 **共享的最新数据文件**，供后续分析类 skill 直接读取。

---

## 1. 技能作用

本技能主要解决以下问题：

- 使用 Boss 平台账号密码进行登录认证
- 通过 `Boss accessToken -> asCode -> AppStudio accessToken` 完成鉴权链路
- 按业务组抓取客户表及合同订单数据
- 自动处理分页，拉取全部客户记录
- 支持向 BOSS CRM 系统回写/创建客户旅程跟进记录 (`create_customer_journey.py`)
- 将结果输出为统一结构的 JSON 文件
- 默认只保留一份 **最新共享数据**，避免不断生成历史文件占用磁盘
- 为后续“分析类 skill”提供稳定的数据输入

---

## 2. 适用场景

适用于以下场景：

- 需要按业务组从影刀 Boss 平台抓取客户数据
- 需要为客户分析、续费分析、健康度分析等下游流程准备基础数据
- 需要将抓取与分析拆分成两个 skill，分别负责“取数”和“分析”
- 希望每次运行后仅更新一份最新数据，而不是积累大量 JSON 历史文件

---

## 3. 当前工作流

本技能默认执行以下流程：

1. 读取本地配置文件
2. 校验必要参数：账号、密码、默认业务组
3. 使用内置 RSA 公钥对密码加密
4. 调用 Boss 登录接口获取 `accessToken`
5. 使用 `accessToken` 获取 `asCode`
6. 使用 `asCode` 获取 `AppStudio accessToken`
7. 调用 AppStudio datasource 接口抓取客户数据
8. 自动处理分页，直到抓取完成
9. 合并全部 `dataList`
10. 输出统一格式 JSON
11. 默认覆盖写入共享最新文件，供后续分析 skill 使用

---

## 4. 目录结构

```text
skills/
└── yingdao-boss-data-hub/
    ├── SKILL.md
    ├── README.md
    ├── config.template.json
    ├── references/
    │   └── api-notes.md
    └── scripts/
        ├── fetch_clients.py
        ├── fetch_contracts.py
        ├── create_customer_journey.py
        ├── export_dashboard.py
        └── requirements.txt
```

说明：

- `SKILL.md`：OpenClaw skill 的核心说明文件
- `README.md`：仓库说明与使用文档
- `config.template.json`：配置模板（不含真实凭据）
- `references/api-notes.md`：接口与存储模式说明
- `scripts/fetch_clients.py`：客户数据抓取脚本
- `scripts/fetch_contracts.py`：合同订单数据抓取脚本
- `scripts/create_customer_journey.py`：客户旅程/跟进记录回写脚本
- `scripts/requirements.txt`：Python 依赖列表

---

## 5. 运行环境要求

### Python 依赖

```bash
pip install -r skills/yingdao-boss-data-hub/scripts/requirements.txt
```

依赖版本：

- `requests==2.31.0`
- `cryptography==44.0.2`

---

## 6. 首次使用前必须配置

在第一次正式运行前，请先根据模板创建本地配置文件：

建议配置文件路径：

```text
runtime/yingdao-boss-data-hub/config.local.json
```

必须填写以下字段：

- `auth.username`
- `auth.password`
- `defaults.default_business_group`

如果缺少上述任何字段，脚本会直接停止执行并提示补全配置。

> 注意：
> - `config.local.json` 不应提交到 Git 仓库
> - 不应将真实账号密码写入 `config.template.json`

---

## 7. 配置说明

### 配置模板示例

```json
{
  "auth": {
    "username": "",
    "password": ""
  },
  "endpoints": {
    "boss_login_url": "https://boss-api.shadow-rpa.net/boss/api/v3/manager/login/ldap",
    "boss_ascode_url": "https://boss-api.shadow-rpa.net/boss/api/v3/manager/login/getAsCode",
    "appstudio_token_url": "https://app.yingdaoapps.com/as/v1/user/auth/generateTokenByCode",
    "datasource_exec_url": "https://app.yingdaoapps.com/as/v1/page/datasource/exec",
    "referer": "https://boss.shadow-rpa.net/"
  },
  "defaults": {
    "default_business_group": "",
    "page_size": 100
  },
  "storage": {
    "mode": "latest",
    "latest_output_path": "",
    "archive_dir": ""
  }
}
```

### 关键配置项说明

#### `auth`
- `username`：Boss 平台账号
- `password`：Boss 平台密码

#### `defaults`
- `default_business_group`：默认业务组
- `page_size`：每页抓取条数，默认 `100`

#### `storage`
- `mode`：输出模式
  - `latest`：默认，仅覆盖最新共享文件
  - `archive`：仅输出归档文件
  - `both`：同时输出最新文件与归档文件
- `latest_output_path`：共享最新文件输出路径（可留空，使用默认值）
- `archive_dir`：归档目录（可留空，使用默认值）

---

## 8. 默认输出模式（推荐）

本技能已经改为：

## **默认只保留一份最新共享数据**

默认输出路径为：

```text
runtime/yingdao-boss/latest-clients.json
```

特点：

- 每次抓取时 **覆盖写入**
- 不会不断生成新的时间戳 JSON 文件
- 磁盘占用稳定
- 下游分析 skill 可以直接读取这个固定路径

这也是推荐的工作模式。

---

## 9. 输出数据结构

抓取结果默认会写成如下结构：

```json
{
  "schema": "yingdao-boss-data-hub.v1",
  "meta": {
    "fetched_at": "2026-03-09T21:56:39+08:00",
    "business_group": "江苏业务组",
    "page_size": 100,
    "page_count": 1,
    "row_count": 59,
    "total": 59,
    "nsId": "706753409603948544",
    "pageId": "795223723223625728"
  },
  "rows": [
    {}
  ]
}
```

说明：

- `meta`：描述本次抓取的元信息
- `rows`：原始客户记录列表

当前版本保留原始行结构，便于后续分析 skill 根据真实字段做多维分析。

---

## 10. 使用方式

### 10.1 使用默认配置抓取

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py
```

### 10.2 指定配置文件

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --config ./runtime/yingdao-boss-data-hub/config.local.json
```

### 10.3 临时指定业务组

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --business-group "江苏业务组"
```

### 10.4 输出到自定义文件

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --output ./custom-output.json
```

### 10.5 在默认 latest 模式下额外保存一次归档快照

```bash
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py --archive
```

---

## 11. 数据看板导出（export_dashboard.py）

该脚本对接 Boss 后台的异步看板导出功能，全流程自动化：

### 使用前提

`fetch_clients.py` 需要先运行过一次，使 `latest-clients.json` 存在（用于根据客户名称查找组织UUID）。

### 运行方式

```bash
# 导出1个或多个客户的看板数据（日期默认：昨天 endDate，倒推365天 startDate）
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "南京***电子商务有限公司" "上海***电子商务有限公司"

# 自定义输出目录
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "江苏***药房连锁有限公司" \
  --output-dir ./runtime/yingdao-boss/exports

# 手动指定结束日期（用于补历史数据）
python3 skills/yingdao-boss-data-hub/scripts/export_dashboard.py \
  --client-names "南京***电子商务有限公司" \
  --end-date 20260401
```

### 三步流程

1. **提交导出申请**：POST `exportTenantDashboard`，传入组织UUID + 日期范围 + 固定 sheetNameList
2. **轮询任务列表**：每10秒查询 `export/task/page`，对前10条结果按客户名称+endDate匹配，直到 `status=success`（最多等3分钟）
3. **下载文件**：POST `download/with/audit` 拿到预签名COS URL，下载 xlsx 保存至本地

### 输出

xlsx 默认保存到 `/tmp`（可通过 `--output-dir` 或 config 中 `export_dashboard.output_dir` 修改）。同时打印 JSON 摘要至 stdout。

---

## 12. 客户成功行动看板（dashboard.html）

该看板是一个本地静态 HTML，用于客户成功日常查看：

- 哪些客户存在续费/流失风险
- 哪些客户需要运营关注
- 哪些客户使用趋势健康增长
- 每个客户在指定指标上的独立趋势图
- 客户真实运行账号、核心应用和应用使用扩散情况

它不同于 `export_dashboard.py`：`export_dashboard.py` 是从 Boss 异步下载 xlsx；本节的 `dashboard.html` 是基于本地 JSON 数据生成的客户成功行动看板。

运行洞察的详细说明见：

- 面向 CSM/团队推广：[docs/run-insights-csm-guide.md](docs/run-insights-csm-guide.md)
- 面向内部维护：[docs/run-insights-technical.md](docs/run-insights-technical.md)

### 12.1 文件职责

```text
skills/yingdao-boss-data-hub/dashboard/
├── _template.html   # 看板源模板：页面结构、样式、分组规则、图表和表格逻辑
├── build_data.py    # 构建脚本：读取 JSON 数据并注入模板
├── refresh_dashboard.py # 编排脚本：今天已有 JSON 就跳过对应取数步骤
└── dashboard.html   # 生成产物：可直接用浏览器打开的静态看板
```

职责说明：

- `_template.html`：需要改页面布局、交互、风险分组规则、图表逻辑时改这里。
- `build_data.py`：需要改读取哪些数据、如何合并数据、缺文件如何降级时改这里。
- `refresh_dashboard.py`：日常入口；检查相关 JSON 是否已经是今天生成的，是则跳过对应取数/分析步骤，最后重新生成看板。
- `dashboard.html`：最终打开查看的文件，通常不要手动修改；每次运行 `build_data.py` 都会覆盖它。

### 12.2 推荐生成顺序

日常推荐直接运行：

```bash
python3 skills/yingdao-boss-data-hub/dashboard/refresh_dashboard.py
```

它会检查以下文件是否已经是今天生成的（默认按 `Asia/Shanghai` 判断）：

- `runtime/yingdao-boss/latest-clients.json`
- `runtime/yingdao-boss/latest-contracts.json`
- `runtime/yingdao-boss/contracts-expiration-summary.json`
- `runtime/yingdao-boss/latest-reports.json`

如果某个文件已经是今天的，跳过对应步骤；如果不存在或不是今天的，才执行对应取数/分析脚本。无论是否跳过取数，最后都会重新生成 `dashboard.html`。

可先预览会执行哪些步骤：

```bash
python3 skills/yingdao-boss-data-hub/dashboard/refresh_dashboard.py --dry-run
```

如需强制重新拉取全部数据：

```bash
python3 skills/yingdao-boss-data-hub/dashboard/refresh_dashboard.py --force
```

等价的完整手动刷新顺序如下：

```bash
# 1. 刷新客户主数据，生成 runtime/yingdao-boss/latest-clients.json
python3 skills/yingdao-boss-data-hub/scripts/fetch_clients.py

# 2. 刷新合同数据，生成 runtime/yingdao-boss/latest-contracts.json
python3 skills/yingdao-boss-data-hub/scripts/fetch_contracts.py

# 3. 分析合同到期情况，生成 runtime/yingdao-boss/contracts-expiration-summary.json
python3 skills/yingdao-boss-data-hub/scripts/analyze_expiring_orders.py

# 4. 刷新日报数据，生成 runtime/yingdao-boss/latest-reports.json
python3 skills/yingdao-boss-data-hub/scripts/fetch_tenant_reports.py

# 5. 生成静态客户成功行动看板
python3 skills/yingdao-boss-data-hub/dashboard/build_data.py
```

生成后打开：

```text
skills/yingdao-boss-data-hub/dashboard/dashboard.html
```

### 12.3 构建脚本读取的数据

`build_data.py` 默认读取：

- `runtime/yingdao-boss/latest-reports.json`：必需，客户每日指标趋势。
- `runtime/yingdao-boss/latest-clients.json`：可选，补充客户成功负责人、服务阶段、合作状态、部署类型、续费字段。
- `runtime/yingdao-boss/contracts-expiration-summary.json`：可选，补充临期/已过期合同信息。
- `runtime/yingdao-boss/latest-app-run-insights.json`：可选，补充运行洞察数据，包括真实运行账号、应用运行者矩阵和账号日期活跃图。

如果可选文件不存在，脚本会提示 warning，但仍会生成只包含日报趋势的看板。

### 12.4 自定义输入或输出

```bash
python3 skills/yingdao-boss-data-hub/dashboard/build_data.py \
  --input ./runtime/yingdao-boss/latest-reports.json \
  --clients-input ./runtime/yingdao-boss/latest-clients.json \
  --expiration-input ./runtime/yingdao-boss/contracts-expiration-summary.json \
  --app-run-insights-input ./runtime/yingdao-boss/latest-app-run-insights.json \
  --output ./skills/yingdao-boss-data-hub/dashboard/dashboard.html
```

### 12.5 看板默认逻辑

看板当前是双模式：

- `指标观察`：默认模式，按所选指标当前值从低到高展示客户，保持客观数据视角。
- `CSM 诊断`：行动工作台，按诊断队列、续费季度和今日优先跟进辅助 CSM 决策。

通用控制：

- 默认指标：运行次数 `dayRunCnt`
- 默认时间段：近一个月
- 指标观察默认对比：环比，即当前时间段 vs 前一段等长时间段
- 可切换对比：环比、去年同期、不对比
- 可切换时间段：近7天、近一个月、近三个月、近半年、近一年
- 支持自定义起止日期筛选，起止日期均包含在筛选范围内
- 支持按服务阶段、客户分层、续费季度、CS 负责人筛选
- 服务阶段筛选默认不展示已流失/已过期客户

指标观察模式：

- 客户卡片按当前指标值从低到高排序。
- 图表支持当期线和对比期虚线叠加。
- 指标观察模式默认开启统一 Y 轴量纲，便于跨客户比较量级。
- 选择去年同期但缺少同期数据时，卡片和图表会显示无同期数据。

CSM 诊断模式：

- `今日优先跟进 Top 10` 排除已过期待挽回和数据异常待核查队列，避免占用可行动客户入口。
- 行动队列包括续费抢救、临期健康续费、新签未激活、使用骤降、健康度低、大客户波动、个人版转化追踪、稳定运营等。
- 诊断标签提供 hover 解释，说明系统判断依据。
- 可切换到续费季度视图，按 Q1/Q2/Q3/Q4/不在续费期展示客户。
- CSM 诊断模式默认关闭统一 Y 轴量纲，更关注单客户趋势变化。

客户详情：

- 点击客户卡片打开右侧详情页。
- 详情页默认展示 9 个指标折线图。
- 详情页包含 `运行洞察` 页签，用于查看核心应用、真实运行账号和运行扩散情况。
- 详情页支持 1/2/3 列图表布局切换，默认 1 列。
- 详情页有独立对比口径选择，不会影响外部看板选择。
- 详情页图表不继承外部统一 Y 轴量纲，按单客户单指标自动适配。
- 详情页宽度可拖拽调整，并保存在浏览器本地。
- 详情页展示合同摘要，并提供 BOSS 客户详情跳转链接。

看板会综合日报趋势、客户主数据和合同到期摘要；当客户主数据或到期摘要缺失时，会降级展示日报趋势。

运行洞察：

- 基于 BOSS 详细 Excel 导出的 `运行明细数据` sheet 聚合生成。
- 解析脚本为 `skills/yingdao-boss-data-hub/scripts/build_app_run_insights.py`。
- 默认读取 `runtime/yingdao-boss/latest-app-run-insights.json`。
- 只使用应用、真实运行者、运行开始时间和运行时长等聚合口径。
- V1 不使用运行状态、启动方式、运行方式做判断。
- 核心应用标记保存在当前浏览器 `localStorage`，不写回 BOSS，也不做团队共享。
- 如果客户没有运行明细数据，运行洞察会展示空态，不影响其他看板模块。

### 12.6 浏览器本地配置

以下交互配置保存在浏览器 `localStorage`，只影响当前浏览器：

| key | 用途 |
|-----|------|
| `dashboard_card_fields` | 卡片字段显示配置 |
| `dashboard_drawer_width` | 客户详情页宽度 |
| `dashboard_drawer_chart_columns` | 客户详情页指标图列数 |
| `dashboard_core_apps_v1` | 运行洞察核心应用标记，按客户 `organizationUuid` 隔离 |

如需恢复默认，可在页面内使用对应的恢复默认操作，或清理浏览器 localStorage。

---

## 13. 与分析类 skill 的配合方式

本技能推荐作为 **数据生产者 skill** 使用。

建议与后续分析类 skill 的协作模式如下：

### 抓取 skill 负责：
- 登录与鉴权
- 拉取客户原始数据
- 刷新 `runtime/yingdao-boss/latest-clients.json`

### 分析 skill 负责：
- 默认读取 `runtime/yingdao-boss/latest-clients.json`
- 做续费分析、健康度分析、客户结构分析、风险识别等
- 输出摘要、名单、分组统计、可视化结果等

这种模式的优点：

- 抓取和分析职责清晰
- 两个 skill 解耦
- 分析 skill 不需要重复处理认证与接口调用
- 共享文件结构稳定，便于迭代

---

## 14. 总结

`yingdao-boss-data-hub` 的定位不是“分析 skill”，而是一个稳定的 **Boss 客户数据与运营数据 hub**。

它的核心价值在于：

- 统一认证流程
- 自动拉全数据
- 固定共享输出
- 为分析 skill 提供稳定、可复用的数据输入

如果后续要做续费分析、客户健康分析、负责人分组分析等，建议直接围绕：

```text
runtime/yingdao-boss/latest-clients.json
```

构建下游分析能力。
