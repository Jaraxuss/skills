---
name: tencent-meeting-recording-downloader
description: 下载腾讯会议分享链接中的录屏视频和逐字稿（转写文本）。适用于分享页面上"另存为"按钮被禁用、无法直接下载的场景。当用户提供腾讯会议录屏分享链接（meeting.tencent.com/meeting-record/shares）并要求下载录屏、视频、文字稿、逐字稿、转写文本时使用本Skill。
---

# 腾讯会议录屏与逐字稿下载

从腾讯会议分享链接中下载录屏视频和逐字稿文本，适用于分享页面"另存为"按钮被禁用的场景。

## 前置条件

- 使用 `mac_computer_use_tool`（`plane="bu"`）操作浏览器
- 浏览器已登录或可通过扫码完成腾讯会议登录
- 输出目录由用户指定，默认保存到当前项目目录

## 工作流程

### 1. 打开分享链接

```python
import seed_browser_use as bu

bu.navigate("<用户提供的腾讯会议分享链接>")
bu.wait_for_load(timeout=20)
bu.snapshot()
```

### 2. 处理登录（如需要）

页面会跳转到腾讯会议登录页，显示扫码二维码。此时必须调用 `interaction.request_action` 让用户接管浏览器完成扫码登录：

```python
interaction.request_action(
    type="browserControl",
    display_message="腾讯会议录屏页面需要登录。请使用微信或腾讯会议App扫码完成登录授权，完成后交回控制权。"
)
```

登录完成后，重新 `bu.wait_for_load()` 并确认页面已显示会议录屏内容。

### 3. 提取并下载录屏视频

从 `<video>` 元素获取真实视频地址，然后用 `bu.download()` 下载：

```python
# 获取video元素的src
video_src = bu.js("""
const videos = document.querySelectorAll('video');
if (videos.length > 0) return videos[0].src || videos[0].currentSrc;
return null;
""")

# 下载视频（大文件需要较长timeout）
record = bu.download(video_src, filename="<自定义文件名>.mp4")
video_path = record["path"]
video_bytes = record["bytes"]
```

视频文件通常较大（几百MB），下载可能需要几分钟，注意设置足够的 `timeout_ms`（建议300000即5分钟以上）。

### 4. 提取逐字稿数据

逐字稿数据存储在React组件的props中，需要通过DOM元素的React fiber节点提取。**不要尝试通过滚动虚拟列表来收集**，虚拟列表只渲染可见的8行左右。

确保已切换到"逐字稿"标签页后执行：

```python
import json

# 从React fiber提取逐字稿完整数据
full_data = bu.js("""
const list = document.querySelector('.minutes-module-list');
if (!list) return '[]';
const fiberKey = Object.keys(list).find(k => k.startsWith('__reactFiber'));
let fiber = list[fiberKey];
let depth = 0;
while (fiber && depth < 20) {
    if (fiber.memoizedProps && Array.isArray(fiber.memoizedProps.data) && fiber.memoizedProps.data.length > 5) {
        return JSON.stringify(fiber.memoizedProps.data);
    }
    fiber = fiber.return;
    depth++;
}
return '[]';
""")

data = json.loads(full_data)
```

每条数据的结构：
- `pid`: 段落ID
- `start_time` / `end_time`: 起止时间（毫秒）
- `speaker`: 发言人对象，包含 `user_name` 字段
- `sentences`: 句子数组，每个句子包含 `words` 数组
- 每个 word 包含 `text` 字段

### 5. 解析并格式化逐字稿

使用 `scripts/parse_transcript.py` 脚本将原始数据转换为可读的文本文件：

```bash
python3 scripts/parse_transcript.py <原始JSON文件> <输出TXT文件> --title "<会议标题>"
```

脚本会：
- 提取发言人姓名（从 speaker.user_name）
- 将毫秒时间戳转换为 HH:MM:SS 格式
- 拼接所有 word.text 为完整段落
- 生成带时间戳和发言人的格式化文本文件

### 6. 移动文件到输出目录

将下载的视频和生成的逐字稿文本文件移动到用户指定的输出目录：

```bash
mv <视频原路径> <输出目录>/<自定义文件名>.mp4
mv <逐字稿原路径> <输出目录>/<自定义文件名>.txt
```

## 关键注意事项

1. **登录是必经步骤**：腾讯会议分享链接通常需要登录才能查看内容，遇到登录页必须调用 `interaction.request_action` 让用户扫码，不要尝试绕过。
2. **视频地址带有时效token**：从 video.src 获取的URL包含鉴权token，必须在登录后立即下载，不要延迟。
3. **逐字稿在React fiber中**：不要通过滚动虚拟列表收集逐字稿，直接从 `.minutes-module-list` 元素的React fiber props.data中提取完整数据数组。
4. **发言人是字典对象**：`speaker` 字段是一个对象，需要取 `user_name` 属性，不要直接转成字符串。
5. **文件命名**：建议用"腾讯会议录屏_<会议主题>_<日期>.mp4"和"腾讯会议逐字稿_<会议主题>_<日期>.txt"的命名格式。

## 常见问题

- **页面跳转到登录页**：正常流程，调用 `interaction.request_action` 让用户扫码。
- **找不到 `.minutes-module-list` 元素**：确认已切换到"逐字稿"标签页。
- **fiber.data 为空或很短**：确保页面已完全加载，且已切换到逐字稿标签。
- **视频下载超时**：增大 `timeout_ms`（建议 300000 即5分钟以上），大文件下载需要时间。
