#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const BOARD_TYPES = new Set([
  "hero-metric",
  "comparison-split",
  "checklist",
  "process-flow",
  "timeline",
  "logistics-map",
  "bar-comparison",
  "risk-matrix",
  "myth-fact",
]);

const PRESETS = new Set([
  "premium-saas",
  "construction-tech",
  "real-estate-premium",
  "bold-reel",
  "minimal-editorial",
]);

const FORMATS = {
  vertical: { width: 1080, height: 1920 },
  landscape: { width: 1920, height: 1080 },
};

const PRESET_VARS = {
  "premium-saas": {
    bg: "#071016",
    panel: "rgba(12, 24, 34, 0.78)",
    panel2: "rgba(22, 38, 50, 0.72)",
    text: "#f7fbff",
    muted: "#9fb3c8",
    accent: "#38bdf8",
    accent2: "#a3e635",
    accent3: "#facc15",
  },
  "construction-tech": {
    bg: "#071012",
    panel: "rgba(18, 30, 33, 0.8)",
    panel2: "rgba(25, 39, 42, 0.72)",
    text: "#f4f7f3",
    muted: "#a4b8b0",
    accent: "#4ade80",
    accent2: "#3b82f6",
    accent3: "#f59e0b",
  },
  "real-estate-premium": {
    bg: "#101210",
    panel: "rgba(28, 31, 27, 0.8)",
    panel2: "rgba(44, 45, 38, 0.72)",
    text: "#fffaf0",
    muted: "#c6c0ae",
    accent: "#d6b46a",
    accent2: "#7dd3a8",
    accent3: "#e5e7eb",
  },
  "bold-reel": {
    bg: "#09090b",
    panel: "rgba(24, 24, 27, 0.82)",
    panel2: "rgba(39, 39, 42, 0.78)",
    text: "#ffffff",
    muted: "#d4d4d8",
    accent: "#fb7185",
    accent2: "#22d3ee",
    accent3: "#facc15",
  },
  "minimal-editorial": {
    bg: "#f7f5ef",
    panel: "rgba(255, 255, 255, 0.78)",
    panel2: "rgba(232, 228, 217, 0.72)",
    text: "#18181b",
    muted: "#62605a",
    accent: "#111827",
    accent2: "#0f766e",
    accent3: "#b45309",
  },
};

function parseArgs(argv) {
  const options = {
    type: "process-flow",
    preset: "premium-saas",
    format: "vertical",
    duration: 6,
    title: "Animated board",
    subtitle: "",
    kicker: "B-ROLL BOARD",
    items: [],
    values: [],
    dataJson: null,
  };

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
      case "--type":
        options.type = next;
        i += 1;
        break;
      case "--preset":
        options.preset = next;
        i += 1;
        break;
      case "--format":
        options.format = next;
        i += 1;
        break;
      case "--duration":
        options.duration = Number(next);
        i += 1;
        break;
      case "--title":
        options.title = next;
        i += 1;
        break;
      case "--subtitle":
        options.subtitle = next;
        i += 1;
        break;
      case "--kicker":
        options.kicker = next;
        i += 1;
        break;
      case "--items":
        options.items = splitList(next);
        i += 1;
        break;
      case "--values":
        options.values = splitList(next).map((value) => Number(value));
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
  if (!BOARD_TYPES.has(options.type)) throw new Error(`Unsupported --type: ${options.type}`);
  if (!PRESETS.has(options.preset)) throw new Error(`Unsupported --preset: ${options.preset}`);
  if (!FORMATS[options.format]) throw new Error(`Unsupported --format: ${options.format}`);
  if (!Number.isFinite(options.duration) || options.duration <= 0) throw new Error("--duration must be positive");

  return options;
}

function splitList(value) {
  return String(value || "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

function printHelp() {
  console.log(`Usage:
  node scripts/create_board.mjs --project-dir <dir> --board-id <id> [options]

Options:
  --type <type>                 ${[...BOARD_TYPES].join(", ")}
  --preset <preset>             ${[...PRESETS].join(", ")}
  --format vertical|landscape
  --duration <seconds>
  --title <text>
  --subtitle <text>
  --kicker <text>
  --items "One|Two|Three"
  --values "80|55|30"
  --data-json <path>            Optional JSON payload overriding text fields
`);
}

async function loadData(options) {
  if (!options.dataJson) return options;
  const payload = JSON.parse(await fs.readFile(path.resolve(options.dataJson), "utf8"));
  return { ...options, ...payload };
}

function safeId(value) {
  const cleaned = String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
  if (!cleaned) throw new Error("--board-id must contain a usable filename");
  return cleaned;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function defaultItems(type) {
  const defaults = {
    "hero-metric": ["2x szybciej", "mniej chaosu", "więcej kontroli"],
    "comparison-split": ["Tradycyjnie", "Prefabrykacja"],
    checklist: ["proces powtarzalny", "materiały pod dachem", "kontrola przed transportem"],
    "process-flow": ["Projekt", "Produkcja", "Transport", "Montaż"],
    timeline: ["Decyzje", "Produkcja", "Dostawa", "Montaż"],
    "logistics-map": ["Projekt", "Transport", "Dźwig", "Działka"],
    "bar-comparison": ["Czas", "Odpady", "Ryzyko"],
    "risk-matrix": ["Niski koszt", "Wysoka kontrola", "Szybki start", "Mniej poprawek"],
    "myth-fact": ["Mit", "Fakt"],
  };
  return defaults[type] || defaults["process-flow"];
}

function sceneMarkup(type, items, values) {
  switch (type) {
    case "hero-metric":
      return heroMetric(items);
    case "comparison-split":
      return comparisonSplit(items);
    case "checklist":
      return checklist(items);
    case "timeline":
      return timeline(items);
    case "logistics-map":
      return logisticsMap(items);
    case "bar-comparison":
      return barComparison(items, values);
    case "risk-matrix":
      return riskMatrix(items);
    case "myth-fact":
      return mythFact(items);
    case "process-flow":
    default:
      return processFlow(items);
  }
}

function processFlow(items) {
  return `<section class="flow">${items
    .map(
      (item, index) => `<div class="flow-step" style="--i:${index}">
        <span class="node">${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(item)}</strong>
      </div>`,
    )
    .join("")}<div class="flow-line"></div></section>`;
}

function checklist(items) {
  return `<section class="checklist">${items
    .map(
      (item, index) => `<div class="check-item" style="--i:${index}">
        <span class="checkmark">✓</span>
        <strong>${escapeHtml(item)}</strong>
      </div>`,
    )
    .join("")}</section>`;
}

function comparisonSplit(items) {
  const left = items[0] || "Opcja A";
  const right = items[1] || "Opcja B";
  return `<section class="split">
    <div class="split-card muted-card"><span>01</span><strong>${escapeHtml(left)}</strong><small>wolniej, więcej zmiennych</small></div>
    <div class="split-card accent-card"><span>02</span><strong>${escapeHtml(right)}</strong><small>równolegle, pod kontrolą</small></div>
  </section>`;
}

function heroMetric(items) {
  return `<section class="metric">
    <div class="metric-number">${escapeHtml(items[0] || "2x")}</div>
    <div class="metric-row">${(items.slice(1, 4).length ? items.slice(1, 4) : ["szybciej", "czyściej", "pewniej"])
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("")}</div>
  </section>`;
}

function timeline(items) {
  return `<section class="timeline">${items
    .map(
      (item, index) => `<div class="time-item" style="--i:${index}">
        <span>${String(index + 1).padStart(2, "0")}</span><strong>${escapeHtml(item)}</strong>
      </div>`,
    )
    .join("")}</section>`;
}

function logisticsMap(items) {
  return `<section class="map-board">
    <svg viewBox="0 0 780 780" aria-hidden="true">
      <path class="route" d="M110 600 C240 510 185 360 345 330 C500 300 480 170 655 130" />
      ${items
        .slice(0, 4)
        .map((item, index) => {
          const points = [
            [110, 600],
            [300, 352],
            [500, 250],
            [655, 130],
          ];
          const [x, y] = points[index];
          return `<g class="map-node" style="--i:${index}" transform="translate(${x} ${y})"><circle r="23" /><text y="-42">${escapeHtml(item)}</text></g>`;
        })
        .join("")}
    </svg>
  </section>`;
}

function barComparison(items, values) {
  const nums = values.length ? values : [88, 64, 42, 28];
  return `<section class="bars">${items
    .slice(0, 4)
    .map((item, index) => {
      const width = Math.max(12, Math.min(100, nums[index] ?? 50));
      return `<div class="bar-row" style="--i:${index};--w:${width}%"><span>${escapeHtml(item)}</span><div class="bar"><i></i></div></div>`;
    })
    .join("")}</section>`;
}

function riskMatrix(items) {
  const labels = items.length >= 4 ? items.slice(0, 4) : defaultItems("risk-matrix");
  return `<section class="matrix">${labels
    .map((item, index) => `<div class="matrix-cell" style="--i:${index}"><strong>${escapeHtml(item)}</strong></div>`)
    .join("")}</section>`;
}

function mythFact(items) {
  return `<section class="myth">
    <div class="myth-card wrong"><span>${escapeHtml(items[0] || "Mit")}</span><strong>Prefab to kompromis</strong></div>
    <div class="myth-card right"><span>${escapeHtml(items[1] || "Fakt")}</span><strong>Prefab to kontrola procesu</strong></div>
  </section>`;
}

function htmlDocument(data, dimensions) {
  const vars = PRESET_VARS[data.preset];
  const items = data.items?.length ? data.items : defaultItems(data.type);
  const values = data.values?.filter(Number.isFinite) || [];
  const markup = sceneMarkup(data.type, items, values);
  const cssVars = Object.entries(vars)
    .map(([key, value]) => `--${key}:${value};`)
    .join("");

  return `<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=${dimensions.width}, initial-scale=1" />
<title>${escapeHtml(data.title)}</title>
<style>
:root{${cssVars}--duration:${data.duration}s;--w:${dimensions.width}px;--h:${dimensions.height}px}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:var(--text)}
body{display:grid;place-items:center}
.stage{position:relative;width:var(--w);height:var(--h);overflow:hidden;background:
  radial-gradient(circle at 76% 12%, color-mix(in srgb,var(--accent) 22%,transparent), transparent 26%),
  linear-gradient(180deg, color-mix(in srgb,var(--panel2) 25%,transparent), transparent 42%),
  var(--bg);isolation:isolate}
.stage:before{content:"";position:absolute;inset:0;background-image:linear-gradient(color-mix(in srgb,var(--muted) 13%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--muted) 13%,transparent) 1px,transparent 1px);background-size:54px 54px;mask-image:linear-gradient(to bottom,transparent,black 14%,black 72%,transparent);opacity:.42}
.stage:after{content:"";position:absolute;inset:38px;border:1px solid color-mix(in srgb,var(--muted) 22%,transparent);border-radius:34px;opacity:.75;pointer-events:none}
.safe{position:absolute;inset:108px 76px 190px;display:grid;grid-template-rows:auto 1fr;gap:58px;z-index:1}
.kicker{font-weight:800;font-size:25px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);opacity:.9;transform:translateY(18px);animation:rise .7s .1s cubic-bezier(.2,.8,.2,1) forwards}
h1{margin:18px 0 0;padding-bottom:12px;font-size:84px;line-height:1.04;letter-spacing:0;text-wrap:balance;max-width:900px;opacity:.9;transform:translateY(18px);animation:rise .8s .22s cubic-bezier(.2,.8,.2,1) forwards}
.subtitle{margin:26px 0 0;color:var(--muted);font-size:32px;line-height:1.25;max-width:810px;opacity:.9;transform:translateY(18px);animation:rise .8s .34s cubic-bezier(.2,.8,.2,1) forwards}
.content{position:relative;min-height:0}
.flow,.checklist,.bars,.timeline,.split,.metric,.map-board,.matrix,.myth{height:100%;display:grid;align-content:center;gap:24px}
.flow{position:relative;gap:22px}
.flow-line{position:absolute;left:47px;top:108px;bottom:108px;width:3px;background:linear-gradient(var(--accent),var(--accent2));transform-origin:top;transform:scaleY(0);animation:lineDraw 1.5s .7s cubic-bezier(.2,.8,.2,1) forwards}
.flow-step,.check-item,.bar-row,.time-item{position:relative;display:flex;align-items:center;gap:24px;padding:30px 34px;border:1px solid color-mix(in srgb,var(--accent) 32%,transparent);background:var(--panel);border-radius:24px;box-shadow:0 24px 80px rgba(0,0,0,.24);opacity:.78;transform:translateY(18px);animation:rise .72s calc(.52s + var(--i)*.18s) cubic-bezier(.2,.8,.2,1) forwards}
.node,.checkmark,.time-item span{display:grid;place-items:center;flex:0 0 58px;width:58px;height:58px;border-radius:18px;background:color-mix(in srgb,var(--accent) 18%,transparent);color:var(--accent);font-weight:900;font-size:24px}
.flow-step strong,.check-item strong,.bar-row span,.time-item strong{font-size:38px;line-height:1.08}
.checkmark{border-radius:999px;background:var(--accent);color:var(--bg)}
.split{grid-template-columns:1fr 1fr;gap:26px}
.split-card,.myth-card{min-height:520px;border-radius:32px;padding:42px;background:var(--panel);border:1px solid color-mix(in srgb,var(--muted) 24%,transparent);display:flex;flex-direction:column;justify-content:space-between;opacity:.78;transform:translateY(18px);animation:rise .85s .62s cubic-bezier(.2,.8,.2,1) forwards}
.split-card:nth-child(2),.myth-card:nth-child(2){animation-delay:.84s}
.split-card span,.myth-card span{color:var(--accent);font-weight:900;font-size:28px;text-transform:uppercase}
.split-card strong,.myth-card strong{font-size:54px;line-height:1}
.split-card small{font-size:27px;color:var(--muted);line-height:1.25}
.accent-card{border-color:color-mix(in srgb,var(--accent) 58%,transparent);background:linear-gradient(180deg,color-mix(in srgb,var(--accent) 17%,transparent),var(--panel))}
.metric{align-content:center;gap:42px}
.metric-number{font-weight:950;font-size:178px;line-height:.9;color:var(--accent);text-shadow:0 0 60px color-mix(in srgb,var(--accent) 30%,transparent);opacity:.9;transform:scale(.96);animation:pop .9s .55s cubic-bezier(.2,.9,.2,1) forwards}
.metric-row{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.metric-row span{padding:24px 18px;border-radius:22px;background:var(--panel);border:1px solid color-mix(in srgb,var(--accent) 34%,transparent);font-weight:800;font-size:27px;text-align:center;opacity:.78;transform:translateY(18px);animation:rise .62s calc(.9s + var(--i,0)*.12s) forwards}
.timeline{gap:18px}
.time-item{min-height:116px}
.map-board svg{width:100%;height:auto;overflow:visible}
.route{fill:none;stroke:var(--accent);stroke-width:11;stroke-linecap:round;stroke-dasharray:980;stroke-dashoffset:980;animation:dash 2.4s .7s cubic-bezier(.2,.8,.2,1) forwards}
.map-node{opacity:.78;transform:scale(.96);animation:pop .55s calc(1s + var(--i)*.26s) cubic-bezier(.2,.8,.2,1) forwards}
.map-node circle{fill:var(--bg);stroke:var(--accent2);stroke-width:8}.map-node text{fill:var(--text);font-size:34px;font-weight:900;text-anchor:middle}
.bars{gap:30px}
.bar-row{display:grid;grid-template-columns:220px 1fr;gap:26px}
.bar{height:24px;border-radius:999px;background:color-mix(in srgb,var(--muted) 20%,transparent);overflow:hidden}
.bar i{display:block;width:var(--w);height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:inherit;transform-origin:left;transform:scaleX(0);animation:fill 1.2s calc(.9s + var(--i)*.18s) cubic-bezier(.2,.8,.2,1) forwards}
.matrix{grid-template-columns:1fr 1fr;gap:22px}
.matrix-cell{min-height:235px;border-radius:28px;padding:34px;background:var(--panel);border:1px solid color-mix(in srgb,var(--accent) 32%,transparent);display:grid;place-items:end start;opacity:.78;transform:translateY(18px);animation:rise .65s calc(.6s + var(--i)*.14s) forwards}
.matrix-cell strong{font-size:38px;line-height:1.05}
.myth{grid-template-columns:1fr;gap:24px}
.myth-card{min-height:240px}.wrong{border-color:color-mix(in srgb,#fb7185 55%,transparent)}.right{border-color:color-mix(in srgb,var(--accent2) 60%,transparent)}
@keyframes rise{to{opacity:1;transform:translateY(0)}}@keyframes pop{to{opacity:1;transform:scale(1)}}@keyframes lineDraw{to{transform:scaleY(1)}}@keyframes dash{to{stroke-dashoffset:0}}@keyframes fill{to{transform:scaleX(1)}}
@media (max-width:1200px){.safe{inset:108px 76px 190px}h1{font-size:82px}.subtitle{font-size:32px}}
</style>
</head>
<body>
<main class="stage" data-board-type="${escapeHtml(data.type)}" data-preset="${escapeHtml(data.preset)}" data-duration="${escapeHtml(data.duration)}">
  <div class="safe">
    <header>
      <div class="kicker">${escapeHtml(data.kicker)}</div>
      <h1>${escapeHtml(data.title)}</h1>
      ${data.subtitle ? `<p class="subtitle">${escapeHtml(data.subtitle)}</p>` : ""}
    </header>
    <div class="content">${markup}</div>
  </div>
</main>
<script>
document.documentElement.style.setProperty("--started-at", String(performance.now()));
</script>
</body>
</html>`;
}

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  const data = await loadData(parsed);
  data.boardId = safeId(data.boardId);
  data.items = data.items?.length ? data.items : defaultItems(data.type);
  const dimensions = FORMATS[data.format];
  const boardDir = path.join(path.resolve(data.projectDir), "broll", "boards", data.boardId);
  await fs.mkdir(boardDir, { recursive: true });

  const indexPath = path.join(boardDir, "index.html");
  const manifestPath = path.join(boardDir, "board-manifest.json");
  const clipPath = path.join(boardDir, `${data.boardId}.webm`);
  const previewPath = path.join(boardDir, "preview.png");
  const manifest = {
    board_id: data.boardId,
    type: data.type,
    preset: data.preset,
    format: data.format,
    width: dimensions.width,
    height: dimensions.height,
    duration: data.duration,
    title: data.title,
    subtitle: data.subtitle,
    kicker: data.kicker,
    items: data.items,
    values: data.values || [],
    html: indexPath,
    preview: previewPath,
    clip: clipPath,
    source_type: "animated-board",
    risk: "synthetic explanatory motion graphic",
  };

  await fs.writeFile(indexPath, htmlDocument(data, dimensions), "utf8");
  await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
  console.log(JSON.stringify({ html: indexPath, manifest: manifestPath, clip: clipPath, preview: previewPath }, null, 2));
}

main().catch((error) => {
  console.error(`ERROR: ${error.message}`);
  process.exit(1);
});
