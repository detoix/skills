#!/usr/bin/env node

import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn, spawnSync } from "node:child_process";
import { chromium } from "playwright";

const PRODUCTION_GATE = "C:\\Users\\kdeptula\\skills\\youtube-autopipeline\\scripts\\production_gate.py";
const TIMINGS_RELATIVE_PATH = path.join("manifests", "production-timings.jsonl");

function parseArgs(argv) {
  const options = {
    duration: 12,
    scroll: "constant",
    viewport: "1600x900",
    videoSize: "1600x900",
    settleMs: 1500,
    screenshot: null,
    click: [],
    hide: [],
    cookieConsent: "off",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    switch (arg) {
      case "--url":
        options.url = next;
        i += 1;
        break;
      case "--output":
        options.output = next;
        i += 1;
        break;
      case "--project-dir":
        options.projectDir = next;
        i += 1;
        break;
      case "--duration":
        options.duration = Number(next);
        i += 1;
        break;
      case "--scroll":
        options.scroll = next;
        i += 1;
        break;
      case "--viewport":
        options.viewport = next;
        i += 1;
        break;
      case "--video-size":
        options.videoSize = next;
        i += 1;
        break;
      case "--wait-for-selector":
        options.waitForSelector = next;
        i += 1;
        break;
      case "--click":
        options.click.push(next);
        i += 1;
        break;
      case "--hide":
        options.hide.push(next);
        i += 1;
        break;
      case "--cookie-consent":
        options.cookieConsent = normalizeCookieConsent(next);
        i += 1;
        break;
      case "--settle-ms":
        options.settleMs = Number(next);
        i += 1;
        break;
      case "--screenshot":
        options.screenshot = next;
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

  if (!options.url) {
    throw new Error("Missing required --url");
  }
  if (!options.output) {
    throw new Error("Missing required --output");
  }
  if (!Number.isFinite(options.duration) || options.duration <= 0) {
    throw new Error("--duration must be a positive number");
  }
  if (!Number.isFinite(options.settleMs) || options.settleMs < 0) {
    throw new Error("--settle-ms must be zero or greater");
  }
  options.scroll = normalizeScrollMode(options.scroll);

  options.viewport = parseSize(options.viewport, "--viewport");
  options.videoSize = parseSize(options.videoSize, "--video-size");

  const resolved = path.resolve(options.output);
  options.output = resolved.toLowerCase().endsWith(".webm") ? resolved : `${resolved}.webm`;
  if (options.screenshot) {
    options.screenshot = path.resolve(options.screenshot);
  }

  return options;
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function inferProjectDir(options) {
  if (options.projectDir) return path.resolve(options.projectDir);
  let current = path.dirname(path.resolve(options.output));
  while (true) {
    if (
      (await fileExists(path.join(current, "script.json"))) &&
      (await fileExists(path.join(current, "manifests", "visual-plan.json")))
    ) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  throw new Error("Production recording requires --project-dir or an output path inside an approved project.");
}

function runProductionGate(projectDir) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || "python", [PRODUCTION_GATE, "--project-dir", projectDir], { stdio: "inherit", windowsHide: true });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Creative gate failed before browser recording. Command exited ${code}.`));
    });
  });
}

function utcNow() {
  return new Date().toISOString();
}

function gpuSnapshot() {
  const result = spawnSync("nvidia-smi", [
    "--query-gpu=name,memory.total,memory.used,utilization.gpu",
    "--format=csv,noheader,nounits",
  ], { encoding: "utf8", timeout: 2000, windowsHide: true });
  if (result.error || result.status !== 0) {
    return { available: false, reason: result.error ? result.error.message : String(result.stderr || "nvidia-smi failed").trim() };
  }
  const devices = String(result.stdout || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, total, used, utilization] = line.split(",").map((part) => part.trim());
      return {
        name,
        memory_total_mib: Number(total),
        memory_used_mib: Number(used),
        utilization_gpu_percent: Number(utilization),
      };
    });
  return { available: true, devices };
}

async function appendTiming(projectDir, event) {
  const timingsPath = path.join(projectDir, TIMINGS_RELATIVE_PATH);
  await fs.mkdir(path.dirname(timingsPath), { recursive: true });
  await fs.appendFile(timingsPath, `${JSON.stringify(event)}\n`, "utf8");
}

async function startStage(projectDir, stage, command, metadata = {}) {
  const record = {
    run_id: `${Date.now().toString(36)}-${Math.random().toString(16).slice(2)}`,
    event: "stage_start",
    stage,
    timestamp_utc: utcNow(),
    perf_counter: performance.now(),
    pid: process.pid,
    command,
    metadata,
    gpu: gpuSnapshot(),
  };
  const publicRecord = { ...record };
  delete publicRecord.perf_counter;
  await appendTiming(projectDir, publicRecord);
  return record;
}

async function endStage(projectDir, record, status, returnCode = null, error = null, metadata = {}) {
  await appendTiming(projectDir, {
    run_id: record.run_id,
    event: "stage_end",
    stage: record.stage,
    timestamp_utc: utcNow(),
    duration_seconds: Number(((performance.now() - record.perf_counter) / 1000).toFixed(3)),
    pid: process.pid,
    status,
    return_code: returnCode,
    error,
    command: record.command,
    metadata,
    gpu: gpuSnapshot(),
  });
}

function parseSize(value, flagName) {
  const match = /^(\d+)x(\d+)$/i.exec(value || "");
  if (!match) {
    throw new Error(`${flagName} must look like 1600x900`);
  }
  return { width: Number(match[1]), height: Number(match[2]) };
}

function normalizeScrollMode(value) {
  const normalized = String(value || "").toLowerCase();
  if (!["constant", "static"].includes(normalized)) {
    throw new Error("--scroll must be one of: constant, static");
  }
  return normalized;
}

function normalizeCookieConsent(value) {
  const normalized = String(value || "").toLowerCase();
  if (!["off", "auto"].includes(normalized)) {
    throw new Error("--cookie-consent must be one of: off, auto");
  }
  return normalized;
}

function printHelp() {
  console.log(`Usage:
  node scripts/record_broll.mjs --url <url> --output <path> [options]

Options:
  --duration <seconds>            Total clip length. Default: 12
  --scroll constant|static        Steady scroll or static capture. Default: constant
  --viewport <width>x<height>     Browser viewport. Default: 1600x900
  --video-size <width>x<height>   Output frame size. Default: 1600x900
  --wait-for-selector <selector>  Wait for a selector before recording
  --cookie-consent off|auto       Try to dismiss cookie consent before recording. Default: off
  --click <selector>              Click selector before recording; repeatable
  --hide <selector>               Hide selector before recording; repeatable
  --settle-ms <milliseconds>      Delay before recording starts. Default: 1500
  --screenshot <path>             Save a validation screenshot before recording
`);
}

async function safeClick(page, selector) {
  try {
    await page.locator(selector).first().click({ timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}

async function safeLocatorClick(locator, timeoutMs = 1200) {
  try {
    await locator.first().click({ timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

async function autoCookieConsent(page) {
  const directSelectors = [
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "button[data-testid='uc-accept-all-button']",
    "button[aria-label='Accept all']",
    "button[aria-label='Accept cookies']",
    "button[mode='primary']:has-text('Accept')",
  ];

  for (const selector of directSelectors) {
    if (await safeLocatorClick(page.locator(selector))) {
      console.log(`Cookie consent handled with selector: ${selector}`);
      return true;
    }
  }

  const consentText = /^(accept|accept all|accept cookies|agree|i agree|allow all|ok|got it|continue|zaakceptuj|akceptuj|akceptuję|akceptuj wszystkie|zgadzam się|rozumiem|przejdź dalej)$/i;
  const roleQueries = [
    page.getByRole("button", { name: consentText }),
    page.getByRole("link", { name: consentText }),
  ];

  for (const locator of roleQueries) {
    if (await safeLocatorClick(locator)) {
      console.log("Cookie consent handled by visible text.");
      return true;
    }
  }

  return false;
}

async function hideSelectors(page, selectors) {
  if (!selectors.length) {
    return;
  }
  await page.evaluate((hiddenSelectors) => {
    for (const selector of hiddenSelectors) {
      for (const node of document.querySelectorAll(selector)) {
        node.style.setProperty("display", "none", "important");
        node.style.setProperty("visibility", "hidden", "important");
        node.style.setProperty("opacity", "0", "important");
      }
    }
  }, selectors);
}

async function constantScroll(page, durationSeconds) {
  await page.evaluate(async (durationMs) => {
    const doc = document.scrollingElement || document.documentElement;
    const maxScroll = Math.max(0, doc.scrollHeight - window.innerHeight);
    if (maxScroll <= 8) {
      await new Promise((resolve) => window.setTimeout(resolve, durationMs));
      return;
    }

    const start = performance.now();

    await new Promise((resolve) => {
      function step(now) {
        const elapsed = now - start;
        if (elapsed < durationMs) {
          const progress = Math.min(1, elapsed / durationMs);
          const target = maxScroll * progress;
          window.scrollTo({ top: target, behavior: "auto" });
          window.requestAnimationFrame(step);
          return;
        }

        window.scrollTo({ top: maxScroll, behavior: "auto" });
        resolve();
      }

      window.requestAnimationFrame(step);
    });
  }, durationSeconds * 1000);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const projectDir = await inferProjectDir(options);
  const gateRecord = await startStage(projectDir, "creative_gate", ["production_gate.py", "--project-dir", projectDir]);
  try {
    await runProductionGate(projectDir);
    await endStage(projectDir, gateRecord, "pass", 0);
  } catch (error) {
    await endStage(projectDir, gateRecord, "fail", 1, error instanceof Error ? error.message : String(error));
    throw error;
  }
  await fs.mkdir(path.dirname(options.output), { recursive: true });
  if (options.screenshot) {
    await fs.mkdir(path.dirname(options.screenshot), { recursive: true });
  }

  const videoDir = await fs.mkdtemp(path.join(os.tmpdir(), "pw-broll-"));
  const browser = await chromium.launch({
    headless: true,
    args: ["--autoplay-policy=no-user-gesture-required"],
  });

  let context;
  let page;
  let videoPath;
  let navigationResponse;
  let finalUrl = null;
  const recordStage = await startStage(projectDir, "webpage_record", ["record_broll.mjs", "--url", options.url, "--output", options.output], {
    duration_seconds: options.duration,
    scroll: options.scroll,
    viewport: options.viewport,
    video_size: options.videoSize,
    cookie_consent: options.cookieConsent,
  });

  try {
    context = await browser.newContext({
      viewport: options.viewport,
      recordVideo: {
        dir: videoDir,
        size: options.videoSize,
      },
    });
    page = await context.newPage();

    navigationResponse = await page.goto(options.url, { waitUntil: "domcontentloaded", timeout: 60000 });

    if (options.waitForSelector) {
      await page.locator(options.waitForSelector).first().waitFor({ state: "visible", timeout: 30000 });
    }

    await page.addStyleTag({
      content: `
        * { scrollbar-width: none !important; }
        *::-webkit-scrollbar { display: none !important; }
        html { scroll-behavior: auto !important; }
      `,
    });

    for (const selector of options.click) {
      await safeClick(page, selector);
      await page.waitForTimeout(300);
    }
    if (options.cookieConsent === "auto") {
      const handled = await autoCookieConsent(page);
      if (!handled) {
        console.log("Cookie consent auto: no matching banner control found.");
      }
      await page.waitForTimeout(300);
    }
    await hideSelectors(page, options.hide);
    await page.waitForTimeout(options.settleMs);
    if (options.screenshot) {
      await page.screenshot({ path: options.screenshot, fullPage: false });
      console.log(`Saved screenshot: ${options.screenshot}`);
    }
    finalUrl = page.url();
    console.log(`Final URL: ${finalUrl}`);
    console.log(`Page title: ${await page.title()}`);
    if (navigationResponse) {
      console.log(`HTTP status: ${navigationResponse.status()}`);
    }

    if (options.scroll === "constant") {
      await constantScroll(page, options.duration);
    } else {
      await page.waitForTimeout(options.duration * 1000);
    }

    const video = page.video();
    if (!video) {
      throw new Error("Playwright did not create a video handle.");
    }

    await page.close();
    videoPath = await video.path();
    await context.close();
    await browser.close();

    await fs.copyFile(videoPath, options.output);
    console.log(`Saved video: ${options.output}`);
    await endStage(projectDir, recordStage, "pass", 0, null, { output: options.output, final_url: finalUrl });
  } catch (error) {
    if (context) {
      await context.close().catch(() => {});
    }
    await browser.close().catch(() => {});
    await endStage(projectDir, recordStage, "error", 1, error instanceof Error ? error.message : String(error));
    throw error;
  } finally {
    await fs.rm(videoDir, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
