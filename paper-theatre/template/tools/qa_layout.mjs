#!/usr/bin/env node
// Layout check of the whole film, without rendering video: runs the film page in headless Chromium, records every text
// and image drawn on the stage canvas, and lists what a viewer would see as a mistake. Run it before a full render.
//
//   node tools/qa_layout.mjs                      the whole film, a sample every 0.25 s (about 2.5 minutes)
//   node tools/qa_layout.mjs --from 640 --to 660  a section
//
// Reported: text cut by the apron or the frame, text on text, an image drawn over text, a stage with nothing on it,
// a label too short to read. Boxes are bounding boxes, so an image's transparent corners also count: look at each hit
// on a still before changing anything. The full-screen moments of transitions show up here as well.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { findChrome, serveFilm } from './preview.mjs';

const ROOT = path.resolve(import.meta.dirname, '..');
const CHROME = findChrome();

const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf(`--${name}`); return i < 0 ? fallback : args[i + 1]; };
const STEP = parseFloat(opt('step', '0.25'));
const APRON_Y = 1004, RAIL_Y = 990;   // film/stage.js; anything lower is the timeline rail on the apron

const server = await serveFilm();

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-layout-'));
const proc = spawn(CHROME, ['--headless', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
  '--hide-scrollbars', '--mute-audio', '--window-size=1920,1080', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const url = await new Promise((ok, fail) => {
  let err = '';
  const timer = setTimeout(() => fail(new Error(`Chromium did not start:\n${err}`)), 20000);
  proc.stderr.on('data', (d) => {
    err += d;
    const m = err.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(timer); ok(m[1]); }
  });
  proc.once('error', (error) => { clearTimeout(timer); fail(error); });
  proc.once('exit', (code) => { clearTimeout(timer); fail(new Error(`Chromium exited (${code}):\n${err}`)); });
});
const ws = new WebSocket(url);
await new Promise((ok) => ws.addEventListener('open', ok));
let id = 0;
const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const { ok, fail } = pending.get(m.id); pending.delete(m.id); if (m.error) fail(new Error(m.error.message)); else ok(m.result); }
});
const send = (method, params = {}, sessionId) => { const i = ++id; ws.send(JSON.stringify({ id: i, method, params, sessionId })); return new Promise((ok, fail) => pending.set(i, { ok, fail })); };
const { targetId } = await send('Target.createTarget', { url: `http://127.0.0.1:${server.address().port}/index.html` });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
await send('Runtime.enable', {}, sessionId);
const run = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};
for (let i = 0; i < 300 && !(await run('window.__ready === true')); i++) await new Promise((r) => setTimeout(r, 100));

// Record what reaches the stage canvas, with its box in stage coordinates.
await run(`(() => {
  const C = document.getElementById('c'), P = CanvasRenderingContext2D.prototype;
  window.__rec = [];
  const box = (m, x0, y0, x1, y1) => {
    const pts = [[x0, y0], [x1, y0], [x0, y1], [x1, y1]].map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
    return [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))].map(Math.round);
  };
  const fillText = P.fillText;
  P.fillText = function (t, x, y, ...r) {
    if (this.canvas === C) {
      const m = this.getTransform(), a = this.measureText(t);
      __rec.push({ text: String(t), b: box(m, x - a.actualBoundingBoxLeft, y - a.actualBoundingBoxAscent, x + a.actualBoundingBoxRight, y + a.actualBoundingBoxDescent), s: Math.hypot(m.a, m.b) });
    }
    return fillText.call(this, t, x, y, ...r);
  };
  const drawImage = P.drawImage;
  P.drawImage = function (im, ...a) {
    if (this.canvas === C) {
      const d = a.length === 2 ? [a[0], a[1], im.width, im.height] : a.length === 4 ? a : a.slice(4);
      __rec.push({ img: im.src ? decodeURIComponent(im.src.split('/').pop()) : 'canvas', b: box(this.getTransform(), d[0], d[1], d[0] + d[2], d[1] + d[3]) });
    }
    return drawImage.call(this, im, ...a);
  };
})()`);

const info = await run('window.__info');
const clock = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, '0')}`;
const hits = new Map();
const hit = (key, t, detail = '') => { if (!hits.has(key)) hits.set(key, { t0: t, n: 0, detail }); const h = hits.get(key); h.n++; h.t1 = t; };
const overlap = (a, b, pad = 0) => { const w = Math.min(a[2], b[2]) - Math.max(a[0], b[0]) + pad, h = Math.min(a[3], b[3]) - Math.max(a[1], b[1]) + pad; return w > 8 && h > 8; };
const shown = new Map();
const empty = [];
const FULL = 0.5 * 1920 * 1080;

for (let t = parseFloat(opt('from', '0')), end = Math.min(info.duration, parseFloat(opt('to', '1e9'))); t < end; t += STEP) {
  const rec = await run(`(window.__rec.length = 0, window.__draw(${t}), window.__rec.slice())`);
  const texts = rec.map((r, i) => ({ ...r, i })).filter((r) => r.text && r.s >= 0.9 && r.b[1] < RAIL_Y && r.b[3] > r.b[1] + 4);
  const usable = (r) => r.img && !r.b.includes(null) && (r.b[2] - r.b[0]) * (r.b[3] - r.b[1]) < FULL;
  if (!rec.some((r) => (r.text && r.b[1] < RAIL_Y) || (usable(r) && r.img !== 'canvas'))) empty.push(t);
  for (const r of texts) {
    if (!shown.has(r.text)) shown.set(r.text, []);
    shown.get(r.text).push(t);
  }
  if (rec.some((r) => r.text?.startsWith('rozdział'))) continue;   // a chapter card covers the stage
  for (const r of texts) {
    if (r.b[3] > APRON_Y - 8) hit(`pod krawędzią sceny: ${r.text}`, t);
    if (r.b[0] < 6 || r.b[2] > 1914 || r.b[1] < 4) hit(`poza kadrem: ${r.text}`, t);
    for (const q of texts) if (q.i > r.i && overlap(r.b, q.b, 14)) hit(`napis na napisie: ${r.text} / ${q.text}`, t);
    for (let j = r.i + 1; j < rec.length; j++) if (usable(rec[j]) && overlap(r.b, rec[j].b)) hit(`obraz na napisie: ${r.text} / ${rec[j].img}`, t);
  }
}

const span = (ts) => { const runs = []; for (const t of ts) { const last = runs[runs.length - 1]; if (last && t - last[1] <= STEP * 2.5) last[1] = t; else runs.push([t, t]); } return runs; };
console.log('Układ:');
[...hits.entries()].filter(([, h]) => h.n * STEP >= 0.5).sort((a, b) => a[1].t0 - b[1].t0).forEach(([k, h]) => console.log(`  ${clock(h.t0)}–${clock(h.t1)}  ${k}`));
console.log('Pusta scena (co najmniej 0,75 s):');
span(empty).filter(([a, b]) => b - a >= 0.75).forEach(([a, b]) => console.log(`  ${clock(a)}–${clock(b)}`));
console.log('Za krótko, żeby przeczytać (długość napisu / 14 + 0,4 s):');
[...shown.entries()].flatMap(([text, ts]) => span(ts).map(([a, b]) => ({ text, a, d: b - a + STEP }))).filter(({ text, d }) => d < text.length / 14 + 0.4).sort((x, y) => x.a - y.a)
  .forEach(({ text, a, d }) => console.log(`  ${clock(a)}  ${d.toFixed(2)} s  ${text}`));

server.close(); proc.kill(); ws.close();
fs.rmSync(profile, { recursive: true, force: true });
process.exit(0);
