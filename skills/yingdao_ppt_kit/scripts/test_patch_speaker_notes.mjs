#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import JSZip from "jszip";
import pptxgen from "pptxgenjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const patcher = path.join(scriptDir, "patch_speaker_notes.mjs");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

async function makeFixture(target) {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  for (const title of ["封面", "业务成果", "下一步协同"]) {
    const slide = pptx.addSlide();
    slide.addText(title, { x: 1, y: 1, w: 8, h: 1, fontSize: 28 });
  }
  await pptx.writeFile({ fileName: target });

  const zip = await JSZip.loadAsync(await readFile(target));
  for (let index = 1; index <= 4; index += 1) zip.file(`ppt/media/video${index}.mp4`, Buffer.from(`fixture-video-${index}`));
  zip.file("ppt/embeddings/fixture.bin", Buffer.from("fixture-embedding"));
  await writeFile(target, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

async function protectedHashes(fileName) {
  const zip = await JSZip.loadAsync(await readFile(fileName));
  const hashes = new Map();
  for (const name of Object.keys(zip.files).filter((value) => !zip.files[value].dir && (value.startsWith("ppt/media/") || value.startsWith("ppt/embeddings/"))).sort()) {
    hashes.set(name, sha256(await zip.file(name).async("nodebuffer")));
  }
  return hashes;
}

async function notesText(fileName) {
  const zip = await JSZip.loadAsync(await readFile(fileName));
  return (await Promise.all(zip.file(/^ppt\/notesSlides\/notesSlide\d+\.xml$/).map((file) => file.async("string")))).join("\n");
}

async function renderWithLibreOffice(fileName, outputDir) {
  const binary = process.env.SOFFICE_BIN || "soffice";
  const userProfile = `file://${path.join(outputDir, "libreoffice-profile")}`;
  execFileSync(binary, [`-env:UserInstallation=${userProfile}`, "--headless", "--convert-to", "pdf", "--outdir", outputDir, fileName], { stdio: "inherit" });
  const rendered = path.join(outputDir, `${path.basename(fileName, ".pptx")}.pdf`);
  assert((await stat(rendered)).size > 0, "LibreOffice did not produce a PDF from the patched PPTX.");
}

async function main() {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), "yingdao-notes-test-"));
  try {
    const source = path.join(tempDir, "source.pptx");
    const output = path.join(tempDir, "output.pptx");
    const outputAgain = path.join(tempDir, "output-again.pptx");
    const notes = path.join(tempDir, "notes.json");
    await makeFixture(source);
    await writeFile(notes, JSON.stringify({
      version: 1,
      slides: [
        { slide: 1, kind: "main", body: "各位领导，今天先从项目背景开始说明。这里包含 <、> 与 &，用于验证中文和 XML 转义。", transition: "明确背景之后，我们再看已经形成的业务成果。", sources: ["测试 brief"] },
        { slide: 2, kind: "main", body: "这一页聚焦业务成果与可验证的运行证据。", transition: "有了成果基础，最后需要确认下一阶段的协同机制。", sources: [] },
        { slide: 3, kind: "closing", body: "最后，我们将建议收敛为具体责任人与行动项。", closing: "以上是本次汇报的重点，欢迎各位领导提出需要优先展开的方向。", sources: ["测试会议纪要"] },
      ],
    }, null, 2));

    execFileSync(process.execPath, [patcher, "--input", source, "--output", output, "--notes", notes, "--verify"], { stdio: "inherit" });
    execFileSync(process.execPath, [patcher, "--input", output, "--output", outputAgain, "--notes", notes, "--verify"], { stdio: "inherit" });

    const before = await protectedHashes(source);
    const after = await protectedHashes(outputAgain);
    assert(before.size === 5 && before.size === after.size, "Expected four media fixtures and one embedding fixture.");
    for (const [name, hash] of before) assert(after.get(name) === hash, `Protected fixture changed: ${name}`);

    const xml = await notesText(outputAgain);
    assert((xml.match(/<p:notes\b/g) || []).length === 3, "Expected one notes slide per visual slide.");
    assert(xml.includes("&lt;") && xml.includes("&amp;"), "Expected XML escape sequences in notes XML.");
    assert(!xml.includes("----\n----"), "Notes were appended instead of replaced on a repeat run.");
    if (process.argv.includes("--render")) await renderWithLibreOffice(outputAgain, tempDir);
    process.stdout.write("patch_speaker_notes regression test passed.\n");
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`test_patch_speaker_notes: ${error.stack || error.message}\n`);
  process.exitCode = 1;
});
