#!/usr/bin/env node
// Frame renderer with no dependencies: serves film/, drives headless Chromium over the DevTools protocol
// (Node's built-in WebSocket) and writes the film as H.264 chunks of --chunk seconds. Every chunk starts with
// its own parameter sets and a key frame, so ffmpeg only joins the chunks with the sound, and a fix draws
// again only the chunks it touches. A chunk is encoded by one of:
//   webcodecs  the page itself (WebCodecs, software H.264) — no frame leaves the browser as an image; the default
//   x264       ffmpeg on the CPU, fed JPEG frames — when the browser has no H.264 encoder, or on request
//   vaapi      ffmpeg on a VAAPI GPU (--vaapi-device, --qp), fed JPEG frames
// --gpu off draws without the GPU (--disable-gpu) where the GPU in a headless browser misbehaves.
//
//   node tools/render.mjs --out out/<slug>_v1.mp4             the whole film
//   node tools/render.mjs --from 10 --to 14 --out out/s.mp4   a section, for quick checks
//   node tools/render.mjs --patch out/<slug>_v1.mp4 --from 83 --to 86 --out out/<slug>_v2.mp4
//                                       the chunks touching 83–86 s drawn again, the others copied from v1,
//                                       the current mix as sound; the old file must come from this renderer
//   node tools/render.mjs --stills 1.5,7,12.2                 PNG stills → out/stills/
//   node tools/render.mjs --page thumb.html --stills 0 --stills-dir out/thumb --prefix thumb
//                                       another page of film/ (the thumbnail) as a still
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
const WORKERS = parseInt(opt('workers', '4'), 10);
const AUDIO = path.resolve(ROOT, opt('audio', 'film/audio/mix.wav'));
let ENCODER = opt('encoder', 'webcodecs');
const BITRATE = parseFloat(opt('bitrate', '12')) * 1e6;   // webcodecs: variable bitrate (the software encoder has no constant-quality mode)
const CRF = opt('crf', '19');                              // x264
const QP = opt('qp', '18');                                // vaapi
const VAAPI_DEVICE = opt('vaapi-device', '/dev/dri/renderD128');
const GPU = opt('gpu', 'on') !== 'off';
const CHUNK = parseFloat(opt('chunk', '2'));               // seconds per independently encoded chunk
const PATCH = opt('patch') ? path.resolve(ROOT, opt('patch')) : null;
const PAGE = opt('page', 'index.html');   // another page of film/ with the same render API, e.g. thumb.html

function launchChrome(profile) {
  const gpu = GPU ? ['--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'] : ['--disable-gpu'];
  const proc = spawn(CHROME, [
    '--headless', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', ...gpu,
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

// Draws frames a..b-1 and returns them as one H.264 Annex B chunk (base64): parameter sets, a key frame, the rest.
const ENCODE_CHUNK = `window.__chunk = async (a, b, bitrate) => {
  const c = document.getElementById('c'), fps = window.__info.fps, parts = [];
  let failure = null;
  const enc = new VideoEncoder({ output: (ch) => { const x = new Uint8Array(ch.byteLength); ch.copyTo(x); parts.push(x); },
                                 error: (e) => { failure = e; } });
  enc.configure({ codec: 'avc1.640028', width: c.width, height: c.height, framerate: fps, bitrateMode: 'variable', bitrate,
                  avc: { format: 'annexb' } });
  for (let i = a; i < b; i++) {
    window.__draw(i / fps);
    const f = new VideoFrame(c, { timestamp: Math.round(i * 1e6 / fps), duration: Math.round(1e6 / fps) });
    enc.encode(f, { keyFrame: i === a });
    f.close();
    while (enc.encodeQueueSize > 4) await new Promise((r) => setTimeout(r, 0));
  }
  await enc.flush(); enc.close();
  if (failure) throw failure;
  const all = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
  let o = 0; for (const p of parts) { all.set(p, o); o += p.length; }
  let s = ''; for (let i = 0; i < all.length; i += 0x8000) s += String.fromCharCode.apply(null, all.subarray(i, i + 0x8000));
  return btoa(s);
};
VideoEncoder.isConfigSupported({ codec: 'avc1.640028', width: 1920, height: 1080, bitrateMode: 'variable', bitrate: 1e7 })
  .then((r) => r.supported)`;

async function openPage(cdp, url) {
  const { targetId } = await cdp.send('Target.createTarget', { url });
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  await cdp.send('Runtime.enable', {}, sessionId);
  const run = async (expression) => {
    const r = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  // several pages loading every cut-out at once can take well over half a minute
  for (let i = 0; i < 1800; i++) {
    if (await run('window.__ready === true')) return run;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('page never became ready');
}

const dataOf = (url) => Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');

/** An Annex B stream from this renderer, split back into its chunks of `size` pictures. A chunk starts at the
 *  parameter sets in front of picture k·size; key frames an encoder adds by itself stay inside their chunk. */
function chunksOf(buf, size) {
  const starts = [];
  let pictures = 0, header = -1;   // header: where the parameter sets in front of the next picture begin
  for (let i = 0; i + 3 < buf.length; i++) {
    if (buf[i] === 0 && buf[i + 1] === 0 && (buf[i + 2] === 1 || (buf[i + 2] === 0 && buf[i + 3] === 1))) {
      const head = buf[i + 2] === 1 ? i + 3 : i + 4;
      const type = buf[head] & 31;
      if ((type === 7 || type === 8) && header < 0) header = i;
      if (type === 1 || type === 5) {
        if (buf[head + 1] & 0x80) {   // first_mb_in_slice = 0: a new picture
          if (pictures % size === 0) starts.push(header >= 0 ? header : i);
          pictures++;
        }
        header = -1;
      }
      i = head;
    }
  }
  return { pictures, chunks: starts.map((s, k) => buf.subarray(s, k + 1 < starts.length ? starts[k + 1] : buf.length)) };
}

/** Frames a..b-1 drawn as JPEG and encoded by ffmpeg (x264 or vaapi) into one Annex B chunk. */
async function ffmpegChunk(run, a, b, fps) {
  const colour = 'scale=in_range=full:in_color_matrix=bt601:out_color_matrix=bt709:out_range=tv';
  // no B-frames: the chunks are joined with one timestamp per frame in stream order
  const video = ENCODER === 'vaapi'
    // the GPU encoder takes nv12 surfaces; constant QP, the quality knob of the low-power encoder
    ? ['-vaapi_device', VAAPI_DEVICE, '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
       '-vf', `${colour},format=nv12,hwupload`, '-c:v', 'h264_vaapi', '-profile:v', 'high', '-rc_mode', 'CQP', '-qp', QP, '-bf', '0']
    : ['-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
       '-vf', `${colour},format=yuv420p`, '-c:v', 'libx264', '-preset', 'medium', '-crf', CRF, '-maxrate', '12M', '-bufsize', '24M', '-bf', '0'];
  const ff = spawn('ffmpeg', ['-loglevel', 'error', ...video, '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-f', 'h264', '-'],
    { stdio: ['pipe', 'pipe', 'inherit'] });
  const parts = [];
  ff.stdout.on('data', (d) => parts.push(d));
  const done = new Promise((ok, fail) => ff.on('exit', (c) => (c === 0 ? ok(Buffer.concat(parts)) : fail(new Error(`ffmpeg (${ENCODER}) exited ${c}`)))));
  for (let i = a; i < b; i++) {
    if (!ff.stdin.write(dataOf(await run(`window.__frame(${i}, 'image/jpeg', 0.94)`)))) await new Promise((r) => ff.stdin.once('drain', r));
  }
  ff.stdin.end();
  return done;
}

function annexBOf(file) {
  return new Promise((ok, fail) => {
    const ff = spawn('ffmpeg', ['-loglevel', 'error', '-i', file, '-map', '0:v:0', '-c:v', 'copy', '-bsf:v', 'h264_mp4toannexb', '-f', 'h264', '-'],
      { stdio: ['ignore', 'pipe', 'inherit'] });
    const parts = [];
    ff.stdout.on('data', (d) => parts.push(d));
    ff.on('exit', (c) => (c === 0 ? ok(Buffer.concat(parts)) : fail(new Error(`ffmpeg could not read ${file}`))));
  });
}

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
      const dir = path.resolve(ROOT, opt('stills-dir', 'out/stills'));
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
    if (ENCODER === 'webcodecs') {
      const supported = (await Promise.all(pages.map((run) => run(ENCODE_CHUNK)))).every(Boolean);
      if (!supported) { console.log('this browser has no H.264 encoder (WebCodecs): encoding with x264'); ENCODER = 'x264'; }
    }
    const info = await pages[0]('window.__info');
    const size = Math.max(1, Math.round(CHUNK * info.fps));
    // the chunks to write: [first frame, end frame, null = draw it | Buffer = copy it]
    let plan;
    if (PATCH) {
      const { pictures, chunks: old } = chunksOf(await annexBOf(PATCH), size);
      if (pictures !== info.frames) throw new Error(`--patch: ${path.relative(ROOT, PATCH)} has ${pictures} frames, the film now has ${info.frames} (the timeline changed): render it in full`);
      const a = Math.floor(parseFloat(opt('from', '0')) * info.fps / size), b = Math.ceil(parseFloat(opt('to', String(info.duration))) * info.fps / size);
      plan = old.map((buf, k) => [k * size, Math.min(info.frames, (k + 1) * size), k >= a && k < b ? null : buf]);
    } else {
      const first = Math.round(parseFloat(opt('from', '0')) * info.fps);
      const last = Math.min(info.frames, Math.round(parseFloat(opt('to', String(info.duration))) * info.fps));
      plan = [];
      for (let i = first; i < last; i += size) plan.push([i, Math.min(last, i + size), null]);
    }
    const start = plan[0][0];
    const withAudio = !flag('no-audio') && fs.existsSync(AUDIO);
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    const ff = spawn('ffmpeg', [
      '-y', '-loglevel', 'error', '-r', String(info.fps), '-f', 'h264', '-i', '-',   // -r: one frame every 1/fps, whatever the chunks say
      ...(withAudio ? ['-ss', String(start / info.fps), '-i', AUDIO] : []),
      // raw chunks carry no timestamps: frame N at N/fps (no encoder here makes B-frames), so the sound can interleave
      '-map', '0:v:0', ...(withAudio ? ['-map', '1:a:0'] : []), '-c:v', 'copy', '-bsf:v', `setts=ts=N/(${info.fps}*TB)`,
      ...(withAudio ? ['-c:a', 'aac', '-b:a', '256k', '-shortest'] : []),
      '-movflags', '+faststart', OUT,
    ], { stdio: ['pipe', 'inherit', 'inherit'] });
    const ffDone = new Promise((ok, fail) => ff.on('exit', (c) => (c === 0 ? ok() : fail(new Error(`ffmpeg exited ${c}`)))));

    const ready = new Map();
    const todo = plan.map((p, k) => k).filter((k) => !plan[k][2]);
    plan.forEach(([, , buf], k) => { if (buf) ready.set(k, buf); });
    let toWrite = 0, drawn = 0;
    const frames = todo.reduce((s, k) => s + plan[k][1] - plan[k][0], 0);
    const started = Date.now();
    const flush = async () => {
      while (ready.has(toWrite)) {
        const buf = ready.get(toWrite);
        ready.delete(toWrite);
        if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
        toWrite++;
      }
    };
    let flushing = flush();
    let next = 0;
    await Promise.all(pages.map(async (run) => {
      while (next < todo.length) {
        const k = todo[next++];
        const [a, b] = plan[k];
        ready.set(k, ENCODER === 'webcodecs' ? Buffer.from(await run(`window.__chunk(${a}, ${b}, ${BITRATE})`), 'base64')
                                             : await ffmpegChunk(run, a, b, info.fps));
        drawn += b - a;
        process.stdout.write(`\rframe ${drawn}/${frames}  ${(drawn / ((Date.now() - started) / 1000)).toFixed(1)} fps   `);
        flushing = flushing.then(flush);
        await flushing;
      }
    }));
    await flushing;
    ff.stdin.end();
    await ffDone;
    const what = `${ENCODER}, ${PATCH ? `${todo.length} of ${plan.length} chunks drawn again, the rest copied from ${path.relative(ROOT, PATCH)}` : `${plan.length} chunks`}`;
    console.log(`\nwrote ${path.relative(ROOT, OUT)}${withAudio ? ' (with audio)' : ' (silent)'}: ${what}, ${((Date.now() - started) / 1000).toFixed(0)}s`);
  } finally {
    await cleanup();
  }
}

main().catch((e) => { console.error(e.message); process.exit(1); });
