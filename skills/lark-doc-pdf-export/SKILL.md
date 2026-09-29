---
name: lark-doc-pdf-export
description: "将禁止下载/导出的飞书文档（docx / wiki）导出为 PDF。当用户要求导出飞书文档为 PDF，但文档设置了禁止下载或导出权限（drive +export 返回 1069902 permission_denied）时使用。通过 API 读取文档全文 + 预览通道下载图片 + 本地 HTML 渲染生成 PDF，全程不需要文档的导出权限。触发词：导出PDF、导出飞书文档、飞书文档转PDF、无权限导出、禁止下载的文档导出。"
---

# 飞书文档 PDF 导出（无导出权限场景）

## 适用场景

文档设置了"禁止下载/导出"，官方 `drive +export` 接口返回 `1069902 permission_denied`，但用户仍有查看权限。

本 Skill 不处理有导出权限的文档——那种情况直接用 `lark-cli drive +export` 即可。

## 工作原理

1. 通过 `docs +fetch` 读取文档全文（DocxXML 格式，含排版结构和图片 token）
2. 提取所有图片 token，通过 `drive +preview` 预览通道逐张下载（预览接口不受"禁止下载"限制）
3. 将 DocxXML 转为带飞书风格排版的 HTML（标题层级、提示框、双栏布局、图片说明等）
4. 用 headless Chrome 将 HTML 渲染为 A4 PDF

## 使用方法

直接运行脚本：

```bash
python3 <skill_dir>/scripts/export_doc_to_pdf.py <飞书文档URL> --output <输出路径.pdf>
```

参数：
- `url`（必填）：飞书 docx 或 wiki 链接
- `--output, -o`（可选）：输出 PDF 路径，默认用文档标题命名保存在当前目录
- `--as`（可选）：lark-cli 身份，默认 `user`
- `--keep-html`（可选）：保留中间 HTML 文件

示例：

```bash
python3 scripts/export_doc_to_pdf.py "https://xxx.feishu.cn/wiki/xxxxx" --output ./report.pdf
```

## 执行步骤（Agent 操作指引）

1. 确认文档无导出权限：调用 `lark-cli drive +export --url <url> --file-extension pdf`，若返回 `1069902` 则进入本 Skill 流程
2. 运行脚本，等待完成（文档图片较多时可能需要 1-3 分钟）
3. 脚本输出会显示页数和图片数，确认与原文一致
4. 通过 `present_files` 交付 PDF

## 注意事项

- 文档中的视频内容会以占位文字标注，无法嵌入 PDF
- 极少数图片若预览通道也无法获取，会以占位框标注，不影响其余内容
- 脚本依赖系统安装的 Google Chrome（`/Applications/Google Chrome.app`），已加 `--password-store=basic` 避免钥匙串弹窗
- 中间文件（图片、HTML）在临时目录中自动清理，加 `--keep-html` 可保留 HTML 用于检查
