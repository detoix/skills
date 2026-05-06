#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

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
      case "--board-id":
        options.boardId = next;
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
  if (!options.boardId) throw new Error("Missing required --board-id");
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/qa_board.mjs --project-dir <dir> --board-id <id>
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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const boardDir = path.join(path.resolve(args.projectDir), "broll", "boards", args.boardId);
  const manifestPath = path.join(boardDir, "board-manifest.json");
  if (!(await fileExists(manifestPath))) throw new Error(`Missing board manifest: ${manifestPath}`);
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const htmlPath = path.resolve(manifest.html || path.join(boardDir, "index.html"));
  const previewPath = path.resolve(manifest.preview || path.join(boardDir, "preview.png"));
  const qaPath = path.join(boardDir, "board-qa.json");
  if (!(await fileExists(htmlPath))) throw new Error(`Missing board HTML: ${htmlPath}`);

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: Number(manifest.width), height: Number(manifest.height) },
  });

  try {
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.waitForTimeout(1200);
    await fs.mkdir(path.dirname(previewPath), { recursive: true });
    await page.screenshot({ path: previewPath, fullPage: false });

    const dom = await page.evaluate(() => {
      const stage = document.querySelector(".stage");
      const textNodes = [...document.querySelectorAll("h1,p,strong,small,span,.kicker,.metric-number")];
      const overflow = [];
      const tiny = [];
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
        bodyTextLength: document.body.innerText.trim().length,
      };
    });

    const first = await page.screenshot({ fullPage: false });
    await page.waitForTimeout(900);
    const second = await page.screenshot({ fullPage: false });
    const changed = !first.equals(second);
    const previewStat = await fs.stat(previewPath);

    const failures = [];
    if (!dom.stage) failures.push("Missing .stage root");
    if (dom.stage && (dom.stage.width !== Number(manifest.width) || dom.stage.height !== Number(manifest.height))) {
      failures.push(`Stage size ${dom.stage.width}x${dom.stage.height} does not match manifest ${manifest.width}x${manifest.height}`);
    }
    if (dom.bodyTextLength < 12) failures.push("Board text is too sparse");
    if (dom.overflow.length) failures.push(`Text overflow detected: ${dom.overflow.map((item) => item.text).join(", ")}`);
    if (dom.tiny.length) failures.push(`Text below 22px detected: ${dom.tiny.map((item) => item.text).join(", ")}`);
    if (!changed) failures.push("No visible animation/change detected between sampled frames");
    if (previewStat.size < 10000) failures.push("Preview screenshot is suspiciously small");

    const qa = {
      board_id: manifest.board_id,
      status: failures.length ? "fail" : "pass",
      failures,
      preview: previewPath,
      html: htmlPath,
      width: manifest.width,
      height: manifest.height,
      duration: manifest.duration,
      dom,
      sampled_frames_changed: changed,
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
