---
name: 根据资料生成 HTML 页面
description: 根据用户上传的资料（文字、图片、视频等）和指定的风格类型，查找 references/html_style_summary 目录下的风格总结文件，生成符合规范的 HTML 页面
---

# 根据资料生成 HTML 页面 Skill

本 Skill 用于根据用户提供的资料（文字、图片、视频等）和指定的页面风格类型，参考 `references/html_style_summary/` 目录下的风格总结文件，生成符合项目规范的 HTML 页面。

## 适用场景

- 需要快速创建新的 HTML 演示页面
- 确保所有页面风格统一
- 将产品资料转换为标准化的展示页面

---

## 前置条件

1. 用户需要提供：
   - **资料内容**：文字描述、图片、视频等素材
   - **页面风格类型**：从以下五种中选择一种
     - 章节页
     - 标准含视频详情页
     - 一般详情页
     - 详情页_背景_痛点_方案_价值_细节（适合业务案例场景，含左右分栏、工作流、价值卡片）
     - 启动会首页风格（适合项目首页/封面页，含大标题、副标题、底部特性卡片）
   - **页面文件名**：目标 HTML 文件的名称

2. 确保 `references/html_style_summary/` 目录下存在对应的风格总结文件：
   - `01_章节页风格.md`
   - `02_标准含视频详情页风格.md`
   - `03_一般详情页风格.md`
   - `04_详情页_背景_痛点_方案_价值_细节.md`
   - `05_启动会首页风格.md`

---

## 步骤 1：确认用户输入

### 1.1 收集必要信息

向用户确认以下信息：

| 信息项 | 说明 | 示例 |
|--------|------|------|
| **页面风格** | 五种类型之一 | 详情页_背景_痛点_方案_价值_细节 |
| **页面标题** | 主标题文字 | 超复杂表单识别并填写 |
| **场景分类（副标题）** | 场景所属分类，04风格专用 | 财务自动化 |
| **需求背景** | 业务场景描述，04风格左栏内容 | 财务部门每月需手工处理... |
| **业务痛点** | 痛点列表（一般3条左右，依据素材内容而定），04风格 | 1. 手工操作耗时 2. 容易出错 |
| **解决方案** | 工作流步骤（一般3-5步，依据素材内容而定），04风格 | 上传→识别→填写→导出 |
| **方案价值** | 关键指标数据（2-4个），04风格 | 95% 准确率、节省80%时间 |
| **右侧展示内容** | 数据预览/文件展示，04风格 | Excel表格数据/PDF文件 |
| **客户名称** | 项目客户名，05风格专用 | 某某科技 |
| **项目标语（Slogan）** | 核心价值主张，05风格 | 构建自动化内容流水线 |
| **底部特性卡片** | 三张核心特性卡（标题+描述），05风格 | 内容矩阵/自动化流水线/飞书协同 |
| **联系人信息** | 姓名+电话，05风格右下角 | 图南 / 199-5165-6379 |
| **功能要点** | 核心功能列表，其他风格 | 1. 自动回复 2. 数据统计 |
| **视频路径** | 仅视频详情页需要 | ./assets/videos/demo.mp4 |
| **图片素材** | 用户上传的图片 | [用户上传图片] |
| **文字描述** | 详细内容描述 | [用户提供文字] |

### 1.2 确定页面类型

根据用户指定的风格类型，确定要参考的风格总结文件：

- **章节页** → 查看 `references/html_style_summary/01_章节页风格.md`
- **标准含视频详情页** → 查看 `references/html_style_summary/02_标准含视频详情页风格.md`
- **一般详情页** → 查看 `references/html_style_summary/03_一般详情页风格.md`
- **详情页_背景_痛点_方案_价值_细节** → 查看 `references/html_style_summary/04_详情页_背景_痛点_方案_价值_细节.md`
- **启动会首页风格** → 查看 `references/html_style_summary/05_启动会首页风格.md`

---

## 步骤 2：查阅风格总结文件

根据用户指定的页面类型，读取对应的风格总结文件。

### 2.1 章节页风格

如果用户选择「章节页」风格，执行：

```
view_file ./references/html_style_summary/01_章节页风格.md
```

重点关注：
- 页面布局结构（居中垂直布局）
- 标题样式（超大字体、品牌色装饰）
- 动画效果（fadeInUp 等）
- 可复用的 HTML 模板代码

### 2.2 标准含视频详情页风格

如果用户选择「标准含视频详情页」风格，执行：

```
view_file ./references/html_style_summary/02_标准含视频详情页风格.md
```

重点关注：
- 头部标题区结构（红色竖条 + 主标题 + 副标题）
- 左右分栏布局（左侧卡片 + 右侧视频）
- 功能卡片组件样式
- 视频播放器组件
- 底部页码装饰
- 动画与入场效果

### 2.3 一般详情页风格

如果用户选择「一般详情页」风格，执行：

```
view_file ./references/html_style_summary/03_一般详情页风格.md
```

重点关注：
- 多种布局变体（痛点+方案、多列卡片、统计数据等）
- 卡片组件类型与样式
- 工作流视图组件
- 数据展示区块样式
- 可复用组件清单

### 2.4 详情页_背景_痛点_方案_价值_细节风格

如果用户选择「详情页_背景_痛点_方案_价值_细节」风格，执行：

```
view_file ./references/html_style_summary/04_详情页_背景_痛点_方案_价值_细节.md
```

重点关注：
- **整体布局**：固定 1280×720，`px-14 py-10`，深蓝外壳 `#0f172a`，页面背景 `#fcfdfe`
- **Header 结构**：场景分类（红色副标题）+ 红色竖条 + 主标题
- **左右分栏**：左栏（50%）放背景/痛点/方案/价值，右栏（50%）放数据/文件预览
- **毛玻璃卡片**（`.glass-card`）：`rgba(255,255,255,0.8)` + `backdrop-filter: blur(12px)`
- **带侧边条卡片**：深色条用于背景/痛点，红色条用于解决方案
- **工作流组件**（`.workflow-box` + `.workflow-step`）：虚线边框 + 步骤图标 + 箭头连接
- **价值卡片**（`.value-card` + `.value-number`）：渐变红色数字 + 悬停上浮
- **Excel/文件预览组件**：右栏常用展示元素
- **动画系统**：`.fragment` + `animation_step` 属性控制分步入场
- **CSS 资源引入**：`../../lib/tailwind@4.js` + `../../lib/font-awesome/all.min.css` + `../../lib/fonts.css`

### 2.5 启动会首页风格

如果用户选择「启动会首页风格」，执行：

```
view_file ./references/html_style_summary/05_启动会首页风格.md
```

重点关注：
- **整体布局**：固定 1280×720，居中对称，全屏背景 `#F8F9FA`
- **背景层**：右上角红色光晕 + 左下角飞书蓝光晕 + 网格点阵纹理
- **顶部标签（Pill Badge）**：圆角全椭圆，红色渐变背景，闪电图标 + 大写品牌文字
- **主标题组合**：主标题 `76px font-bold` + 副标题 `64px` + Slogan（含左右渐变装饰线）
- **底部特性卡片**：三列玻璃拟态卡片（`.glass-card`），高度 `128px`，图标 `64×64px`
  - 卡片配色：橙色（内容矩阵）/ 红色强调（自动化） / 蓝色（飞书协同/其他系统）
- **右下角联系信息**：固定绝对定位，默认 `opacity-60`，hover 渐显
- **入场动画**：`@keyframes fade-in-up` + `.animate-enter`，底部卡片延迟 `0.2s`
- **CSS 资源引入**：`../lib/tailwind@4.js` + `../lib/fonts.css`（注意路径层级）
- **变量占位符**：`{{CLIENT_NAME}}` 替换为实际客户名

---

## 步骤 3：处理用户资料

### 3.0 🚫 严格完整还原原则（严禁缩减/创意发挥）

当根据用户上传的原始图片资料（尤其是 `full_page_render` 等全页原图）或资料文件（如 `assets_manifest.json`）生成 HTML 页面时，**必须严格、完全地还原**原资料中的所有业务逻辑节点、流程图步骤（Workflow）、痛点列表和价值点。
1. **禁止缩减与发挥**：不得为了排版简便而随意删除原有步骤，不得使用 AI 擅自概括、省略、缩减或合并原始步骤。
2. **完整还原工作流**：原始资料或原图工作流中有多少个步骤节点，最终生成的 HTML 页面中的 `.workflow-box` 组件内就必须完整保留多少个 `.workflow-step` 节点，且文字标题与说明必须与原资料一一对应。绝不要因为页面排版或空间问题而自行精简步骤。
3. **精准提取文字**：痛点、背景、方案价值等文字说明应尽可能与原始材料保持完全一致，切勿由于创意发挥而丢失核心业务数据与专有名词。

### 3.1 文字内容处理

将用户提供的文字内容结构化：

- **提取标题**：识别主标题和副标题
- **提取要点**：识别功能列表、价值点、痛点等
- **提取数据**：识别统计数字、效益指标等

### 3.2 图片资料处理

如果用户上传了图片或提供了 `assets_manifest.json` 资源清单：

1. **分析图片内容**：理解图片中的布局、颜色、元素
2. **提取关键信息**：文字、图标、数据等
3. **确定使用方式**：
   - 作为背景图
   - 作为功能展示图
   - 作为图标素材
   - 需要转换为 HTML 元素
4. **图片嵌入强化规范**：
   - **支持点击放大（Lightbox 灯箱）**：对于嵌入页面的主要图片资源（如系统截图、应用展示、Excel 截图等），**必须**内置 Lightbox 灯箱功能，**禁止**使用 `window.open(this.src, '_blank')` 这种粗糙的新标签页方式。具体实现要求：
     1. 在页面 `<body>` 末尾（`slide-core.js` 之前）添加 Lightbox 遮罩容器 `<div id="img-lightbox">`
     2. 在 `<style>` 中内联 Lightbox 相关的 CSS 样式与动画（`.lightbox-overlay`、`.lightbox-img`、`.lightbox-close`、`@keyframes lightbox-fade-in`、`@keyframes lightbox-zoom-in`）
     3. 在 `<script>` 中内联 Lightbox 的 JS 逻辑（打开/关闭/ESC 键盘关闭）
     4. 可点击放大的图片元素统一添加 `class="lightbox-trigger"` 和 `cursor-pointer` 样式
     5. 灯箱交互规范：
        - 点击图片 → 弹出半透明黑色遮罩（`rgba(0,0,0,0.85)`），图片居中以 `scale(0.9)→scale(1)` + `opacity(0→1)` 动画放大展示
        - 右上角显示白色圆形关闭按钮（✕），hover 时旋转90°
        - 点击遮罩背景或关闭按钮 → 关闭灯箱
        - 按 ESC 键 → 关闭灯箱
     6. **完整的 Lightbox 代码模板**如下，直接复制到每个页面中使用：
     
     ```html
     <!-- Lightbox CSS（放入 <style> 标签内） -->
     .lightbox-overlay {
         position: fixed; inset: 0; z-index: 9999;
         background: rgba(0, 0, 0, 0.85);
         display: flex; align-items: center; justify-content: center;
         opacity: 0; pointer-events: none;
         transition: opacity 0.3s ease;
         cursor: zoom-out;
     }
     .lightbox-overlay.active { opacity: 1; pointer-events: auto; }
     .lightbox-overlay .lightbox-img {
         max-width: 90vw; max-height: 90vh;
         border-radius: 12px;
         box-shadow: 0 20px 60px rgba(0,0,0,0.5);
         transform: scale(0.9); opacity: 0;
         transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
     }
     .lightbox-overlay.active .lightbox-img { transform: scale(1); opacity: 1; }
     .lightbox-close {
         position: absolute; top: 20px; right: 24px;
         width: 40px; height: 40px;
         background: rgba(255,255,255,0.15);
         border: 1px solid rgba(255,255,255,0.3);
         border-radius: 50%; color: white;
         font-size: 18px; cursor: pointer;
         display: flex; align-items: center; justify-content: center;
         transition: all 0.3s ease; backdrop-filter: blur(8px);
     }
     .lightbox-close:hover { background: rgba(255,255,255,0.3); transform: rotate(90deg); }
     .lightbox-trigger { cursor: pointer; transition: opacity 0.2s ease; }
     .lightbox-trigger:hover { opacity: 0.85; }
     
     <!-- Lightbox HTML（放在 </body> 之前） -->
     <div class="lightbox-overlay" id="img-lightbox" onclick="closeLightbox()">
         <button class="lightbox-close" onclick="closeLightbox()">&times;</button>
         <img class="lightbox-img" id="lightbox-img" src="" alt="放大预览" onclick="event.stopPropagation()" />
     </div>
     
     <!-- Lightbox JS（放在 Lightbox HTML 之后） -->
     <script>
     function openLightbox(src) {
         const overlay = document.getElementById('img-lightbox');
         document.getElementById('lightbox-img').src = src;
         overlay.classList.add('active');
         document.body.style.overflow = 'hidden';
     }
     function closeLightbox() {
         document.getElementById('img-lightbox').classList.remove('active');
         document.body.style.overflow = '';
     }
     document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
     </script>
     ```
     
     图片元素使用方式：`<img src="..." class="lightbox-trigger" onclick="openLightbox(this.src)" />`
   - **配套图注与说明**：对于有图片资源的区块，必须在图片下方或侧边带有对应的标题或者解释说明文案，具体的文案内容请直接参考 `assets_manifest.json` 里的 `label` 和 `description` 字段。
   - **Logo类资源免边框处理**：对于 Logo 类的资源图片（如各厂商 Logo 等），由于它们通常是不规则或者是特定长宽比的透明图像，因此嵌入时**不要**在其外部添加类似 `.step-icon` 或其他具有强行统一大小、背景色和边框阴影的容器样式，这会导致显示效果极差。请直接使用纯 `<img>` 标签，并通过适当的宽度/高度类（例如 `h-10 object-contain` 等）来进行样式控制即可。

5. **🚫 Flex 布局防溢出规范（重要）**：

   在 1280×720 固定尺寸的幻灯片布局中，**Flexbox 的子元素默认 `min-height: auto`（即内容的自然高度）**，这意味着即使设置了 `flex-1`，**如果子元素内容（如一张很高的纵向图片）的自然高度超过了分配的空间，它会撑爆父容器，导致其他兄弟元素被挤出视口**。这是一个极其常见的溢出 Bug。

   **必须遵循以下规则：**

   1. **逐层添加 `min-h-0`**：从主内容区域到右栏容器，再到每个卡片及其内部的图片容器，所有使用 `flex` + `flex-col` 布局的层级都必须添加 `min-h-0` 类，打破默认的 `min-height: auto` 行为。
      ```
      主内容区（flex-1 min-h-0）
      └── 右栏（flex flex-col min-h-0）
          ├── 卡片1（flex-[3] flex flex-col min-h-0）
          │   └── 图片容器（flex-1 min-h-0 overflow-hidden）
          └── 卡片2（flex-[2] flex flex-col min-h-0）
              └── 图片容器（flex-1 min-h-0 overflow-hidden）
      ```

   2. **用比例 flex 替代固定高度**：当右栏有多个卡片时，不要用 `flex-1` + `h-40` 这种混用方式，应使用 `flex-[3]` / `flex-[2]` 等比例来分配空间，确保不同卡片按合理比例占据可用高度。

   3. **图片容器必须 `overflow-hidden`**：所有包含预览图片的容器必须设置 `overflow-hidden`，确保图片被裁切在容器范围内，而不是撑开容器。

   4. **纵向长图使用 `object-cover object-top`**：对于纵向比例很高的图片（如技术规格书、长表单截图），使用 `object-cover object-top` 展示顶部缩略，用户可点击 Lightbox 查看完整图片。横向图片可继续使用 `object-contain`。

   5. **完整的防溢出右栏模板**：
      ```html
      <!-- 右栏容器：必须加 min-h-0 -->
      <div class="fragment w-1/2 flex flex-col gap-4 min-h-0" animation_step="2">
          <!-- 卡片1：用 flex-[3] 占60%空间 -->
          <div class="glass-card p-4 flex-[3] flex flex-col min-h-0">
              <div class="flex items-center gap-2 mb-3">...</div>
              <!-- 图片容器：flex-1 + min-h-0 + overflow-hidden -->
              <div class="flex-1 rounded-xl overflow-hidden border border-slate-200 bg-white min-h-0">
                  <img src="..." class="w-full h-full object-cover object-top lightbox-trigger"
                       onclick="openLightbox(this.src)" />
              </div>
              <p class="text-[10px] text-slate-400 mt-1.5 text-center">图注 — 点击可放大</p>
          </div>
          <!-- 卡片2：用 flex-[2] 占40%空间 -->
          <div class="glass-card p-4 flex-[2] flex flex-col min-h-0">
              <div class="flex items-center gap-2 mb-3">...</div>
              <div class="flex-1 rounded-lg overflow-hidden border border-slate-200 bg-white min-h-0">
                  <img src="..." class="w-full h-full object-contain lightbox-trigger"
                       onclick="openLightbox(this.src)" />
              </div>
              <p class="text-[10px] text-slate-400 mt-1.5 text-center">图注 — 点击可放大</p>
          </div>
      </div>
      ```

### 3.3 视频资料处理

如果用户提供了视频：

1. **确认视频路径**：相对于项目根目录的路径
2. **确认视频格式**：MP4 等
3. **确认播放设置**：自动播放、循环、静音等

---

## 步骤 4：生成 HTML 页面

### 4.1 基础结构

所有页面都需要包含以下基础结构：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[页面标题] - [CLIENT_NAME]</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="../../assets/style.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body class="page-wrapper">
    <main class="page-container">
        <!-- 页面内容 -->
    </main>
    <script src="../../assets/script.js"></script>
</body>
</html>
```

### 4.2 根据风格类型填充内容

#### 章节页模板

```html
<main class="page-container relative flex items-center justify-center">
    <!-- 背景光晕效果 -->
    <div class="absolute top-1/4 left-1/4 w-[400px] h-[400px] bg-gradient-to-br from-[#C00000]/20 to-transparent rounded-full blur-3xl"></div>
    
    <!-- 主标题区 -->
    <div class="text-center z-10 animate-fadeInUp">
        <h1 class="text-6xl font-bold text-gray-800 mb-4">[主标题]</h1>
        <div class="w-24 h-1 bg-[#C00000] mx-auto mb-4"></div>
        <p class="text-xl text-gray-500">[副标题]</p>
    </div>
</main>
```

#### 标准含视频详情页模板

```html
<main class="page-container flex flex-col p-12">
    <!-- 头部标题区 -->
    <header class="mb-8 flex items-start gap-4 animate-fadeInDown">
        <div class="w-1.5 h-16 bg-[#C00000] rounded-full"></div>
        <div>
            <h1 class="text-3xl font-bold text-gray-800">[主标题]</h1>
            <p class="text-lg text-gray-500 mt-2">[副标题]</p>
        </div>
    </header>
    
    <!-- 内容区：左右分栏 -->
    <div class="flex-1 grid grid-cols-2 gap-8">
        <!-- 左侧：功能卡片 -->
        <div class="space-y-4">
            <!-- 功能卡片组 -->
        </div>
        
        <!-- 右侧：视频区 -->
        <div class="flex items-center justify-center">
            <video class="rounded-2xl shadow-lg max-h-full" src="[视频路径]" controls></video>
        </div>
    </div>
    
    <!-- 底部页码 -->
    <footer class="mt-4 text-right text-gray-400 text-sm">
        <span class="text-[#C00000] font-bold">[当前页码]</span> / [总页数]
    </footer>
</main>
```

#### 一般详情页模板

根据内容类型选择合适的布局变体，参考 `03_一般详情页风格.md` 中的具体模板。

#### 详情页_背景_痛点_方案_价值_细节模板

> 完整模板请参考 `04_详情页_背景_痛点_方案_价值_细节.md` 第 6 章「固化 HTML 片段」。以下为关键结构速查：

```html
<!-- 资源引入（页面目录层级为 pages/custom/） -->
<script src="../../lib/tailwind@4.js"></script>
<link href="../../lib/font-awesome/all.min.css" rel="stylesheet" />
<link href="../../lib/fonts.css" rel="stylesheet" />

<!-- 页面外壳 -->
<div id="page-shell" class="w-screen h-screen flex items-center justify-center bg-[#0f172a]">
  <div id="slide-scale-wrapper" class="relative w-[1280px] h-[720px]">
    <div id="slide-container" class="w-full h-full bg-[#fcfdfe] relative overflow-hidden flex flex-col px-14 py-10">

      <!-- 背景装饰光晕 -->
      <div class="bg-img-overlay pointer-events-none"></div>

      <!-- Header：场景分类 + 主标题 -->
      <header class="relative z-20 mb-6 shrink-0">
        <div class="flex items-center gap-3 mb-1">
          <span class="text-rpa-red font-bold text-lg">[场景分类]：[副标题]</span>
        </div>
        <div class="flex items-center gap-4">
          <span class="w-2 h-8 bg-rpa-red rounded"></span>
          <h1 class="text-3xl font-extrabold tracking-tight text-slate-900">
            [主标题]
            <span class="text-rpa-red ml-2">（[技术标签]）</span>
          </h1>
        </div>
      </header>

      <!-- 主内容：左右各50% -->
      <div class="flex gap-8 flex-1 relative z-10 min-h-0">

        <!-- 左栏 -->
        <div class="w-1/2 flex flex-col gap-4">

          <!-- 背景+痛点卡片 -->
          <div class="fragment glass-card p-4 relative overflow-hidden group" animation_step="1">
            <div class="absolute top-0 left-0 w-1.5 h-full bg-slate-800 transition-all group-hover:w-2"></div>
            <div class="flex gap-6">
              <!-- 需求背景 -->
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <div class="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center text-slate-800 shadow-sm">
                    <i class="fa-solid fa-file-lines text-sm"></i>
                  </div>
                  <h3 class="text-sm font-bold text-slate-900 tracking-tight">需求背景：</h3>
                </div>
                <p class="text-[11px] text-slate-600 leading-relaxed">[需求背景描述]</p>
              </div>
              <!-- 业务痛点 -->
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <div class="w-7 h-7 rounded-lg bg-orange-100 flex items-center justify-center text-orange-600 shadow-sm">
                    <i class="fa-solid fa-triangle-exclamation text-sm"></i>
                  </div>
                  <h3 class="text-sm font-bold text-slate-900 tracking-tight">业务痛点：</h3>
                </div>
                <div class="space-y-1.5">
                  <div class="pain-point-item">1. [痛点一]</div>
                  <div class="pain-point-item">2. [痛点二]</div>
                  <div class="pain-point-item">3. [痛点三]</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 解决方案（含工作流）-->
          <div class="fragment glass-card p-4 relative overflow-hidden group flex-1" animation_step="2">
            <div class="absolute top-0 left-0 w-1.5 h-full bg-rpa-red transition-all group-hover:w-2"></div>
            <div class="flex items-center gap-2 mb-3">
              <div class="w-7 h-7 rounded-lg bg-red-50 flex items-center justify-center text-rpa-red shadow-sm">
                <i class="fa-solid fa-robot text-sm"></i>
              </div>
              <h3 class="text-sm font-bold text-slate-900 tracking-tight">影刀RPA解决方案</h3>
            </div>
            <div class="workflow-box mt-2 !py-4">
              <div class="flex items-center justify-between px-2">
                <!-- 工作流步骤（根据图标类型选择：样式图标或真实截图图标） -->

                <!-- 模式1：样式图标（CSS 图标） -->
                <div class="workflow-step group">
                  <div class="step-icon transition-all group-hover:bg-blue-600 group-hover:text-white">
                    <i class="fa-solid fa-[图标名]"></i>
                  </div>
                  <div class="text-[10px] font-bold text-slate-800 leading-tight">[步骤名称]<br>[说明]</div>
                </div>
                
                <div class="connector-arrow text-slate-300"><i class="fa-solid fa-arrow-right"></i></div>
                
                <!-- 模式2：真实截图图标（图片） -->
                <div class="workflow-step group">
                  <div class="step-icon transition-all group-hover:shadow-md p-1 overflow-hidden">
                    <img src="[图片路径]" alt="[步骤名称]" class="w-full h-full object-contain rounded-lg" />
                  </div>
                  <div class="text-[10px] font-bold text-slate-800 leading-tight">[步骤名称]<br>[说明]</div>
                </div>
                <!-- 更多步骤... -->
              </div>
            </div>
          </div>

          <!-- 方案价值 -->
          <div class="fragment mt-auto" animation_step="3">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-1 h-3.5 bg-rpa-red"></span>
              <h3 class="text-sm font-bold text-slate-900">方案价值：</h3>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="value-card">
                <div class="value-number">[数字]%</div>
                <p class="text-[11px] text-slate-600 leading-relaxed mt-2">[价值描述]</p>
              </div>
              <div class="value-card">
                <div class="value-number">[数字]%</div>
                <p class="text-[11px] text-slate-600 leading-relaxed mt-2">[价值描述]</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 右栏：数据/文件展示（⚠️ 必须加 min-h-0 防溢出，用 flex-[N] 按比例分配卡片空间） -->
        <div class="fragment w-1/2 flex flex-col gap-4 min-h-0" animation_step="2">
          <!-- 卡片1：flex-[3] 占 ~60% 空间，min-h-0 防溢出 -->
          <div class="glass-card p-4 flex-[3] flex flex-col min-h-0">
            <div class="flex items-center gap-2 mb-3">...</div>
            <!-- 图片容器：flex-1 + min-h-0 + overflow-hidden；纵向长图用 object-cover object-top -->
            <div class="flex-1 rounded-xl overflow-hidden border border-slate-200 bg-white min-h-0">
              <img src="[图片路径]" class="w-full h-full object-cover object-top lightbox-trigger"
                   onclick="openLightbox(this.src)" />
            </div>
            <p class="text-[10px] text-slate-400 mt-1.5 text-center">图注 — 点击可放大</p>
          </div>
          <!-- 卡片2：flex-[2] 占 ~40% 空间 -->
          <div class="glass-card p-4 flex-[2] flex flex-col min-h-0">
            <div class="flex items-center gap-2 mb-3">...</div>
            <div class="flex-1 rounded-lg overflow-hidden border border-slate-200 bg-white min-h-0">
              <img src="[图片路径]" class="w-full h-full object-contain lightbox-trigger"
                   onclick="openLightbox(this.src)" />
            </div>
            <p class="text-[10px] text-slate-400 mt-1.5 text-center">图注 — 点击可放大</p>
          </div>
        </div>

      </div>
    </div>
  </div>
</div>
<script src="../../js/slide-core.js"></script>
```

#### 启动会首页模板

> 完整模板请参考 `05_启动会首页风格.md` 第 6 章「固化 HTML 片段」。以下为关键结构速查：

```html
<!-- 资源引入（页面目录层级为 pages/） -->
<script src="../lib/tailwind@4.js"></script>
<link href="../lib/fonts.css" rel="stylesheet" />

<!-- 页面外壳 -->
<body class="bg-gray-900 flex items-center justify-center h-screen w-screen font-sans">
<div id="page-shell" class="w-full h-full flex items-center justify-center">
  <div id="slide-scale-wrapper" class="relative w-[1280px] h-[720px]">
    <div id="slide-container" class="w-[1280px] h-[720px] flex flex-col relative overflow-hidden bg-[#F8F9FA]">

      <!-- 背景层（光晕 + 网格） -->
      <!-- 右上角红色光晕 -->
      <div class='absolute top-0 right-0 w-[600px] h-[600px] bg-gradient-to-b from-[#C00000]/5 to-transparent rounded-full blur-3xl -translate-y-1/2 translate-x-1/3 z-0 pointer-events-none'></div>
      <!-- 左下角蓝色光晕 -->
      <div class="absolute bottom-0 left-0 w-[800px] h-[800px] bg-[#3370FF]/5 rounded-full blur-3xl translate-y-1/3 -translate-x-1/4 z-0 pointer-events-none"></div>
      <!-- 网格纹理 -->
      <div class="absolute inset-0 z-0 opacity-30" style="background-image: radial-gradient(#cbd5e1 1px, transparent 1px); background-size: 40px 40px;"></div>

      <!-- 右下角联系信息 -->
      <div class="absolute bottom-6 right-8 z-30 flex flex-col items-end opacity-60 hover:opacity-100 transition-opacity duration-500 cursor-default group">
        <div class="flex items-center gap-2 text-xs text-gray-500 font-medium">
          <span>影刀客户成功</span>
          <span class="w-px h-3 bg-gray-300"></span>
          <span class="text-gray-800 font-bold">[姓名]</span>
        </div>
        <div class="text-[10px] text-gray-600 font-mono tracking-wider mt-0.5 group-hover:text-[#C00000] transition-colors duration-300">[电话]</div>
      </div>

      <!-- 主内容区 -->
      <div class="relative z-20 w-full h-full flex flex-col items-center justify-center px-20 pt-8 pb-32">

        <!-- 标题组合 -->
        <div class="text-center space-y-8 max-w-6xl animate-enter">
          <!-- 顶部标签 -->
          <div class="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-gradient-to-r from-[#C00000]/5 to-[#C00000]/10 border border-[#C00000]/10 mb-2">
            <svg class="w-4 h-4 text-[#C00000]" fill="currentColor" viewBox="0 0 24 24">
              <path d="M7 2v11h3v9l7-12h-4l4-8z" />
            </svg>
            <span class="text-[#C00000] font-bold text-sm tracking-wide uppercase">[标签文字，如：核心价值主张]</span>
          </div>

          <!-- 主标题 -->
          <h1 class="text-[76px] font-bold text-[#1F2937] tracking-tight leading-[1.15]">
            {{CLIENT_NAME}} &amp; 影刀RPA<br>
            <span class="text-[64px] font-bold text-[#374151]">项目启动宣讲会</span>
          </h1>

          <!-- Slogan -->
          <div class="flex items-center justify-center gap-6 mt-6">
            <div class="h-px w-20 bg-gradient-to-r from-transparent to-gray-300"></div>
            <p class="text-2xl text-[#4B5563] font-medium tracking-wide">
              [Slogan前半段]<span class="text-[#C00000] font-bold mx-1">[核心关键词]</span>[Slogan后半段]
            </p>
            <div class="h-px w-20 bg-gradient-to-l from-transparent to-gray-300"></div>
          </div>
        </div>

        <!-- 底部三列特性卡片 -->
        <div class="absolute bottom-16 flex gap-10 w-full justify-center px-20 animate-enter" style="animation-delay: 0.2s;">
          <!-- 卡片1（橙色）-->
          <div class="glass-card flex-1 h-32 rounded-2xl flex items-center p-6 gap-5 group cursor-default">
            <div class="w-16 h-16 rounded-xl bg-orange-50 border border-orange-100 flex items-center justify-center text-orange-500 shrink-0 group-hover:scale-110 transition-transform duration-300">
              <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><!-- SVG 图标 --></svg>
            </div>
            <div>
              <h3 class="text-lg font-bold text-gray-800 mb-1">[特性名称1]</h3>
              <p class="text-xs text-gray-500 leading-relaxed">[描述行1]<br>[描述行2]</p>
            </div>
          </div>
          <!-- 卡片2（红色强调）-->
          <div class="glass-card flex-1 h-32 rounded-2xl flex items-center p-6 gap-5 group cursor-default border-red-100 bg-white/70">
            <div class="w-16 h-16 rounded-xl bg-red-50 border border-red-100 flex items-center justify-center text-[#C00000] shrink-0 group-hover:scale-110 transition-transform duration-300">
              <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><!-- SVG 图标 --></svg>
            </div>
            <div>
              <h3 class="text-lg font-bold text-[#C00000] mb-1">[特性名称2]</h3>
              <p class="text-xs text-gray-500 leading-relaxed">[描述行1]<br>[描述行2]</p>
            </div>
          </div>
          <!-- 卡片3（蓝色）-->
          <div class="glass-card flex-1 h-32 rounded-2xl flex items-center p-6 gap-5 group cursor-default">
            <div class="w-16 h-16 rounded-xl bg-[#3370FF]/10 border border-[#3370FF]/20 flex items-center justify-center text-[#3370FF] shrink-0 group-hover:scale-110 transition-transform duration-300">
              <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5"><!-- SVG 图标 --></svg>
            </div>
            <div>
              <h3 class="text-lg font-bold text-gray-800 mb-1">[特性名称3]</h3>
              <p class="text-xs text-gray-500 leading-relaxed">[描述行1]<br>[描述行2]</p>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</div>
<script src="../js/slide-core.js"></script>
```

### 4.3 填充具体内容

1. 替换占位符为实际内容
2. 调整卡片数量和布局
3. 添加适当的动画延迟
4. 确保颜色和间距符合设计规范

---

## 步骤 5：保存和验证

### 5.1 确定保存路径

根据页面类型确定保存路径：

- **通用页面**（如章节页）：`./pages/common/[文件名].html`
- **定制页面**（如详情页）：`./pages/custom/[文件名].html`

### 5.2 保存文件

使用 `write_to_file` 工具保存生成的 HTML 文件。

### 5.3 验证页面

1. 启动本地服务（如果尚未启动）：
   ```bash
   cd [project_root] && python3 -m http.server 8000
   ```

2. 使用浏览器访问页面验证效果：
   ```
   http://localhost:8000/pages/[路径]/[文件名].html
   ```

3. 检查要点：
   - 布局是否正确
   - 样式是否符合规范
   - 动画是否流畅
   - 内容是否完整

---

## 风格对应关系速查表

| 用户需求 | 推荐风格类型 | 参考文件 |
|----------|--------------|----------|
| 章节过渡、分隔页 | 章节页 | `01_章节页风格.md` |
| 功能介绍 + 演示视频 | 标准含视频详情页 | `02_标准含视频详情页风格.md` |
| 痛点分析、方案对比 | 一般详情页 | `03_一般详情页风格.md` |
| 场景列表、功能矩阵 | 一般详情页 | `03_一般详情页风格.md` |
| 价值展示、数据统计 | 一般详情页 | `03_一般详情页风格.md` |
| 业务案例（背景+痛点+方案+价值+数据预览） | 详情页_背景_痛点_方案_价值_细节 | `04_详情页_背景_痛点_方案_价值_细节.md` |
| 项目启动会首页、封面页、演示文稿首页 | 启动会首页风格 | `05_启动会首页风格.md` |

---

## 设计规范速查

### 关键颜色

| 颜色名称 | 色值 | 用途 | 适用风格 |
|----------|------|------|----------|
| 品牌红 | `#C00000` | 标题装饰、强调色 | 全部 |
| 飞书蓝 | `#3370FF` | 辅助强调色、蓝色光晕 | 05启动会 |
| 浅灰背景 | `#F8F9FA` | 页面背景 | 05启动会 |
| 极浅蓝灰 | `#fcfdfe` | 页面背景 | 04详情页 |
| 深蓝外壳 | `#0f172a` | 幻灯片外层壳 | 04详情页 |
| 主文字 | `#1F2937` | 标题、正文 | 05启动会 |
| 主文字（深） | `#0f172a` | 标题、正文 | 04详情页 |
| 辅助文字 | `#475569` (`slate-600`) | 正文说明 | 04详情页 |
| 辅助文字 | `#6B7280` | 副标题、说明 | 其他风格 |
| 毛玻璃卡片 | `rgba(255,255,255,0.8)` + blur(12px) | 信息承载卡片 | 04详情页 |
| 毛玻璃卡片 | `rgba(255,255,255,0.6)` + blur(10px) | 特性展示卡片 | 05启动会 |

### 关键间距

| 间距类型 | 数值 | Tailwind 类 | 适用风格 |
|----------|------|-------------|----------|
| 页面边距（横） | 56px | `px-14` | 04详情页 |
| 页面边距（纵） | 40px | `py-10` | 04详情页 |
| 页面边距（横） | 80px | `px-20` | 05启动会 |
| 页面边距（上） | 32px | `pt-8` | 05启动会 |
| 页面边距（下） | 128px | `pb-32` | 05启动会 |
| 页面边距 | 48px | `p-12` | 其他风格 |
| 卡片内边距（04） | 16px | `p-4` | 04详情页 |
| 卡片内边距（05） | 24px | `p-6` | 05启动会 |
| 栏间距 | 32px | `gap-8` | 04详情页 |

### 关键圆角

| 元素类型 | 数值 | Tailwind 类 |
|----------|------|-------------|
| 卡片圆角 | 16px | `rounded-2xl` |
| 图标容器 | 12px | `rounded-xl` |
| 标签/Pill | 全圆 | `rounded-full` |
| 按钮圆角 | 8px | `rounded-lg` |

### 标准动画

| 动画名称 | 效果 | 常用场景 | 适用风格 |
|----------|------|----------|----------|
| `animate-fadeInUp` | 从下往上淡入 | 卡片入场 | 01/02/03 |
| `animate-fadeInDown` | 从上往下淡入 | 标题入场 | 01/02/03 |
| `animate-fadeInLeft` | 从左往右淡入 | 左侧内容 | 01/02/03 |
| `animate-fadeInRight` | 从右往左淡入 | 右侧内容 | 01/02/03 |
| `.fragment` + `animation_step` | 分步入场（点击触发） | 渐进式信息展示 | 04详情页 |
| `.animate-enter` (`fade-in-up`) | 自动淡入上浮 | 首页整体入场 | 05启动会 |

---

## 注意事项

1. **保持风格一致**：严格参考风格总结文件中的规范
2. **响应式考虑**：优先保证 1280x720 展示效果
3. **动画适度**：不要过度使用动画，保持简洁
4. **语义化标签**：使用正确的 HTML5 语义标签
5. **资源路径**：确保图片、视频等资源路径正确
6. **变量替换**：使用 `[CLIENT_NAME]` 等占位符，由 script.js 自动替换

---

## 常见问题

### Q: 如何确定使用哪种详情页布局？

A: 根据内容类型判断：
- 有视频演示 → 标准含视频详情页
- 痛点+方案分析（简单对比） → 一般详情页（对比布局）
- 多个场景/功能列表 → 一般详情页（卡片网格布局）
- 数据/价值展示 → 一般详情页（统计卡片布局）
- **完整业务案例**（背景+痛点+工作流方案+价值数据+文件预览）→ **详情页_背景_痛点_方案_价值_细节**
- **项目首页/封面** → **启动会首页风格**

### Q: 04风格的右栏应该放什么内容？

A: 右栏（50%）用于展示「细节/实现效果」，常见内容：
1. **Excel/表格数据预览**：使用 `.excel-preview` 组件展示结构化数据
2. **文件占位预览**：使用文件图标卡片展示 PDF、图片等文件
3. **截图/效果图**：如有实际截图，用 `<img>` 内嵌在 `.glass-card` 中
4. **工作流/流程图**：复杂流程可用 `.workflow-box` 展示在右栏

### Q: 04风格的 animation_step 怎么分配？

A: 通常按以下顺序分配：
- `animation_step="1"`：背景+痛点卡片（最先展示）
- `animation_step="2"`：解决方案卡片 + 右栏内容（同步展示）
- `animation_step="3"`：方案价值区域（最后展示）

### Q: 05风格底部三张卡片的配色怎么选？

A: 遵循「橙/红/蓝」三色平衡原则：
- **第1张**：橙色系（`bg-orange-50` + `text-orange-500`）- 通常是内容/数据相关
- **第2张**：红色强调（`bg-red-50` + `text-[#C00000]`，卡片加 `border-red-100 bg-white/70`）- 通常是核心自动化功能
- **第3张**：蓝色系（`bg-[#3370FF]/10` + `text-[#3370FF]`）- 通常是协同/平台相关

### Q: 图片素材如何处理？

A:
1. 如果是展示用途，保存到 `./assets/images/` 目录
2. 如果是设计参考，分析后转换为 HTML/CSS 实现
3. 确保使用相对路径引用

### Q: 页面需要添加到配置吗？

A: 是的，新页面需要添加到 `./js/config.js` 的 slides 数组中才能在幻灯片中展示。
