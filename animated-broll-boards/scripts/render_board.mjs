#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

const RECORDER = "C:\\Users\\kdeptula\\skills\\playwright-broll-recorder\\scripts\\record_broll.mjs";
const PRODUCTION_GATE = "C:\\Users\\kdeptula\\skills\\youtube-autopipeline\\scripts\\production_gate.py";

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
      case "--output":
        options.output = next;
        i += 1;
        break;
      case "--duration":
        options.duration = Number(next);
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
  node scripts/render_board.mjs --project-dir <dir> --board-id <id> [--output <file.webm>] [--duration <seconds>]
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

function runNode(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { stdio: "inherit", windowsHide: true });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Command failed with exit code ${code}: node ${args.join(" ")}`));
    });
  });
}

function ffmpegPath() {
  const known = path.join(process.env.USERPROFILE || "", "Documents", "FFmpeg", "ffmpeg-master-latest-win64-gpl", "bin", "ffmpeg.exe");
  return known || "ffmpeg";
}

function runCommand(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", windowsHide: true });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Command failed with exit code ${code}: ${command} ${args.join(" ")}`));
    });
  });
}

function runProductionGate(projectDir, boardId) {
  return runCommand(process.env.PYTHON || "python", [
    PRODUCTION_GATE,
    "--project-dir",
    path.resolve(projectDir),
    "--require-source-strategy",
    "synthetic-motion",
    "--board-id",
    boardId,
  ]);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await runProductionGate(args.projectDir, args.boardId);
  const boardDir = path.join(path.resolve(args.projectDir), "broll", "boards", args.boardId);
  const manifestPath = path.join(boardDir, "board-manifest.json");
  if (!(await fileExists(manifestPath))) throw new Error(`Missing board manifest: ${manifestPath}`);
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const htmlPath = path.resolve(manifest.html || path.join(boardDir, "index.html"));
  const output = path.resolve(args.output || manifest.clip || path.join(boardDir, `${args.boardId}.webm`));
  const preview = path.resolve(manifest.preview || path.join(boardDir, "preview.png"));
  const duration = Number.isFinite(args.duration) ? args.duration : Number(manifest.duration || 6);
  const rawOutput = path.join(boardDir, `${args.boardId}.raw-recording.webm`);
  const qaPath = path.join(boardDir, "board-qa.json");
  if (!(await fileExists(htmlPath))) throw new Error(`Missing board HTML: ${htmlPath}`);
  if (!(await fileExists(qaPath))) throw new Error(`Missing passing QA report. Run qa_board.mjs before render: ${qaPath}`);
  const qa = JSON.parse(await fs.readFile(qaPath, "utf8"));
  if (qa.status !== "pass") throw new Error(`Board QA status must be pass before render. Current status: ${qa.status || "unknown"}`);

  await runNode([
    RECORDER,
    "--url",
    pathToFileURL(htmlPath).href,
    "--output",
    rawOutput,
    "--duration",
    String(duration + 2),
    "--scroll",
    "static",
    "--viewport",
    `${manifest.width}x${manifest.height}`,
    "--video-size",
    `${manifest.width}x${manifest.height}`,
    "--settle-ms",
    "120",
  ]);

  await runCommand(ffmpegPath(), [
    "-y",
    "-v",
    "error",
    "-i",
    rawOutput,
    "-t",
    String(duration),
    "-an",
    "-vf",
    `fps=30,scale=${manifest.width}:${manifest.height}`,
    "-c:v",
    "libvpx",
    "-deadline",
    "realtime",
    "-cpu-used",
    "6",
    "-b:v",
    "2M",
    output,
  ]);
  await fs.rm(rawOutput, { force: true });

  if (!(await fileExists(output))) throw new Error(`Recorder did not create output: ${output}`);
  manifest.clip = output;
  manifest.rendered = true;
  manifest.rendered_at = new Date().toISOString();
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
  console.log(JSON.stringify({ output, manifest: manifestPath, preview }, null, 2));
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
