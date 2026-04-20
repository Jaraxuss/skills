# API 笔记与数据结构参考

## 认证流程

1. **Boss LDAP 登录**
   - 接口: `endpoints.boss_login_url`
   - 请求体: 用户名 + RSA 加密的密码
   - 输出: `data.accessToken`

2. **Boss asCode 兑换**
   - 接口: `endpoints.boss_ascode_url`
   - Header: `Authorization: Bearer {accessToken}`
   - 输出: `data`

3. **AppStudio Token 兑换**
   - 接口: `endpoints.appstudio_token_url`
   - Query 参数: `code={ascode}`
   - 输出: `data.accessToken`

## 数据源请求

使用 `endpoints.datasource_exec_url` 进行请求，要求：

- `Authorization: Bearer {appStudio_v2_accessToken}`
- `Content-Type: application/json`
- `Referer: endpoints.referer`

请求体默认使用 `config.template.json` 中的如下参数配置：
- `nsId`
- `pageId`
- `name`
- `envId`
- `editorMode`
- `build_show_columns`
- `fixed_filters`
- `business_group_filter`

## 分页机制

请求从第 `1` 页 (`page`) 开始。
持续发起请求，直到 `current_page >= pages` 为止。
在响应中从 `dataList` 读取具体的行数据。

## 数据持久化规范

默认输出模式是 `storage.mode = "latest"`。
这意味着每次抓取的数据会**覆盖**同一个共享文件，而不会自动创建带有时间戳的归档文件。

默认共享数据文件路径：
```text
runtime/yingdao-boss/latest-clients.json
runtime/yingdao-boss/latest-contracts.json
```

可选的文件归档行为：
- `storage.mode = "archive"` -> 仅生成带时间戳的归档文件
- `storage.mode = "both"` -> 同时生成共享最新文件 (`latest-*.json`) 以及归档文件
- 命令行带有 `--archive` 参数 -> 保持更新最新的共享文件，并针对当次运行生成一个额外的归档快照文件。

**注意**：当下游有其他分析工具或者技能时，应该**统一把 `runtime/yingdao-boss/latest-x.json` 作为默认的数据读取源。**

## 代理配置

脚本默认配置了 `network.use_env_proxy = false`。
因此 Python 的 `requests` 库会**忽略**通过环境变量 (`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`) 设置的代理，除非显式修改配置为开启（这对于防止局域网抓取时被不相关代理拦截非常重要）。

## 使用前必要配置

开发者在第一次运行抓包脚本之前，必须确保在本地配置中填入了以下内容：

- `auth.username` (账号)
- `auth.password` (密码)
- `defaults.default_business_group` (例如：xx业务组)

如果缺少配置，脚本将拦截并给出明确报错。

## 响应体结构与嵌套

后端平台返回的结构可能存在极深的包裹嵌套层级。当前脚本会尝试常见的路径，并抽取出：

- `pages` (总页数)
- `total` (数据总数)
- `dataList` (数据明细列表)

处理逻辑应保持宽容与防御性设计，以兼容后端的响应体二次包装。

---

# 合同模块 JSON 结构参考

这份描述用于梳理 `fetch_contracts.py` 所输出的合同数据结构 (`latest-contracts.json`)。
当 AI 模型和下一步数据流脚本需要进行加工分析时，须参考本节点的结构设计。

## 基础层级

无论输出哪个对象，其基础的 JSON 外部结构如下：
```json
{
  "schema": "yingdao-boss-client-fetch-contracts.v1",
  "meta": {
    "fetched_at": "2026-04-19T23:28:17.382024+00:00",
    "business_group": "...",
    "total_contracts": 109
  },
  "rows": [
    // 所有客户合同的数组，或者单个客户的诸多合同
  ]
}
```

## 合同对象 (`rows` 元素)

`rows` 数组中的每一项代表一个 **主合同记录** (Contract)。
注意，一个主合同往往会包含多个子订单、商品明细，其信息保存在下面的嵌套列表中。

### 主合同级别重要字段
- `_customNo` *(字符串)*: 由抓取脚本临时注入，代表 CRM 上的客户编码。
- `contractNo` *(字符串)*: 合同唯一标识编号 (例如：`HT-2026-01-30-0011`)。
- `contractType` *(字符串)*: 合同类型。示例枚举：
  - `un_standard` (非标合同)
  - (`standard` 预估可能的其他值)
- `signStatus` *(字符串)*: 签约状态 / 邮寄状态。常见枚举值：
  - `archived` (已归档)
  - `history` (历史)
  - `not_has_address` (无地址/未回寄)
  - `not_need_send` (无需邮寄)
  - `not_re_receive` (未收回)
  - `null` (无状态)
- `status` *(字符串)*: 整体审核状态。常见枚举值：
  - `approved` (已审批通过)
  - `200`
  - `null` (无状态)
- `createTime` *(字符串)*: 合同最初创建时间 (`YYYY-MM-DD HH:MM:SS`)。**在分析时，通常利用此字段来鉴别客户的“最新合同”是哪一份。**
- `signDate` *(字符串)*: 合同签字日期。
- `startTime` / `endTime` *(字符串)*: 主合同框架级别的总体起止时间。
- `paymentAmount` / `totalAmount` *(数字)*: 金额指标数字。
- `customIdExtra.name` *(字符串)*: 客户的企业中文名称 (如“江苏****有限公司”)。

### 子订单明细列表 (`contractOrderDTOList2`)

这个数组中存放了归属于主合同的具体**商品、SKU、服务类型**明细。只有子订单上才会有详细的独立起止时间和续费信息。

- `commodityIdExtra.name` *(字符串)*: 商品/费用名称 (例如：数据连接器-机器人费用, 套餐B-59800)。
- `startDate` *(字符串)*: 这个的具体商品的有效开始期 (`YYYY-MM-DD HH:MM:SS`)。
- `endDate` *(字符串)*: 这个具体商品的**到期截止时间** (也就是最核心的 Expiration Date)。
- `actualAmount` *(数字)*: 该行对应的实付价格记录。
- `itemsDetailDesc` *(字符串)*: 结构化备注（例如包含："RPA账号数量：5\r\n购买时长：1年..." 等详细描述）。
- `orderType` *(字符串)*: 订单性质。常见枚举值及其分析逻辑：
  - `new` (新签/新购)
  - `renew` (续费)
  - `add` (增购)
  - `once` (一次性费用，可能是充值、买断或硬件实施服务。**这类不包含长期跟踪性质，通常在统计临期监控中将其直接过滤忽略**)

## 最佳实践与数据抽象逻辑推荐

如果要找到一个客户的“最新有效的订单到期日”：
1. 按 `_customNo` 将 `rows` 下的数据分组。
2. 对每个组内的数据，判断 `createTime` 并经过降序排序，提取那条 **最近创建（Latest）的合同**。
3. 进入该最新合同的内容，遍历 `contractOrderDTOList2` 订单明细数组。
4. **剔除 `orderType` 不合规的条目**（排除 `once` 的那些）。取出剩下的订单中的 `endDate` 和 `startDate`，取 `endDate` 中的最大值，即视作这个客户最新的可用续费截止锚点。
