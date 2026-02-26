# AI Power 工作流 JSON Schema 参考

## 顶层结构

```json
{
  "edges": [],            // Edge[] — 节点间的连线，定义数据流向
  "inputsSchemas": [],    // InputSchema[] — 工作流输入面板定义（与 input 节点一一对应）
  "nodes": [],            // Node[] — 所有节点
  "outputsSchemas": []    // OutputSchema[] — 工作流输出面板定义（与 output 节点一一对应）
}
```

---

## Edge 对象

连接两个节点，定义数据从 `source` 流向 `target`。

```json
{
  "id": "01H6Z57WAGPTMM345R3NDVZED4",        // ULID，全局唯一
  "source": "01H6Z57S1T...",                   // 源节点 UUID
  "target": "01H6Z57DQDEY4...",                // 目标节点 UUID
  "sourceHandle": "{source_uuid}-1-{output_apiName}",  // 可选，精确指定源端口
  "targetHandle": "{target_uuid}-in-in-mask",          // 可选，精确指定目标端口（或 {uuid}-1-{input_name}-in-mask）
  "type": "ClosableEdge",
  "animated": true,
  "selected": false,
  "data": { "weight": "1" },                   // 可选，条件分支用 "1000" 表示满足条件
  "markerEnd": { "color": "#9DA0B3", "width": 25, "type": "arrowclosed", "height": 10 },
  "style": { "strokeWidth": 2, "strokeLinejoin": "miter", "strokeDashoffset": 2, "stroke": "#9DA0B3", "strokeDasharray": 4 }
}
```

### Edge Handle 命名规则

| 场景 | sourceHandle | targetHandle |
|------|-------------|--------------|
| 简单连接（无歧义） | 不需要 | 不需要 |
| 多输出节点指定端口 | `{uuid}-1-{output_apiName}` | `{uuid}-in` 或 `{uuid}-in-in-mask` |
| 指定目标输入端口 | — | `{uuid}-1-{input_name}-in-mask` |
| 条件分支满足条件 | `{uuid}-1000` | — |
| 条件分支不满足 | `{uuid}-1` | — |

---

## Node 对象

```json
{
  "uuid": "01H6Z57NEGPDEAX3VA7NHDD46C",   // ULID，全局唯一
  "functionName": "llm",                    // 节点类型标识（参见 node_catalog.json）
  "name": "ai_llm",                         // 节点内部名称
  "title": "大语言模型",                     // 显示名称（可自定义）
  "desc": "大语言模型，根据Prompt输出内容",    // 描述（通常保持默认）
  "version": "1.13.0",                      // 节点版本
  "position": { "x": 500, "y": 200 },       // 画布坐标
  "inputs": [...],                           // 输入参数数组
  "outputs": [...]                           // 输出参数数组
}
```

### Position 布局建议

节点从左到右排列，水平间距约 **400-500px**，垂直间距约 **250px**：

```
input 节点:    x=100,   y=200
处理节点:      x=500,   y=200
LLM 节点:     x=900,   y=200
output 节点:  x=1300,  y=200
```

并行节点垂直排列（同一 x，不同 y），间距约 250px。

---

## InputsSchemas

与 `input_text` / `input_image` 节点一一对应，定义工作流运行时的输入面板。

```json
{
  "uuid": "01H839QH4VSMMH...",     // 对应 input 节点的 UUID
  "name": "input_text",             // 与节点 name 相同
  "inputs": [{                      // 面板配置
    "component": {
      "editableLabel": true,
      "runtime": true,
      "renderType": "variableInput",   // input_text 用 variableInput，input_image 用 imageInput
      "props": { "autoSize": { "minRows": 1, "maxRows": 15 } }
    },
    "defaultValue": "",
    "name": "text",                    // input_text 固定为 "text"，input_image 固定为 "image"
    "label": "请输入文本",              // 面板显示标签（可自定义）
    "type": "TEXT",                    // TEXT 或 IMAGE
    "value": "",
    "required": true
  }],
  "outputs": [{                     // 与节点 outputs 完全相同
    "apiName": "input_text_0",
    "name": "input_text_0",
    "type": "TEXT"
  }]
}
```

---

## OutputsSchemas

与 `output_text` / `output_image` / `output_table` 节点一一对应，定义工作流运行后的输出面板。

```json
{
  "uuid": "01H839QMNQNPJF...",    // 对应 output 节点的 UUID
  "name": "output_text",           // 与节点 name 相同
  "inputs": [...],                 // 面板字段配置（参见 node_catalog.json 中各 output 节点的 outputsSchema）
  "outputs": [{                    // 与节点 outputs 完全相同
    "apiName": "output_text_0",
    "name": "output_text_0",
    "type": "TEXT"
  }]
}
```

---

## 变量引用语法 `{{}}`

| 语法 | 说明 | 示例 |
|------|------|------|
| `{{output_apiName}}` | 引用节点输出 | `{{openai_llm_0}}` |
| `{{output_apiName.字段}}` | 引用 JSON 输出的子字段 | `{{text_json_0.持证人}}` |
| `{{自定义name}}` | 引用自定义命名的输出 | `{{申请人姓名}}` |

### 变量解析规则
1. 变量名对应上游节点 `outputs` 中的 `name` 或 `apiName`
2. JSON 类型输出可用 `.` 访问子字段
3. 变量只能引用**直接或间接上游**节点的输出（沿 Edge 方向可达）

---

## UUID / ULID 生成规则

所有 UUID 使用 [ULID](https://github.com/ulid/spec) 格式：
- 26 个字符，Crockford Base32 编码
- 前 10 字符是时间戳，后 16 字符是随机数
- 示例：`01H6Z57NEGPDEAX3VA7NHDD46C`

生成时保证：
1. 同一工作流内所有 UUID 唯一
2. Edge ID、Node UUID、InputsSchemas UUID、OutputsSchemas UUID 不重复
