# yingdao-boss-client-fetch

一个用于 **OpenClaw / Agent Skill** 的内部数据抓取技能。

该技能用于从 **影刀 Boss 平台** 拉取指定业务组的客户数据，完成认证链路转换后，自动抓取分页数据，并将结果写入一个 **共享的最新数据文件**，供后续分析类 skill 直接读取。

---

## 1. 技能作用

本技能主要解决以下问题：

- 使用 Boss 平台账号密码进行登录认证
- 通过 `Boss accessToken -> asCode -> AppStudio accessToken` 完成鉴权链路
- 按业务组抓取客户表数据
- 自动处理分页，拉取全部客户记录
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
└── yingdao-boss-client-fetch/
    ├── SKILL.md
    ├── README.md
    ├── config.template.json
    ├── references/
    │   └── api-notes.md
    └── scripts/
        ├── fetch_clients.py
        └── requirements.txt
```

说明：

- `SKILL.md`：OpenClaw skill 的核心说明文件
- `README.md`：仓库说明与使用文档
- `config.template.json`：配置模板（不含真实凭据）
- `references/api-notes.md`：接口与存储模式说明
- `scripts/fetch_clients.py`：主抓取脚本
- `scripts/requirements.txt`：Python 依赖列表

---

## 5. 运行环境要求

### Python 依赖

```bash
pip install -r skills/yingdao-boss-client-fetch/scripts/requirements.txt
```

依赖版本：

- `requests==2.31.0`
- `cryptography==44.0.2`

---

## 6. 首次使用前必须配置

在第一次正式运行前，请先根据模板创建本地配置文件：

建议配置文件路径：

```text
runtime/yingdao-boss-client-fetch/config.local.json
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
  "schema": "yingdao-boss-client-fetch.v1",
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
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py
```

### 10.2 指定配置文件

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --config ./runtime/yingdao-boss-client-fetch/config.local.json
```

### 10.3 临时指定业务组

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --business-group "江苏业务组"
```

### 10.4 输出到自定义文件

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --output ./custom-output.json
```

### 10.5 在默认 latest 模式下额外保存一次归档快照

```bash
python3 skills/yingdao-boss-client-fetch/scripts/fetch_clients.py --archive
```

---

## 11. 与分析类 skill 的配合方式

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

## 16. 总结

`yingdao-boss-client-fetch` 的定位不是“分析 skill”，而是一个稳定的 **Boss 客户数据抓取 skill**。

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
