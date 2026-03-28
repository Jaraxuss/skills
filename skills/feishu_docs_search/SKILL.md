---
name: 飞书云文档搜索
description: 根据关键词搜索当前用户在飞书中可见的云文档，返回包含文档标题、类型、Token 和直达链接的结构化列表。包含完整的 OAuth 2.0 用户授权流程（获取授权码 → 换取 user_access_token → 刷新 token），以及最终的关键词搜索能力。所有步骤均由 Python 脚本执行，无需额外依赖。
---

# 飞书云文档搜索 Skill (feishu_docs_search)

本 Skill 通过完整的 OAuth 2.0 用户授权流程获取 `user_access_token`，再调用飞书[搜索云文档](https://open.feishu.cn/document/server-docs/docs/drive-v1/search/document-search) API，对当前用户可见的所有云文档进行全文检索，并以 Markdown 表格返回结果。

## 文件说明

| 文件 | 作用 |
|---|---|
| `config.json` | 存储 `app_id` 和 `app_secret`（**首次使用必填**） |
| `get_oauth_code.py` | 步骤一：本地起临时服务器，浏览器授权，自动捕获 `code` |
| `get_user_token.py` | 步骤二：用 `code` 换取 `user_access_token`，缓存至 `token_cache.json` |
| `refresh_token.py` | 步骤三（可选）：用 `refresh_token` 静默刷新，无需再次浏览器授权 |
| `token_cache.json` | 自动生成的 token 缓存（含 token、refresh_token、过期时间） |
| `search.py` | 核心搜索脚本，用 `user_access_token` 调用搜索 API |

---

## 使用前提

1. 在[飞书开放平台](https://open.feishu.cn/app)创建**自建应用**，获取 `app_id` 和 `app_secret`，填入 `config.json`。
2. 在应用的**权限管理**中开通以下权限（至少其一）：
   - `search:docs:read`（推荐，最小权限）
   - `drive:drive:readonly`
   - `drive:drive`
3. 在应用的**安全设置** → **重定向 URL** 中添加（一次性配置）：
   ```
   http://localhost:9527/callback
   ```

---

## 传参说明（搜索阶段）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `search_key` | string | **是** | 要搜索的关键词，例如 `"项目周报"` |
| `count` | int | 否 | 返回文档数量，范围 [1, 50]，默认 `10` |
| `offset` | int | 否 | 翻页偏移量，默认 `0`，`offset + count < 200` |
| `docs_types` | list | 否 | 类型过滤，可选值：`doc`、`sheet`、`slides`、`bitable`、`mindnote`、`file` |
| `owner_ids` | list | 否 | 按文件所有者 Open ID 过滤 |

---

## 执行步骤

### 步骤 0：配置应用凭证（仅首次，且 config.json 未填时）

编辑 `config.json`，填入真实凭证：

```json
{
  "app_id": "cli_你的应用ID",
  "app_secret": "你的应用密钥"
}
```

> 凭证来源：飞书开放平台 → 我的应用 → 选择应用 → 凭证与基础信息。

---

### 步骤 1：获取 user_access_token

#### 情况 A：首次授权 / token 已过期无法刷新

**1a. 获取 OAuth 授权码**（浏览器弹窗授权，自动捕获）：

```bash
python3 ./get_oauth_code.py
```

脚本会自动打开浏览器 → 用户点击授权 → 终端自动打印 `code`。

**1b. 用 code 换 user_access_token**：

```bash
python3 ./get_user_token.py --code "终端中拿到的code"
```

⚠️ `code` 仅能使用**一次**，有效期约 **5 分钟**，请立即执行。

成功后 token 自动保存至 `token_cache.json`，有效期 **2 小时**。

---

#### 情况 B：token 未过期或需要续期（推荐日常使用）

先检查当前 token 剩余有效期：

```bash
python3 ./refresh_token.py --check
```

若需要刷新（无需浏览器授权）：

```bash
python3 ./refresh_token.py
```

⚠️ `refresh_token` 是**一次性**的，刷新成功后旧 `refresh_token` 立即失效，新凭证自动写入 `token_cache.json`。

---

### 步骤 2：执行搜索

使用 `run_command` 工具运行 `search.py`，**`Cwd` 设置为本 Skill 所在目录**：

```bash
python3 ./search.py \
  --token "$(python3 -c "import json; print(json.load(open('token_cache.json'))['user_access_token'])")" \
  --key "搜索关键词" \
  --count 10
```

或在获取 token 后直接复制终端中输出的完整命令。

常用参数示例：

```bash
# 只搜文档和表格
python3 ./search.py --token "eyJ..." --key "周报" --types "doc,sheet"

# 翻页（获取第 11-20 条）
python3 ./search.py --token "eyJ..." --key "OKR" --count 10 --offset 10
```

---

### 步骤 3：展示结果

`search.py` 直接输出 Markdown 表格，包含：

- 序号、文档标题（附飞书直达链接）、文件类型、文档 Token
- 共找到 X 个文档（`total`）、是否还有更多（`has_more`）

文件类型映射：`doc` 📄 文档 ｜ `sheet` 📊 电子表格 ｜ `slides` 📑 幻灯片 ｜ `bitable` 🗃️ 多维表格 ｜ `mindnote` 🧠 思维笔记 ｜ `file` 📎 文件

若 `has_more=true`，提示用户通过增加 `--offset` 翻页。

---

## 飞书文档直达链接规则

| 类型 | 链接模板 |
|---|---|
| `doc` | `https://docs.feishu.cn/docs/{docs_token}` |
| `sheet` | `https://docs.feishu.cn/sheets/{docs_token}` |
| `slides` | `https://docs.feishu.cn/slides/{docs_token}` |
| `bitable` | `https://docs.feishu.cn/base/{docs_token}` |
| `mindnote` | `https://docs.feishu.cn/mindnotes/{docs_token}` |
| `file` | `https://docs.feishu.cn/file/{docs_token}` |
