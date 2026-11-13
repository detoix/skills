// Paper-theatre machinery shared by every scene: bands, hanging cards, paper-strip wipes,
// sparkles and the word-by-word captions. Everything is a pure function of (stepped) time.
import {
  W, H, KRAFT, INK, clamp, lerp, seg, rad, ease, pop, drop, spring, hash, hs, boilStep,
  paper, place, rectPts, starPts, string, chip, textWidth, fontOf,
} from './engine.js';
import { WORDS, RAIL_YEARS } from './config.js';

export const COL = {
  ink: INK, kraft: KRAFT, kraftDark: '#8a6440', cream: '#f4e8cf', white: '#fbf7ee',
  gold: '#e8b23a', red: '#b8432f', violet: '#6b4a9a', blue: '#2f5d9e', egyptian: '#1f6fa8',
  ochre: '#d79a45', terracotta: '#b0533a', olive: '#6d7a3a',
  night: '#1b2c52', night2: '#24386a', nightHill: '#2c3b55', nightHill2: '#34442f', nightEarth: '#3d3022',
  apron: '#2c2118',
};

/** Hand-cut wavy band: top edge around yTop, filled down past the bottom of the frame. */
export function bandPts(yTop, amp, wl, seed, x0 = -160, x1 = W + 160, yBottom = H + 200) {
  const pts = [];
  for (let x = x0; x <= x1; x += 48) pts.push([x, yTop + amp * Math.sin((x / wl) * Math.PI * 2 + seed) + hs(seed, x) * 4]);
  pts.push([x1, yBottom], [x0, yBottom]);
  return pts;
}

/** The stage apron along the bottom edge: a slim front strip; the timeline rail slides up over it. */
export const APRON_Y = 1004;
export function apron(ctx, S, dy = 0) {
  paper(ctx, place(bandPts(APRON_Y, 5, 900, 41), { y: dy }), { fill: COL.apron, rim: 4, rimColor: COL.kraftDark, lift: 1.2 });
}

// ---------- timeline rail ----------
// Comes up from below the apron whenever the story moves to another time, slides its marker there,
// shows the date on a card and goes down again. The span of years is the film's (config.js RAIL_YEARS).
const RAIL = { x0: 170, x1: 1750, y: 1046, ...RAIL_YEARS };
const railX = (year) => lerp(RAIL.x0, RAIL.x1, (RAIL.from - year) / (RAIL.from - RAIL.to));

export function makeRail(cues) {
  // cues: [{ t, a, b, label }] sorted by t; a..b is the highlighted span (a == b for a single date)
  const SHOW = 4.4;
  return function rail(ctx, S, b) {
    let cur = null, prev = null;
    for (const c of cues) { if (S >= c.t) { prev = cur; cur = c; } }
    if (!cur) return;
    const age = S - cur.t;
    const up = ease.out(seg(age, 0, 0.35)) * (1 - ease.in(seg(age, SHOW - 0.35, SHOW)));
    if (up <= 0) return;
    const dy = (1 - up) * 120;
    ctx.save();
    ctx.translate(0, dy);
    paper(ctx, [[RAIL.x0 - 40, RAIL.y - 16], [RAIL.x1 + 40, RAIL.y - 18], [RAIL.x1 + 40, RAIL.y + 16], [RAIL.x0 - 40, RAIL.y + 18]], { fill: '#c89f6c', rim: 3, rimColor: COL.kraftDark, lift: 0.8 });
    const dir = Math.sign(RAIL.to - RAIL.from);
    for (let y = RAIL.from; dir > 0 ? y <= RAIL.to : y >= RAIL.to; y += dir * RAIL.tick) {
      const x = railX(y), big = y % RAIL.major === 0;
      paper(ctx, [[x - 2, RAIL.y - 14], [x + 2, RAIL.y - 14], [x + 2, RAIL.y + (big ? 12 : 2)], [x - 2, RAIL.y + (big ? 12 : 2)]], { fill: INK, rim: 0, lift: 0 });
      if (big) {
        ctx.font = fontOf(20, 700); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = COL.ink;
        ctx.fillText(String(y), x, RAIL.y + 2 - 1);
      }
    }
    // the highlighted span and the marker glide from the previous position on twos
    const k = ease.inOut(seg(age, 0.25, 1.05));
    const a = lerp(prev ? prev.a : cur.a, cur.a, k), bb = lerp(prev ? prev.b : cur.b, cur.b, k);
    const xa = railX(a), xb = railX(bb);
    if (Math.abs(xb - xa) > 4) paper(ctx, [[xa, RAIL.y - 9], [xb, RAIL.y - 9], [xb, RAIL.y + 9], [xa, RAIL.y + 9]], { fill: COL.gold, rim: 2, rimColor: COL.cream, lift: 0.5 });
    const xm = (xa + xb) / 2;
    paper(ctx, place([[0, 0], [-16, -26], [16, -26]], { x: xm + hs(b, 5) * 1.2, y: RAIL.y - 12 }), { fill: COL.red, rim: 2.5, rimColor: COL.cream, lift: 0.8 });
    const ls = pop(age, 0.9, 0.25);
    if (ls > 0.01) chip(ctx, cur.label, { x: clamp(xm, 260, W - 260), y: RAIL.y - 66, size: 30, seed: Math.round(cur.t * 10), rot: hs(Math.round(cur.t), 3) * 2, s: ls, lift: 0.8, fill: COL.white, color: INK });
    ctx.restore();
  };
}

/**
 * A card hanging on two visible strings. It drops in with a springy landing at t0,
 * swings a little while it hangs and flies out upwards at t1.
 * Returns the transform (or null when off stage) so the caller can draw the card's face.
 */
export function hang(S, b, { x, y, w, h, t0, t1 = Infinity, seed = 1, swing = 1.6, from = -260 }) {
  if (S < t0 - 0.05) return null;
  const inY = spring(S, t0, 1.6, 5.2);
  const out = Number.isFinite(t1) ? ease.in(seg(S, t1, t1 + 0.45)) : 0;
  const cy = lerp(from - h, y, inY) - out * (y + h + 300);
  if (cy < -h - 200) return null;
  const settle = Math.exp(-2.4 * Math.max(0, S - t0));
  const rot = swing * Math.sin((S - t0) * 4.2 + seed) * settle + hs(b, seed) * 0.25 + (1 - Math.min(1, inY)) * 3;
  return { x, y: cy, w, h, rot };
}

/** Draw the two strings for a hanging card; the knots sit on the card's top edge. */
export function strings(ctx, c, inset = 0.32, alpha = 1) {
  const c0 = Math.cos(rad(c.rot)), s0 = Math.sin(rad(c.rot));
  for (const k of [-1, 1]) {
    const dx = k * c.w * inset, dy = -c.h / 2 + 10;
    string(ctx, c.x + dx * c0 - dy * s0, -30, c.y + dx * s0 + dy * c0, alpha);
  }
}

/** Plain card face on a hanging transform (call between save/restore with the transform applied). */
export function cardFace(ctx, c, fill, seed, rim = 5) {
  paper(ctx, rectPts(c.w, c.h, seed, 6), { fill, rim, lift: 1.4 });
}

/** Apply a hanging transform: translate + rotate around the card centre. */
export function withCard(ctx, c, fn) {
  ctx.save();
  ctx.translate(c.x, c.y); ctx.rotate(rad(c.rot));
  fn();
  ctx.restore();
}

/**
 * Scene change: strips of painted paper slide across the frame, cover it at T and slide off.
 * Draw it on top of everything; switch the set underneath exactly at T.
 */
const WIPE_COLORS = [['#b0533a', '#d79a45', '#1f6fa8', '#c89f6c', '#6d7a3a', '#e3c48a'], ['#1f6fa8', '#c89f6c', '#b0533a', '#e3c48a', '#d79a45', '#2c3b55']];
export function wipe(ctx, S, T, seed = 1, tex = null, d = 0.42) {
  if (S < T - d - 0.05 || S > T + d + 0.3) return;
  const n = 6, sh = H / n;
  const cols = WIPE_COLORS[seed % 2];
  for (let k = 0; k < n; k++) {
    const lag = (k % 2 ? 0.05 : 0) + hash(k, seed) * 0.06;
    const pin = ease.inOut(seg(S, T - d + lag, T - 0.02));
    const pout = ease.inOut(seg(S, T + 0.04 + lag, T + d + 0.06 + lag));
    // leading edge travels from the left edge to past the right edge; the tail follows on the way out
    const lead = lerp(-60, W + 220, pin) + pout * 300;
    const tail = lerp(-W - 300, -60, pin) + pout * (W + 400);
    if (lead <= -50 || tail >= W + 60) continue;
    const y0 = k * sh - 14, y1 = (k + 1) * sh + 14;
    const pts = [[tail, y0 + hs(k, seed + 1) * 6]];
    for (let i = 0; i <= 8; i++) pts.push([lead + hs(seed * 13 + k, i) * 26 + (i % 2 ? 18 : 0), lerp(y0, y1, i / 8)]);
    pts.push([tail, y1 + hs(k, seed + 2) * 6]);
    paper(ctx, pts, { fill: cols[k % cols.length], rim: 5, rimColor: KRAFT, lift: 1.6 });
    if (tex) {
      ctx.save();
      ctx.beginPath(); pts.forEach(([x, yy], i) => (i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy))); ctx.closePath(); ctx.clip();
      ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.45;
      ctx.drawImage(tex.brush, 0, 0);
      ctx.restore();
    }
  }
}

/** A burst of little paper stars, e.g. when something golden appears. */
export function sparkle(ctx, S, t0, x, y, r = 160, n = 7, seed = 1, fill = '#fff3c4') {
  for (let i = 0; i < n; i++) {
    const ti = t0 + i * 0.05;
    const k = pop(S, ti, 0.2) * drop(S, ti + 0.42, 0.22);
    if (k <= 0) continue;
    const a = rad(-90 + (i / n) * 360 + hs(seed, i) * 20), rr = r * (0.75 + 0.4 * hash(seed, i));
    paper(ctx, place(starPts(20, 7, 4, seed + i), { x: x + Math.cos(a) * rr, y: y + Math.sin(a) * rr, s: k, rot: i * 23 }), { fill, rim: 0, lift: 0.4 });
  }
}

/** Big paper stamp (an X, a ?): lands from above with a thump at t0. */
export function stamp(S, t0) {
  if (S < t0) return 0;
  const k = seg(S, t0, t0 + 0.14);
  return 1 + 0.9 * (1 - ease.out(k)) - 0.08 * Math.sin(Math.PI * seg(S, t0 + 0.14, t0 + 0.34));
}

export function crossPts(size, seed = 1) {
  const a = size, w = size * 0.26;
  const bar = (rot) => place(rectPts(a * 2, w, seed + rot, 3), { rot });
  return [bar(45), bar(-45)];
}

// ---------- captions ----------
// gold: highlights · red: names · violet: legends · white: numbers · kraft: everything else
const KIND_STYLE = {
  legend: { fill: COL.violet, color: COL.cream },
  name: { fill: COL.red, color: COL.cream },
  highlight: { fill: COL.gold, color: INK },
  number: { fill: COL.white, color: INK },
};
const KEYS = WORDS.map(([re, kind]) => [re, KIND_STYLE[kind]]);
export function chipStyle(word) {
  const w = word.replace(/^[„"(]+/, '');
  const k = KEYS.find(([re]) => re.test(w));
  return k ? k[1] : { fill: '#d9b98a', color: INK };
}

function chunkLine(line) {
  const chunks = [];
  let cur = [], chars = 0;
  line.words.forEach((w, i) => {
    cur.push(i); chars += w.w.length + 1;
    const stop = /[?!.,:;—”]$/.test(w.w);
    const next = line.words[i + 1];
    if (!next || (stop && cur.length >= 2) || cur.length >= 5 || chars + (next ? next.w.length : 0) > 34) {
      chunks.push(cur); cur = []; chars = 0;
    }
  });
  return chunks;
}

export function makeCaptions(lines) {
  lines.forEach((l) => { l.chunks = chunkLine(l); });
  const SIZE = 54, CY = 1006, GAP = 12;
  return function captions(ctx, S) {
    for (const l of lines) {
      if (S < l.start - 0.1 || S > l.end + 0.5) continue;
      let ci = 0;
      l.chunks.forEach((c, i) => { if (S >= l.words[c[0]].s - 0.07) ci = i; });
      const c = l.chunks[ci];
      const endsAt = ci + 1 < l.chunks.length ? l.words[l.chunks[ci + 1][0]].s - 0.07 : l.end + 0.35;
      const gone = drop(S, endsAt - 0.08, 0.12);
      if (gone <= 0) continue;
      const ws = c.map((wi) => textWidth(ctx, l.words[wi].w, SIZE) + SIZE * 0.68 + GAP);
      let x = W / 2 - ws.reduce((a, v) => a + v, 0) / 2;
      c.forEach((wi, k) => {
        const word = l.words[wi];
        const seed = wi * 7 + Math.round(l.start * 100);
        chip(ctx, word.w, {
          x: x + ws[k] / 2, y: CY + hs(seed, 1) * 5, size: SIZE, rot: hs(seed, 2) * 2.4, seed,
          s: pop(S, word.s - 0.07, 0.2) * gone, lift: 0.9, ...chipStyle(word.w),
        });
        x += ws[k];
      });
    }
  };
}

export function grain(ctx, S, tex) {
  const g = boilStep(S, 7.5);
  ctx.save();
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.36;
  ctx.translate(-Math.floor(hash(g, 1) * 200), -Math.floor(hash(g, 2) * 200));
  ctx.fillStyle = ctx.createPattern(tex.grain[g % 3], 'repeat');
  ctx.fillRect(0, 0, W + 256, H + 256);
  ctx.restore();
  const v = ctx.createRadialGradient(W / 2, H * 0.46, H * 0.42, W / 2, H * 0.5, H * 1.02);
  v.addColorStop(0, 'rgba(18,10,4,0)'); v.addColorStop(1, 'rgba(18,10,4,0.3)');
  ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
}

/** Flat painted backdrop: a colour with the dry-brush streaks multiplied over it. */
export function backdrop(ctx, color, tex, alpha = 0.5) {
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = alpha;
  ctx.drawImage(tex.brush, 0, 0);
  ctx.restore();
}

export { clamp, lerp, seg, ease, pop, drop, spring, hash, hs };
