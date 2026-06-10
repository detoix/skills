#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const OLD_TEMPLATE_CLASSES = new Set([
  "flow",
  "checklist",
  "timeline",
  "map-board",
  "bars",
  "matrix",
  "myth",
  "flow-step",
  "check-item",
  "split-card",
  "matrix-cell",
  "myth-card",
]);

const PLACEHOLDER_PATTERNS = [
  /replace this creative shell/i,
  /creative shell/i,
  /starter/i,
  /placeholder/i,
  /test harness/i,
  /lorem ipsum/i,
  /template mode/i,
  /b-roll board/i,
];

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    return require("C:\\Users\\kdeptula\\skills\\playwright-broll-recorder\\node_modules\\playwright");
  }
}

function parseArgs(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    switch (arg) {
      case "--project-dir":
        options.projectDir = next;
        i += 1;
        break;
      case "--segment-id":
        options.segmentId = next;
        i += 1;
        break;
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!options.projectDir) throw new Error("Missing required --project-dir");
  options.outputId = options.segmentId;
  if (!options.outputId) throw new Error("Missing required --segment-id");
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/qa_board.mjs --project-dir <dir> --segment-id <id>
`);
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function uniqueBuffers(buffers) {
  const unique = [];
  for (const buffer of buffers) {
    if (!unique.some((seen) => seen.equals(buffer))) unique.push(buffer);
  }
  return unique;
}

function hashText(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function validateCreativeManifest(manifest, failures) {
  const brief = manifest.creative_brief;
  if (!brief || typeof brief !== "object" || Array.isArray(brief)) {
    failures.push("Missing creative_brief object in board manifest");
    return;
  }
  if (typeof brief.visual_metaphor !== "string" || !brief.visual_metaphor.trim()) {
    failures.push("creative_brief.visual_metaphor is required");
  }
  if (!Array.isArray(brief.motion_beats) || brief.motion_beats.length < 2) {
    failures.push("creative_brief.motion_beats must contain at least two beats");
  }
  if (manifest.scene_hash === undefined || typeof manifest.scene_hash !== "string" || manifest.scene_hash.length !== 64) {
    failures.push("manifest.scene_hash must be a SHA-256 hex string");
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const boardDir = path.join(path.resolve(args.projectDir), "broll", "boards", args.outputId);
  const manifestPath = path.join(boardDir, "board-manifest.json");
  if (!(await fileExists(manifestPath))) throw new Error(`Missing board manifest: ${manifestPath}`);
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const htmlPath = path.resolve(manifest.html || path.join(boardDir, "index.html"));
  const previewPath = path.resolve(manifest.preview || path.join(boardDir, "preview.png"));
  const qaPath = path.join(boardDir, "board-qa.json");
  if (!(await fileExists(htmlPath))) throw new Error(`Missing board HTML: ${htmlPath}`);
  const htmlSource = await fs.readFile(htmlPath, "utf8");
  const currentSceneHash = hashText(htmlSource);

  const failures = [];
  validateCreativeManifest(manifest, failures);
  if (manifest.scene_hash !== currentSceneHash) {
    failures.push("manifest.scene_hash does not match current index.html. Re-run create_board.mjs after editing the scene.");
  }

  for (const pattern of PLACEHOLDER_PATTERNS) {
    if (pattern.test(htmlSource)) failures.push(`Placeholder/starter text detected: ${pattern}`);
  }

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: Number(manifest.width), height: Number(manifest.height) },
  });

  try {
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.waitForTimeout(250);
    await fs.mkdir(path.dirname(previewPath), { recursive: true });

    const dom = await page.evaluate((oldTemplateClasses) => {
      const stage = document.querySelector(".stage");
      const textNodes = [...document.querySelectorAll("h1,h2,h3,p,strong,small,span,em,b,li,label,button")];
      const overflow = [];
      const tiny = [];
      const oldClasses = [];
      const animated = [];
      const creativeShell = Boolean(document.querySelector("[data-creative-shell='true'], .creative-shell"));

      for (const node of [...document.querySelectorAll("*")]) {
        for (const className of node.classList) {
          if (oldTemplateClasses.includes(className)) oldClasses.push(className);
        }
        const style = getComputedStyle(node);
        const animationNames = style.animationName.split(",").map((value) => value.trim()).filter((value) => value && value !== "none");
        const transitionDurations = style.transitionDuration.split(",").map((value) => Number.parseFloat(value)).filter((value) => value > 0);
        const rect = node.getBoundingClientRect();
        if ((animationNames.length || transitionDurations.length || node.getAnimations().length) && rect.width > 2 && rect.height > 2) {
          animated.push({
            tag: node.tagName.toLowerCase(),
            className: String(node.className || ""),
            animationName: style.animationName,
            transitionDuration: style.transitionDuration,
            webAnimations: node.getAnimations().length,
          });
        }
      }

      for (const node of textNodes) {
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        const text = (node.textContent || "").trim();
        if (!text || rect.width < 1 || rect.height < 1) continue;
        if (node.scrollWidth > node.clientWidth + 3 || node.scrollHeight > node.clientHeight + 3) {
          overflow.push({ text, width: rect.width, height: rect.height, scrollWidth: node.scrollWidth, scrollHeight: node.scrollHeight });
        }
        const fontSize = Number.parseFloat(style.fontSize);
        if (fontSize < 22) tiny.push({ text, fontSize });
      }
      const stageRect = stage?.getBoundingClientRect();
      return {
        title: document.title,
        stage: stageRect ? { width: stageRect.width, height: stageRect.height } : null,
        overflow,
        tiny,
        oldClasses: [...new Set(oldClasses)],
        creativeShell,
        animatedCount: animated.length,
        animated: animated.slice(0, 12),
        bodyText: document.body.innerText,
        bodyTextLength: document.body.innerText.trim().length,
      };
    }, [...OLD_TEMPLATE_CLASSES]);

    const samples = [];
    const durationMs = Math.max(1000, Number(manifest.duration || 6) * 1000);
    const sampleAt = [0.12, 0.34, 0.62, 0.86].map((ratio) => Math.min(durationMs - 120, Math.max(250, Math.round(durationMs * ratio))));
    let elapsed = 250;
    for (const target of sampleAt) {
      if (target > elapsed) {
        await page.waitForTimeout(target - elapsed);
        elapsed = target;
      }
      samples.push(await page.screenshot({ fullPage: false }));
    }
    await fs.writeFile(previewPath, samples[Math.min(2, samples.length - 1)]);

    const uniqueSampleCount = uniqueBuffers(samples).length;
    const previewStat = await fs.stat(previewPath);

    if (!dom.stage) failures.push("Missing .stage root");
    if (dom.stage && (dom.stage.width !== Number(manifest.width) || dom.stage.height !== Number(manifest.height))) {
      failures.push(`Stage size ${dom.stage.width}x${dom.stage.height} does not match manifest ${manifest.width}x${manifest.height}`);
    }
    if (dom.creativeShell) failures.push("Creative shell/starter scene is still present");
    if (dom.oldClasses.length) failures.push(`Old template classes detected: ${dom.oldClasses.join(", ")}`);
    if (dom.bodyTextLength < 12) failures.push("Board text is too sparse");
    if (dom.overflow.length) failures.push(`Text overflow detected: ${dom.overflow.map((item) => item.text).join(", ")}`);
    if (dom.tiny.length) failures.push(`Text below 22px detected: ${dom.tiny.map((item) => item.text).join(", ")}`);
    if (dom.animatedCount < 4) failures.push(`Too few animated elements: ${dom.animatedCount}; custom motion scenes require at least 4`);
    if (uniqueSampleCount < 3) failures.push(`Scene appears too static; only ${uniqueSampleCount} unique sampled frames`);
    if (previewStat.size < 10000) failures.push("Preview screenshot is suspiciously small");
    const qa = {
      status: failures.length ? "fail" : "pass",
      failures,
      preview: previewPath,
      html: htmlPath,
      width: manifest.width,
      height: manifest.height,
      duration: manifest.duration,
      visual_metaphor: manifest.visual_metaphor,
      motion_beats: manifest.motion_beats,
      dom,
      sampled_frames_unique: uniqueSampleCount,
      sampled_frames_changed: uniqueSampleCount >= 3,
    };
    await fs.writeFile(qaPath, JSON.stringify(qa, null, 2), "utf8");
    console.log(JSON.stringify(qa, null, 2));
    if (failures.length) process.exit(1);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
