---
name: 从 PDF 提取高质量图片资源
description: 从 PDF 文件中提取高清整页大图以及无损的原始内嵌图像素材（如 Logo、系统截图），并通过 AI 清洗后生成标准的 assets_manifest.json 供下游使用。
---

# 从 PDF 提取高质量图片资源 Skill (extract_pdf_assets)

本 Skill 用于分析用户提供的原始 PDF 资料，精准、无损地从中提取两类核心资源：
1. **完整的高清页面大图**（作为整体背景或对照参考）
2. **纯粹原生的内部图片素材**（无 AI 重绘失真，直接剥离原始无损像素，如各种软件 Logo、系统高清截图等）

并将提取后的资源经过 AI 智能清洗、规范命名，统一输出到 `assets/extracted/[页面名]/` 目录，最终生成 `assets_manifest.json` 作为下游 Skill（如 `generate_html_from_material`）的输入数据。

## 核心价值

- **绝对无损**：使用 `pdfimages` 从底层剥离 PDF 中原路贴入的位图数据，杜绝 AI 截图识别造成的画面篡改（“脑补”）或模糊失真。
- **自动化分拣**：借助大模型视觉理解能力，自动剔除无意义的背景色块、细小线条等噪点，精准抽取出真正有业务价值的图像素材。
- **大图兜底**：同步生成完整的高质量页面大图，保留排版的原生上下文。
- **标准化输出**：自动生成详尽的 JSON 清单，规范化向下打通。

---

## 适用场景

1. **拥有原厂 PDF / PPT 导出 PDF**：只要客户提资是含高质量配图的 PDF 文件。
2. **对真实截图有强诉求**：比如 SAP、ERP 系统截图，Excel 详表截图，其中微小文字绝不能被 AI 破坏。
3. **工作流 Logo 提取**：在工作流中要摆放很多各系统真实的 Logo 但懒得满网去找原图。

---

需要操作系统内安装了 `poppler` 工具集。
- 检查命令：`pdfimages -v` 和 `pdftoppm -v`
- 通常在 Mac 下可以使用 `brew install poppler` 安装。

**推荐安装助手**：
- **ImageMagick**：用于自动合并透明度蒙版（SMask）。安装：`brew install imagemagick`。

---

## 传参说明

调用本 Skill 需要用户明确提供：
- **`pdf_path`**: PDF 文件的绝对路径（如 `/Users/velen/.../xxx.pdf`）。
- **`target_page`**: 需要提取的 PDF 具体页码（第几页，例如 `4`）。

*注意：`page_name` 不需要用户手动提供。本 Skill 会自动分析提取出来的页面大图的左上角标题作为 `page_name`。*

---

## 执行步骤

### 步骤 1：提取整页高清大图 (pdftoppm)

首先将特定也整体渲染为一张高质量底图输出到临时目录（分辨率建议 300dpi）：

```bash
# 生成并暂存大图
mkdir -p ./temp_pdfimages/full_pages
pdftoppm -png -r 300 -f [target_page] -l [target_page] "[pdf_path]" "./temp_pdfimages/full_pages/page"
```
*这会在临时目录生成类似于 `page-04.png` 或 `page-1.png` 的文件。*

### 步骤 2：识别 page_name 并创立目标目录

Agent 使用视觉能力（`view_file`）查看生成的这页大图，读取其 **左上角的大标题**，作为本页面的业务主题名 `[page_name]`（如标题是 `采购每日原材料价格获取`，则 `page_name=采购每日原材料价格获取`）。

随后创建正式工作目录，并将生成的大图挪动至正式位：

```bash
mkdir -p "./assets/extracted/[page_name]"
mkdir -p "./temp_pdfimages/[page_name]"
mv "./temp_pdfimages/full_pages/page-"*".png" "./assets/extracted/[page_name]/full_page.png"
```

### 步骤 3：无损剥离内嵌碎片素材 (pdfimages)

使用 `pdfimages` 瞬间把该页内挂载的所有“底片资源”无损吐出来：

```bash
pdfimages -png -f [target_page] -l [target_page] "[pdf_path]" "./temp_pdfimages/[page_name]/img"
```
*这会在临时目录生成一大堆 `img-000.png`、`img-001.png` 等散图文件。*

**进阶技巧：检查透明度蒙版 (SMask)**
运行以下命令查看图片列表，寻找带有 `smask` 标识的对象：
```bash
pdfimages -list -f [target_page] -l [target_page] "[pdf_path]"
```
如果看到 `num` 连续的对象（如 16 和 17），且其中一个类型是 `smask`，说明这两个文件分别是**颜色层**和**透明蒙版层**，需要后续合并。

### 步骤 4：AI 智能分拣与清洗 (核心环节)

这一步你需要作为 AI Agent 发挥“大脑”的作用，对 `temp_pdfimages/[page_name]` 内的散图进行地毯式审查（可以使用 `view_file` 人肉看，或是写临时 Python 脚本调用 `PIL / OpenAI Vision API` 来批量看）：

#### 过滤清洗规则：
1. **尺寸过滤**：自动丢弃/忽略长或宽小于 30px 的极小线条、黑点。
2. **比例过滤**：自动丢弃长宽比超过 1:10 或 10:1 的极端长条（通常是边界线或背景装饰）。
3. **内容甄别 (Vision)**：
   - 如果图像是 **系统/软件截图、电子表格（Excel）**，则保留，归类为 `system_screenshot` 或 `excel_preview`。
   - 如果图像是 **某个公司/产品的应用图标、Logo**，则保留，归类为 `workflow_icon`。
   - 其他背景色块、被切掉一半的残缺元素、毫无意义的点缀块全部丢弃！

#### 透明度处理 (针对 Logo)：
如果发现 Logo 呈现“黑底”且有一个对应的灰度蒙版图，**必须合并**以还原透明效果：

- **使用 ImageMagick (推荐)**：
  ```bash
  magick [颜色图].png [蒙版图].png -alpha off -compose copy_opacity -composite [输出文件名].png
  ```
- **使用 Python (PIL) 备选方案**：
  编写简单脚本将蒙版转换为 Alpha 通道：`img.putalpha(mask.convert("L"))`。

#### 转移重命名：
将成功甄别（并修复透明度）为有效素材的图片，**拷贝并重命名** 到正式目录：
- 从 `./temp_pdfimages/[page_name]/img-016_merged.png` 移动变成 
- `./assets/extracted/[page_name]/workflow_icon_smm.png` （需自己根据认出的 Logo 定义英文后缀）

*完成识别与转移后，可安全删除 `temp_pdfimages/[page_name]` 这个临时目录。*

### 步骤 5：生成 assets_manifest.json

仔细汇总刚刚生成的全景大图和精选后的细部素材，在 `./assets/extracted/[page_name]/` 下写入规范的 `assets_manifest.json` 文件。

```json
{
  "page_name": "[page_name]",
  "extracted_at": "[ISO 时间戳]",
  "source_pdf": "[pdf_path]",
  "source_page": [target_page],
  "full_page_render": "./assets/extracted/[page_name]/full_page-01.png",
  "assets": [
    {
      "id": "workflow_icon_sci99",
      "type": "workflow_icon",
      "path": "./assets/extracted/[page_name]/workflow_icon_sci99.png",
      "label": "卓创咨询",
      "description": "SCI99.COM 卓创资讯 Logo",
      "html_usage": "workflow_step"
    },
    {
      "id": "excel_preview_summary",
      "type": "excel_preview",
      "path": "./assets/extracted/[page_name]/excel_preview_summary.png",
      "label": "汇总成表",
      "description": "价格汇总 Excel 表格无损原切截图",
      "html_usage": "right_column_preview"
    }
  ]
}
```

### 步骤 6：向用户汇报

提取完成！使用 `notify_user` 或直接气泡回复告知用户素材提取的路径、提取到了多少个高质量素材，并推荐下游可以直接将其传入 `generate_html_from_material` 技能，通过真实图片增强网页真实感。
