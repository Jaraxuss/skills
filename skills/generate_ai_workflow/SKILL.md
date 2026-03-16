---
name: generate_ai_workflow
description: 根据用户需求生成 AI Power 工作流 JSON 文件
---

# AI Power 工作流生成 Skill

根据用户的需求描述，生成可直接导入 AI Power 平台的工作流 JSON 文件。

## 前置知识

在执行本 Skill 前，你必须先阅读以下参考文件：
1. **节点注册表**：`references/node_catalog.json` — 所有节点类型的完整字段定义
2. **Schema 参考**：`references/schema_reference.md` — JSON 格式规范
3. **模式模板**：`templates/` 目录下的对应模板
4. **官方示例（可选）**：`AI工作流参考示例/` 目录（本仓库默认仅保留占位，可自行补充官方样例 JSON）

---

## 阶段 1：需求分析

从用户的需求描述中，提取以下结构化信息：

```
需求摘要：
├─ 任务名称：      （如"发票信息识别"）
├─ 输入类型：      TEXT / IMAGE / TEXT+IMAGE / 多个TEXT
├─ 输出类型：      TEXT / IMAGE / TEXT+IMAGE / TABLE / 多个输出
├─ 核心能力：      LLM文本生成 / OCR识别 / 多模态理解(Vision) / 文生图 / 图生图 / 知识库搜索 / 数据库查询
├─ 是否多步骤：    是否需要中间处理（JSON解析、代码执行、条件判断等）
├─ 是否需要知识库：是/否
├─ 是否需要数据库：是/否
├─ 是否需要审核判断：是/否
└─ 特殊说明：      （用户额外要求）
```

---

## 阶段 2：模式匹配

根据需求摘要，按以下决策树选择模板：

```
用户需求
├─ 需要数据库? → database_query 模式
├─ 需要审核/材料图片+多条件判断? → complex_review 模式
├─ 需要知识库? → knowledge_base 模式
├─ 输入包含图片?
│   ├─ 需要生成多张图片/套图? → multi_output 模式（图生图变体）
│   └─ 需要分析/提取图片内容? → image_analysis 模式
├─ 需要拆分为多个结构化输出? → multi_output 模式
└─ 其他 → simple_linear 模式
```

### 模板位置

| 模式名 | 文件路径 |
|--------|---------|
| `simple_linear` | `templates/simple_linear.json` |
| `image_analysis` | `templates/image_analysis.json` |
| `multi_output` | `templates/multi_output.json` |
| `knowledge_base` | `templates/knowledge_base.json` |
| `database_query` | `templates/database_query.json` |
| `complex_review` | `templates/complex_review.json` |

### 多模式混合

如果需求跨越多个模式（如"图片识别+知识库搜索"），应：
1. 选择主模式作为骨架
2. 从其他模式中补充需要的节点
3. 参考 `references/node_catalog.json` 构建额外节点
4. 参考 `AI工作流参考示例/` 中的类似官方示例

---

## 阶段 3：模板填充

### 步骤 3.1：读取模板

读取选中的模板 JSON 文件，理解其骨架结构。

### 步骤 3.2：生成 UUID

为每个节点和每条 Edge 生成新的 ULID 格式 UUID：
- 格式：26 个字符，Crockford Base32
- 确保同一工作流内所有 UUID 唯一
- **重要**：生成后，需要更新所有引用该 UUID 的地方（Edge 的 source/target、inputsSchemas 的 uuid、outputsSchemas 的 uuid、Edge 的 sourceHandle/targetHandle）

### 步骤 3.3：填充节点内容

根据用户需求填充以下字段：

#### 输入节点
- `inputs[].label`：设置有意义的输入提示（如"请输入产品名称"、"请上传发票照片"）
- `outputs[].name`：可自定义为有意义的变量名（如"产品名称"而非"input_text_0"）

#### LLM 节点
- `inputs.channel`：选择合适的厂商
  - `azure`（OpenAI 系列），`deepseek`，`gemini`
- `inputs.model`：选择合适的模型
  - 文本生成/创意类：`gpt-5.2`
  - 精确/代码/分析类：`gpt-4o`、`deepseek-chat`
  - 多模态/视觉类：`gemini-3-flash`、`gemini-2.5-flash`（用 vision 节点）
  - 性价比优先：`deepseek-chat`
- `inputs.temperature`：创意程度
  - 创意文案类：0.7-1.0
  - 分析/提取类：0-0.3
  - 通用：0.5
- `inputs.system`：**核心** — 根据用户需求编写高质量的 System Prompt
- `inputs.user`：用户输入 Prompt，通过 `{{变量名}}` 引用上游输出

#### 输出节点
- `inputs[1].label`：设置有意义的输出标签（如"分析结果"、"生成的文案"）

### 步骤 3.4：构建 Edge 连接

根据节点间的数据依赖关系构建 Edge：

1. 每条 Edge 需要新的 ULID 作为 `id`
2. `source` 设为上游节点 UUID，`target` 设为下游节点 UUID
3. Edge 样式使用固定模板（参见 `node_catalog.json` 中的 `edge_template`）
4. 多输入节点需要设置 `sourceHandle` 和 `targetHandle`：
   - `sourceHandle`: `{source_uuid}-1-{output_apiName}`
   - `targetHandle`: `{target_uuid}-in-in-mask` 或 `{target_uuid}-1-{input_name}-in-mask`

### 步骤 3.5：计算 Position 坐标

按照从左到右的布局排列节点：
- 水平间距：400-500px
- 垂直间距：250px（并行节点）
- 输入节点从 x=100 开始
- 后续节点每层增加 ~450px

### 步骤 3.6：同步 InputsSchemas 和 OutputsSchemas

- `inputsSchemas`：与所有 `input_text` / `input_image` 节点一一对应
  - `uuid` 与对应 input 节点 UUID 相同
  - `inputs[].label` 与节点 `inputs[].label` 相同
  - `outputs` 与节点 `outputs` 相同
- `outputsSchemas`：与所有 `output_text` / `output_image` / `output_table` 节点一一对应
  - `uuid` 与对应 output 节点 UUID 相同
  - 面板配置参考 `node_catalog.json` 中各 output 节点的 `outputsSchema`
  - `inputs[0].value`（param_variable 的 value）与节点中 `param_variable` 的 value 相同

### 步骤 3.7：增减节点（如需要）

如果模板的节点数量与实际需求不匹配：

**增加节点时**：
1. 从 `node_catalog.json` 获取节点字段模板
2. 生成新 UUID
3. 设置合理的 Position
4. 增加对应的 Edge
5. 如果是 input/output 节点，同步更新 inputsSchemas/outputsSchemas
6. 多个同类节点时，`outputs[].apiName` 需递增（如 `output_text_0`, `output_text_1`, `output_text_2`）

**删除节点时**：
1. 删除节点本身
2. 删除相关 Edge
3. 如果是 input/output 节点，同步删除 inputsSchemas/outputsSchemas

---

## 阶段 4：校验

生成 JSON 后，按以下清单逐项校验：

### 4.1 结构完整性
- [ ] JSON 顶层包含 `edges`、`inputsSchemas`、`nodes`、`outputsSchemas` 四个数组
- [ ] 可被 `JSON.parse()` 正确解析（无语法错误）

### 4.2 节点完整性
- [ ] 每个节点都有 `uuid`、`functionName`、`name`、`title`、`version`、`position`、`inputs`、`outputs`
- [ ] 所有 UUID 在整个 JSON 内唯一（节点间不重复，节点与 Edge ID 不重复）
- [ ] 节点 `functionName` 和 `name` 与 `node_catalog.json` 中的定义匹配

### 4.3 Edge 完整性
- [ ] 每条 Edge 都有唯一 `id`
- [ ] 每条 Edge 的 `source` 指向一个存在的节点 UUID
- [ ] 每条 Edge 的 `target` 指向一个存在的节点 UUID
- [ ] `sourceHandle`（如存在）格式正确且引用的 output_apiName 存在
- [ ] `targetHandle`（如存在）引用的节点 UUID 存在

### 4.4 变量引用完整性
- [ ] 所有 `{{变量名}}` 引用都能解析到某个上游节点的 `outputs[].name` 或 `outputs[].apiName`
- [ ] 不存在循环引用（A 引用 B、B 引用 A）

### 4.5 Schema 一致性
- [ ] `inputsSchemas` 数量 == `input_text` + `input_image` 节点数量
- [ ] `outputsSchemas` 数量 == `output_text` + `output_image` + `output_table` 节点数量
- [ ] 每个 Schema 的 `uuid` 与对应节点 UUID 匹配
- [ ] 每个 Schema 的 `outputs` 与对应节点 outputs 一致

---

## 阶段 5：输出

### 输出文件
将生成的 JSON 保存到项目目录下：
```
生成的工作流/{工作流名称}.json
```

### 输出说明
同时提供一段简要的设计说明，包含：
1. **工作流名称**
2. **使用的模式**（如"简单线性"、"图片分析"等）
3. **节点清单**（列出所有节点及其作用）
4. **数据流向**（简要描述数据如何从输入流向输出）
5. **需要用户配置的项**（如知识库 ID、数据库 ID、API Key 等）

---

## 补充说明

### Prompt 编写原则

为 LLM 节点编写 System Prompt 时，遵循以下原则：
1. **角色定义**：明确 AI 扮演的角色
2. **任务描述**：清晰说明任务目标
3. **输出格式**：指定输出的格式要求（纯文本/JSON/Markdown等）
4. **约束条件**：列出必须遵守的规则
5. **示例**（可选）：提供1-2个输入输出示例

参考 `AI工作流参考示例/` 中的官方 Prompt 获取灵感。

### 模型选择指南

| 场景 | 推荐模型 | channel |
|------|---------|---------|
| 通用文本生成 | gpt-5.2 | azure |
| 精确分析/代码 | gpt-4o | azure |
| 多模态视觉理解 | gemini-3-flash | gemini |
| 高级推理 | gemini-2.5-flash | gemini |
| 性价比优先 | deepseek-chat | deepseek |
| 文生图 | gpt-image-1.5 | azure |
| 图生图 | gemini-3-pro-image-preview | google |

### 从官方示例学习

如果用户的需求与某个官方示例非常相似，优先参考该示例的 JSON 结构：
1. 在 `AI工作流参考示例/` 目录中查找相关文件
2. 读取其 JSON 内容
3. 理解其 Prompt 写法和节点连接方式
4. 基于该示例进行调整
