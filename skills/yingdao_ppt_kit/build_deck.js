// Yingdao customer PPT — 合肥联宝 · 第二天 Python 数据处理培训
// Follows references/design-tokens.md exactly.

const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.title = "影刀 RPA 进阶：Python 数据处理库在 Excel 自动化中的应用";
pres.author = "影刀 · 图南";
pres.company = "影刀 RPA";

// ---------- design tokens ----------
const T = {
  red: "F0263C",
  redDeep: "C9202F",
  pink1: "FFF3F5",
  pink2: "FFE4E9",
  ink: "17181C",
  body: "565B63",
  muted: "8A8F98",
  faint: "B7BCC4",
  line: "F2D8DC",
  cardBorder: "F1E3E6",
  tableLine: "F1F2F4",
  codeBg: "FFF9FA",
  codeHead: "FDEFF1",
  codeEdge: "F4DCE0",
  keyword: "C9202F",
  string: "B45909",
  fn: "7E3F98",
  darkTag: "2B2D33",
  success: "1E7A44",
  successBg: "EDF7F0",
  white: "FFFFFF",
};

const FONT = "Microsoft YaHei";
const FONT_MONO = "Menlo";

// px -> in helpers (1280 x 720)
const PX = 96;
const px = (n) => n / PX;
const IN_W = 13.333;
const IN_H = 7.5;

const asset = (...p) => path.join(__dirname, "assets", ...p);

const LOGO = asset("yingdao_logo.png");
// hero 层：封面主视觉
const HERO = asset("hero", "hero_office_generic.png");
// concept 层：只放内容区，禁止铺底
const IMG_WORKFLOW = asset("concept", "concept_workflow_loop.png");
const IMG_CLEAN = asset("concept", "concept_data_cleaning.png");
const IMG_MATCH = asset("concept", "concept_table_matching.png");
const IMG_PIPE = asset("concept", "concept_data_pipeline.png");
// atmosphere 层：章节页铺底，必配 scrim
const ATMO = {
  orbit: asset("atmosphere", "atmosphere_orbit_grid.png"),
  radial: asset("atmosphere", "atmosphere_radial_rays.png"),
  mesh: asset("atmosphere", "atmosphere_mesh_flow.png"),
  ribbon: asset("atmosphere", "atmosphere_ribbon_wave.png"),
};

// fresh shadow objects each time (pptxgenjs mutates)
const cardShadow = () => ({ type: "outer", angle: 90, offset: 3, blur: 9, color: T.ink, opacity: 0.08 });
const imgShadow = () => ({ type: "outer", angle: 90, offset: 8, blur: 22, color: T.ink, opacity: 0.14 });

// ---------- shared furniture ----------
function addBackground(slide, opts = {}) {
  slide.background = { color: T.white };
  // subtle prism triangle (very faint)
  slide.addShape(pres.ShapeType.line, {
    x: px(540), y: px(720), w: px(360), h: -px(480),
    line: { color: T.ink, width: 0.75, transparency: 97 },
  });
  slide.addShape(pres.ShapeType.line, {
    x: px(900), y: px(240), w: px(360), h: px(480),
    line: { color: T.ink, width: 0.75, transparency: 97 },
  });
  // brand ring top-right (large stroke ring, faint red)
  slide.addShape(pres.ShapeType.ellipse, {
    x: px(1120), y: -px(30), w: px(260), h: px(260),
    fill: { type: "solid", color: T.white, transparency: 100 },
    line: { color: T.red, width: 18, transparency: 95 },
  });
  // pink glow (approximated with a faint rounded rect radial isn't possible; skip)
}

function addFurniture(slide, pageNo, total, opts = {}) {
  // logo top right
  slide.addImage({
    path: LOGO,
    x: IN_W - px(48) - px(90), y: px(38), w: px(90), h: px(26),
  });
  // footer slogan
  slide.addText("From human doing to human being.", {
    x: px(96), y: IN_H - px(46), w: px(500), h: px(24),
    fontFace: FONT, fontSize: 8.5, color: T.faint, charSpacing: 1,
  });
  // page number
  if (pageNo && total) {
    slide.addText(`${String(pageNo).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, {
      x: IN_W - px(150), y: IN_H - px(46), w: px(100), h: px(24),
      fontFace: FONT, fontSize: 9.5, color: T.red, bold: true, align: "right",
    });
  }
}

function addTitleBlock(slide, title, subtitle) {
  // red vertical bar
  slide.addShape(pres.ShapeType.roundRect, {
    x: px(74), y: px(71), w: px(6), h: px(34),
    fill: { color: T.red }, line: { type: "none" }, rectRadius: 0.03,
  });
  // title
  slide.addText(title, {
    x: px(96), y: px(56), w: px(1000), h: px(48),
    fontFace: FONT, fontSize: 23, bold: true, color: T.ink,
    valign: "middle", margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: px(96), y: px(108), w: px(1000), h: px(22),
      fontFace: FONT, fontSize: 12, bold: true, color: T.red, margin: 0,
    });
  }
}

// ---------- SLIDE 1: cover ----------
function slideCover() {
  const s = pres.addSlide();
  s.background = { color: T.white };
  // hero full-bleed
  s.addImage({ path: HERO, x: 0, y: 0, w: IN_W, h: IN_H });
  // white scrim on left (approximate gradient with two overlapping semi-transparent rects)
  s.addShape(pres.ShapeType.rect, {
    x: 0, y: 0, w: px(600), h: IN_H,
    fill: { color: T.white, transparency: 8 }, line: { type: "none" },
  });
  s.addShape(pres.ShapeType.rect, {
    x: px(600), y: 0, w: px(220), h: IN_H,
    fill: { color: T.white, transparency: 30 }, line: { type: "none" },
  });
  // logo
  s.addImage({ path: LOGO, x: IN_W - px(48) - px(100), y: px(38), w: px(100), h: px(30) });

  // badge
  s.addShape(pres.ShapeType.roundRect, {
    x: px(96), y: px(148), w: px(240), h: px(34),
    fill: { color: T.red }, line: { type: "none" }, rectRadius: 0.07,
  });
  s.addText("客户培训 · 第二天 · 2 小时", {
    x: px(96), y: px(148), w: px(240), h: px(34),
    fontFace: FONT, fontSize: 12, bold: true, color: T.white, align: "center", valign: "middle",
    charSpacing: 1, margin: 0,
  });

  // eyebrow
  s.addText("影刀 RPA 进阶", {
    x: px(96), y: px(202), w: px(560), h: px(30),
    fontFace: FONT, fontSize: 16, bold: true, color: T.ink, charSpacing: 2, margin: 0,
  });
  // main title
  s.addText([
    { text: "Python 数据处理库在", options: { breakLine: true } },
    { text: "Excel 自动化中的应用", options: {} },
  ], {
    x: px(96), y: px(240), w: px(720), h: px(160),
    fontFace: FONT, fontSize: 38, bold: true, color: T.ink, lineSpacingMultiple: 1.25, margin: 0,
  });
  // sub
  s.addText("围绕供应链 Excel 场景，把复杂数据处理沉淀为稳定的自动化链路。", {
    x: px(96), y: px(408), w: px(600), h: px(60),
    fontFace: FONT, fontSize: 13, color: T.body, margin: 0,
  });
  // rule + meta
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(514), w: px(34), h: px(3),
    fill: { color: T.red }, line: { type: "none" },
  });
  s.addText("合肥联宝 · 供应链部门     |     主讲：影刀 · 图南", {
    x: px(140), y: px(500), w: px(560), h: px(30),
    fontFace: FONT, fontSize: 11.5, color: "5B6069", bold: true, margin: 0,
  });
  // slogan bottom-left (no pageno on cover)
  s.addText("From human doing to human being.", {
    x: px(96), y: IN_H - px(46), w: px(500), h: px(24),
    fontFace: FONT, fontSize: 9, color: T.faint, charSpacing: 1,
  });
}

// ---------- SLIDE 2: setup / 大字观点页 ----------
function slideSetup(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "为什么第二天要引入 Python？", "影刀跑得动流程，Python 让数据规则跑得稳");

  // Left: big statement + supporting bullets
  s.addText("常规 Excel 指令处理不了的场景，", {
    x: px(96), y: px(184), w: px(760), h: px(50),
    fontFace: FONT, fontSize: 26, color: T.ink, bold: true, margin: 0,
  });
  s.addText([
    { text: "交给 ", options: { color: T.ink } },
    { text: "Python", options: { color: T.red, bold: true } },
    { text: " 处理数据规则；", options: { color: T.ink } },
  ], {
    x: px(96), y: px(232), w: px(760), h: px(50),
    fontFace: FONT, fontSize: 26, bold: true, margin: 0,
  });
  s.addText([
    { text: "影刀继续负责 ", options: { color: T.ink } },
    { text: "流程动作", options: { color: T.red, bold: true } },
    { text: " 与业务闭环。", options: { color: T.ink } },
  ], {
    x: px(96), y: px(282), w: px(760), h: px(50),
    fontFace: FONT, fontSize: 26, bold: true, margin: 0,
  });

  // 3 supporting rows
  const items = [
    ["单表操作可以拖拉拽，", "多表匹配、异常筛选、批量清洗要写规则"],
    ["报表口径经常变，", "让处理逻辑沉淀成脚本，避免每月重做"],
    ["Excel 公式做完了不算结束，", "结果还要接回下发、归档、通知"],
  ];
  const startY = 360;
  items.forEach((it, i) => {
    const y = startY + i * 46;
    // red dot
    s.addShape(pres.ShapeType.ellipse, {
      x: px(96), y: px(y + 12), w: px(9), h: px(9),
      fill: { color: T.red }, line: { type: "none" },
    });
    s.addText([
      { text: it[0], options: { color: T.ink, bold: true } },
      { text: it[1], options: { color: T.body } },
    ], {
      x: px(116), y: px(y), w: px(720), h: px(30),
      fontFace: FONT, fontSize: 12.5, margin: 0,
    });
  });

  // Right: illustrated card
  s.addImage({
    path: IMG_PIPE,
    x: px(864), y: px(180), w: px(340), h: px(300),
    sizing: { type: "cover", w: px(340), h: px(300) },
  });
  // frame
  s.addShape(pres.ShapeType.roundRect, {
    x: px(864), y: px(180), w: px(340), h: px(300),
    fill: { type: "solid", color: T.white, transparency: 100 },
    line: { color: T.ink, width: 0.5, transparency: 90 },
    rectRadius: 0.15,
  });
  s.addText("供应链报表处理链路", {
    x: px(864), y: px(494), w: px(340), h: px(22),
    fontFace: FONT, fontSize: 10.5, color: T.muted, align: "center", margin: 0,
  });

  // bottom pill flow: 第一天  ›  第二天进阶  ›  组合闭环
  drawPillFlow(s, ["第一天：影刀 Excel 基础", "第二天：Python 数据规则", "组合：端到端自动化"], 2);
}

// ---------- helper: bottom pill flow ----------
function drawPillFlow(s, steps, activeIndex) {
  const y = 620;
  let x = 96;
  steps.forEach((step, i) => {
    const isNow = i === activeIndex;
    const w = 8.5 * step.length + 40; // rough width in px
    const wPx = Math.max(w, 130);
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x), y: px(y), w: px(wPx), h: px(34),
      fill: { color: isNow ? T.red : T.pink1 },
      line: { color: isNow ? T.red : T.line, width: 1 },
      rectRadius: 0.24,
    });
    s.addText(step, {
      x: px(x), y: px(y), w: px(wPx), h: px(34),
      fontFace: FONT, fontSize: 10.5, bold: true,
      color: isNow ? T.white : T.redDeep,
      align: "center", valign: "middle", margin: 0,
    });
    x += wPx + 8;
    if (i < steps.length - 1) {
      s.addText("›", {
        x: px(x - 4), y: px(y), w: px(18), h: px(34),
        fontFace: FONT, fontSize: 16, color: "E3A9B2", align: "center", valign: "middle", margin: 0,
      });
      x += 18;
    }
  });
}

/**
 * 蒙版配方，数值见 references/design-tokens.md「蒙版配方」。
 * pptxgenjs 没有渐变填充，用几段不同 transparency 的白矩形近似横向渐变。
 */
function drawScrim(s, kind, opts = {}) {
  if (kind === "left") {
    // 封面用：左侧压到近全白，到画布 58% 处收干净
    [[0, 340, 6], [340, 200, 20], [540, 200, 55], [740, 160, 80]].forEach(([x, w, tr]) => {
      s.addShape(pres.ShapeType.rect, {
        x: px(x), y: 0, w: px(w), h: IN_H,
        fill: { color: T.white, transparency: tr }, line: { type: "none" },
      });
    });
  } else if (kind === "feather") {
    // 半出血图的左缘羽化：三段窄白条，把硬边融进文字区
    const x0 = opts.x || 620;
    [[x0, 60, 15], [x0 + 60, 60, 42], [x0 + 120, 60, 70]].forEach(([x, w, tr]) => {
      s.addShape(pres.ShapeType.rect, {
        x: px(x), y: 0, w: px(w), h: IN_H,
        fill: { color: T.white, transparency: tr }, line: { type: "none" },
      });
    });
  } else if (kind === "band-tb") {
    // 出血图上下柔光带：保护 logo（右上）和页码（右下）的可读性。
    // 图片内容不可控，靠这两道带子把家具区亮度拉到能压字，同时保持出血观感。
    const x = px(opts.x || 0);
    const w = IN_W - x;
    [[0, 32, 12], [32, 32, 30], [64, 34, 62]].forEach(([y, h, tr]) => {
      s.addShape(pres.ShapeType.rect, {
        x, y: px(y), w, h: px(h),
        fill: { color: T.white, transparency: tr }, line: { type: "none" },
      });
    });
    [[620, 34, 58], [654, 32, 26], [686, 34, 8]].forEach(([y, h, tr]) => {
      s.addShape(pres.ShapeType.rect, {
        x, y: px(y), w, h: px(h),
        fill: { color: T.white, transparency: tr }, line: { type: "none" },
      });
    });
  } else if (kind === "wash") {
    // atmosphere 底图铺满后的轻压，只是把纹理再退一档，不做压字用
    s.addShape(pres.ShapeType.rect, {
      x: 0, y: 0, w: IN_W, h: IN_H,
      fill: { color: T.white, transparency: opts.transparency ?? 45 }, line: { type: "none" },
    });
  }
}

const FRAMEWORK = ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"];

// ---------- chapter divider ----------
// variant "split"     ：左文 + 右侧圆角卡片图（样张 slide_b_divider）
// variant "halfbleed" ：左文 + 右侧图三边出血，视觉分量更重，用来给长 deck 换气
//                      底层垫 atmosphere 纹理，左侧文字区不留裸白
function slideDivider(pn, total, partNum, partTotal, bigTitle, subtitle, modules, activeIdx, opts = {}) {
  const variant = opts.variant || "split";
  const s = pres.addSlide();

  if (variant === "halfbleed") {
    s.background = { color: T.white };
    // 1. atmosphere 铺底，给左侧文字区一点纹理
    s.addImage({ path: opts.atmo || ATMO.radial, x: 0, y: 0, w: IN_W, h: IN_H });
    drawScrim(s, "wash", { transparency: 40 });
    // 2. 主图占右侧 660px，上/下/右三边出血
    const imgX = 620;
    s.addImage({
      path: opts.img, x: px(imgX), y: 0, w: IN_W - px(imgX), h: IN_H,
      sizing: { type: "cover", w: IN_W - px(imgX), h: IN_H },
    });
    // 3. 左缘羽化，硬边融进文字区
    drawScrim(s, "feather", { x: imgX });
    // 4. 上下柔光带，保证 logo 和页码压在图上仍可读
    drawScrim(s, "band-tb", { x: imgX });
  } else {
    addBackground(s);
  }
  addFurniture(s, pn, total);

  // halfbleed 整体下移一档、标题加大，让画面呼吸
  const topY = variant === "halfbleed" ? 180 : 148;
  const titleSize = variant === "halfbleed" ? 34 : 32;

  // chip
  s.addShape(pres.ShapeType.roundRect, {
    x: px(96), y: px(topY), w: px(120), h: px(30),
    fill: { color: T.red }, line: { type: "none" }, rectRadius: 0.06,
  });
  s.addText(`第 ${partNum} 部分`, {
    x: px(96), y: px(topY), w: px(120), h: px(30),
    fontFace: FONT, fontSize: 11, bold: true, color: T.white, align: "center", valign: "middle", margin: 0,
  });
  s.addText(`PART 0${partNum} / 0${partTotal}`, {
    x: px(228), y: px(topY), w: px(200), h: px(30),
    fontFace: FONT, fontSize: 12, color: T.muted, bold: true, valign: "middle", charSpacing: 2, margin: 0,
  });
  // halfbleed 的文字区被右侧出血图压到 620px 以内，文本宽度要收窄
  const textW = variant === "halfbleed" ? 480 : 620;

  // big title
  s.addText(bigTitle, {
    x: px(96), y: px(topY + 48), w: px(textW), h: px(130),
    fontFace: FONT, fontSize: titleSize, bold: true, color: T.ink, margin: 0, lineSpacingMultiple: 1.25,
  });
  s.addText(subtitle, {
    x: px(96), y: px(topY + 186), w: px(textW), h: px(52),
    fontFace: FONT, fontSize: 13, color: T.body, margin: 0, lineSpacingMultiple: 1.55,
  });

  // 模块进度列表，单列
  const listY = topY + 250;
  modules.forEach((m, i) => {
    const y = listY + i * 36;
    const active = i === activeIdx;
    s.addShape(pres.ShapeType.ellipse, {
      x: px(96), y: px(y + 11), w: px(9), h: px(9),
      fill: { color: active ? T.red : "D8DBDF" }, line: { type: "none" },
    });
    s.addText(`0${i + 1}   ${m}`, {
      x: px(116), y: px(y), w: px(textW - 20), h: px(28),
      fontFace: FONT, fontSize: 12.5, bold: active,
      color: active ? T.ink : T.muted, margin: 0,
    });
  });

  // right image（仅 split 变体；halfbleed 的图已在上面出血铺好）
  if (variant === "split" && opts.img) {
    s.addImage({
      path: opts.img, x: px(740), y: px(180), w: px(460), h: px(360),
      sizing: { type: "cover", w: px(460), h: px(360) },
    });
    s.addShape(pres.ShapeType.roundRect, {
      x: px(740), y: px(180), w: px(460), h: px(360),
      fill: { type: "solid", color: T.white, transparency: 100 },
      line: { color: T.ink, width: 0.5, transparency: 92 },
      rectRadius: 0.18,
    });
  }

  // bottom pill flow: framework parts
  const flowSteps = [];
  for (let i = 1; i <= partTotal; i++) flowSteps.push(`0${i} · ${FRAMEWORK[i - 1]}`);
  drawPillFlow(s, flowSteps, partNum - 1);
}

// ---------- SLIDE 4: role split ----------
function slideRoleSplit(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "影刀 × Python：谁负责什么", "先分清工具边界，再谈组合价值");

  // 3 columns
  const cols = [
    {
      tag: "影刀 RPA", tagBg: T.red, tagFg: T.white,
      title: "流程动作 · 系统操作",
      pts: [
        "打开文件、下载报表、切换系统",
        "读写 Excel、发邮件、发飞书",
        "定时触发、失败重跑、结果归档",
        "把每一步串起来，业务能直接看",
      ],
    },
    {
      tag: "Python", tagBg: T.darkTag, tagFg: T.white,
      title: "复杂数据规则 · 批量处理",
      pts: [
        "批量清洗：空值、日期、金额、编码",
        "多表匹配：VLOOKUP 力不从心的场景",
        "多条件筛选：交期、库存、异常口径",
        "分组汇总：稳定的报表口径",
      ],
    },
    {
      tag: "影刀 + Python", tagBg: T.white, tagFg: T.red, tagBorder: T.red,
      title: "组合价值 · 端到端闭环",
      pts: [
        "影刀负责“跑起来”",
        "Python 负责“算得准”",
        "结果自动接回通知、归档、审批",
        "同一条流程，业务和 IT 都能维护",
      ],
    },
  ];
  const y0 = 172;
  const cw = 366, gap = 20;
  cols.forEach((c, i) => {
    const x = 96 + i * (cw + gap);
    // card
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x), y: px(y0), w: px(cw), h: px(410),
      fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
      rectRadius: 0.12, shadow: cardShadow(),
    });
    // pill tag
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x + 22), y: px(y0 + 22), w: px(110), h: px(28),
      fill: { color: c.tagBg }, line: c.tagBorder ? { color: c.tagBorder, width: 1 } : { type: "none" },
      rectRadius: 0.19,
    });
    s.addText(c.tag, {
      x: px(x + 22), y: px(y0 + 22), w: px(110), h: px(28),
      fontFace: FONT, fontSize: 10.5, bold: true, color: c.tagFg,
      align: "center", valign: "middle", margin: 0,
    });
    // title
    s.addText(c.title, {
      x: px(x + 22), y: px(y0 + 68), w: px(cw - 44), h: px(30),
      fontFace: FONT, fontSize: 15, bold: true, color: T.ink, margin: 0,
    });
    // separator
    s.addShape(pres.ShapeType.line, {
      x: px(x + 22), y: px(y0 + 108), w: px(30), h: 0,
      line: { color: T.red, width: 2 },
    });
    // bullets
    c.pts.forEach((p, k) => {
      const yy = y0 + 128 + k * 54;
      s.addShape(pres.ShapeType.ellipse, {
        x: px(x + 22), y: px(yy + 8), w: px(6), h: px(6),
        fill: { color: T.red }, line: { type: "none" },
      });
      s.addText(p, {
        x: px(x + 34), y: px(yy), w: px(cw - 56), h: px(48),
        fontFace: FONT, fontSize: 11, color: T.body, margin: 0, lineSpacingMultiple: 1.45,
      });
    });
  });

  drawPillFlow(s, ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"], 0);
}

// ---------- SLIDE 5: Excel → Python 数据结构映射 ----------
function slideConceptExcel(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "把 Excel 翻译成 Python 语言", "先建立映射关系，再谈代码怎么写");

  // table 2 cols: Excel / Python
  const rows = [
    ["Excel 里的东西", "Python 里怎么表达", "举例"],
    ["一个单元格文本", "字符串 (str)", "物料编码、订单号、供应商"],
    ["一个单元格数字", "数字 (int / float)", "数量、金额、比例"],
    ["是否满足条件", "布尔 (bool)", "是否异常、是否已匹配"],
    ["一列日期", "日期时间 (datetime)", "下单、入库、交付日期"],
    ["一列数据", "列表 (list)", "本月订单号清单"],
    ["物料编码 → 物料名称", "字典 (dict)", "编码到名称的对照表"],
    ["整张工作表", "DataFrame", "Pandas 里的表格对象"],
  ];
  const tableX = 96, tableY = 174, tableW = 800;
  const colWs = [230, 210, 360];
  const rowH = 40;
  rows.forEach((r, i) => {
    const y = tableY + i * rowH;
    if (i === 0) {
      // header underline
      s.addShape(pres.ShapeType.line, {
        x: px(tableX), y: px(y + rowH - 4), w: px(tableW), h: 0,
        line: { color: T.red, width: 2 },
      });
    } else {
      if (i % 2 === 0) {
        s.addShape(pres.ShapeType.rect, {
          x: px(tableX), y: px(y), w: px(tableW), h: px(rowH),
          fill: { color: "FFFBFB" }, line: { type: "none" },
        });
      }
      s.addShape(pres.ShapeType.line, {
        x: px(tableX), y: px(y + rowH - 1), w: px(tableW), h: 0,
        line: { color: T.tableLine, width: 0.75 },
      });
    }
    let cx = tableX;
    r.forEach((cell, k) => {
      const isHead = i === 0;
      s.addText(cell, {
        x: px(cx + 10), y: px(y), w: px(colWs[k] - 20), h: px(rowH),
        fontFace: FONT, fontSize: 11, bold: isHead,
        color: isHead ? T.ink : (k === 1 ? T.redDeep : T.body),
        valign: "middle", margin: 0,
      });
      cx += colWs[k];
    });
  });

  // right side: DataFrame conceptual sketch
  const rx = 940, ry = 174, rw = 260, rh = 320;
  s.addShape(pres.ShapeType.roundRect, {
    x: px(rx), y: px(ry), w: px(rw), h: px(rh),
    fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
    rectRadius: 0.12, shadow: cardShadow(),
  });
  s.addText("DataFrame 是什么", {
    x: px(rx + 18), y: px(ry + 16), w: px(rw - 36), h: px(24),
    fontFace: FONT, fontSize: 12.5, bold: true, color: T.ink, margin: 0,
  });
  s.addText("Excel 的一张表 → Python 里的一个 DataFrame。行 = 一条记录，列 = 一个字段，可以像 Excel 一样按字段筛选、增删列。", {
    x: px(rx + 18), y: px(ry + 44), w: px(rw - 36), h: px(96),
    fontFace: FONT, fontSize: 10.5, color: T.body, margin: 0, lineSpacingMultiple: 1.55,
  });
  // mini table sketch
  const miniHeaders = ["订单号", "编码", "数量"];
  const miniRows = [["PO-018", "MAT-88021", "120"], ["PO-019", "MAT-90112", "80"], ["PO-020", "MAT-71503", "45"]];
  const mx = rx + 18, my = ry + 156, mw = rw - 36, mrh = 26;
  miniHeaders.forEach((h, k) => {
    s.addText(h, {
      x: px(mx + k * (mw / 3)), y: px(my), w: px(mw / 3), h: px(mrh),
      fontFace: FONT, fontSize: 10, bold: true, color: T.redDeep, valign: "middle", margin: 0,
    });
  });
  s.addShape(pres.ShapeType.line, {
    x: px(mx), y: px(my + mrh - 2), w: px(mw), h: 0,
    line: { color: T.red, width: 1.5 },
  });
  miniRows.forEach((rr, i) => {
    const yy = my + mrh + i * 32;
    rr.forEach((c, k) => {
      s.addText(c, {
        x: px(mx + k * (mw / 3)), y: px(yy), w: px(mw / 3), h: px(28),
        fontFace: FONT, fontSize: 10, color: T.body, valign: "middle", margin: 0,
      });
    });
    s.addShape(pres.ShapeType.line, {
      x: px(mx), y: px(yy + 30), w: px(mw), h: 0,
      line: { color: T.tableLine, width: 0.75 },
    });
  });

  drawPillFlow(s, ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"], 1);
}

// ---------- SLIDE 6: NumPy vs Pandas ----------
function slideNumpyPandas(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "NumPy 与 Pandas 各自的位置", "Excel 自动化里 90% 的活是 Pandas 干");

  // Two cards
  const cards = [
    {
      tag: "NumPy", tagBg: T.darkTag,
      subtitle: "批量数值计算的底层",
      body: "用来做批量加减乘除、条件判断、缺失值填充和简单统计。Pandas 很多能力底层其实靠它，业务日常不用直接写。",
      chips: ["批量运算", "条件判断", "统计计算", "底层库"],
    },
    {
      tag: "Pandas", tagBg: T.red,
      subtitle: "表格数据处理的主力",
      body: "读写 Excel/CSV、按字段筛选、多表匹配、分组汇总、字段清洗都靠它。DataFrame 就是 Excel 表的 Python 表达。",
      chips: ["读写 Excel", "字段筛选", "多表 merge", "分组汇总"],
    },
  ];
  const y0 = 172;
  const cw = 552, ch = 300, gap = 24;
  cards.forEach((c, i) => {
    const x = 96 + i * (cw + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x), y: px(y0), w: px(cw), h: px(ch),
      fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
      rectRadius: 0.12, shadow: cardShadow(),
    });
    // tag
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x + 22), y: px(y0 + 22), w: px(80), h: px(28),
      fill: { color: c.tagBg }, line: { type: "none" }, rectRadius: 0.2,
    });
    s.addText(c.tag, {
      x: px(x + 22), y: px(y0 + 22), w: px(80), h: px(28),
      fontFace: FONT, fontSize: 11, bold: true, color: T.white, align: "center", valign: "middle", margin: 0,
    });
    s.addText(c.subtitle, {
      x: px(x + 22), y: px(y0 + 62), w: px(cw - 44), h: px(28),
      fontFace: FONT, fontSize: 15, bold: true, color: T.ink, margin: 0,
    });
    s.addText(c.body, {
      x: px(x + 22), y: px(y0 + 100), w: px(cw - 44), h: px(90),
      fontFace: FONT, fontSize: 11.5, color: T.body, margin: 0, lineSpacingMultiple: 1.6,
    });
    // chips
    c.chips.forEach((ch, k) => {
      const cx = x + 22 + k * 122;
      s.addShape(pres.ShapeType.roundRect, {
        x: px(cx), y: px(y0 + 220), w: px(108), h: px(30),
        fill: { color: T.pink1 }, line: { color: T.line, width: 1 }, rectRadius: 0.22,
      });
      s.addText(ch, {
        x: px(cx), y: px(y0 + 220), w: px(108), h: px(30),
        fontFace: FONT, fontSize: 10.5, bold: true, color: T.redDeep,
        align: "center", valign: "middle", margin: 0,
      });
    });
  });

  // Below: 一句结论带
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(510), w: px(1128), h: px(70),
    fill: { color: "FFF3F5" }, line: { type: "none" },
  });
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(510), w: px(5), h: px(70),
    fill: { color: T.red }, line: { type: "none" },
  });
  s.addText([
    { text: "今天课程重点在 ", options: { color: T.ink } },
    { text: "Pandas", options: { color: T.red, bold: true } },
    { text: "。NumPy 只需要知道它是底层，我们用两三行代码演示它在批量计算里的位置就够了。", options: { color: T.ink } },
  ], {
    x: px(120), y: px(510), w: px(1090), h: px(70),
    fontFace: FONT, fontSize: 13, bold: true, valign: "middle", margin: 0,
  });

  drawPillFlow(s, ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"], 1);
}

// ---------- SLIDE 7: Pandas 常用能力清单 ----------
function slidePandasToolbox(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "Pandas 处理 Excel 的六个动作", "一张表进来，做什么，出去");

  const tools = [
    { icon: "①", title: "读取", api: "pd.read_excel(...)", body: "把 Excel 变成 DataFrame，一张表就是一个 df。" },
    { icon: "②", title: "查看", api: "df.head() / .columns / .shape", body: "看看前几行、有哪些字段、多少行多少列。" },
    { icon: "③", title: "筛选", api: 'df[df["状态"] == "异常"]', body: "按字段值挑出关心的行；多条件用 & 和 |。" },
    { icon: "④", title: "计算列", api: 'df["差异"] = df["实际"] - df["计划"]', body: "基于已有字段生成新字段，一列一列加。" },
    { icon: "⑤", title: "缺失值", api: "df.fillna(...) / df.dropna()", body: "空值不能进流程，先填充或按业务规则删除。" },
    { icon: "⑥", title: "输出", api: 'df.to_excel("结果.xlsx", index=False)', body: "结果落成 Excel，交给影刀继续跑。" },
  ];
  const startX = 96, startY = 172;
  const cw = 366, ch = 156, gapX = 20, gapY = 18;
  tools.forEach((t, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = startX + col * (cw + gapX);
    const y = startY + row * (ch + gapY);
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x), y: px(y), w: px(cw), h: px(ch),
      fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
      rectRadius: 0.12, shadow: cardShadow(),
    });
    // icon chip
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x + 18), y: px(y + 18), w: px(30), h: px(30),
      fill: { color: T.pink2 }, line: { type: "none" }, rectRadius: 0.09,
    });
    s.addText(t.icon, {
      x: px(x + 18), y: px(y + 18), w: px(30), h: px(30),
      fontFace: FONT, fontSize: 14, bold: true, color: T.red, align: "center", valign: "middle", margin: 0,
    });
    s.addText(t.title, {
      x: px(x + 58), y: px(y + 18), w: px(cw - 76), h: px(30),
      fontFace: FONT, fontSize: 14, bold: true, color: T.ink, valign: "middle", margin: 0,
    });
    // api chip
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x + 18), y: px(y + 56), w: px(cw - 36), h: px(28),
      fill: { color: T.codeBg }, line: { color: T.codeEdge, width: 1 }, rectRadius: 0.08,
    });
    s.addText(t.api, {
      x: px(x + 24), y: px(y + 56), w: px(cw - 48), h: px(28),
      fontFace: FONT_MONO, fontSize: 10, color: T.redDeep, valign: "middle", margin: 0,
    });
    s.addText(t.body, {
      x: px(x + 18), y: px(y + 92), w: px(cw - 36), h: px(50),
      fontFace: FONT, fontSize: 11, color: T.body, margin: 0, lineSpacingMultiple: 1.5,
    });
  });

  drawPillFlow(s, ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"], 1);
}

// ---------- shared helper: case slide ----------
function drawCasePage(s, pn, total, opts) {
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, opts.title, opts.subtitle);

  // left: 3 semantic cards
  const lx = 96, ly = 172, lw = 400;
  const cards = opts.cards;
  cards.forEach((c, i) => {
    const y = ly + i * 128;
    s.addShape(pres.ShapeType.roundRect, {
      x: px(lx), y: px(y), w: px(lw), h: px(112),
      fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
      rectRadius: 0.12, shadow: cardShadow(),
    });
    // icon chip
    s.addShape(pres.ShapeType.roundRect, {
      x: px(lx + 18), y: px(y + 18), w: px(30), h: px(30),
      fill: { color: c.chipDark ? "EEEFF2" : T.pink2 }, line: { type: "none" }, rectRadius: 0.09,
    });
    s.addText(c.icon, {
      x: px(lx + 18), y: px(y + 18), w: px(30), h: px(30),
      fontFace: FONT, fontSize: 14, bold: true, color: c.chipDark ? T.ink : T.red,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(c.head, {
      x: px(lx + 58), y: px(y + 18), w: px(lw - 76), h: px(30),
      fontFace: FONT, fontSize: 13.5, bold: true, color: T.ink, valign: "middle", margin: 0,
    });
    s.addText(c.body, {
      x: px(lx + 18), y: px(y + 54), w: px(lw - 36), h: px(52),
      fontFace: FONT, fontSize: 11.5, color: T.body, margin: 0, lineSpacingMultiple: 1.5,
    });
  });

  // right: code panel + evidence table
  const rx = 536, ry = 172, rw = 688;
  // code panel
  const codeH = opts.codeH || 232;
  s.addShape(pres.ShapeType.roundRect, {
    x: px(rx), y: px(ry), w: px(rw), h: px(codeH),
    fill: { color: T.codeBg }, line: { color: T.codeEdge, width: 1 },
    rectRadius: 0.12, shadow: cardShadow(),
  });
  s.addShape(pres.ShapeType.rect, {
    x: px(rx + 1), y: px(ry + 1), w: px(rw - 2), h: px(34),
    fill: { color: T.codeHead }, line: { type: "none" },
  });
  // dots
  [0, 1, 2].forEach((k) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: px(rx + 14 + k * 14), y: px(ry + 13), w: px(9), h: px(9),
      fill: { color: ["F4B4BC", "F8CDD3", "FBE3E7"][k] }, line: { type: "none" },
    });
  });
  s.addText(opts.filename, {
    x: px(rx + 64), y: px(ry + 4), w: px(rw - 80), h: px(26),
    fontFace: FONT_MONO, fontSize: 10, color: "A9727B", valign: "middle", margin: 0,
  });
  // code lines with syntax coloring
  const lineH = 22;
  opts.codeLines.forEach((tokens, i) => {
    const yLine = ry + 44 + i * lineH;
    // render tokens by concatenation using richText
    const runs = tokens.map((tk) => {
      const [text, kind] = Array.isArray(tk) ? tk : [tk, "t"];
      let color = "40363A";
      let bold = false;
      if (kind === "k") { color = T.keyword; bold = true; }
      else if (kind === "s") color = T.string;
      else if (kind === "f") color = T.fn;
      else if (kind === "c") color = T.muted;
      else if (kind === "v") color = "0F5FA8";
      return { text, options: { color, bold, fontFace: FONT_MONO } };
    });
    s.addText(runs, {
      x: px(rx + 18), y: px(yLine), w: px(rw - 36), h: px(lineH),
      fontFace: FONT_MONO, fontSize: 10.5, valign: "middle", margin: 0,
    });
  });

  // evidence card
  const ex = rx, ey = ry + codeH + 14, ew = rw;
  const evH = opts.evidence.type === "table" ? 180 : 148;
  s.addShape(pres.ShapeType.roundRect, {
    x: px(ex), y: px(ey), w: px(ew), h: px(evH),
    fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
    rectRadius: 0.12, shadow: cardShadow(),
  });
  s.addText([
    { text: "▸ ", options: { color: T.red, bold: true } },
    { text: opts.evidence.caption, options: { color: T.ink, bold: true } },
  ], {
    x: px(ex + 18), y: px(ey + 12), w: px(ew - 36), h: px(22),
    fontFace: FONT, fontSize: 11.5, margin: 0,
  });
  if (opts.evidence.type === "table") {
    const t = opts.evidence.table;
    const tx = ex + 18, ty = ey + 42, tw = ew - 36;
    const cols = t.cols;
    const colW = tw / cols.length;
    // header
    cols.forEach((c, k) => {
      s.addText(c, {
        x: px(tx + k * colW), y: px(ty), w: px(colW), h: px(24),
        fontFace: FONT, fontSize: 10, bold: true, color: T.redDeep, valign: "middle", margin: 0,
      });
    });
    s.addShape(pres.ShapeType.line, {
      x: px(tx), y: px(ty + 22), w: px(tw), h: 0,
      line: { color: T.pink2, width: 2 },
    });
    t.rows.forEach((rr, ri) => {
      const yy = ty + 26 + ri * 24;
      rr.forEach((cell, k) => {
        // support tag object
        if (typeof cell === "object" && cell.tag) {
          const tagBg = cell.ok ? T.successBg : T.red;
          const tagFg = cell.ok ? T.success : T.white;
          const tw2 = 82;
          s.addShape(pres.ShapeType.roundRect, {
            x: px(tx + k * colW), y: px(yy + 2), w: px(tw2), h: px(18),
            fill: { color: tagBg }, line: { type: "none" }, rectRadius: 0.2,
          });
          s.addText(cell.tag, {
            x: px(tx + k * colW), y: px(yy + 2), w: px(tw2), h: px(18),
            fontFace: FONT, fontSize: 9, bold: true, color: tagFg,
            align: "center", valign: "middle", margin: 0,
          });
        } else {
          s.addText(String(cell), {
            x: px(tx + k * colW), y: px(yy), w: px(colW - 4), h: px(22),
            fontFace: FONT, fontSize: 10, color: T.body, valign: "middle", margin: 0,
          });
        }
      });
      s.addShape(pres.ShapeType.line, {
        x: px(tx), y: px(yy + 22), w: px(tw), h: 0,
        line: { color: T.tableLine, width: 0.75 },
      });
    });
  } else if (opts.evidence.type === "text") {
    s.addText(opts.evidence.text, {
      x: px(ex + 18), y: px(ey + 42), w: px(ew - 36), h: px(evH - 60),
      fontFace: FONT, fontSize: 11.5, color: T.body, margin: 0, lineSpacingMultiple: 1.55,
    });
  }

  // bottom pill flow
  drawPillFlow(s, opts.flow, opts.flowActive != null ? opts.flowActive : opts.flow.length - 1);
}

// ---------- SLIDE 9: case 1 clean ----------
function slideCase1(pn, total) {
  const s = pres.addSlide();
  drawCasePage(s, pn, total, {
    title: "案例 1：批量清洗导出报表",
    subtitle: "自动化流程稳定运行的第一步",
    cards: [
      { icon: "⚠", head: "业务问题", body: "系统导出的 Excel 空行、重复、字段带空格、日期格式不统一，直接进流程就会报错。" },
      { icon: "⚙", head: "处理规则", chipDark: true, body: "去重、删除关键字段为空的行、去空格、日期与数字字段统一格式。" },
      { icon: "✓", head: "输出结果", body: "输出「订单数据_清洗后.xlsx」，供影刀继续做匹配、审核和归档。" },
    ],
    filename: "clean_orders.py",
    codeH: 232,
    codeLines: [
      [["import", "k"], [" pandas ", "t"], ["as", "k"], [" pd", "t"]],
      [""],
      [["df = pd.", "t"], ["read_excel", "f"], ["(", "t"], ['"订单数据.xlsx"', "s"], [")", "t"]],
      [["df = df.", "t"], ["drop_duplicates", "f"], ["()", "t"]],
      [["df = df.", "t"], ["dropna", "f"], ["(subset=[", "t"], ['"物料编码"', "s"], ["])", "t"]],
      [["df[", "t"], ['"供应商"', "s"], ["] = df[", "t"], ['"供应商"', "s"], ["].", "t"], ["astype", "f"], ["(str).str.", "t"], ["strip", "f"], ["()", "t"]],
      [["df[", "t"], ['"下单日期"', "s"], ["] = pd.", "t"], ["to_datetime", "f"], ["(df[", "t"], ['"下单日期"', "s"], ["], errors=", "t"], ['"coerce"', "s"], [")", "t"]],
      [["df[", "t"], ['"计划数量"', "s"], ["] = pd.", "t"], ["to_numeric", "f"], ["(df[", "t"], ['"计划数量"', "s"], ["], errors=", "t"], ['"coerce"', "s"], [")", "t"]],
      [""],
      [["df.", "t"], ["to_excel", "f"], ["(", "t"], ['"订单数据_清洗后.xlsx"', "s"], [", index=", "t"], ["False", "k"], [")", "t"]],
    ],
    evidence: {
      type: "table",
      caption: "清洗前后对照（示意）",
      table: {
        cols: ["订单号", "物料编码", "下单日期", "计划数量", "状态"],
        rows: [
          ["  PO-018 ", " MAT-88021 ", "2026/7/1", "'120'", { tag: "清洗前" }],
          ["PO-018", "MAT-88021", "2026-07-01", "120", { tag: "已清洗", ok: true }],
          ["PO-019", "MAT-90112", "2026-07-02", "80", { tag: "已清洗", ok: true }],
        ],
      },
    },
    flow: ["影刀下载报表", "Python 清洗数据", "输出标准表", "影刀继续流程"],
    flowActive: 3,
  });
}

// ---------- SLIDE 11: case 2 multi-table match ----------
function slideCase2(pn, total) {
  const s = pres.addSlide();
  drawCasePage(s, pn, total, {
    title: "案例 2：多表匹配替代手工 VLOOKUP",
    subtitle: "大批量、多字段、要反复跑的匹配，交给 Pandas 更稳",
    cards: [
      { icon: "⚠", head: "业务问题", body: "订单表要人工 VLOOKUP 物料主数据，字段多、耗时长，漏配很难被发现。" },
      { icon: "⚙", head: "处理规则", chipDark: true, body: "按「物料编码」左连接主数据，补齐名称、类别、负责人；名称为空即判定未匹配。" },
      { icon: "✓", head: "输出结果", body: "完整明细一张、未匹配清单一张，影刀接着做通知与归档。" },
    ],
    filename: "match_orders.py",
    codeLines: [
      [["import", "k"], [" pandas ", "t"], ["as", "k"], [" pd", "t"]],
      [""],
      [["orders = pd.", "t"], ["read_excel", "f"], ["(", "t"], ['"订单表.xlsx"', "s"], [")", "t"]],
      [["master = pd.", "t"], ["read_excel", "f"], ["(", "t"], ['"物料主数据.xlsx"', "s"], [")", "t"]],
      [""],
      [["result = orders.", "t"], ["merge", "f"], ["(master, on=", "t"], ['"物料编码"', "s"], [", how=", "t"], ['"left"', "s"], [")", "t"]],
      [["unmatched = result[result[", "t"], ['"物料名称"', "s"], ["].", "t"], ["isna", "f"], ["()]", "t"]],
      [""],
      [["result.", "t"], ["to_excel", "f"], ["(", "t"], ['"订单匹配结果.xlsx"', "s"], [", index=", "t"], ["False", "k"], [")", "t"]],
      [["unmatched.", "t"], ["to_excel", "f"], ["(", "t"], ['"未匹配清单.xlsx"', "s"], [", index=", "t"], ["False", "k"], [")", "t"]],
    ],
    evidence: {
      type: "table",
      caption: "运行后拿到的表（示意）",
      table: {
        cols: ["订单号", "物料编码", "物料名称", "负责人", "匹配状态"],
        rows: [
          ["PO-018", "MAT-88021", "PCB 主板", "王磊", { tag: "已补齐", ok: true }],
          ["PO-019", "MAT-90112", "散热模组", "李娜", { tag: "已补齐", ok: true }],
          ["PO-020", "MAT-71503", "—", "—", { tag: "未匹配·待复核" }],
        ],
      },
    },
    flow: ["影刀下载报表", "Python 匹配补齐", "输出明细与清单", "影刀通知归档"],
  });
}

// ---------- SLIDE 12: case 3 multi-condition filter ----------
function slideCase3(pn, total) {
  const s = pres.addSlide();
  drawCasePage(s, pn, total, {
    title: "案例 3：多条件筛选出异常清单",
    subtitle: "把「需要人关注的行」自动挑出来",
    cards: [
      { icon: "⚠", head: "业务问题", body: "库存低于安全库存、状态异常、超期未更新，需要每天从大表里挑出来通知负责人。" },
      { icon: "⚙", head: "处理规则", chipDark: true, body: "库存 < 安全库存 或 状态=异常；再筛超过 7 天未更新的记录。" },
      { icon: "✓", head: "输出结果", body: "异常清单、超期清单各一张。有清单就发通知，没清单就跳过。" },
    ],
    filename: "filter_stock.py",
    codeLines: [
      [["import", "k"], [" pandas ", "t"], ["as", "k"], [" pd", "t"]],
      [""],
      [["df = pd.", "t"], ["read_excel", "f"], ["(", "t"], ['"库存数据.xlsx"', "s"], [")", "t"]],
      [""],
      [["abnormal = df[", "t"]],
      [["    (df[", "t"], ['"库存数量"', "s"], ["] < df[", "t"], ['"安全库存"', "s"], ["]) |", "t"]],
      [["    (df[", "t"], ['"状态"', "s"], ["] == ", "t"], ['"异常"', "s"], [")", "t"]],
      [["]", "t"]],
      [""],
      [["overdue = df[df[", "t"], ['"最近更新时间"', "s"], ["] < pd.", "t"], ["Timestamp", "f"], [".today() - pd.", "t"], ["Timedelta", "f"], ["(days=", "t"], ["7", "v"], [")]", "t"]],
    ],
    evidence: {
      type: "table",
      caption: "异常清单（示意）",
      table: {
        cols: ["物料编码", "库存数量", "安全库存", "状态", "负责人"],
        rows: [
          ["MAT-88021", "18", "50", { tag: "低于安全" }, "王磊"],
          ["MAT-71503", "0", "20", { tag: "缺料" }, "李娜"],
          ["MAT-90112", "42", "40", { tag: "状态异常" }, "陈涛"],
        ],
      },
    },
    flow: ["Python 筛选异常", "输出异常清单", "影刀判断是否为空", "自动通知负责人"],
  });
}

// ---------- SLIDE 13: case 4 groupby summary ----------
function slideCase4(pn, total) {
  const s = pres.addSlide();
  drawCasePage(s, pn, total, {
    title: "案例 4：分组汇总替代重复透视表",
    subtitle: "把定期报表沉淀成稳定的统计口径",
    cards: [
      { icon: "⚠", head: "业务问题", body: "每月要按供应商、部门做金额与数量透视，人工维护公式和口径容易出错。" },
      { icon: "⚙", head: "处理规则", chipDark: true, body: "按供应商 sum 金额；按部门同时 count 订单号 与 sum 金额，列名重命名。" },
      { icon: "✓", head: "输出结果", body: "供应商金额汇总、部门订单汇总两张 Excel，影刀发给固定人员并归档。" },
    ],
    filename: "summary_purchase.py",
    codeLines: [
      [["import", "k"], [" pandas ", "t"], ["as", "k"], [" pd", "t"]],
      [""],
      [["df = pd.", "t"], ["read_excel", "f"], ["(", "t"], ['"采购数据.xlsx"', "s"], [")", "t"]],
      [""],
      [["supplier = (df.", "t"], ["groupby", "f"], ["(", "t"], ['"供应商"', "s"], [")[", "t"], ['"金额"', "s"], ["].", "t"], ["sum", "f"], ["().", "t"], ["reset_index", "f"], ["())", "t"]],
      [""],
      [["dept = (df.", "t"], ["groupby", "f"], ["(", "t"], ['"部门"', "s"], [").", "t"], ["agg", "f"], ["({", "t"]],
      [["    ", "t"], ['"订单号"', "s"], [": ", "t"], ['"count"', "s"], [", ", "t"], ['"金额"', "s"], [": ", "t"], ['"sum"', "s"]],
      [["}).", "t"], ["reset_index", "f"], ["())", "t"]],
      [["dept = dept.", "t"], ["rename", "f"], ["(columns={", "t"], ['"订单号"', "s"], [": ", "t"], ['"订单数量"', "s"], [", ", "t"], ['"金额"', "s"], [": ", "t"], ['"总金额"', "s"], ["})", "t"]],
    ],
    evidence: {
      type: "table",
      caption: "部门订单汇总（示意）",
      table: {
        cols: ["部门", "订单数量", "总金额（元）", "环比", "状态"],
        rows: [
          ["整机装配部", "148", "3,820,600", "+8.2%", { tag: "正常", ok: true }],
          ["主板 SMT 部", "92", "2,140,300", "+1.5%", { tag: "正常", ok: true }],
          ["物流调度部", "34", "612,800", "-12.6%", { tag: "关注" }],
        ],
      },
    },
    flow: ["影刀定时取数", "Python 分组汇总", "输出报表", "影刀发送并归档"],
  });
}

// ---------- SLIDE 14: workflow loop ----------
function slideLoop(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "Python 处理结果如何接回影刀", "四步闭环：取数 → 处理 → 出结果 → 通知归档");

  // Left column: 4 steps
  const steps = [
    { no: "01", head: "影刀取数", body: "定时下载、系统抓取或从内网 Excel 打开源数据，交给下一步。" },
    { no: "02", head: "Python 处理", body: "按规则清洗、匹配、筛选、汇总，产出标准结果 Excel。" },
    { no: "03", head: "输出结果", body: "结果表落到共享路径，命名带日期，方便追溯与回滚。" },
    { no: "04", head: "影刀通知归档", body: "有异常发飞书/邮件，无异常静默归档；失败自动重跑。" },
  ];
  const lx = 96, ly = 176;
  steps.forEach((st, i) => {
    const y = ly + i * 92;
    // number
    s.addShape(pres.ShapeType.roundRect, {
      x: px(lx), y: px(y), w: px(50), h: px(50),
      fill: { color: i === 3 ? T.red : T.pink1 }, line: { color: i === 3 ? T.red : T.line, width: 1 },
      rectRadius: 0.09,
    });
    s.addText(st.no, {
      x: px(lx), y: px(y), w: px(50), h: px(50),
      fontFace: FONT, fontSize: 15, bold: true,
      color: i === 3 ? T.white : T.redDeep, align: "center", valign: "middle", margin: 0,
    });
    // head + body
    s.addText(st.head, {
      x: px(lx + 66), y: px(y - 2), w: px(500), h: px(26),
      fontFace: FONT, fontSize: 14, bold: true, color: T.ink, margin: 0,
    });
    s.addText(st.body, {
      x: px(lx + 66), y: px(y + 26), w: px(500), h: px(44),
      fontFace: FONT, fontSize: 11.5, color: T.body, margin: 0, lineSpacingMultiple: 1.55,
    });
  });

  // Right: workflow scene image
  s.addImage({
    path: IMG_WORKFLOW,
    x: px(680), y: px(176), w: px(544), h: px(340),
    sizing: { type: "cover", w: px(544), h: px(340) },
  });
  // caption card
  s.addShape(pres.ShapeType.roundRect, {
    x: px(680), y: px(528), w: px(544), h: px(56),
    fill: { color: T.pink1 }, line: { color: T.line, width: 1 }, rectRadius: 0.09,
  });
  s.addText([
    { text: "组合价值：", options: { color: T.red, bold: true } },
    { text: "同一条流程，业务看得懂、IT 维护得动、结果可追溯。", options: { color: T.ink } },
  ], {
    x: px(696), y: px(528), w: px(512), h: px(56),
    fontFace: FONT, fontSize: 12, bold: true, valign: "middle", margin: 0, lineSpacingMultiple: 1.4,
  });

  drawPillFlow(s, ["定位与分工", "Pandas 基础", "业务案例", "闭环与总结"], 3);
}

// ---------- SLIDE 15: decision matrix ----------
function slideMatrix(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "什么场景用影刀，什么场景用 Python", "一张判断表，把边界讲清楚");

  const cols = ["场景类型", "典型例子", "推荐方案", "为什么"];
  const rows = [
    ["单表操作、字段少", "打开报表 / 复制单元格 / 保存为", { tag: "影刀", scheme: "red" }, "拖拉拽即可，维护成本低"],
    ["跨系统流程编排", "从 ERP 下载 → 处理 → 邮件通知", { tag: "影刀", scheme: "red" }, "影刀本身就是流程编排工具"],
    ["批量清洗 / 格式统一", "空值、日期、编码、数字型转换", { tag: "Python", scheme: "dark" }, "规则明确、批量执行更稳"],
    ["多表匹配 / 复杂 VLOOKUP", "订单 × 主数据 × 供应商信息", { tag: "Python", scheme: "dark" }, "字段多、体量大，写代码更稳定"],
    ["多条件筛选异常", "库存/交期/金额异常识别", { tag: "Python", scheme: "dark" }, "条件复杂、需要每天跑"],
    ["定期分组汇总报表", "按供应商/部门/物料汇总", { tag: "Python", scheme: "dark" }, "口径可复用、维护成本低"],
    ["数据处理 + 流程闭环", "取数 → 处理 → 通知 → 归档", { tag: "影刀 + Python", scheme: "combo" }, "组合能力，端到端自动化"],
  ];
  const tx = 96, ty = 174, tw = 1132;
  const colW = [220, 380, 200, 332];
  const rowH = 40;
  // header row underline
  cols.forEach((c, k) => {
    const xx = tx + colW.slice(0, k).reduce((a, b) => a + b, 0);
    s.addText(c, {
      x: px(xx + 10), y: px(ty), w: px(colW[k] - 20), h: px(rowH),
      fontFace: FONT, fontSize: 11.5, bold: true, color: T.ink, valign: "middle", margin: 0,
    });
  });
  s.addShape(pres.ShapeType.line, {
    x: px(tx), y: px(ty + rowH - 2), w: px(tw), h: 0,
    line: { color: T.red, width: 2 },
  });
  rows.forEach((r, i) => {
    const y = ty + rowH + i * 44;
    if (i % 2 === 1) {
      s.addShape(pres.ShapeType.rect, {
        x: px(tx), y: px(y), w: px(tw), h: px(44),
        fill: { color: "FFFBFB" }, line: { type: "none" },
      });
    }
    r.forEach((cell, k) => {
      const xx = tx + colW.slice(0, k).reduce((a, b) => a + b, 0);
      if (typeof cell === "object" && cell.tag) {
        const scheme = cell.scheme;
        const bg = scheme === "red" ? T.red : scheme === "dark" ? T.darkTag : T.white;
        const fg = scheme === "combo" ? T.red : T.white;
        const border = scheme === "combo" ? { color: T.red, width: 1 } : { type: "none" };
        const cw2 = scheme === "combo" ? 128 : 84;
        s.addShape(pres.ShapeType.roundRect, {
          x: px(xx + 12), y: px(y + 8), w: px(cw2), h: px(26),
          fill: { color: bg }, line: border, rectRadius: 0.19,
        });
        s.addText(cell.tag, {
          x: px(xx + 12), y: px(y + 8), w: px(cw2), h: px(26),
          fontFace: FONT, fontSize: 10.5, bold: true, color: fg,
          align: "center", valign: "middle", margin: 0,
        });
      } else {
        s.addText(cell, {
          x: px(xx + 10), y: px(y), w: px(colW[k] - 20), h: px(44),
          fontFace: FONT, fontSize: 11, color: T.body, valign: "middle", margin: 0,
        });
      }
    });
    s.addShape(pres.ShapeType.line, {
      x: px(tx), y: px(y + 44), w: px(tw), h: 0,
      line: { color: T.tableLine, width: 0.75 },
    });
  });

  // conclusion band
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(556), w: px(1132), h: px(52),
    fill: { color: "FFF3F5" }, line: { type: "none" },
  });
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(556), w: px(5), h: px(52),
    fill: { color: T.red }, line: { type: "none" },
  });
  s.addText([
    { text: "先按业务场景选工具，", options: { color: T.ink } },
    { text: "复杂数据规则 = Python", options: { color: T.red, bold: true } },
    { text: "，", options: { color: T.ink } },
    { text: "跨系统流程 = 影刀", options: { color: T.red, bold: true } },
    { text: "，端到端就用组合。", options: { color: T.ink } },
  ], {
    x: px(120), y: px(556), w: px(1090), h: px(52),
    fontFace: FONT, fontSize: 13, bold: true, valign: "middle", margin: 0,
  });
}

// ---------- SLIDE 16: summary + next steps ----------
function slideSummary(pn, total) {
  const s = pres.addSlide();
  addBackground(s);
  addFurniture(s, pn, total);
  addTitleBlock(s, "下一步：把今天学到的能力落到你的报表上", "从一个真实场景开始，先跑起来再优化");

  const steps = [
    {
      no: "01", title: "选一个高频 Excel 场景",
      body: "从每周/每月都要重复处理的报表里选一个，先选口径最痛的那张。",
      icon: "▣",
    },
    {
      no: "02", title: "梳理业务规则",
      body: "写清楚字段、条件、异常判定、要输出什么表，规则先讲清楚，代码才好落。",
      icon: "▤",
    },
    {
      no: "03", title: "影刀 + Python 接起来",
      body: "影刀取数与通知、Python 做数据规则，用一次真实数据跑通一条完整链路。",
      icon: "▥",
    },
  ];
  const y0 = 176;
  const cw = 366, ch = 240, gap = 20;
  steps.forEach((st, i) => {
    const x = 96 + i * (cw + gap);
    s.addShape(pres.ShapeType.roundRect, {
      x: px(x), y: px(y0), w: px(cw), h: px(ch),
      fill: { color: T.white }, line: { color: T.cardBorder, width: 1 },
      rectRadius: 0.13, shadow: cardShadow(),
    });
    // top red band
    s.addShape(pres.ShapeType.rect, {
      x: px(x), y: px(y0), w: px(cw), h: px(6),
      fill: { color: T.red }, line: { type: "none" },
    });
    // number
    s.addText(st.no, {
      x: px(x + 22), y: px(y0 + 22), w: px(80), h: px(30),
      fontFace: FONT, fontSize: 15, bold: true, color: T.red, margin: 0,
    });
    s.addText(st.title, {
      x: px(x + 22), y: px(y0 + 58), w: px(cw - 44), h: px(30),
      fontFace: FONT, fontSize: 16, bold: true, color: T.ink, margin: 0,
    });
    s.addShape(pres.ShapeType.line, {
      x: px(x + 22), y: px(y0 + 96), w: px(30), h: 0,
      line: { color: T.red, width: 2 },
    });
    s.addText(st.body, {
      x: px(x + 22), y: px(y0 + 112), w: px(cw - 44), h: px(112),
      fontFace: FONT, fontSize: 12, color: T.body, margin: 0, lineSpacingMultiple: 1.6,
    });
  });

  // bottom: Q&A / discussion band
  s.addShape(pres.ShapeType.roundRect, {
    x: px(96), y: px(500), w: px(1128), h: px(96),
    fill: { color: T.pink1 }, line: { color: T.line, width: 1 }, rectRadius: 0.09,
  });
  s.addShape(pres.ShapeType.rect, {
    x: px(96), y: px(500), w: px(5), h: px(96),
    fill: { color: T.red }, line: { type: "none" },
  });
  s.addText("现场讨论", {
    x: px(120), y: px(510), w: px(200), h: px(28),
    fontFace: FONT, fontSize: 14, bold: true, color: T.red, margin: 0,
  });
  s.addText("把手上正在处理的一张 Excel 说给大家听：字段是什么、每次要做什么、卡点在哪一步。我们现场帮你拆一遍：这一段影刀做，哪一段 Python 做，输出结果又怎么接回来。", {
    x: px(120), y: px(536), w: px(1100), h: px(56),
    fontFace: FONT, fontSize: 11.5, color: T.body, margin: 0, lineSpacingMultiple: 1.55,
  });
}

// ---------- assemble ----------
const TOTAL = 16;
slideCover();                       // 1 (no pageno)
slideSetup(2, TOTAL);              // 2
slideDivider(3, TOTAL, 1, 4,
  "第一部分\n定位与分工",
  "影刀 × Python：先分清工具边界，再谈组合价值。",
  ["为什么第二天要引入 Python", "影刀与 Python 的角色分工", "Excel 与 Python 数据结构映射", "NumPy 与 Pandas 各自的位置", "Pandas 常用能力清单"],
  1, { variant: "halfbleed", img: HERO, atmo: ATMO.orbit },
);                                  // 3
slideRoleSplit(4, TOTAL);          // 4
slideConceptExcel(5, TOTAL);       // 5
slideNumpyPandas(6, TOTAL);        // 6
slideDivider(7, TOTAL, 2, 4,
  "第二部分\nPandas 基础动作",
  "读表、看表、筛选、算列、清缺失、输出——六件套。",
  ["读取 Excel 变成 DataFrame", "查看数据结构与形状", "按字段筛选与多条件筛选", "新增计算列", "缺失值处理与格式转换", "输出结果表"],
  0, { variant: "split", img: IMG_CLEAN },
);                                  // 7
slidePandasToolbox(8, TOTAL);      // 8
slideCase1(9, TOTAL);              // 9
slideDivider(10, TOTAL, 3, 4,
  "第三部分\n典型业务案例",
  "四类高频 Excel 场景：清洗、匹配、筛选、汇总。",
  ["案例 1：批量清洗导出报表", "案例 2：多表匹配替代 VLOOKUP", "案例 3：多条件筛选异常清单", "案例 4：分组汇总替代透视表"],
  1, { variant: "halfbleed", img: IMG_MATCH, atmo: ATMO.mesh },
);                                  // 10
slideCase2(11, TOTAL);             // 11
slideCase3(12, TOTAL);             // 12
slideCase4(13, TOTAL);             // 13
slideLoop(14, TOTAL);              // 14
slideMatrix(15, TOTAL);            // 15 (skip divider to keep 15)
// summary as extra
slideSummary(16, TOTAL);           // 16 / 16

// ---------- save ----------
const OUT = path.join(__dirname, "影刀RPA进阶_合肥联宝_Python数据处理库Excel自动化.pptx");
pres.writeFile({ fileName: OUT }).then((f) => {
  console.log("WROTE:", f);
});
