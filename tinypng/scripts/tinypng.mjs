#!/usr/bin/env node

import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import tinify from "tinify";

const FORMAT_TYPES = {
  webp: "image/webp",
  png: "image/png",
  jpeg: "image/jpeg",
  avif: "image/avif",
};
const RESIZE_METHODS = new Set(["scale", "fit", "cover", "thumb"]);

function usage() {
  return `TinyPNG/Tinify image optimizer

Usage:
  node scripts/tinypng.mjs <file-or-url> [options]
  node scripts/tinypng.mjs --validate

Options:
  -o, --output <path>       Output file or existing directory
  -f, --format <format>     keep|webp|png|jpeg|avif|smallest (default: keep)
      --resize <method>     scale|fit|cover|thumb
      --width <pixels>      Resize width
      --height <pixels>     Resize height
      --preserve <fields>   Comma-separated metadata fields
      --force               Replace an existing output file
      --json                Print machine-readable output
      --validate            Validate credentials without compressing
  -h, --help                Show this help

Environment:
  TINIFY_API_KEY or TINYPNG_API_KEY
`;
}

function fail(message) {
  throw new Error(message);
}

function positiveInteger(value, flag) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    fail(`${flag} must be a positive integer.`);
  }
  return parsed;
}

function parseArgs(argv) {
  const options = {
    input: null,
    output: null,
    format: "keep",
    resize: null,
    width: null,
    height: null,
    preserve: [],
    force: false,
    json: false,
    validate: false,
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      const value = argv[index + 1];
      if (!value || value.startsWith("-")) fail(`${arg} requires a value.`);
      index += 1;
      return value;
    };

    if (arg === "-h" || arg === "--help") options.help = true;
    else if (arg === "--validate") options.validate = true;
    else if (arg === "--force") options.force = true;
    else if (arg === "--json") options.json = true;
    else if (arg === "-o" || arg === "--output") options.output = next();
    else if (arg === "-f" || arg === "--format") options.format = next().toLowerCase();
    else if (arg === "--resize") options.resize = next().toLowerCase();
    else if (arg === "--width") options.width = positiveInteger(next(), arg);
    else if (arg === "--height") options.height = positiveInteger(next(), arg);
    else if (arg === "--preserve") {
      options.preserve = next().split(",").map((value) => value.trim()).filter(Boolean);
    } else if (arg.startsWith("-")) fail(`Unknown option: ${arg}`);
    else if (options.input) fail("Only one input is accepted per invocation.");
    else options.input = arg;
  }

  return options;
}

function validateOptions(options) {
  const formats = new Set(["keep", ...Object.keys(FORMAT_TYPES), "smallest"]);
  if (!formats.has(options.format)) fail(`Unsupported format: ${options.format}`);
  if (options.resize && !RESIZE_METHODS.has(options.resize)) {
    fail(`Unsupported resize method: ${options.resize}`);
  }
  if (!options.resize && (options.width || options.height)) {
    fail("--width and --height require --resize.");
  }
  if (options.resize === "scale" && Boolean(options.width) === Boolean(options.height)) {
    fail("The scale method requires exactly one of --width or --height.");
  }
  if (options.resize && options.resize !== "scale" && (!options.width || !options.height)) {
    fail(`${options.resize} requires both --width and --height.`);
  }
  if (!options.validate && !options.input) fail("Provide a local image file or image URL.");
}

function isUrl(value) {
  return /^https?:\/\//i.test(value);
}

async function exists(target) {
  try {
    return await stat(target);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function sourceStem(input) {
  if (!isUrl(input)) return path.parse(path.resolve(input)).name;
  const pathname = new URL(input).pathname;
  return path.parse(path.basename(pathname) || "image").name || "image";
}

async function resolveOutput(input, requested, extension) {
  const generatedName = `${sourceStem(input)}.tinypng.${extension}`;
  if (!requested) {
    return isUrl(input)
      ? path.resolve(generatedName)
      : path.join(path.dirname(path.resolve(input)), generatedName);
  }

  const resolved = path.resolve(requested);
  const info = await exists(resolved);
  if (info?.isDirectory()) return path.join(resolved, generatedName);
  return resolved;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  validateOptions(options);

  const apiKey = process.env.TINIFY_API_KEY || process.env.TINYPNG_API_KEY;
  if (!apiKey) fail("Set TINIFY_API_KEY or TINYPNG_API_KEY before using the TinyPNG API.");
  tinify.key = apiKey;

  if (options.validate) {
    await tinify.validate();
    const result = {
      valid: true,
      compressionCount: tinify.compressionCount ?? null,
    };
    process.stdout.write(options.json ? `${JSON.stringify(result)}\n` : "TinyPNG credentials are valid.\n");
    return;
  }

  const localInput = !isUrl(options.input);
  const absoluteInput = localInput ? path.resolve(options.input) : options.input;
  let inputBytes = null;
  if (localInput) {
    const inputInfo = await exists(absoluteInput);
    if (!inputInfo?.isFile()) fail(`Input file does not exist: ${absoluteInput}`);
    inputBytes = inputInfo.size;
  }

  let source = localInput ? tinify.fromFile(absoluteInput) : tinify.fromUrl(options.input);
  if (options.resize) {
    source = source.resize({
      method: options.resize,
      ...(options.width ? { width: options.width } : {}),
      ...(options.height ? { height: options.height } : {}),
    });
  }
  if (options.preserve.length) source = source.preserve(...options.preserve);
  if (options.format === "smallest") {
    source = source.convert({ type: Object.values(FORMAT_TYPES) });
  } else if (options.format !== "keep") {
    source = source.convert({ type: FORMAT_TYPES[options.format] });
  }

  const result = source.result();
  const extension = (await result.extension()) || (
    localInput ? path.extname(absoluteInput).slice(1).toLowerCase() : "image"
  );
  const output = await resolveOutput(options.input, options.output, extension);
  const outputInfo = await exists(output);
  if (outputInfo && !options.force) {
    fail(`Output already exists: ${output}. Use --force to replace it.`);
  }
  if (outputInfo?.isDirectory()) fail(`Output path is a directory: ${output}`);

  await mkdir(path.dirname(output), { recursive: true });
  await result.toFile(output);
  const outputBytes = (await stat(output)).size;
  const report = {
    input: options.input,
    output,
    inputBytes,
    outputBytes,
    savedBytes: inputBytes === null ? null : inputBytes - outputBytes,
    reductionPercent: inputBytes === null || inputBytes === 0
      ? null
      : Number(((1 - outputBytes / inputBytes) * 100).toFixed(2)),
    mediaType: (await result.mediaType()) || null,
    extension,
    compressionCount: tinify.compressionCount ?? null,
  };

  if (options.json) {
    process.stdout.write(`${JSON.stringify(report)}\n`);
  } else {
    process.stdout.write(`Wrote ${output}\n`);
    process.stdout.write(`Size: ${inputBytes ?? "unknown"} -> ${outputBytes} bytes`);
    if (report.reductionPercent !== null) {
      process.stdout.write(` (${report.reductionPercent}% smaller)`);
    }
    process.stdout.write("\n");
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`TinyPNG error: ${message}\n`);
  process.exitCode = 1;
});
