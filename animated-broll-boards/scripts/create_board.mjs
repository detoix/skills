#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const FORMATS = {
  vertical: { width: 1080, height: 1920 },
  landscape: { width: 1920, height: 1080 },
};

const REQUIRED_BRIEF_FIELDS = [
  "intent",
  "audience",
  "visual_metaphor",
  "art_direction",
  "composition",
  "motion_beats",
  "copy_blocks",
  "avoid",
  "acceptance_notes",
];

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
      case "--data-json":
        options.dataJson = next;
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
  if (!options.dataJson) throw new Error("Missing required --data-json. Animated boards require a creative brief.");
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/create_board.mjs --project-dir <dir> --board-id <id> --data-json <board-creative-brief.json>

The data JSON must be a creative brief, not a template config. Required fields:
  ${REQUIRED_BRIEF_FIELDS.join(", ")}

Optional fields:
  format: vertical|landscape
  duration: seconds
  narrative_intent: semantic board intent such as process-flow, checklist, timeline
  preset: high-level aesthetic hint only
`);
}

function safeId(value) {
  const cleaned = String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
  if (!cleaned) throw new Error("--board-id must contain a usable filename");
  return cleaned;
}

function hashText(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function requireString(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Creative brief field ${field} must be a non-empty string`);
  }
}

function requireArray(value, field) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`Creative brief field ${field} must be a non-empty array`);
  }
  for (const [index, item] of value.entries()) {
    if (typeof item !== "string" || !item.trim()) {
      throw new Error(`Creative brief field ${field}[${index}] must be a non-empty string`);
    }
  }
}

async function loadCreativeBrief(dataJson) {
  const briefPath = path.resolve(dataJson);
  const brief = JSON.parse(await fs.readFile(briefPath, "utf8"));
  if (!brief || typeof brief !== "object" || Array.isArray(brief)) {
    throw new Error("Creative brief JSON must be an object");
  }
  for (const field of REQUIRED_BRIEF_FIELDS) {
    if (!(field in brief)) throw new Error(`Creative brief is missing required field ${field}`);
  }
  for (const field of ["intent", "audience", "visual_metaphor", "art_direction", "composition", "acceptance_notes"]) {
    requireString(brief[field], field);
  }
  for (const field of ["motion_beats", "copy_blocks", "avoid"]) {
    requireArray(brief[field], field);
  }
  const format = brief.format || "vertical";
  if (!FORMATS[format]) throw new Error("Creative brief format must be vertical or landscape");
  const duration = Number(brief.duration || 6);
  if (!Number.isFinite(duration) || duration <= 0) throw new Error("Creative brief duration must be positive");
  return { briefPath, brief: { ...brief, format, duration } };
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function starterHtml(brief, dimensions) {
  const title = String(brief.intent).replace(/[<&>"]/g, "");
  return `<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=${dimensions.width}, initial-scale=1" />
<title>${title}</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#111;color:#fff;font-family:Inter,Arial,sans-serif}
.stage{width:${dimensions.width}px;height:${dimensions.height}px;display:grid;place-items:center}
.creative-shell{max-width:760px;padding:64px;border:2px dashed #666}
</style>
</head>
<body>
<main class="stage" data-creative-shell="true">
  <section class="creative-shell">
    <h1>Replace this creative shell with a custom motion scene</h1>
    <p>This starter is intentionally rejected by QA. Build original HTML/CSS/JS for: ${title}</p>
  </section>
</main>
</body>
</html>`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const boardId = safeId(args.boardId);
  const { briefPath, brief } = await loadCreativeBrief(args.dataJson);
  const dimensions = FORMATS[brief.format];
  const boardDir = path.join(path.resolve(args.projectDir), "broll", "boards", boardId);
  await fs.mkdir(boardDir, { recursive: true });

  const indexPath = path.join(boardDir, "index.html");
  const briefOutputPath = path.join(boardDir, "board-creative-brief.json");
  const manifestPath = path.join(boardDir, "board-manifest.json");
  const clipPath = path.join(boardDir, `${boardId}.webm`);
  const previewPath = path.join(boardDir, "preview.png");

  if (!(await fileExists(indexPath))) {
    await fs.writeFile(indexPath, starterHtml(brief, dimensions), "utf8");
  }

  const html = await fs.readFile(indexPath, "utf8");
  const sceneHash = hashText(html);
  const briefHash = hashText(JSON.stringify(brief));
  const manifest = {
    board_id: boardId,
    narrative_intent: brief.narrative_intent || brief.intent,
    preset: brief.preset || "custom-directed",
    format: brief.format,
    width: dimensions.width,
    height: dimensions.height,
    duration: brief.duration,
    creative_brief_path: briefOutputPath,
    creative_brief_source: briefPath,
    creative_brief: brief,
    visual_metaphor: brief.visual_metaphor,
    motion_beats: brief.motion_beats,
    scene_hash: sceneHash,
    creative_brief_hash: briefHash,
    html: indexPath,
    preview: previewPath,
    clip: clipPath,
    source_type: "animated-board",
    risk: "synthetic explanatory motion graphic",
  };

  await fs.writeFile(briefOutputPath, JSON.stringify(brief, null, 2), "utf8");
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
  console.log(JSON.stringify({ html: indexPath, brief: briefOutputPath, manifest: manifestPath, clip: clipPath, preview: previewPath }, null, 2));
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
