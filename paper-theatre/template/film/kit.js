// Scene-writing kit: anchors from the narration, cut-outs that enter and leave the stage,
// labels, map pins and arrows, flames and the common sets. Pure functions of stepped time S.
import {
  W, H, INK, KRAFT, clamp, lerp, seg, rad, ease, pop, drop, spring, bump, hash, hs,
  cut, paper, place, rectPts, circlePts, starPts, stripPts, arrowPts, ribbonPts, chip, fontOf,
} from './engine.js';
import { COL, bandPts, backdrop, hang, strings, withCard, cardFace, chipStyle, sparkle, stamp, crossPts } from './stage.js';

export { W, H, INK, KRAFT, clamp, lerp, seg, rad, ease, pop, drop, spring, bump, hash, hs, cut, paper, place, rectPts, circlePts, starPts, stripPts, arrowPts, ribbonPts, chip, fontOf };
export { COL, bandPts, backdrop, hang, strings, withCard, cardFace, chipStyle, sparkle, stamp, crossPts };

export const GROUND = 884;

/** Narration anchors: L[id] is a line, wt(id, prefix) the start of its first word starting with prefix. */
export function anchorsOf(tl) {
  const L = Object.fromEntries(tl.lines.map((l) => [l.id, l]));
  const norm = (w) => w.toLowerCase().replace(/^[„"(]+/, '');
  const wt = (id, prefix, key = 's') => {
    const l = L[id];
    if (!l) { console.warn('no line', id); return 0; }
    const w = l.words.find((x) => norm(x.w).startsWith(prefix.toLowerCase()));
    if (!w) console.warn('no word', id, prefix);
    return w ? w[key] : l.start;
  };
  const we = (id, prefix) => wt(id, prefix, 'e');
  return { L, wt, we };
}

/** Boil: every piece is re-placed by hand a few times a second. */
export const J = (b, k, a = 1.2) => hs(b, k) * a;

/**
 * A cut-out with an entrance at t0 and an exit at t1.
 * enter: 'pop' | 'drop' | 'rise' | 'left' | 'right' | 'none'; exit: 'pop' | 'up' | 'down' | 'left' | 'right' | 'none'.
 * Walking entrances ('left'/'right') hop on every step. Extra keys go straight to cut().
 */
export function piece(ctx, img, S, b, o) {
  const { t0 = -1e9, t1 = Infinity, enter = 'pop', exit = 'pop', k = 1, dur = 1.0 } = o;
  if (!img || S < t0 - 0.01) return null;
  if (Number.isFinite(t1) && S > t1 + 0.7) return null;
  let x = o.x, y = o.y, s = 1, rot = o.rot || 0;
  const a = S - t0;
  if (enter === 'pop') s *= pop(S, t0, 0.3);
  else if (enter === 'drop') y -= (1 - spring(S, t0, 1.6, 5.2)) * 900;
  else if (enter === 'rise') y += (1 - spring(S, t0, 1.6, 5.2)) * 700;
  else if (enter === 'left' || enter === 'right') {
    const q = ease.out(seg(S, t0, t0 + dur));
    const from = o.from ?? (enter === 'left' ? -420 : W + 420);
    x = lerp(from, o.x, q);
    if (q < 0.98) {
      const ph = a / 0.36;
      y -= 12 * Math.abs(Math.sin(Math.PI * ph));
      rot += Math.floor(ph) % 2 ? 2 : -1.5;
    }
  }
  if (Number.isFinite(t1) && S >= t1) {
    const q = ease.in(seg(S, t1, t1 + 0.4));
    if (exit === 'pop') s *= 1 - q;
    else if (exit === 'up') y -= q * 1400;
    else if (exit === 'down') y += q * 1100;
    else if (exit === 'left') x -= q * (x + 700);
    else if (exit === 'right') x += q * (W - x + 700);
  }
  if (s <= 0.005) return null;
  const sw = o.sway ? o.sway * Math.sin(S * 1.7 + k) : 0;
  const hop = o.hop ? o.hop.reduce((acc, [th, hgt]) => acc + hgt * bump(S, th, 0.3), 0) : 0;
  const q = { ...o, x: x + J(b, k), y: y - hop, rot: rot + J(b, k + 1, 0.5) + sw, sx: s * (o.sx || 1), sy: s * (o.sy || 1) };
  cut(ctx, img, q);
  return q;
}

/** Pose swaps: poses = [[t, imgName], ...] → the image shown at S and how long ago it changed. */
export function poseAt(S, poses) {
  let cur = poses[0], since = -1e9;
  for (const p of poses) if (S >= p[0]) { cur = p; since = p[0]; }
  return { name: cur[1], since, squash: since > -1e8 ? bump(S, since, 0.2) : 0 };
}

/** A word card on the stage (not a caption): pops at t0, leaves at t1. */
export function label(ctx, text, S, o) {
  const { t0 = -1e9, t1 = Infinity, size = 44, seed = 1, rot = 0 } = o;
  let s = pop(S, t0, 0.25);
  if (Number.isFinite(t1)) s *= drop(S, t1, 0.18);
  if (o.stamp) s = stamp(S, t0) * (Number.isFinite(t1) ? drop(S, t1, 0.18) : 1);
  if (s <= 0.005) return;
  const style = o.style || chipStyle(text);
  chip(ctx, text, { x: o.x, y: o.y, size, seed, rot, s, lift: o.lift ?? 0.9, ...style, ...(o.fill ? { fill: o.fill } : {}), ...(o.color ? { color: o.color } : {}) });
}

/** Map helper: a map cut-out drawn in a rectangle; pt(u, v) maps fractions of the image to the screen. */
export function mapAt(img, x, y, w) {
  const h = img.height * (w / img.width);
  return { x, y, w, h, pt: (u, v) => [x - w / 2 + u * w, y - h / 2 + v * h] };
}

/** A paper pin stamped onto a map. */
export function pin(ctx, S, b, [x, y], t0, fill = COL.red, r = 16, seed = 1) {
  const s = stamp(S, t0);
  if (s <= 0) return;
  paper(ctx, place(circlePts(r, seed, 0.06, 24), { x, y, s }), { fill, rim: 3, rimColor: COL.cream, lift: 0.8 });
}

/** An arrow of paper growing along a polyline between t0 and t0 + d. */
export function trail(ctx, S, pts, t0, d = 0.8, fill = COL.red, th = 12, seed = 1, t1 = Infinity) {
  if (S < t0) return;
  if (Number.isFinite(t1) && S > t1) return;
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = lens[lens.length - 1];
  const at = (s) => {
    s = clamp(s, 0, total);
    let i = 1;
    while (i < lens.length - 1 && lens[i] < s) i++;
    const f = (s - lens[i - 1]) / Math.max(1e-6, lens[i] - lens[i - 1]);
    return [lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)];
  };
  const head = total * ease.inOut(seg(S, t0, t0 + d));
  if (head < 2) return;
  // dashed paper strip: the cut-out look of a route on a map
  for (let s = 0; s < head - 18; s += 34) {
    const [x0, y0] = at(s), [x1, y1] = at(Math.min(head - 18, s + 20));
    paper(ctx, stripPts(x0, y0, x1, y1, th, th, seed + s, 1), { fill, rim: 2, rimColor: COL.cream, lift: 0.5 });
  }
  const [hx, hy] = at(head), [px, py] = at(head - 6);
  paper(ctx, place(arrowPts(th * 1.9, seed), { x: hx, y: hy, rot: (Math.atan2(hy - py, hx - px) * 180) / Math.PI }), { fill, rim: 2, rimColor: COL.cream, lift: 0.6 });
}

/** The point a fraction f (0..1) of the way along a polyline: a cargo riding a trail. */
export function along(pts, f) {
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const s = clamp(f, 0, 1) * lens[lens.length - 1];
  let i = 1;
  while (i < lens.length - 1 && lens[i] < s) i++;
  const k = (s - lens[i - 1]) / Math.max(1e-6, lens[i] - lens[i - 1]);
  return [lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k)];
}

/** Paper flames: tongues of red, orange and yellow card that flicker on twos. */
export function flames(ctx, S, b, x, y, w, h, seed = 1, k = 1) {
  if (k <= 0.01) return;
  const n = Math.max(3, Math.round(w / 34));
  const cols = ['#b8432f', '#e0702f', '#f2a83b', '#f7d36b'];
  cols.forEach((c, layer) => {
    const lh = h * (1 - layer * 0.22) * k;
    const pts = [[x - w / 2, y]];
    for (let i = 0; i <= n; i++) {
      const u = i / n;
      const xx = x - w / 2 + u * w;
      const tip = (i % 2 === 0) ? lh * (0.55 + 0.45 * hash(seed + i + layer * 7, b)) : lh * 0.25;
      pts.push([xx + hs(seed + i, b + layer) * 6, y - tip * Math.sin(Math.PI * (0.15 + 0.7 * u))]);
    }
    pts.push([x + w / 2, y]);
    paper(ctx, pts, { fill: c, rim: layer ? 0 : 3, rimColor: '#7a2a18', lift: layer ? 0 : 0.6 });
  });
}

/** Which set is showing: cuts are the wipe times; returns 0 before cuts[0], 1 after it, … */
export const setIndex = (S, cuts) => cuts.filter((c) => S >= c).length;

// ---------- common sets ----------
/** Sunny landscape: sky, a far band, a mid band, the front band where people stand. */
export function landscape(ctx, S, b, tex, img, o = {}) {
  const { sky = '#e9c27a', far = '#c99a55', mid = '#a49a4e', front = '#a77a45', sun = true, trees = [] } = o;
  backdrop(ctx, sky, tex);
  if (sun) {
    const sx = o.sunX ?? 1620, sy = o.sunY ?? 170;
    stringTop(ctx, sx, sy - 70);
    paper(ctx, place(starPts(120, 84, 14, 9, 0.04), { x: sx, y: sy, rot: Math.round(S * 6 / 3) * 3 }), { fill: '#f0c050', rim: 3, lift: 0.8 });
    paper(ctx, place(circlePts(72, 9, 0.02, 60), { x: sx, y: sy }), { fill: '#f7dc8a', rim: 3, lift: 0.6 });
  }
  paper(ctx, bandPts(600, 24, 820, 13), { fill: far, rim: 4, lift: 0.8 });
  if (o.behindMid) o.behindMid();
  paper(ctx, bandPts(720, 14, 600, 17), { fill: mid, rim: 4, lift: 0.9 });
  trees.forEach(([name, x, h, flip], i) => cut(ctx, img[name], { x: x + J(b, 300 + i), y: 768, h, flip, rot: J(b, 310 + i, 0.5), lift: 1 }));
  paper(ctx, bandPts(826, 10, 520, 19), { fill: front, rim: 4, lift: 1 });
}

/** A kraft board with a map on it. */
export function mapBoard(ctx, S, b, tex, img, o = {}) {
  backdrop(ctx, o.bg || '#8a6440', tex, 0.6);
  const m = mapAt(img, o.x ?? 960, o.y ?? 470, o.w ?? 1360);
  cut(ctx, img, { x: m.x + J(b, 320, 0.8), y: m.y, w: m.w, ax: 0.5, ay: 0.5, rot: (o.rot ?? -0.6) + J(b, 321, 0.25), lift: 1.2 });
  return m;
}

/** Under the sea: sky strip, waves, deepening water bands and a sandy floor. */
export function seaSet(ctx, S, b, tex) {
  backdrop(ctx, '#1d4f86', tex);
  paper(ctx, [[-20, -20], [W + 20, -20], [W + 20, 120], [-20, 120]], { fill: '#e9c27a', rim: 0, lift: 0 });
  const wave = (y, amp, wl, ph) => {
    const pts = [];
    for (let x = -60; x <= W + 60; x += 40) pts.push([x, y + amp * Math.sin(x / wl + ph + Math.round(S * 6) / 6 * 0.6)]);
    pts.push([W + 60, H + 100], [-60, H + 100]);
    return pts;
  };
  paper(ctx, wave(118, 10, 60, 0), { fill: '#2f78b8', rim: 3, rimColor: '#cfe6f2', lift: 0.6 });
  paper(ctx, wave(300, 8, 110, 1), { fill: '#286aa6', rim: 0, lift: 0.4 });
  paper(ctx, wave(520, 8, 140, 2), { fill: '#215d95', rim: 0, lift: 0.4 });
  paper(ctx, bandPts(790, 16, 520, 51), { fill: '#d4b27a', rim: 4, lift: 0.9 });
  for (let i = 0; i < 14; i++) {
    const t0 = hash(i, 5) * 6, ph = ((S + t0) % 6) / 6;
    const x = 120 + hash(i, 6) * 1680 + 20 * Math.sin(S * 2 + i), y = 760 - ph * 680;
    paper(ctx, place(circlePts(5 + hash(i, 7) * 7, i, 0.05, 14), { x, y }), { fill: '#bfe0f2', rim: 0, lift: 0.2 });
  }
}

/** Fresco room: painted wall, frieze of rosettes on top, ochre floor. */
export function frescoRoom(ctx, S, b, tex, wall = '#a8432f') {
  backdrop(ctx, wall, tex, 0.55);
  paper(ctx, [[-20, -20], [W + 20, -20], [W + 20, 78], [-20, 82]], { fill: COL.egyptian, rim: 4, lift: 0.8 });
  for (let i = 0; i < 17; i++) {
    paper(ctx, place(circlePts(20, i + 3, 0.05, 20), { x: 60 + i * 115, y: 38 }), { fill: COL.cream, rim: 2, lift: 0.3 });
    paper(ctx, place(circlePts(8, i + 30, 0.05, 14), { x: 60 + i * 115, y: 38 }), { fill: COL.red, rim: 0, lift: 0 });
  }
  paper(ctx, [[-20, 82], [W + 20, 78], [W + 20, 100], [-20, 104]], { fill: COL.ochre, rim: 3, lift: 0.6 });
  paper(ctx, bandPts(842, 8, 700, 23), { fill: COL.ochre, rim: 4, lift: 1 });
}

/** Night sky with stars and a moon on a string. */
export function nightSky(ctx, S, b, tex, color = COL.night) {
  backdrop(ctx, color, tex);
  for (let i = 0; i < 30; i++) {
    const x = 40 + hash(i, 1) * 1840, y = 30 + hash(i, 2) * 520;
    const r = 6 + hash(i, 3) * 8;
    paper(ctx, place(starPts(r, r * 0.45, 5, i), { x, y, rot: hs(i, 4) * 20, s: 0.75 + 0.4 * hash(i, b % 3) }), { fill: '#f3e3ad', rim: 0, lift: 0.3 });
  }
  const mx = 1590 + 6 * Math.sin(S * 0.5);
  stringTop(ctx, mx, 120);
  paper(ctx, place(circlePts(66, 5, 0.02, 60), { x: mx, y: 186 }), { fill: '#efe2bd', rim: 4, lift: 1 });
}

/** Plain string from above the frame down to y1. */
export function stringTop(ctx, x, y1) {
  ctx.save();
  ctx.strokeStyle = '#efe6d2'; ctx.lineWidth = 3; ctx.lineCap = 'round';
  ctx.shadowColor = 'rgba(10,8,30,0.35)'; ctx.shadowBlur = 6; ctx.shadowOffsetX = 4; ctx.shadowOffsetY = 6;
  ctx.beginPath(); ctx.moveTo(x, -30); ctx.lineTo(x, y1); ctx.stroke();
  ctx.restore();
}

/** A hanging card with a cut-out on it and an optional caption strip. */
export function picCard(ctx, S, b, img, o) {
  const c = hang(S, b, { x: o.x, y: o.y, w: o.w, h: o.h, t0: o.t0, t1: o.t1 ?? Infinity, seed: o.seed ?? 1, swing: o.swing ?? 1.6 });
  if (!c) return null;
  strings(ctx, c, o.inset ?? 0.32);
  withCard(ctx, c, () => {
    cardFace(ctx, c, o.fill || COL.cream, (o.seed ?? 1) + 40, 5);
    if (o.inner) paper(ctx, rectPts(c.w - 30, c.h - 30, (o.seed ?? 1) + 41, 3), { fill: o.inner, rim: 0, lift: 0 });
    const capH = o.text ? 56 : 0;
    if (img) {
      const box = Math.min(c.w - 50, (c.h - 50 - capH) * (img.width / img.height));
      cut(ctx, img, { x: 0, y: -capH / 2, w: box, ax: 0.5, ay: 0.5, lift: 0.5 });
    }
    if (o.text) {
      ctx.font = fontOf(o.size || 40); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = o.color || INK;
      ctx.fillText(o.text, 0, c.h / 2 - 38);
    }
    if (o.draw) o.draw(c);
  });
  return c;
}

/** Big paper X stamped at t0 over (x, y). */
export function cross(ctx, S, x, y, t0, size = 80, seed = 1) {
  const k = stamp(S, t0);
  if (k <= 0) return;
  crossPts(size, seed).forEach((p) => paper(ctx, place(p, { x, y, s: k }), { fill: COL.red, rim: 3, rimColor: COL.cream, lift: 0.9 }));
}

/** A golden glow behind something precious. */
export function glow(ctx, x, y, r, k = 1, rgb = '255,205,120') {
  if (k <= 0) return;
  const g = ctx.createRadialGradient(x, y, 4, x, y, r);
  g.addColorStop(0, `rgba(${rgb},${0.45 * k})`); g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2); ctx.restore();
}

/** A hanging card with a year or a short word on it. */
export function yearCard(ctx, S, b, text, o) {
  const c = hang(S, b, { x: o.x ?? 560, y: o.y ?? 300, w: o.w ?? 440, h: o.h ?? 230, t0: o.t0, t1: o.t1 ?? Infinity, seed: o.seed ?? 3 });
  if (!c) return;
  strings(ctx, c);
  withCard(ctx, c, () => {
    cardFace(ctx, c, o.fill || COL.cream, (o.seed ?? 3) + 28);
    ctx.font = fontOf(o.size || 120); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = o.color || INK;
    ctx.fillText(text, 0, 8);
    if (o.sub) { ctx.font = fontOf(34); ctx.fillText(o.sub, 0, c.h / 2 - 34); }
  });
}

/** Cross-section of a shaft grave lit by a hanging lantern. */
export function pitSet(ctx, S, b, tex) {
  backdrop(ctx, COL.night, tex);
  [[150, '#4a3524'], [330, '#5a4029'], [520, '#4f3826'], [700, '#5e432b']].forEach(([y, c], i) =>
    paper(ctx, bandPts(y, 9, 500 + i * 90, 30 + i), { fill: c, rim: 4, rimColor: '#7a5a3a', lift: 0.7 }));
  paper(ctx, [[560, 140], [1360, 140], [1340, 812], [580, 812]], { fill: '#24180f', rim: 0, lift: 0 });
  for (let k = 0; k < 26; k++) {
    const side = k % 2 ? 1 : -1, row = Math.floor(k / 2);
    const x = 960 + side * 395 + hs(k, 8) * 6, y = 170 + row * 52;
    paper(ctx, place(rectPts(64 + hash(k, 9) * 26, 42 + hash(k, 10) * 10, k, 6), { x, y, rot: hs(k, 11) * 8 }), { fill: ['#8b8172', '#9a8f7d', '#7d7466', '#a39886'][k % 4], rim: 3, rimColor: '#4a3a2a', lift: 0.6 });
  }
  paper(ctx, bandPts(800, 4, 300, 39, 520, 1400, 840), { fill: '#6b5440', rim: 3, lift: 0.5 });
  const lx = 960 + 18 * Math.sin(S * 1.4), ly = 250;
  stringTop(ctx, lx, ly - 30);
  glow(ctx, lx, ly + 150, 330, 0.9);
  paper(ctx, place(rectPts(44, 60, 61, 3), { x: lx, y: ly }), { fill: '#e2a640', rim: 3, lift: 0.8 });
  paper(ctx, place(rectPts(26, 36, 62, 2), { x: lx, y: ly + 2 }), { fill: '#fff0b8', rim: 0, lift: 0 });
}

/** Scatter of little paper beads poured out between t0 and t0 + d around (x, y). */
export function beads(ctx, S, x, y, t0, n = 60, spread = 320, d = 1.2) {
  if (S < t0) return;
  const cols = ['#c0392b', '#8e44ad', '#e8b23a', '#d35400', '#f3e3ad', '#1f6fa8'];
  for (let i = 0; i < n; i++) {
    const ti = t0 + (i / n) * d;
    const k = pop(S, ti, 0.18);
    if (k <= 0) continue;
    const a = hash(i, 71) * Math.PI * 2, r = spread * Math.sqrt(hash(i, 72));
    paper(ctx, place(circlePts(7 + hash(i, 73) * 5, i, 0.08, 12), { x: x + Math.cos(a) * r, y: y + Math.sin(a) * r * 0.32, s: k }), { fill: cols[i % cols.length], rim: 1.5, lift: 0.3 });
  }
}

/** Kraft workshop board as a plain backdrop. */
export function board(ctx, tex, color = '#9b7146') {
  backdrop(ctx, color, tex, 0.6);
  paper(ctx, bandPts(842, 8, 700, 23), { fill: '#7a5532', rim: 4, lift: 1 });
}
