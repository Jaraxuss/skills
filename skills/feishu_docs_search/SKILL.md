---
name: 飞书云文档搜索
description: 根据关键词搜索当前用户在飞书（Lark）中可见的云文档，返回包含文档标题、类型、Token 和所有者信息的结构化列表。执行由 Python 脚本完成，需要提供 user_access_token 和搜索关键词。
---

# 飞书云文档搜索 Skill (feishu_docs_search)

本 Skill 通过调用飞书开放平台的[搜索云文档](https://open.feishu.cn/document/server-docs/docs/drive-v1/search/document-search) API，根据搜索关键词对当前用户（`user_access_token`）可见的所有云文档进行全文检索，并返回结构化的文档列表结果。

## 核心能力

- **关键词搜索**：精准定位用户有权限访问的云文档。
- **类型过滤**：可按文件类型筛选（文档、表格、幻灯片、多维表格、思维笔记、文件）。
- **分页支持**：通过 `count` 和 `offset` 控制返回数量与翻页。
- **所有者过滤**：可按文件 Owner 的 Open ID 缩小范围。
- **结构化输出**：以 Markdown 表格形式展示结果，包含文档在飞书中的直达链接。

---

## 使用前提

1. 在[飞书开放平台](https://open.feishu.cn/app)创建自建应用，获取 **`app_id`** 和 **`app_secret`**，填入本 Skill 目录下的 `config.json`。
2. 对应的飞书应用需已开通以下**任意一项**权限：
   - `drive:drive`（查看、评论、编辑和管理云文档所有文件）
   - `drive:drive:readonly`（查看、评论和下载云文档所有文件）
   - `search:docs:read`（搜索用户有权限的云文档）
3. ⚠️ **关于 Token 类型的重要说明**：
   - `get_token.py` 获取的是 **`tenant_access_token`**（应用身份），可直接用于调用大多数飞书 API。
   - 搜索云文档接口原则上需要 **`user_access_token`**（用户身份）才能返回该用户可见的文档；若使用 `tenant_access_token` 搜索结果为空，属正常限制。
   - 如需以用户身份搜索，须通过 OAuth 2.0 流程额外获取 `user_access_token`（超出本 Skill 范围）。

---

## 传参说明

调用本 Skill 时，用户需要明确提供：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_access_token` | string | **是** | 飞书用户授权凭证，格式为 `u-xxxx` |
| `search_key` | string | **是** | 要搜索的关键词，例如 `"项目周报"` |
| `count` | int | 否 | 返回文档数量，范围 [1, 50]，默认 `10` |
| `offset` | int | 否 | 偏移量（翻页用），默认 `0`，`offset + count < 200` |
| `docs_types` | list | 否 | 文件类型过滤，可选值：`doc`、`sheet`、`slides`、`bitable`、`mindnote`、`file`。不填则搜索全部类型 |
| `owner_ids` | list | 否 | 按文件所有者 Open ID 过滤，不填则不过滤 |

---

## 执行步骤

### 步骤 0：配置应用凭证（仅首次使用）

编辑本 Skill 目录下的 `config.json`，填入真实的 `app_id` 和 `app_secret`：

```json
{
  "app_id": "cli_你的应用ID",
  "app_secret": "你的应用密钥"
}
```

> 凭证来源：飞书开放平台 → 我的应用 → 选择应用 → 凭证与基础信息。

### 步骤 1：获取 tenant_access_token

运行 `get_token.py` 获取访问凭证（**`Cwd` 设置为本 Skill 所在目录**）：

```bash
# 正常模式（展示 token 和有效期）
python3 ./get_token.py

# plain 模式（仅输出 token 字符串，便于直接复制传入 search.py）
python3 ./get_token.py --plain
```

token 有效期最长 **2 小时**，重复调用若剩余有效期 ≥ 30 分钟则返回原 token，无需担心频繁调用消耗配额。

### 步骤 2：准备搜索参数

从用户对话中提取并整理搜索参数。若用户未提供 `count`，默认设为 `10`；`offset` 默认为 `0`。

### 步骤 3：执行搜索脚本

使用 `run_command` 工具运行 `search.py` 脚本，**`Cwd` 设置为本 Skill 所在目录**，通过命令行参数传入所有配置：

```bash
python3 ./search.py \
  --token "u-your_user_access_token" \
  --key "搜索关键词" \
  --count 10 \
  --offset 0 \
  --types "doc,sheet"
```

> **注意**：`--types` 为逗号分隔的字符串，例如 `"doc,sheet"`；不传则搜全部类型。

脚本会调用飞书 API，将结果以 **Markdown 表格**格式打印到 stdout。

### 步骤 4：解析并展示结果

读取脚本输出的 JSON，进行格式化展示。

**正常情况**（`code == 0`）：

以 Markdown 表格呈现结果，包含以下列：
- **序号**
- **标题**（附飞书文档直达链接）
- **类型**（中文映射，见下方）
- **文档 Token**

文件类型中文映射：

| 英文值 | 中文展示 |
|---|---|
| `doc` | 📄 文档 |
| `sheet` | 📊 电子表格 |
| `slides` | 📑 幻灯片 |
| `bitable` | 🗃️ 多维表格 |
| `mindnote` | 🧠 思维笔记 |
| `file` | 📎 文件 |

同时展示：
- **共找到 X 个文档**（来自 `total` 字段）
- **是否还有更多**（来自 `has_more` 字段）

**异常情况**（`code != 0`）：

直接向用户展示错误码和错误信息，常见错误参考[服务端错误码说明](https://open.feishu.cn/document/ukTMukTMukTM/ugjM14COyUjL4ITN)。

### 步骤 5：向用户汇报

输出搜索结果表格，并根据 `has_more` 提示用户是否可通过增大 `offset` 获取更多结果。

---

## 飞书文档直达链接规则

根据 `docs_type` 和 `docs_token` 拼接跳转链接：

| 类型 | 链接模板 |
|---|---|
| `doc` | `https://docs.feishu.cn/docs/{docs_token}` |
| `sheet` | `https://docs.feishu.cn/sheets/{docs_token}` |
| `slides` | `https://docs.feishu.cn/slides/{docs_token}` |
| `bitable` | `https://docs.feishu.cn/base/{docs_token}` |
| `mindnote` | `https://docs.feishu.cn/mindnotes/{docs_token}` |
| `file` | `https://docs.feishu.cn/file/{docs_token}` |
