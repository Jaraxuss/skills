#!/usr/bin/env node
/**
 * 把任意来源的图片映射成影刀红白粉调。
 *
 * 用途：图库原本最大的约束是"图必须自带红白粉配色"，可用图源因此极少。
 * 先 duotone 再入库，普通商务图片、免费图库图、客户提供的照片都能用。
 *
 * 做法是真正的双色调映射，不是叠一层红色蒙版：
 *   去色 → 调对比/提亮 → 把亮度 0-255 线性映射到 [shadow, highlight] 两个品牌色之间
 *   → 可选混回一点原图，保留人物肤色和场景可读性
 *
 * 用法：
 *   node scripts/duotone.js <输入图> [输出图] [--tier atmosphere|hero|concept]
 *                           [--mix 0.2] [--contrast 1.0] [--lift 0.1]
 *
 * --tier 决定预设：
 *   atmosphere  高提亮、低对比，出来是极淡的粉调，直接能当铺底
 *   hero        保留明暗层次，人物和场景仍然可读，用于封面
 *   concept     最轻，混回较多原图，只统一色温
 */

const sharp = require("sharp");
const path = require("path");
const fs = require("fs");

const hex = (h) => {
  const n = parseInt(h.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

// shadow = 亮度 0 映射到的颜色，highlight = 亮度 255 映射到的颜色
const TIER_PRESETS = {
  atmosphere: { shadow: "#E5919E", highlight: "#FFFDFD", contrast: 0.62, lift: 0.30, mix: 0 },
  hero: { shadow: "#8C1A28", highlight: "#FFF4F6", contrast: 1.06, lift: 0.08, mix: 0.16 },
  concept: { shadow: "#6B2029", highlight: "#FFFFFF", contrast: 1.0, lift: 0.05, mix: 0.28 },
};

async function duotone(input, output, opts = {}) {
  const {
    shadow = "#6E1420",
    highlight = "#FFF4F6",
    contrast = 1.0,
    lift = 0.06,
    mix = 0.2,
  } = opts;

  const meta = await sharp(input).metadata();
  const W = meta.width;
  const H = meta.height;

  const s = hex(shadow);
  const hl = hex(highlight);

  // 1. 去色 + 对比/提亮控制
  const grey = await sharp(input)
    .greyscale()
    .linear(contrast, 255 * lift)
    .png()
    .toBuffer();

  // 2. 亮度 → 双色渐变：out_c = shadow_c + (g/255) * (highlight_c - shadow_c)
  const a = [0, 1, 2].map((i) => (hl[i] - s[i]) / 255);
  const b = [0, 1, 2].map((i) => s[i]);

  let img = sharp(grey).toColourspace("srgb").linear(a, b);

  // 3. 混回原图，找回材质和明暗细节。
  //    混回的是**去饱和**的原图：目的是保留质感，不是保留颜色。
  //    直接混原图会把蓝绿等非品牌色重新带进来，duotone 就白做了。
  if (mix > 0) {
    const duo = await img.png().toBuffer();
    // removeAlpha 必须先调用：ensureAlpha 对已带 alpha 通道的图是空操作，
    // 少了这一步原图会以 100% 不透明盖掉 duotone 结果
    const orig = await sharp(input)
      .resize(W, H, { fit: "fill" })
      .modulate({ saturation: 0.18 })
      .removeAlpha()
      .ensureAlpha(mix)
      .png()
      .toBuffer();
    img = sharp(duo).composite([{ input: orig, blend: "over" }]);
  }

  await img.png({ compressionLevel: 9 }).toFile(output);
  return { width: W, height: H, bytes: fs.statSync(output).size };
}

if (require.main === module) {
  const argv = process.argv.slice(2);
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--")) {
      flags[argv[i].slice(2)] = argv[i + 1];
      i++;
    } else {
      positional.push(argv[i]);
    }
  }
  const [input, outputArg] = positional;
  if (!input) {
    console.error(
      "用法: node scripts/duotone.js <输入图> [输出图] [--tier atmosphere|hero|concept] [--mix 0.2]"
    );
    process.exit(1);
  }
  const tier = flags.tier || "hero";
  const preset = TIER_PRESETS[tier];
  if (!preset) {
    console.error(`未知 tier: ${tier}（可选 ${Object.keys(TIER_PRESETS).join(" / ")}）`);
    process.exit(1);
  }
  const opts = { ...preset };
  for (const k of ["mix", "contrast", "lift"]) {
    if (flags[k] !== undefined) opts[k] = Number(flags[k]);
  }
  if (flags.shadow) opts.shadow = flags.shadow;
  if (flags.highlight) opts.highlight = flags.highlight;

  const output = outputArg || input.replace(path.extname(input), "_duotone.png");

  duotone(input, output, opts)
    .then((r) => {
      console.log(
        `duotone(${tier}) -> ${output}  ${r.width}×${r.height}  ${(r.bytes / 1024).toFixed(0)} KB`
      );
    })
    .catch((e) => {
      console.error("失败:", e.message);
      process.exit(1);
    });
}

module.exports = { duotone, TIER_PRESETS };
