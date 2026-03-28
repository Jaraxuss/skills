---
name: 飞书文档搜索（云文档 + Wiki）
description: 根据关键词搜索当前用户在飞书中可见的云文档和 Wiki 知识库节点，返回包含文档标题、类型和直达链接的结构化列表。包含完整的 OAuth 2.0 用户授权流程（获取授权码 → 换取 user_access_token → 刷新 token）。所有步骤均由 Python 脚本执行，无需额外依赖。
---

# 飞书文档搜索 Skill (feishu_docs_search)

本 Skill 通过 OAuth 2.0 用户授权流程获取 `user_access_token`，支持两类搜索：
- **云文档搜索**（`search_docs.py`）：搜索「我的空间/共享空间」中的文档、表格、多维表格等
- **Wiki 知识库搜索**（`search_wiki.py`）：搜索用户有权访问的 Wiki 知识库节点

两类搜索互补，建议同时搜索以获取最全结果。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `config.json` | 存储 `app_id`、`app_secret`、`redirect_uri`（**首次使用必填**） |
| `get_oauth_code.py` | 步骤一：启动本地回调服务，打印授权 URL 发给用户 |
| `get_user_token.py` | 步骤二：用 `code` 换取 `user_access_token`，缓存至 `token_cache.json` |
| `refresh_token.py` | 步骤三（可选）：用 `refresh_token` 静默刷新，无需再次浏览器授权 |
| `token_cache.json` | 自动生成的 token 缓存（含 token、refresh_token、过期时间） |
| `search_docs.py` | 搜索云文档（旧版接口，offset 翻页） |
| `search_wiki.py` | 搜索 Wiki 知识库（新版接口，page_token 游标翻页） |

---

## 使用前提

1. 在[飞书开放平台](https://open.feishu.cn/app)创建**自建应用**，获取 `app_id` 和 `app_secret`，填入 `config.json`。
2. 在应用的**权限管理**中开通以下权限：
   - `search:docs:read`（搜索云文档）
   - `wiki:wiki:readonly`（搜索 Wiki，即「查看知识库」）
3. 在应用的**安全设置** → **重定向 URL** 中添加与 `config.json` 中 `redirect_uri` 相同的地址（一次性配置）。

---

## 传参说明

### 云文档搜索（search_docs.py）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `search_key` | string | **是** | 搜索关键词 |
| `count` | int | 否 | 返回数量，范围 [1, 50]，默认 `10` |
| `offset` | int | 否 | 翻页偏移量，默认 `0`，`offset + count < 200` |
| `docs_types` | list | 否 | 类型过滤：`doc`、`sheet`、`slides`、`bitable`、`mindnote`、`file` |
| `owner_ids` | list | 否 | 按文件所有者 Open ID 过滤 |

### Wiki 搜索（search_wiki.py）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `query` | string | **是** | 搜索关键词（不超过 50 个字符） |
| `page_size` | int | 否 | 每页返回数量，范围 (0, 50]，默认 `20` |
| `page_token` | string | 否 | 翻页游标，首次调用留空，填上次返回的值获取下一页 |
| `space_id` | string | 否 | 知识空间 ID，为空则搜索全部有权访问的知识空间 |
| `node_id` | string | 否 | 节点 ID，需配合 `space_id` 使用，限定搜索范围 |

---

## 执行步骤

### 步骤 0：配置应用凭证（仅首次，且 config.json 未填时）

编辑 `config.json`，填入真实凭证：

```json
{
  "app_id": "cli_你的应用ID",
  "app_secret": "你的应用密钥",
  "redirect_uri": "http://192.168.x.x:9527/callback"
}
```

> 凭证来源：飞书开放平台 → 我的应用 → 选择应用 → 凭证与基础信息。

---

### 步骤 1：获取 user_access_token

#### 情况 A：首次授权 / token 已过期无法刷新

**1a. 在服务器上启动授权码监听服务**

使用 `run_command` 工具运行（`Cwd` 设置为本 Skill 所在目录）：

```bash
python3 ./get_oauth_code.py
```

脚本启动后会立即打印一条授权链接，**格式如下**：

```
👉 请在浏览器中打开以下授权链接：
   https://accounts.feishu.cn/open-apis/authen/v1/authorize?client_id=...
```

**1b. 将授权链接发给用户**

直接把上面这条 URL **展示给用户**，并说明：

> 请在浏览器中打开以下链接，完成飞书授权，授权成功后页面会显示"✅ 授权成功！"，请稍候片刻。

等待用户完成授权后，脚本会自动捕获 `code` 并打印到终端。

**1c. 用 code 换 user_access_token**

读取命令输出中的 `code`，然后运行：

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

从 `token_cache.json` 读取 token 的快捷方式：

```bash
TOKEN=$(python3 -c "import json; print(json.load(open('token_cache.json'))['user_access_token'])")
```

#### 搜索云文档（search_docs.py）— 适合搜索个人/共享文档

```bash
python3 ./search_docs.py --token "$TOKEN" --key "搜索关键词" --count 10

# 只搜文档和表格
python3 ./search_docs.py --token "$TOKEN" --key "周报" --types "doc,sheet"

# 翻页（获取第 11-20 条）
python3 ./search_docs.py --token "$TOKEN" --key "OKR" --count 10 --offset 10
```

#### 搜索 Wiki 知识库（search_wiki.py）— 适合搜索知识库/规范文档

```bash
python3 ./search_wiki.py --token "$TOKEN" --key "搜索关键词"

# 指定知识空间搜索
python3 ./search_wiki.py --token "$TOKEN" --key "周报" --space-id "7307457194084925443"

# 翻页（使用上次返回的 page_token）
python3 ./search_wiki.py --token "$TOKEN" --key "周报" --page-token "上次返回的token"
```

---

### 步骤 3：展示结果

两个脚本均直接输出 Markdown 表格：

**云文档结果** 包含：序号、标题（附直达链接）、文件类型、文档 Token、总数 / 是否有更多
- 若 `has_more=true`：提示用户增大 `--offset` 翻页

**Wiki 结果** 包含：序号、标题（附直达链接）、节点类型、node_id
- 若 `has_more=true`：输出中会显示下一页的 `--page-token` 值，直接复制使用

---

## 两种搜索的区别

| 维度 | search_docs.py（云文档） | search_wiki.py（Wiki） |
|---|---|---|
| 覆盖范围 | 个人空间 + 共享空间的文档 | 用户有权访问的 Wiki 知识库 |
| 翻页方式 | `--offset` 偏移量 | `--page-token` 游标 |
| 返回内容 | docs_token + 标题 + 类型 | node_id + 标题 + 类型 + **直接包含 url** |
| 权限要求 | `search:docs:read` | `wiki:wiki:readonly` |
