#!/usr/bin/env node

/**
 * Patch PowerPoint speaker notes without round-tripping slide, media, or OLE
 * content through a presentation editor. `slide` in notes.json is 1-based
 * visual slide order, not the internal slide file number.
 */

import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import JSZip from "jszip";
import { XMLValidator } from "fast-xml-parser";

const REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships";
const REL_NOTES_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide";
const REL_NOTES_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster";
const REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide";
const CONTENT_NOTES_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml";
const CONTENT_NOTES_MASTER = "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml";

function usage() {
  return [
    "Usage: node scripts/patch_speaker_notes.mjs --input source.pptx --output target.pptx --notes notes.json [--verify]",
    "",
    "notes.json uses 1-based visual slide order. Each record requires slide and body; transition or closing is optional.",
  ].join("\n");
}

function parseArgs(argv) {
  const parsed = { verify: false };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--verify") {
      parsed.verify = true;
      continue;
    }
    if (token === "--help" || token === "-h") {
      parsed.help = true;
      continue;
    }
    if (["--input", "--output", "--notes"].includes(token)) {
      const value = argv[index + 1];
      if (!value || value.startsWith("--")) throw new Error(`Missing value for ${token}.`);
      parsed[token.slice(2)] = value;
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${token}`);
  }
  return parsed;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function decodeXml(value) {
  return value
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, "\"")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&");
}

function normalizePartPath(partName) {
  return partName.replace(/^\/+/, "").replace(/\\/g, "/");
}

function resolveTarget(sourcePart, target) {
  return path.posix.normalize(path.posix.join(path.posix.dirname(sourcePart), target));
}

function relativeTarget(sourcePart, targetPart) {
  return path.posix.relative(path.posix.dirname(sourcePart), targetPart);
}

function validateXml(xml, label) {
  const validation = XMLValidator.validate(xml);
  if (validation !== true) {
    throw new Error(`${label} is not valid XML: ${validation.err.msg}`);
  }
}

function xmlHeader() {
  return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>";
}

function emptyRelationshipsXml() {
  return `${xmlHeader()}<Relationships xmlns=\"${REL_NS}\"></Relationships>`;
}

function attributeValue(attributes, name) {
  const match = attributes.match(new RegExp(`\\b${escapeRegExp(name)}\\s*=\\s*([\"'])([\\s\\S]*?)\\1`));
  return match ? decodeXml(match[2]) : undefined;
}

function relationshipList(xml) {
  const records = [];
  const relationRegex = /<Relationship\b([^>]*)\/?>(?:<\/Relationship>)?/g;
  let match;
  while ((match = relationRegex.exec(xml))) {
    const attributes = match[1];
    records.push({
      id: attributeValue(attributes, "Id"),
      type: attributeValue(attributes, "Type"),
      target: attributeValue(attributes, "Target"),
      targetMode: attributeValue(attributes, "TargetMode"),
    });
  }
  return records;
}

function nextRelationshipId(xml) {
  let largest = 0;
  for (const relationship of relationshipList(xml)) {
    const match = String(relationship.id || "").match(/^rId(\d+)$/i);
    if (match) largest = Math.max(largest, Number(match[1]));
  }
  return `rId${largest + 1}`;
}

function addRelationship(xml, { type, target, targetMode }) {
  const existing = relationshipList(xml).find((item) => item.type === type && item.target === target);
  if (existing) return { xml, id: existing.id };
  const id = nextRelationshipId(xml);
  const mode = targetMode ? ` TargetMode=\"${escapeXml(targetMode)}\"` : "";
  const relation = `<Relationship Id=\"${escapeXml(id)}\" Type=\"${escapeXml(type)}\" Target=\"${escapeXml(target)}\"${mode}/>`;
  assert(/<\/Relationships>\s*$/.test(xml), "Relationships XML has no closing Relationships element.");
  return { xml: xml.replace(/<\/Relationships>\s*$/, `${relation}</Relationships>`), id };
}

function findElementEnd(xml, startIndex, tagName) {
  const tokenRegex = new RegExp(`<\\/?${escapeRegExp(tagName)}(?=\\s|/?>)[^>]*>`, "g");
  tokenRegex.lastIndex = startIndex;
  let depth = 0;
  let started = false;
  let match;
  while ((match = tokenRegex.exec(xml))) {
    const token = match[0];
    const isClosing = token.startsWith(`</${tagName}`);
    const isSelfClosing = /\/>$/.test(token);
    if (!started) {
      assert(!isClosing, `Unexpected closing ${tagName} before opening tag.`);
      started = true;
      depth = isSelfClosing ? 0 : 1;
      if (depth === 0) return tokenRegex.lastIndex;
      continue;
    }
    if (isClosing) depth -= 1;
    else if (!isSelfClosing) depth += 1;
    if (depth === 0) return tokenRegex.lastIndex;
  }
  throw new Error(`Unable to find closing tag for ${tagName}.`);
}

function findShapeSpans(xml) {
  const spans = [];
  const openRegex = /<p:sp(?=\s|>)/g;
  let match;
  while ((match = openRegex.exec(xml))) {
    const end = findElementEnd(xml, match.index, "p:sp");
    spans.push({ start: match.index, end, xml: xml.slice(match.index, end) });
    openRegex.lastIndex = end;
  }
  return spans;
}

function nextShapeId(xml) {
  let maximum = 1;
  const idRegex = /<p:cNvPr\b[^>]*\bid\s*=\s*([\"'])(\d+)\1[^>]*\/>/g;
  let match;
  while ((match = idRegex.exec(xml))) maximum = Math.max(maximum, Number(match[2]));
  return maximum + 1;
}

function textParagraphs(text) {
  return text.replace(/\r\n?/g, "\n").split("\n").map((line) => {
    if (!line) return "<a:p/>";
    return `<a:p><a:r><a:rPr lang=\"zh-CN\" dirty=\"0\"/><a:t>${escapeXml(line)}</a:t></a:r></a:p>`;
  }).join("");
}

function textBody(text) {
  return `<p:txBody><a:bodyPr/><a:lstStyle/>${textParagraphs(text)}</p:txBody>`;
}

function bodyPlaceholderShape(id, text) {
  return [
    "<p:sp>",
    `<p:nvSpPr><p:cNvPr id=\"${id}\" name=\"Notes Placeholder ${id}\"/><p:cNvSpPr/><p:nvPr><p:ph type=\"body\" idx=\"1\"/></p:nvPr></p:nvSpPr>`,
    "<p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>",
    textBody(text),
    "</p:sp>",
  ].join("");
}

function slideImagePlaceholderShape(id) {
  return [
    "<p:sp>",
    `<p:nvSpPr><p:cNvPr id=\"${id}\" name=\"Slide Image Placeholder ${id}\"/><p:cNvSpPr/><p:nvPr><p:ph type=\"sldImg\"/></p:nvPr></p:nvSpPr>`,
    "<p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>",
    "<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>",
    "</p:sp>",
  ].join("");
}

function createNotesSlideXml(text) {
  return [
    xmlHeader(),
    "<p:notes xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">",
    "<p:cSld name=\"\"><p:spTree>",
    "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>",
    slideImagePlaceholderShape(2),
    bodyPlaceholderShape(3, text),
    "</p:spTree></p:cSld>",
    "<p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/>",
    "</p:notes>",
  ].join("");
}

function createNotesMasterXml() {
  const level = "<a:lvl1pPr marL=\"0\" indent=\"0\"><a:defRPr lang=\"en-US\"/></a:lvl1pPr>";
  return [
    xmlHeader(),
    "<p:notesMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">",
    "<p:cSld name=\"\"><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>",
    "<p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/>",
    `<p:txStyles><p:titleStyle>${level}</p:titleStyle><p:bodyStyle>${level}</p:bodyStyle><p:otherStyle>${level}</p:otherStyle></p:txStyles>`,
    "</p:notesMaster>",
  ].join("");
}

function isNotesBodyShape(shapeXml) {
  return /<p:ph\b[^>]*\btype\s*=\s*([\"'])body\1[^>]*\/?\s*>/.test(shapeXml)
    || /<p:ph\b[^>]*\bidx\s*=\s*([\"'])1\1[^>]*\/?\s*>/.test(shapeXml);
}

function updateNotesBody(notesXml, notesText) {
  for (const shape of findShapeSpans(notesXml)) {
    if (!isNotesBodyShape(shape.xml)) continue;
    const txMatch = /<p:txBody(?=\s|>)/.exec(shape.xml);
    if (!txMatch) continue;
    const txStart = txMatch.index;
    const txEnd = findElementEnd(shape.xml, txStart, "p:txBody");
    const replacement = `${shape.xml.slice(0, txStart)}${textBody(notesText)}${shape.xml.slice(txEnd)}`;
    return `${notesXml.slice(0, shape.start)}${replacement}${notesXml.slice(shape.end)}`;
  }

  const insertion = notesXml.lastIndexOf("</p:spTree>");
  assert(insertion >= 0, "Notes slide has no shape tree.");
  return `${notesXml.slice(0, insertion)}${bodyPlaceholderShape(nextShapeId(notesXml), notesText)}${notesXml.slice(insertion)}`;
}

function ensureContentType(xml, partName, contentType) {
  const normalized = partName.startsWith("/") ? partName : `/${partName}`;
  const exists = new RegExp(`<Override\\b[^>]*\\bPartName\\s*=\\s*([\"'])${escapeRegExp(normalized)}\\1[^>]*\\/>`).test(xml);
  if (exists) return xml;
  assert(/<\/Types>\s*$/.test(xml), "[Content_Types].xml has no closing Types element.");
  return xml.replace(/<\/Types>\s*$/, `<Override PartName=\"${escapeXml(normalized)}\" ContentType=\"${contentType}\"/></Types>`);
}

function ensureNotesMasterIdList(presentationXml, relationshipId) {
  const existingList = /<p:notesMasterIdLst\b[^>]*>([\s\S]*?)<\/p:notesMasterIdLst>/.exec(presentationXml);
  if (existingList) {
    const idPattern = new RegExp(`<p:notesMasterId\\b[^>]*\\br:id\\s*=\\s*([\"'])${escapeRegExp(relationshipId)}\\1[^>]*\\/?>`);
    if (idPattern.test(existingList[0])) return presentationXml;
    const expanded = existingList[0].replace("</p:notesMasterIdLst>", `<p:notesMasterId r:id=\"${escapeXml(relationshipId)}\"/></p:notesMasterIdLst>`);
    return presentationXml.replace(existingList[0], expanded);
  }
  const list = `<p:notesMasterIdLst><p:notesMasterId r:id=\"${escapeXml(relationshipId)}\"/></p:notesMasterIdLst>`;
  if (presentationXml.includes("<p:sldIdLst")) return presentationXml.replace("<p:sldIdLst", `${list}<p:sldIdLst`);
  return presentationXml.replace("</p:presentation>", `${list}</p:presentation>`);
}

function getNumericSuffix(fileName, prefix, suffix) {
  const match = fileName.match(new RegExp(`^${escapeRegExp(prefix)}(\\d+)${escapeRegExp(suffix)}$`));
  return match ? Number(match[1]) : 0;
}

async function getText(zip, partName) {
  const file = zip.file(partName);
  assert(file, `Missing OOXML part: ${partName}`);
  return file.async("string");
}

async function setText(zip, partName, value) {
  validateXml(value, partName);
  zip.file(partName, value);
}

async function orderedSlideParts(zip) {
  const presentationXml = await getText(zip, "ppt/presentation.xml");
  const relsXml = await getText(zip, "ppt/_rels/presentation.xml.rels");
  const relationships = new Map(relationshipList(relsXml).map((item) => [item.id, item]));
  const ids = [];
  const slideIdRegex = /<p:sldId\b([^>]*)\/?\s*>/g;
  let match;
  while ((match = slideIdRegex.exec(presentationXml))) {
    const id = attributeValue(match[1], "r:id");
    const relation = relationships.get(id);
    if (relation?.type === REL_SLIDE && relation.target) ids.push(resolveTarget("ppt/presentation.xml", relation.target));
  }
  if (ids.length) return ids;
  return zip.file(/^ppt\/slides\/slide\d+\.xml$/)
    .map((file) => file.name)
    .sort((left, right) => getNumericSuffix(left, "ppt/slides/slide", ".xml") - getNumericSuffix(right, "ppt/slides/slide", ".xml"));
}

function relsPartFor(partName) {
  return `${path.posix.dirname(partName)}/_rels/${path.posix.basename(partName)}.rels`;
}

async function getOrCreateRelationships(zip, partName) {
  const relsPart = relsPartFor(partName);
  const file = zip.file(relsPart);
  return { relsPart, xml: file ? await file.async("string") : emptyRelationshipsXml() };
}

async function ensureNotesMaster(zip) {
  const masters = zip.file(/^ppt\/notesMasters\/notesMaster\d+\.xml$/).map((file) => file.name);
  let masterPart = masters.sort((left, right) => left.localeCompare(right))[0];
  if (!masterPart) {
    masterPart = "ppt/notesMasters/notesMaster1.xml";
    await setText(zip, masterPart, createNotesMasterXml());
  }

  const presentationPart = "ppt/presentation.xml";
  const { relsPart, xml: relsXml } = await getOrCreateRelationships(zip, presentationPart);
  const target = relativeTarget(presentationPart, masterPart);
  const relationship = addRelationship(relsXml, { type: REL_NOTES_MASTER, target });
  await setText(zip, relsPart, relationship.xml);

  let presentationXml = await getText(zip, presentationPart);
  presentationXml = ensureNotesMasterIdList(presentationXml, relationship.id);
  await setText(zip, presentationPart, presentationXml);

  let contentTypes = await getText(zip, "[Content_Types].xml");
  contentTypes = ensureContentType(contentTypes, masterPart, CONTENT_NOTES_MASTER);
  await setText(zip, "[Content_Types].xml", contentTypes);
  return masterPart;
}

async function nextNotesSlidePart(zip) {
  const current = zip.file(/^ppt\/notesSlides\/notesSlide\d+\.xml$/).map((file) => file.name);
  const largest = current.reduce((maximum, fileName) => Math.max(maximum, getNumericSuffix(fileName, "ppt/notesSlides/notesSlide", ".xml")), 0);
  return `ppt/notesSlides/notesSlide${largest + 1}.xml`;
}

async function notesPartForSlide(zip, slidePart, masterPart, notesText) {
  const { relsPart: slideRelsPart, xml: slideRelsXml } = await getOrCreateRelationships(zip, slidePart);
  const existing = relationshipList(slideRelsXml).find((item) => item.type === REL_NOTES_SLIDE && item.target);
  if (existing) {
    const part = resolveTarget(slidePart, existing.target);
    assert(zip.file(part), `Slide notes relationship points to missing part: ${part}`);
    return part;
  }

  const notesPart = await nextNotesSlidePart(zip);
  const relationship = addRelationship(slideRelsXml, {
    type: REL_NOTES_SLIDE,
    target: relativeTarget(slidePart, notesPart),
  });
  await setText(zip, slideRelsPart, relationship.xml);
  await setText(zip, notesPart, createNotesSlideXml(notesText));

  const notesRelsPart = relsPartFor(notesPart);
  let notesRelsXml = emptyRelationshipsXml();
  notesRelsXml = addRelationship(notesRelsXml, {
    type: REL_SLIDE,
    target: relativeTarget(notesPart, slidePart),
  }).xml;
  notesRelsXml = addRelationship(notesRelsXml, {
    type: REL_NOTES_MASTER,
    target: relativeTarget(notesPart, masterPart),
  }).xml;
  await setText(zip, notesRelsPart, notesRelsXml);

  let contentTypes = await getText(zip, "[Content_Types].xml");
  contentTypes = ensureContentType(contentTypes, notesPart, CONTENT_NOTES_SLIDE);
  await setText(zip, "[Content_Types].xml", contentTypes);
  return notesPart;
}

function normalizedSources(sources) {
  if (sources === undefined) return [];
  assert(Array.isArray(sources), "sources must be an array of strings.");
  return sources.map((source, index) => {
    assert(typeof source === "string" && source.trim(), `sources[${index}] must be a non-empty string.`);
    return source.trim();
  });
}

function validateRecords(payload) {
  assert(payload && typeof payload === "object", "notes.json must be a JSON object.");
  assert(payload.version === 1, "notes.json version must be 1.");
  assert(Array.isArray(payload.slides) && payload.slides.length, "notes.json slides must be a non-empty array.");
  const usedSlides = new Set();
  return payload.slides.map((record, index) => {
    assert(record && typeof record === "object", `slides[${index}] must be an object.`);
    assert(Number.isInteger(record.slide) && record.slide > 0, `slides[${index}].slide must be a positive integer.`);
    assert(!usedSlides.has(record.slide), `notes.json has duplicate slide ${record.slide}.`);
    usedSlides.add(record.slide);
    assert(typeof record.body === "string" && record.body.trim(), `slides[${index}].body must be a non-empty string.`);
    assert(!(record.transition && record.closing), `slides[${index}] cannot have both transition and closing.`);
    if (record.transition !== undefined) assert(typeof record.transition === "string" && record.transition.trim(), `slides[${index}].transition must be a non-empty string.`);
    if (record.closing !== undefined) assert(typeof record.closing === "string" && record.closing.trim(), `slides[${index}].closing must be a non-empty string.`);
    return {
      slide: record.slide,
      kind: typeof record.kind === "string" ? record.kind : "main",
      body: record.body.trim(),
      transition: record.transition?.trim(),
      closing: record.closing?.trim(),
      sources: normalizedSources(record.sources),
    };
  });
}

function formatNotesText(record) {
  const ending = record.closing || record.transition;
  const chunks = [record.body];
  if (ending) chunks.push(`----\n\n${ending}`);
  if (record.sources.length) chunks.push(`[Sources]\n${record.sources.join("\n")}`);
  return chunks.join("\n\n");
}

function extractNotesText(notesXml) {
  const bodyShape = findShapeSpans(notesXml).find((shape) => isNotesBodyShape(shape.xml));
  assert(bodyShape, "Notes slide has no body placeholder.");
  const lines = [];
  const paragraphRegex = /<a:p(?=\s|>)[^>]*>([\s\S]*?)<\/a:p>|<a:p\s*\/>/g;
  let paragraph;
  while ((paragraph = paragraphRegex.exec(bodyShape.xml))) {
    const runText = [];
    const textRegex = /<a:t[^>]*>([\s\S]*?)<\/a:t>/g;
    let text;
    while ((text = textRegex.exec(paragraph[0]))) runText.push(decodeXml(text[1]));
    lines.push(runText.join(""));
  }
  return lines.join("\n").replace(/\n+$/, "");
}

async function hashPart(zip, name) {
  const data = await zip.file(name).async("nodebuffer");
  return createHash("sha256").update(data).digest("hex");
}

async function protectedPartHashes(zip) {
  const protectedNames = Object.keys(zip.files)
    .filter((name) => !zip.files[name].dir && (name.startsWith("ppt/media/") || name.startsWith("ppt/embeddings/")))
    .sort();
  const hashes = new Map();
  for (const name of protectedNames) hashes.set(name, await hashPart(zip, name));
  return hashes;
}

async function findNotesTextForSlide(zip, slidePart) {
  const { xml } = await getOrCreateRelationships(zip, slidePart);
  const relationship = relationshipList(xml).find((item) => item.type === REL_NOTES_SLIDE && item.target);
  assert(relationship, `Slide ${slidePart} has no notes relationship.`);
  const notesPart = resolveTarget(slidePart, relationship.target);
  return extractNotesText(await getText(zip, notesPart));
}

async function verifyPatch(inputPath, outputPath, records) {
  const [sourceZip, outputZip] = await Promise.all([
    JSZip.loadAsync(await readFile(inputPath)),
    JSZip.loadAsync(await readFile(outputPath)),
  ]);
  const [sourceSlides, outputSlides] = await Promise.all([orderedSlideParts(sourceZip), orderedSlideParts(outputZip)]);
  assert(sourceSlides.length === outputSlides.length, "Slide count changed during notes patch.");
  const sourceMasters = Object.keys(sourceZip.files).filter((name) => name.startsWith("ppt/slideMasters/")).length;
  const outputMasters = Object.keys(outputZip.files).filter((name) => name.startsWith("ppt/slideMasters/")).length;
  assert(sourceMasters === outputMasters, "Slide master count changed during notes patch.");

  const [sourceHashes, outputHashes] = await Promise.all([protectedPartHashes(sourceZip), protectedPartHashes(outputZip)]);
  assert(sourceHashes.size === outputHashes.size, "Media or embedding member count changed during notes patch.");
  for (const [name, hash] of sourceHashes) assert(outputHashes.get(name) === hash, `Protected member changed: ${name}`);

  for (const record of records) {
    const slidePart = outputSlides[record.slide - 1];
    assert(slidePart, `Cannot verify slide ${record.slide}; output deck has fewer slides.`);
    const actual = await findNotesTextForSlide(outputZip, slidePart);
    assert(actual === formatNotesText(record), `Notes text does not match notes.json for visual slide ${record.slide}.`);
  }

  return {
    slides: outputSlides.length,
    notesUpdated: records.length,
    mediaMembers: sourceHashes.size,
    slideMasters: outputMasters,
  };
}

async function patchNotes(inputPath, outputPath, records) {
  assert(path.resolve(inputPath) !== path.resolve(outputPath), "Use a different --output path to preserve the source PPTX.");
  const sourceZip = await JSZip.loadAsync(await readFile(inputPath));
  const slideParts = await orderedSlideParts(sourceZip);
  const masterPart = await ensureNotesMaster(sourceZip);

  for (const record of records) {
    const slidePart = slideParts[record.slide - 1];
    assert(slidePart, `notes.json references slide ${record.slide}, but the deck has ${slideParts.length} slides.`);
    const notesText = formatNotesText(record);
    const notesPart = await notesPartForSlide(sourceZip, slidePart, masterPart, notesText);
    const existingXml = await getText(sourceZip, notesPart);
    await setText(sourceZip, notesPart, updateNotesBody(existingXml, notesText));
  }

  await mkdir(path.dirname(outputPath), { recursive: true });
  const archive = await sourceZip.generateAsync({ type: "nodebuffer", compression: "DEFLATE", compressionOptions: { level: 6 } });
  await writeFile(outputPath, archive);
  return { slides: slideParts.length, notesUpdated: records.length };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  assert(args.input && args.output && args.notes, usage());
  const payload = JSON.parse(await readFile(args.notes, "utf8"));
  const records = validateRecords(payload);
  const result = await patchNotes(args.input, args.output, records);
  const verification = args.verify ? await verifyPatch(args.input, args.output, records) : undefined;
  process.stdout.write(`${JSON.stringify({ ...result, verification }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`patch_speaker_notes: ${error.message}\n`);
  process.exitCode = 1;
});
