#!/usr/bin/env node
// Frame renderer with no dependencies: serves film/, drives headless Chromium over the
// DevTools protocol (Node's built-in WebSocket), and pipes canvas frames into ffmpeg.
//
//   node tools/render.mjs                         full reel → out/reel.mp4
//   node tools/render.mjs --stills 1.5,7,12.2     PNG stills → out/stills/
//   node tools/render.mjs --from 10 --to 14       a section, for quick checks
//   node tools/render.mjs --page thumb.html --stills 0 --stills-dir out/thumb --prefix thumb
//                                                 another page of film/ (the thumbnail) as a still
//   node tools/render.mjs --encoder vaapi         H.264 on the Intel GPU (Quick Sync via VAAPI): frees the CPU
//                                                 for the Chromium workers; --qp sets its quality (lower = better)
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { findChrome, serveFilm } from './preview.mjs';

const ROOT = path.resolve(import.meta.dirname, '..');
const CHROME = findChrome();

const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf(`--${name}`); return i < 0 ? fallback : args[i + 1]; };
const flag = (name) => args.includes(`--${name}`);
const OUT = path.resolve(ROOT, opt('out', 'out/film.mp4'));
const WORKERS = parseInt(opt('workers', '3'), 10);
const AUDIO = path.resolve(ROOT, opt('audio', 'film/audio/mix.wav'));
const CRF = opt('crf', '19');
const ENCODER = opt('encoder', 'x264');
const QP = opt('qp', '18');
const VAAPI_DEVICE = opt('vaapi-device', '/dev/dri/renderD128');
const PAGE = opt('page', 'index.html');   // another page of film/ with the same render API, e.g. thumb.html

function launchChrome(profile) {
  const proc = spawn(CHROME, [
    '--headless', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
    '--hide-scrollbars', '--mute-audio', '--window-size=1920,1080', 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  return new Promise((ok, fail) => {
    let err = '';
    const timer = setTimeout(() => fail(new Error(`Chromium did not start:\n${err}`)), 20000);
    proc.stderr.on('data', (d) => {
      err += d;
      const m = err.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(timer); ok({ proc, url: m[1] }); }
    });
    proc.once('error', (error) => { clearTimeout(timer); fail(error); });
    proc.on('exit', (code) => { clearTimeout(timer); fail(new Error(`Chromium exited (${code}):\n${err}`)); });
  });
}

class CDP {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.onEvent = () => {};
    ws.addEventListener('message', (e) => {
      const m = JSON.parse(e.data);
      if (m.id && this.pending.has(m.id)) {
        const { ok, fail } = this.pending.get(m.id);
        this.pending.delete(m.id);
        if (m.error) fail(new Error(m.error.message)); else ok(m.result);
      } else if (m.method) this.onEvent(m);
    });
  }
  static connect(url) {
    return new Promise((ok, fail) => {
      const ws = new WebSocket(url);
      ws.addEventListener('open', () => ok(new CDP(ws)));
      ws.addEventListener('error', () => fail(new Error('DevTools socket failed')));
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((ok, fail) => this.pending.set(id, { ok, fail }));
  }
}

async function openPage(cdp, url) {
  const { targetId } = await cdp.send('Target.createTarget', { url });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  await cdp.send('Runtime.enable', {}, sessionId);
  const run = async (expression) => {
    const r = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  for (let i = 0; i < 300; i++) {
    if (await run('window.__ready === true')) return run;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('page never became ready');
}

const dataOf = (url) => Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');

async function main() {
  const server = await serveFilm();
  const base = `http://127.0.0.1:${server.address().port}/${PAGE}`;
  fs.mkdirSync(path.join(ROOT, 'out'), { recursive: true });
  const profile = fs.mkdtempSync(path.join(ROOT, 'out', '.chrome-'));
  const { proc, url } = await launchChrome(profile);
  const cdp = await CDP.connect(url);
  cdp.onEvent = (m) => {
    if (m.method === 'Runtime.exceptionThrown') console.error('page error:', m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') console.error('console:', m.params.args.map((a) => a.value ?? a.description).join(' '));
  };
  const cleanup = async () => {
    server.close();
    const gone = new Promise((r) => proc.once('exit', r));
    proc.removeAllListeners('exit');
    try { proc.kill(); } catch {}
    await Promise.race([gone, new Promise((r) => setTimeout(r, 3000))]);
    try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
  };

  try {
    if (opt('stills')) {
      const run = await openPage(cdp, base);
      const dir = path.join(ROOT, opt('stills-dir', 'out/stills'));
      fs.mkdirSync(dir, { recursive: true });
      for (const s of opt('stills').split(',')) {
        const t = parseFloat(s);
        const png = await run(`(window.__draw(${t}), document.getElementById('c').toDataURL('image/png'))`);
        const file = path.join(dir, `${opt('prefix', 't')}_${t.toFixed(2).padStart(6, '0')}.png`);
        fs.writeFileSync(file, dataOf(png));
        console.log(file);
      }
      return;
    }

    const pages = await Promise.all(Array.from({ length: WORKERS }, () => openPage(cdp, base)));
    const info = await pages[0]('window.__info');
    const first = Math.round(parseFloat(opt('from', '0')) * info.fps);
    const last = Math.min(info.frames, Math.round(parseFloat(opt('to', String(info.duration))) * info.fps));
    const withAudio = !flag('no-audio') && fs.existsSync(AUDIO);
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    const colour = 'scale=in_range=full:in_color_matrix=bt601:out_color_matrix=bt709:out_range=tv';
    const video = ENCODER === 'vaapi'
      // the GPU encoder takes nv12 surfaces; constant QP, the quality knob of the low-power encoder
      ? ['-vf', `${colour},format=nv12,hwupload`, '-c:v', 'h264_vaapi', '-profile:v', 'high', '-rc_mode', 'CQP', '-qp', QP]
      : ['-vf', `${colour},format=yuv420p`, '-c:v', 'libx264', '-preset', 'medium', '-crf', CRF, '-maxrate', '12M', '-bufsize', '24M'];
    const ff = spawn('ffmpeg', [
      '-y', '-loglevel', 'error', ...(ENCODER === 'vaapi' ? ['-vaapi_device', VAAPI_DEVICE] : []),
      '-f', 'image2pipe', '-framerate', String(info.fps), '-c:v', 'mjpeg', '-i', '-',
      ...(withAudio ? ['-ss', String(first / info.fps), '-i', AUDIO] : []),
      ...video, '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
      ...(withAudio ? ['-c:a', 'aac', '-b:a', '256k', '-shortest'] : []),
      '-movflags', '+faststart', OUT,
    ], { stdio: ['pipe', 'inherit', 'inherit'] });
    const ffDone = new Promise((ok, fail) => ff.on('exit', (c) => (c === 0 ? ok() : fail(new Error(`ffmpeg exited ${c}`)))));

    const ready = new Map();
    let next = first, toWrite = first;
    const started = Date.now();
    const flush = async () => {
      while (ready.has(toWrite)) {
        const buf = ready.get(toWrite);
        ready.delete(toWrite);
        if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
        toWrite++;
        if ((toWrite - first) % 60 === 0 || toWrite === last) {
          const fps = (toWrite - first) / ((Date.now() - started) / 1000);
          process.stdout.write(`\rframe ${toWrite - first}/${last - first}  ${fps.toFixed(1)} fps   `);
        }
      }
    };
    let flushing = Promise.resolve();
    await Promise.all(pages.map(async (run) => {
      while (next < last) {
        const i = next++;
        while (i - toWrite > 90) await new Promise((r) => setTimeout(r, 20));
        ready.set(i, dataOf(await run(`window.__frame(${i}, 'image/jpeg', 0.94)`)));
        flushing = flushing.then(flush);
        await flushing;
      }
    }));
    await flushing;
    ff.stdin.end();
    await ffDone;
    console.log(`\nwrote ${path.relative(ROOT, OUT)}${withAudio ? ' (with audio)' : ' (silent)'} in ${((Date.now() - started) / 1000).toFixed(0)}s`);
  } finally {
    await cleanup();
  }
}

main().catch((e) => { console.error(e.message); process.exit(1); });
