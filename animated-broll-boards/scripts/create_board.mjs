#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

const FORMATS = {
  vertical: { width: 1080, height: 1920 },
  landscape: { width: 1920, height: 1080 },
};

const PRODUCTION_GATE = "C:\\Users\\kdeptula\\skills\\youtube-autopipeline\\scripts\\production_gate.py";

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
  if (!options.segmentId) throw new Error("Missing required --segment-id");
  return options;
}

function printHelp() {
  console.log(`Usage:
  node scripts/create_board.mjs --project-dir <dir> --segment-id <id>

Default mode derives the creative brief from script.json.
`);
}

function safeId(value) {
  if (value === undefined || value === null || String(value).trim() === "") {
    throw new Error("Output id must be derivable from segment_id");
  }
  const cleaned = String(value).trim().replace(/[^a-zA-Z0-9_-]/g, "_");
  if (!cleaned) throw new Error("Output id must contain a usable filename");
  return cleaned;
}

function hashText(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

async function readJson(filePath, label) {
  try {
    return JSON.parse((await fs.readFile(filePath, "utf8")).replace(/^\uFEFF/, ""));
  } catch (error) {
    throw new Error(`Cannot read ${label} at ${filePath}: ${error.message}`);
  }
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

function normalizeCreativeBrief(brief) {
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
  return { ...brief, format, duration };
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function toStringArray(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function formatFromMetadata(script) {
  const raw = firstString(script?.metadata?.format_mode, "vertical").toLowerCase();
  if (raw === "landscape" || raw === "16:9") return "landscape";
  return "vertical";
}

function findSegment(script, segmentId) {
  const segments = Array.isArray(script?.segments) ? script.segments : [];
  const wanted = segmentId;
  const segment = segments.find((item) => item && item.segment_id === wanted);
  if (!segment) throw new Error(`No script segment found for segment_id=${wanted || "(missing)"}`);
  return segment;
}

async function deriveCreativeBrief(projectDir, segmentId) {
  const root = path.resolve(projectDir);
  const scriptPath = path.join(root, "script.json");
  const script = await readJson(scriptPath, "script.json");
  const segment = findSegment(script, segmentId);
  const acceptance = toStringArray(segment.acceptance_criteria || segment.editor_notes);
  const copyBlocks = toStringArray(segment.on_screen_text);
  const motionBeats = [
    firstString(segment.pattern_interrupt_type, segment.layout),
    firstString(segment.visual_direction, segment.narration),
    ...acceptance.slice(0, 2),
  ].filter(Boolean);
  const avoid = [
    "fake product UI",
    "long paragraphs",
    "unreadable phone-scale text",
    ...acceptance.filter((item) => /\b(no|not|avoid|without|bez|nie)\b/i.test(item)).slice(0, 3),
  ];
  const brief = {
    segment_id: segment.segment_id,
    intent: firstString(segment.visual_direction, segment.narration),
    audience: firstString(script?.metadata?.target_audience, "reel viewer"),
    visual_metaphor: firstString(segment.visual_direction, segment.narration),
    art_direction: firstString(script?.metadata?.visual_style, segment.editor_notes, "custom motion-design board"),
    composition: firstString(
      segment.layout ? `${segment.layout}: ${segment.visual_direction || ""}` : "",
      segment.visual_direction,
    ),
    motion_beats: motionBeats.length ? motionBeats : ["establish visual metaphor", "animate key states", "resolve on readable message"],
    copy_blocks: copyBlocks.length ? copyBlocks : [firstString(segment.on_screen_text, segment.narration, segment.visual_direction)],
    avoid,
    acceptance_notes: acceptance.length ? acceptance.join(" ") : firstString(segment.editor_notes, "Readable at phone scale and aligned with script visual fields."),
    format: formatFromMetadata(script),
    duration: Number(segment.duration_seconds || 6),
    narrative_intent: firstString(segment.pattern_interrupt_type, segment.visual_direction),
    preset: "custom-directed",
  };
  return {
    briefPath: path.relative(root, scriptPath),
    brief: normalizeCreativeBrief(brief),
  };
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

function runProductionGate(projectDir, brief) {
  const args = [
    PRODUCTION_GATE,
    "--project-dir",
    path.resolve(projectDir),
    "--require-broll-source-type",
    "synthetic-motion",
  ];
  if (typeof brief.segment_id === "string" && brief.segment_id.trim()) {
    args.push("--segment-id", brief.segment_id.trim());
  }
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || "python", args, { stdio: "inherit", windowsHide: true });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Creative gate failed before board creation. Command exited ${code}: python ${args.join(" ")}`));
    });
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { briefPath, brief } = await deriveCreativeBrief(args.projectDir, args.segmentId);
  const outputId = safeId(args.segmentId);
  await runProductionGate(args.projectDir, brief);
  const dimensions = FORMATS[brief.format];
  const boardDir = path.join(path.resolve(args.projectDir), "broll", "boards", outputId);
  await fs.mkdir(boardDir, { recursive: true });

  const indexPath = path.join(boardDir, "index.html");
  const briefOutputPath = path.join(boardDir, "board-creative-brief.json");
  const manifestPath = path.join(boardDir, "board-manifest.json");
  const clipPath = path.join(boardDir, `${outputId}.webm`);
  const previewPath = path.join(boardDir, "preview.png");

  if (!(await fileExists(indexPath))) {
    await fs.writeFile(indexPath, starterHtml(brief, dimensions), "utf8");
  }

  const html = await fs.readFile(indexPath, "utf8");
  const sceneHash = hashText(html);
  const briefHash = hashText(JSON.stringify(brief));
  const manifest = {
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
    source_type: "synthetic-motion",
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
