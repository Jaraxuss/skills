#!/usr/bin/env node
/*
 * Fast Feishu Minutes downloader.
 *
 * One persistent Playwright process owns login and download. Public output is
 * JSON Lines only; cookies and signed URLs must never be printed.
 */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { once } from 'node:events';
import { performance } from 'node:perf_hooks';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';

const startedAt = performance.now();
const playwrightModule = process.env.FEISHU_PLAYWRIGHT_MODULE ||
  '/home/velen/.openclaw/workspace/skills/nblm/node_modules/playwright/index.mjs';

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith('--')) continue;
    const equals = item.indexOf('=');
    if (equals >= 0) {
      result[item.slice(2, equals)] = item.slice(equals + 1);
      continue;
    }
    const key = item.slice(2);
    const next = argv[index + 1];
    if (next && !next.startsWith('--')) {
      result[key] = next;
      index += 1;
    } else {
      result[key] = true;
    }
  }
  return result;
}

function boolArg(value, fallback) {
  if (value === undefined) return fallback;
  return !['0', 'false', 'no', '否'].includes(String(value).toLowerCase());
}

function numberArg(value, fallback, minimum = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}

function elapsedMs() {
  return Math.round(performance.now() - startedAt);
}

function emit(payload) {
  process.stdout.write(JSON.stringify({ ...payload, elapsed_ms: elapsedMs() }) + '\n');
}

function tokenFromUrl(raw) {
  const url = new URL(raw);
  const parts = url.pathname.split('/').filter(Boolean);
  const index = parts.lastIndexOf('minutes');
  if (index < 0 || !parts[index + 1]) {
    throw new Error('链接不是可识别的飞书妙记 /minutes/ 链接');
  }
  return { url, token: parts[index + 1] };
}

function isLoginPage(url) {
  return /accounts\/page\/login|accounts\/trap|accounts\/login/i.test(String(url));
}

function safeName(value) {
  const cleaned = String(value || 'feishu-minutes')
    .replace(/[\/\\:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[. ]+$/, '');
  return (cleaned || 'feishu-minutes').slice(0, 180);
}

function uniquePath(filePath) {
  if (!fs.existsSync(filePath)) return filePath;
  const extension = path.extname(filePath);
  const stem = extension ? filePath.slice(0, -extension.length) : filePath;
  for (let index = 2; index < 10000; index += 1) {
    const candidate = `${stem}-${index}${extension}`;
    if (!fs.existsSync(candidate)) return candidate;
  }
  throw new Error('无法生成不冲突的输出文件名');
}

function formatTimestamp(value, srt = false) {
  const total = Math.max(0, Number(value) || 0);
  const hours = Math.floor(total / 3600000);
  const minutes = Math.floor((total % 3600000) / 60000);
  const seconds = Math.floor((total % 60000) / 1000);
  const millis = total % 1000;
  const separator = srt ? ',' : '.';
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:` +
    `${String(seconds).padStart(2, '0')}${separator}${String(millis).padStart(3, '0')}`;
}

function cleanText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function paragraphText(paragraph) {
  return cleanText((paragraph.sentences || [])
    .map((sentence) => (sentence.contents || []).map((item) => item.content || '').join(''))
    .join(''));
}

function paragraphSpeaker(paragraph) {
  return cleanText(
    paragraph.speaker?.user_name || paragraph.speaker?.display_name || '未知说话人'
  ) || '未知说话人';
}

function renderTranscript(paragraphs, format, title, sourceUrl) {
  if (format === 'srt') {
    const blocks = [];
    let sequence = 1;
    for (const paragraph of paragraphs) {
      const text = paragraphText(paragraph);
      if (!text) continue;
      blocks.push(String(sequence));
      blocks.push(
        `${formatTimestamp(paragraph.start_time, true)} --> ` +
        `${formatTimestamp(paragraph.stop_time, true)}`
      );
      blocks.push(`${paragraphSpeaker(paragraph)}: ${text}`);
      blocks.push('');
      sequence += 1;
    }
    return blocks.join('\n');
  }

  if (format === 'txt') {
    const lines = [];
    for (const paragraph of paragraphs) {
      const text = paragraphText(paragraph);
      if (!text) continue;
      lines.push(
        `[${formatTimestamp(paragraph.start_time)}–${formatTimestamp(paragraph.stop_time)}] ` +
        `${paragraphSpeaker(paragraph)}`
      );
      lines.push(text, '');
    }
    return lines.join('\n');
  }

  const lines = [
    `# ${title}`,
    '',
    `- 妙记链接：${sourceUrl}`,
    `- 转写段落：${paragraphs.length}`,
    '',
    '## 全文',
    ''
  ];
  for (const paragraph of paragraphs) {
    const text = paragraphText(paragraph);
    if (!text) continue;
    lines.push(
      `**[${formatTimestamp(paragraph.start_time)}–${formatTimestamp(paragraph.stop_time)}] ` +
      `${paragraphSpeaker(paragraph)}**`
    );
    lines.push('', text, '');
  }
  return lines.join('\n');
}

async function captureLoginQr(page, filePath) {
  await page.waitForTimeout(800);
  const selectors = ['[class*="qr" i] canvas', '[class*="qr" i] img', 'canvas', 'img'];
  for (const selector of selectors) {
    const locator = page.locator(selector);
    const count = Math.min(await locator.count(), 20);
    for (let index = 0; index < count; index += 1) {
      const box = await locator.nth(index).boundingBox().catch(() => null);
      if (!box) continue;
      const ratio = box.width / box.height;
      if (box.width < 120 || box.height < 120 || ratio < 0.75 || ratio > 1.25) continue;
      const padding = 20;
      const viewport = page.viewportSize() || { width: 1200, height: 820 };
      const x = Math.max(0, box.x - padding);
      const y = Math.max(0, box.y - padding);
      await page.screenshot({
        path: filePath,
        clip: {
          x,
          y,
          width: Math.min(viewport.width - x, box.width + padding * 2),
          height: Math.min(viewport.height - y, box.height + padding * 2)
        }
      });
      return 'qr_crop';
    }
  }
  await page.screenshot({ path: filePath, fullPage: false });
  return 'viewport';
}

async function waitForLogin(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!isLoginPage(page.url())) return;
    await page.waitForTimeout(1000);
  }
  throw new Error('等待扫码登录超时');
}

async function appendPart(partPath, outputStream) {
  const input = fs.createReadStream(partPath);
  const errorPromise = once(input, 'error').then(([error]) => Promise.reject(error));
  input.pipe(outputStream, { end: false });
  await Promise.race([once(input, 'end'), errorPromise]);
}

const args = parseArgs(process.argv.slice(2));
if (args.help) {
  process.stdout.write([
    'Usage: node download_feishu_minutes.mjs --url <minutes-url> [options]',
    '  --mode login|media|transcript|both   default: both',
    '  --output-dir <dir>                   default: downloads/feishu-minutes/<token>',
    '  --profile <dir>                      persistent Chrome profile',
    '  --format md|txt|srt                  default: md',
    '  --login-timeout <ms>                 default: 300000',
    '  --range-concurrency <n>              default: 4',
    '  --range-threshold <bytes>             default: 20971520',
    '  --prefer-mp4 true|false              default: false',
    '  --reuse-existing true|false          default: true',
    '  --overwrite true|false               default: false'
  ].join('\n') + '\n');
  process.exit(0);
}

if (!args.url) {
  emit({ event: 'error', ok: false, error: '缺少 --url' });
  process.exit(1);
}

let parsed;
try {
  parsed = tokenFromUrl(args.url);
} catch (error) {
  emit({ event: 'error', ok: false, error: error.message });
  process.exit(1);
}

const mode = String(args.mode || 'both').toLowerCase();
const format = String(args.format || 'md').toLowerCase();
if (!['login', 'media', 'transcript', 'both'].includes(mode)) {
  emit({ event: 'error', ok: false, error: '--mode 必须是 login、media、transcript 或 both' });
  process.exit(1);
}
if (!['md', 'txt', 'srt'].includes(format)) {
  emit({ event: 'error', ok: false, error: '--format 必须是 md、txt 或 srt' });
  process.exit(1);
}

const profileDir = path.resolve(String(
  args.profile || '/home/velen/.cache/feishu-minutes-web/profile'
));
const outputDir = path.resolve(String(
  args['output-dir'] ||
  `/home/velen/.openclaw/workspace/downloads/feishu-minutes/${parsed.token}`
));
const screenshotDir = path.resolve(String(
  args['screenshot-dir'] || '/home/velen/.openclaw/media/outbound'
));
const navigationTimeout = numberArg(args.timeout, 45000, 1000);
const loginTimeout = numberArg(args['login-timeout'], 300000, 1000);
const rangeConcurrency = Math.floor(numberArg(args['range-concurrency'], 4, 1));
const rangeThreshold = numberArg(args['range-threshold'], 20 * 1024 * 1024, 0);
const reuseExisting = boolArg(args['reuse-existing'], true);
const overwrite = boolArg(args.overwrite, false);
const preferMp4 = boolArg(args['prefer-mp4'], false);

await fsp.mkdir(profileDir, { recursive: true, mode: 0o700 });
await fsp.chmod(profileDir, 0o700).catch(() => {});
await fsp.mkdir(outputDir, { recursive: true, mode: 0o700 });
await fsp.mkdir(screenshotDir, { recursive: true, mode: 0o700 });

let context;
let exitCode = 0;
try {
  const { chromium } = await import(playwrightModule);
  context = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    executablePath: process.env.FEISHU_CHROME_PATH || '/opt/google/chrome/chrome',
    viewport: { width: 1200, height: 820 },
    args: ['--no-sandbox', '--disable-dev-shm-usage']
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(parsed.url.href, { waitUntil: 'domcontentloaded', timeout: navigationTimeout });

  if (isLoginPage(page.url())) {
    const screenshot = path.join(
      screenshotDir,
      `feishu-minutes-login-${parsed.token}-${Date.now()}.png`
    );
    const screenshotKind = await captureLoginQr(page, screenshot);
    emit({
      event: 'needs_login',
      ok: true,
      needs_login: true,
      screenshot,
      screenshot_kind: screenshotKind,
      waiting: true
    });
    await waitForLogin(page, loginTimeout);
    emit({ event: 'login_complete', ok: true, needs_login: false });
  }

  if (mode === 'login') {
    emit({ event: 'complete', ok: true, mode, outputs: [] });
  } else {
    if (!page.url().includes(`/minutes/${parsed.token}`)) {
      await page.goto(parsed.url.href, { waitUntil: 'domcontentloaded', timeout: navigationTimeout });
    }
    if (isLoginPage(page.url())) throw new Error('飞书网页登录态无效');

    const initial = await page.evaluate(async ({ token }) => {
      const getJson = async (url) => {
        const response = await fetch(url, { credentials: 'include' });
        const json = await response.json();
        if (!response.ok || json.code !== 0) {
          throw new Error(`API ${response.status} code=${json.code}`);
        }
        return json.data;
      };
      const [status, ids] = await Promise.all([
        getJson(`/minutes/api/status?object_token=${token}&language=zh_cn`),
        getJson(
          `/minutes/api/subtitles/paragraph-ids?page_size=10000&page_num=0` +
          `&object_token=${token}&language=zh_cn`
        )
      ]);
      return {
        statusTitle: status.title || status.topic || '',
        paragraphIds: (ids.list || []).map((item) => item.pid).filter(Boolean),
        oggUrl: status.video_info?.video_download_url || '',
        mp4Url: status.video_info?.audio_url || ''
      };
    }, { token: parsed.token });

    const pageTitle = cleanText(await page.title().catch(() => ''));
    const title = safeName(
      initial.statusTitle ||
      (!/^Feishu(?:\s*-\s*Log in)?$/i.test(pageTitle) ? pageTitle : '') ||
      `feishu-minutes-${parsed.token}`
    );

    const cookies = await context.cookies([
      parsed.url.href,
      'https://ying-dao.feishu.cn',
      'https://internal-api-drive-stream.feishu.cn'
    ]);
    const cookieHeader = cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ');
    const requestHeaders = {
      cookie: cookieHeader,
      referer: parsed.url.href,
      origin: new URL(parsed.url.href).origin,
      'user-agent': await page.evaluate(() => navigator.userAgent)
    };

    function chooseOutput(raw, defaultName) {
      const requested = raw ? path.resolve(String(raw)) : path.join(outputDir, defaultName);
      if (overwrite || reuseExisting || !fs.existsSync(requested)) return requested;
      return uniquePath(requested);
    }

    async function downloadTranscript() {
      if (!initial.paragraphIds.length) throw new Error('妙记没有可导出的全文段落');
      const paragraphs = await page.evaluate(async ({ token, paragraphIds }) => {
        const all = [];
        for (let index = 0; index < paragraphIds.length; index += 1000) {
          const firstPid = paragraphIds[index];
          const url = `/minutes/api/subtitles_v2?paragraph_id=${encodeURIComponent(firstPid)}` +
            `&size=1000&translate_lang=default&is_fluent=false&filter_speaker=false` +
            `&object_token=${token}&language=zh_cn`;
          const response = await fetch(url, { credentials: 'include' });
          const json = await response.json();
          if (!response.ok || json.code !== 0) {
            throw new Error(`subtitles HTTP ${response.status} code=${json.code}`);
          }
          all.push(...(json.data.paragraphs || []));
        }
        return all;
      }, { token: parsed.token, paragraphIds: initial.paragraphIds });
      const extension = `.${format}`;
      let output = chooseOutput(args['transcript-output'], `transcript${extension}`);
      const content = renderTranscript(paragraphs, format, title, parsed.url.href);
      if (reuseExisting && fs.existsSync(output) && await fsp.readFile(output, 'utf8') === content) {
        return {
          kind: 'transcript', path: output, bytes: (await fsp.stat(output)).size,
          format, paragraphs: paragraphs.length, cached: true
        };
      }
      if (fs.existsSync(output) && !overwrite && !reuseExisting) output = uniquePath(output);
      const temporary = `${output}.${process.pid}.part`;
      try {
        await fsp.writeFile(temporary, content, { encoding: 'utf8', mode: 0o600 });
        await fsp.rename(temporary, output);
      } catch (error) {
        await fsp.unlink(temporary).catch(() => {});
        throw error;
      }
      return {
        kind: 'transcript', path: output, bytes: (await fsp.stat(output)).size,
        format, paragraphs: paragraphs.length, cached: false
      };
    }

    async function downloadMedia() {
      const mediaUrl = preferMp4
        ? (initial.mp4Url || initial.oggUrl)
        : (initial.oggUrl || initial.mp4Url);
      if (!mediaUrl) throw new Error('妙记没有可下载的媒体地址');

      const probe = await fetch(mediaUrl, {
        headers: { ...requestHeaders, range: 'bytes=0-0' },
        redirect: 'follow'
      });
      const contentRange = probe.headers.get('content-range') || '';
      const totalBytes = Number(contentRange.match(/\/(\d+)$/)?.[1] || 0);
      const contentType = probe.headers.get('content-type') || '';
      await probe.arrayBuffer();
      const extension = /ogg/i.test(contentType) ? '.ogg'
        : /mp4/i.test(contentType) ? '.mp4'
          : /mpeg/i.test(contentType) ? '.mp3' : '.bin';
      let output = chooseOutput(args['media-output'], `media${extension}`);

      if (reuseExisting && fs.existsSync(output) && totalBytes > 0 &&
          (await fsp.stat(output)).size === totalBytes) {
        return {
          kind: 'media', path: output, bytes: totalBytes,
          content_type: contentType, ranges: 0, cached: true
        };
      }
      if (fs.existsSync(output) && !overwrite && !reuseExisting) output = uniquePath(output);

      if (probe.status === 206 && totalBytes >= rangeThreshold && rangeConcurrency > 1) {
        const chunkSize = Math.ceil(totalBytes / rangeConcurrency);
        const parts = await Promise.all(Array.from({ length: rangeConcurrency }, async (_, index) => {
          const start = index * chunkSize;
          const end = Math.min(totalBytes - 1, start + chunkSize - 1);
          if (start > end) return '';
          const part = `${output}.${process.pid}.part-${index}`;
          const response = await fetch(mediaUrl, {
            headers: { ...requestHeaders, range: `bytes=${start}-${end}` },
            redirect: 'follow'
          });
          if (response.status !== 206 || !response.body) {
            throw new Error(`媒体分片下载失败 HTTP ${response.status}`);
          }
          await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(part, { mode: 0o600 }));
          return part;
        }));
        const validParts = parts.filter(Boolean);
        const assembled = `${output}.${process.pid}.assembling`;
        const outputStream = fs.createWriteStream(assembled, { mode: 0o600 });
        try {
          for (const part of validParts) await appendPart(part, outputStream);
          outputStream.end();
          await once(outputStream, 'finish');
          await fsp.rename(assembled, output);
        } finally {
          await fsp.unlink(assembled).catch(() => {});
          await Promise.all(validParts.map((part) => fsp.unlink(part).catch(() => {})));
        }
        const bytes = (await fsp.stat(output)).size;
        if (bytes !== totalBytes) throw new Error(`媒体大小校验失败 ${bytes}/${totalBytes}`);
        return {
          kind: 'media', path: output, bytes,
          content_type: contentType, ranges: rangeConcurrency, cached: false
        };
      }

      const response = await fetch(mediaUrl, {
        headers: requestHeaders,
        redirect: 'follow'
      });
      if (!response.ok || !response.body) {
        throw new Error(`媒体下载失败 HTTP ${response.status}`);
      }
      const temporary = `${output}.${process.pid}.part`;
      try {
        await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(temporary, { mode: 0o600 }));
        await fsp.rename(temporary, output);
      } catch (error) {
        await fsp.unlink(temporary).catch(() => {});
        throw error;
      }
      const bytes = (await fsp.stat(output)).size;
      if (!bytes) throw new Error('媒体文件为空');
      return {
        kind: 'media', path: output, bytes,
        content_type: contentType, ranges: 1, cached: false
      };
    }

    const jobs = [];
    if (mode === 'media' || mode === 'both') jobs.push(downloadMedia());
    if (mode === 'transcript' || mode === 'both') jobs.push(downloadTranscript());
    const outputs = await Promise.all(jobs);
    const manifest = {
      schema: 'feishu-minutes-web-download.v2',
      token: parsed.token,
      title,
      downloaded_at: new Date().toISOString(),
      elapsed_ms: elapsedMs(),
      outputs
    };
    const manifestPath = path.join(outputDir, 'download.json');
    await fsp.writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n', {
      encoding: 'utf8', mode: 0o600
    });
    emit({ event: 'complete', ok: true, mode, token: parsed.token, title, outputs, manifest: manifestPath });
  }
} catch (error) {
  exitCode = /login|登录/i.test(String(error && error.message)) ? 2 : 1;
  const message = error && error.message ? error.message : String(error);
  const friendly = /ProcessSingleton|profile directory.*in use/i.test(message)
    ? '浏览器 profile 正被另一个 Chrome 进程使用，请等待上一个任务结束后重试'
    : message;
  emit({ event: 'error', ok: false, error: friendly });
} finally {
  if (context) await context.close().catch(() => {});
}

process.exitCode = exitCode;
