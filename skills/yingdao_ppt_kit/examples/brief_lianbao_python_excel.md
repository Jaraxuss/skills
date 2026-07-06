# Yingdao Customer PPT Creative Brief

## Basic Info

- Title: 影刀 RPA 进阶：Python 数据处理库在 Excel 自动化中的应用
- Customer: 合肥联宝供应链部门
- Audience: 业务人员为主，已完成第一阶段影刀基础培训
- Duration: 2小时
- Use case: 客户培训
- Output filename: 影刀RPA进阶_合肥联宝_Python数据处理库Excel自动化.pptx

## Business Context

- 客户当前已经完成第一阶段影刀基础培训。
- 本次内容承接上一阶段，不重复基础 Excel 指令。
- 客户 IT / 数字化团队希望业务部门理解影刀可以与 Python、AI、系统接口等能力结合，解决复杂流程卡点。
- 供应链场景中存在大量 Excel 报表处理、多表匹配、异常筛选和结果分发需求。

## Deck Context

- Source summary: 第二天课程围绕 Python 数据处理库在 Excel 自动化中的应用，重点讲清 Python 与影刀的分工，并用供应链报表处理案例解释 Pandas / NumPy 的业务价值。
- Core claim: 影刀负责流程动作和业务闭环，Python 负责复杂数据规则，两者结合可以把高频 Excel 报表处理沉淀成稳定的自动化链路。
- Canonical terms: 影刀 RPA、Python、Pandas、NumPy、DataFrame、Excel 报表、多表匹配、异常筛选、分组汇总、字段标准化、流程闭环。
- Audience assumptions: 学员已经了解影刀基础操作，但不是程序员；页面表达要从业务问题出发，再解释关键代码能力。
- Reusable business frame: 输入报表 -> 数据规则 -> 输出结果 -> 影刀接回通知/归档/分发。

## Goals

1. 让客户理解 Python 在 RPA 数据处理中的定位。
2. 讲清楚影刀负责流程编排、系统操作、文件流转；Python 负责复杂数据清洗、匹配、筛选、汇总、格式转换。
3. 用供应链/Excel 数据处理场景组织内容，突出业务价值。
4. 每个核心知识点配一个业务例子，避免抽象概念堆砌。
5. 输出适合直接对客讲解的 PPT。

## Content Scope

- Python 在 RPA 数据处理中的定位
- Python 基础数据结构与 Excel 数据的关系
- NumPy 基础：批量计算与数组处理
- Pandas 基础：读取 Excel、查看数据、筛选数据、新增计算列、缺失值处理、输出 Excel
- Pandas 处理 Excel 常见业务场景：批量清洗、多表匹配、异常筛选、分组汇总、字段拆分与格式转换
- Python 处理结果如何接回影刀 RPA 流程
- 总结：什么场景用影刀，什么场景用 Python

## Visual Direction

- 参考影刀品牌 PPT：白底、红色强调、浅粉氛围、干净商务。
- 需要图片或信息图，不要只使用文本框和代码框。
- 可以生成供应链办公室、Excel 数据清洗、多表匹配、自动化流程闭环等主题插图。
- Logo 使用 `assets/yingdao_logo.png`。
- Style identity rule: 保持影刀红白粉主视觉，每页按内容语义改变构图，不复制同一种三卡片布局。
- Optional sample gate: 可直接生成；若用于正式客户精修，可先选“案例 2：多表匹配”作为代表性样张渲染确认。

## Asset Map

| Asset | Type | Role | Fidelity Requirement | Target Slide |
| --- | --- | --- | --- | --- |
| `assets/yingdao_logo.png` | strict input asset | 品牌标识 | 保持 logo 可见、比例正常、不变色 | 全 deck |
| 影刀网页版生成的优秀 PPT 或导出图 | style reference | 参考视觉完整度、图片使用、层级关系 | 借鉴构图节奏，不复制内容 | deck-level |
| 固定脚本“拉胯样张”截图 | style reference / anti-pattern | 识别重复卡片、代码过小、缺少图片的问题 | 只作为反例，不作为模板 | deck-level |
| 供应链数据处理 / Excel 自动化场景图 | generated visual | 体现客户业务感 | 匹配影刀红白粉主视觉，避免泛化 stock 图 | Cover、Context、Workflow |

## Structured Slide Plan

| Slide | Role | Intent | Key Points | Layout Family | Visual Asset | Density | Local Context / Speaker Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cover | 建立正式客户培训开场 | 影刀 RPA 进阶；Python 数据处理库；Excel 自动化应用 | title + hero visual | generated visual: 供应链数据处理 | low | 强调这是第二阶段进阶课程 |
| 2 | setup | 说明为什么需要进阶数据能力 | 基础操作解决流程动作；复杂报表需要规则沉淀；Python 处理数据规则 | statement + business scene | generated visual: 业务报表痛点 | low-medium | 避免讲成纯编程课，改成业务链路升级 |
| 3 | map | 呈现 2 小时课程路线 | 能力定位；数据结构；NumPy/Pandas；业务案例；流程闭环 | route map | icons / step map | medium | 让客户知道每部分对应业务结果 |
| 4 | comparison | 对齐影刀与 Python 分工 | 影刀负责系统动作；Python 负责复杂数据处理；组合形成端到端闭环 | role split comparison | 对比图 | medium | 先讲业务边界，再讲工具能力 |
| 5 | concept | 把 Excel 映射到 Python 数据结构 | 工作簿/工作表；行/列；字段/记录；DataFrame | table + callout | 信息表格 | medium | 用业务人员熟悉的 Excel 语言解释 |
| 6 | concept | 解释 NumPy 和 Pandas 的适用位置 | NumPy 偏批量计算；Pandas 偏表格处理；Excel 自动化主要用 Pandas | two-column explainer | 概念对比 | medium | 不展开底层数学细节 |
| 7 | concept | 建立 Pandas 常用能力清单 | 读取；查看；筛选；新增列；缺失值；输出 | toolbox grid | 小型能力卡 + 流程线 | medium | 每个能力都连接到报表处理动作 |
| 8 | case | 案例 1：批量清洗 Excel 数据 | 业务问题；清洗规则；输出标准表 | case story | generated visual + code snippet | medium | 关键规则：空值、日期、金额、编码格式 |
| 9 | case | 案例 2：多表匹配替代重复 VLOOKUP | 订单表与主数据匹配；未匹配输出；结果可追踪 | split layout | strict/example table if provided; generated matching visual | medium | 可作为样张 gate 的代表页面 |
| 10 | case | 案例 3：多条件筛选异常数据 | 交期、库存、金额等异常条件；筛选异常清单 | process + code | flow arrows + code snippet | medium | 只放核心筛选条件，不放完整脚本 |
| 11 | case | 案例 4：分组汇总与报表统计 | 按供应商/物料/日期汇总；形成稳定统计口径 | data table + summary | 简化表格 / 小图表 | medium-high | 表格必须可读，必要时拆页 |
| 12 | case | 案例 5：字段拆分与格式转换 | 字段标准化；日期/编码统一；生成唯一键 | transformation pipeline | 步骤条 + code snippet | medium | 解释唯一键服务匹配、去重、追踪 |
| 13 | process | 说明 Python 输出如何接回影刀 | 获取数据；Python 处理；输出结果；影刀通知归档 | automation loop | generated workflow visual | medium | 回到 RPA 端到端价值 |
| 14 | matrix | 判断什么场景用影刀，什么场景用 Python | 流程动作 vs 数据规则；简单 Excel vs 复杂清洗；汇总报表 | decision matrix | 表格 / 判断矩阵 | medium-high | 让业务和 IT 对齐边界 |
| 15 | summary | 收束到客户下一步行动 | 选场景；梳规则；接流程；真实 Excel 场景讨论 | action checklist | 三步行动卡 + Q&A | low-medium | 引导学员提出真实报表场景 |

## Customer-Facing Copy Rules

- 页面文字必须能直接对客户展示。
- 不出现内部备课话术。
- 用业务结果解释代码能力。
- 每页文字不要过满。

## Visual Anti-Patterns

- 不要重复固定三卡片布局。
- 不要让代码块占据大部分页面。
- 不要做成只有白底、浅粉圆环和文字框的模板化页面。
- 不要出现看不清的代码或拥挤表格。
- 不要默认做成整页图片 PPT，除非客户明确接受不可编辑页面。
- 不要把参考风格里的非影刀主色迁移成主视觉。

## Acceptance Criteria

- 首屏像正式客户培训材料。
- 至少部分页面有图片、截图、信息图或流程图。
- 案例页先讲业务问题和结果，再讲关键代码。
- 整体版式有节奏变化。
- 渲染预览无明显重叠、裁切、溢出、断图。
- 页面内容能对应 structured slide plan，偏离计划时必须是为了提升故事表达。
- 如使用客户提供截图或表格，必须按 `strict input asset` 保留业务含义。
- 交付说明包含源材料、视觉资产、渲染 QA 结果和已知限制。
