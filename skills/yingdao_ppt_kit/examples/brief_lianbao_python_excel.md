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

## Page-Level Intent

| Slide | Purpose | Must Say | Suggested Visual |
| --- | --- | --- | --- |
| 1 | Cover | 影刀 RPA 进阶与 Python 数据处理主题 | 供应链数据处理 hero visual |
| 2 | Context | 为什么基础 Excel 自动化后需要进阶数据能力 | 业务痛点视觉 |
| 3 | Course map | 课程模块和业务落点 | 路线图 |
| 4 | Role split | 影刀与 Python 的分工 | 对比图 |
| 5 | Data mapping | Excel 与 DataFrame/字段/记录关系 | 表格或信息图 |
| 6-10 | Business cases | 清洗、匹配、异常、汇总、字段转换 | 每页一个业务案例，代码只放关键片段 |
| 11 | Workflow closure | Python 输出接回影刀 | 流程图 |
| 12 | Scenario judgment | 什么场景用影刀，什么场景用 Python | 判断矩阵 |
| 13 | Landing advice | 如何选场景、梳字段、接流程 | 行动清单 |
| 14 | Summary/Q&A | 复杂数据处理更简单，自动化链路更稳定 | 简洁总结页 |

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

## Acceptance Criteria

- 首屏像正式客户培训材料。
- 至少部分页面有图片、截图、信息图或流程图。
- 案例页先讲业务问题和结果，再讲关键代码。
- 整体版式有节奏变化。
- 渲染预览无明显重叠、裁切、溢出、断图。
