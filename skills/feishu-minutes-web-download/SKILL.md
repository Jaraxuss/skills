---
name: "feishu-minutes-web-download"
description: "通过飞书网页会话下载妙记媒体和全文；支持从智能纪要 docx 链接提取妙记链接；失效时二维码登录并自动续传。"
---

# 飞书妙记网页下载

## 使用时机

当用户要求下载录音、媒体、全文或转写时使用：

- 用户直接给出包含 `/minutes/<token>` 的飞书妙记链接；
- 用户给出飞书智能纪要链接（通常包含 `/docx/<token>`），希望获取其中的妙记链接，或进一步下载其中的媒体和全文。

该流程使用用户自己的飞书网页会话，适用于应用机器人没有妙记原始媒体/全文下载权限的情况。

## 输入链接处理

1. 先判断用户提供的链接类型：
   - `/minutes/<token>`：直接作为妙记链接处理；
   - `/docx/<token>`：将其视为飞书智能纪要，使用飞书文档读取工具（`feishu_mcp_fetch_doc` / `feishu_fetch_doc`）获取 Markdown 正文。不要把 docx 链接直接传给妙记下载脚本。
2. 从智能纪要返回的 Markdown 中提取所有飞书妙记 URL：
   - 同时检查“相关链接”区域、Markdown 链接目标和纯文本 URL；
   - 识别路径中包含 `/minutes/<token>` 的链接，并保留其查询参数；
   - 只处理用户有权访问且由用户提供的文档中的链接。
3. 如果智能纪要中恰好提取到一个妙记链接，自动把它交给下面的妙记下载流程。
4. 如果提取到多个妙记链接，先列出标题（能获取时）和链接，请用户选择要下载的一个或多个；不要擅自选择。
5. 如果没有提取到妙记链接，明确告知智能纪要中未发现可识别的飞书妙记链接，并说明文档读取可能成功但没有相关链接。
6. 如果智能纪要读取失败、无权访问或链接类型无法确认，说明具体原因，不要猜测妙记链接。

## 固定执行方式

脚本：

`/home/velen/.openclaw/workspace/skills/feishu-minutes-web-download/scripts/download_feishu_minutes.mjs`

同时下载录音和全文：

```bash
node /home/velen/.openclaw/workspace/skills/feishu-minutes-web-download/scripts/download_feishu_minutes.mjs \
  --url '<妙记链接>' \
  --mode both
```

只下载录音：

```bash
node /home/velen/.openclaw/workspace/skills/feishu-minutes-web-download/scripts/download_feishu_minutes.mjs \
  --url '<妙记链接>' \
  --mode media
```

只导出全文：

```bash
node /home/velen/.openclaw/workspace/skills/feishu-minutes-web-download/scripts/download_feishu_minutes.mjs \
  --url '<妙记链接>' \
  --mode transcript \
  --format md
```

用户指定保存目录时传入 `--output-dir '<目录>'`。未指定时保存至：

`/home/velen/.openclaw/workspace/downloads/feishu-minutes/<token>/`

## 登录过期时的必须流程

直接执行用户需要的 `media`、`transcript` 或 `both` 命令，不要先单独执行 `login`。

如果脚本输出：

```json
{"event":"needs_login","needs_login":true,"screenshot":"<path>","waiting":true}
```

必须：

1. 立即把 `screenshot` 作为图片发给当前用户。
2. 告知用户扫码即可，无需回复“已登录”。
3. 保持当前 exec cell 和 Chrome 进程运行，继续等待同一个进程输出。
4. 收到 `login_complete` 后不做任何重启；脚本会自动继续下载。
5. 最终以 `event: "complete"` 为成功标志。

不要关闭二维码所在的 browser context，不要开第二个 Chrome，不要要求用户回复后再运行一次。

## 默认输出

默认文件名使用“妙记原标题 + 类型 + 批次时间”：

- `<妙记原标题>_录音_<yyMMddHHmm>.ogg`：妙记录音。大文件默认用 4 路 Range 分片流式落盘。
- `<妙记原标题>_转写_<yyMMddHHmm>.md`：带说话人和毫秒时间戳的完整转写。
- `<妙记原标题>_信息_<yyMMddHHmm>.json`：标题、token、文件路径、大小、段落数和耗时。

`yyMMddHHmm` 默认是首次下载开始时的上海时区时间，例如：

```text
二期需求规划讨论会_录音_2609030324.ogg
二期需求规划讨论会_转写_2609030324.md
二期需求规划讨论会_信息_2609030324.json
```

同一次下载的三个文件共用同一时间戳。对同一 token 在同一目录重跑时，脚本从已有信息文件中复用原批次时间，不会因重跑产生新的时间戳副本。

全文可选 `--format md|txt|srt`。用户明确需要 MP4 时传入 `--prefer-mp4 true`。
如需指定批次时间，传入 `--filename-timestamp <yyMMddHHmm>`；默认时区可用 `--filename-timezone <IANA 时区>` 调整。显式传入 `--media-output`、`--transcript-output` 或 `--info-output` 时，优先使用指定路径。

## 性能和稳定性规则

- 直接执行脚本。不要在下载前重复读取 Skill、枚举 Cookie、搜索临时脚本或自行探测多个 API。
- 脚本会并行获取状态/全文索引，再并行写入媒体和全文。
- 录音优先使用较小的 OGG。大于 20 MB 时使用 4 路 Range；不使用 8 路。
- 默认通过文件大小/内容校验复用已完整下载的文件，避免重复下载。
- 如果 profile 正被另一个任务使用，等待该任务结束，不要删除 Chrome 锁文件强行启动。

## 兜底顺序

1. 本脚本的 Playwright 登录态 + 页内同源 API。
2. 内部 API 变化时，用 Playwright 操作妙记 UI 的导出/下载按钮。
3. 只有 Playwright UI 也无法稳定执行时，才转 RPA 视觉/控件自动化。

## 安全边界

- 只处理用户提供或明确授权的智能纪要和妙记。
- 网页会话 profile 仅保存在 `/home/velen/.cache/feishu-minutes-web/profile`，权限为 700。
- 不输出、记录、回复或写入 Cookie、Authorization 或签名媒体 URL。
- 录音和全文默认仅保存本地，不上传第三方服务。
- 不删除、修改或上传云端智能纪要或妙记。
