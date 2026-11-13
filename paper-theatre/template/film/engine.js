// Cut-out animation toolkit on Canvas 2D (from the cardboards reel, widened to 16:9). No dependencies.
// Everything is a pure function of time, so any frame can be drawn in any order.

export const W = 1920;
export const H = 1080;
export const FPS = 30;
export const KRAFT = '#b98d5c';
export const INK = '#2a2019';

// ---------- maths ----------
export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const seg = (t, a, b) => clamp((t - a) / (b - a));
export const rad = (deg) => (deg * Math.PI) / 180;

export const ease = {
  lin: (t) => t,
  in: (t) => t * t * t,
  out: (t) => 1 - Math.pow(1 - t, 3),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  back: (t) => 1 + 2.70158 * Math.pow(t - 1, 3) + 1.70158 * Math.pow(t - 1, 2),
};

/** 0 → 1 with an overshoot, starting at t0. */
export const pop = (t, t0, d = 0.3) => (t < t0 ? 0 : ease.back(seg(t, t0, t0 + d)));
/** 1 → 0, starting at t0. */
export const drop = (t, t0, d = 0.2) => 1 - ease.in(seg(t, t0, t0 + d));
/** Damped wobble that settles on 1: used for bouncy landings. */
export const spring = (t, t0, freq = 3.2, damp = 5.5) =>
  t < t0 ? 0 : 1 - Math.exp(-damp * (t - t0)) * Math.cos(freq * 2 * Math.PI * (t - t0));
/** A short bump (0 → 1 → 0) used for squash, hops and hits. */
export const bump = (t, t0, d = 0.3) => (t < t0 || t > t0 + d ? 0 : Math.sin(Math.PI * seg(t, t0, t0 + d)));

/** Deterministic hash → [0, 1). */
export function hash(a, b = 0) {
  let h = Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
export const hs = (a, b = 0) => hash(a, b) * 2 - 1; // signed, [-1, 1)

/** Hold time on "twos": the stop-motion cadence used for every cardboard piece. */
export const stepped = (t, rate = 15) => Math.floor(t * rate + 1e-4) / rate;
/** Index of the current boil step: pieces are "re-placed by hand" a few times a second. */
export const boilStep = (t, rate = 7.5) => Math.floor(t * rate + 1e-4);

export function mix(c1, c2, t) {
  const p = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const a = p(c1), b = p(c2);
  return `rgb(${a.map((v, i) => Math.round(lerp(v, b[i], clamp(t)))).join(',')})`;
}

// ---------- textures ----------
function noiseCanvas(w, h, seed, lo, hi) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const x = c.getContext('2d');
  const d = x.createImageData(w, h);
  for (let i = 0; i < w * h; i++) {
    const v = Math.round(lerp(lo, hi, hash(i, seed)));
    d.data[i * 4] = d.data[i * 4 + 1] = d.data[i * 4 + 2] = v;
    d.data[i * 4 + 3] = 255;
  }
  x.putImageData(d, 0, 0);
  return c;
}

export function makeTextures() {
  // fine paper grain, tiled; three variants so the grain can "boil"
  const grain = [11, 23, 37].map((s) => noiseCanvas(256, 256, s, 196, 255));
  // wide horizontal dry-brush streaks for painted backdrops
  const small = noiseCanvas(25, 84, 5, 188, 255);
  const brush = document.createElement('canvas');
  brush.width = W; brush.height = H;
  const bx = brush.getContext('2d');
  bx.imageSmoothingEnabled = true; bx.imageSmoothingQuality = 'high';
  bx.drawImage(small, 0, 0, W, H);
  const fine = noiseCanvas(480, 270, 9, 205, 255);
  bx.globalCompositeOperation = 'multiply'; bx.globalAlpha = 0.5;
  bx.drawImage(fine, 0, 0, W, H);
  return { grain, brush };
}

// ---------- shadows ----------
function setShadow(ctx, lift) {
  if (lift <= 0) { ctx.shadowColor = 'transparent'; return; }
  ctx.shadowColor = 'rgba(14,18,44,0.36)';
  ctx.shadowBlur = 8 + 12 * lift;
  ctx.shadowOffsetX = 7 * lift;
  ctx.shadowOffsetY = 11 * lift;
}

// ---------- cut-out images ----------
/**
 * Draw a generated cut-out figure.
 * x,y = where the anchor sits; h or w = drawn size; ax,ay = anchor inside the figure (0..1).
 */
export function cut(ctx, img, o) {
  const { x, y, h, w, ax = 0.5, ay = 1, rot = 0, sx = 1, sy = 1, flip = false, alpha = 1, lift = 1, over = null, overAlpha = 0 } = o;
  if (alpha <= 0 || sx === 0 || sy === 0) return;
  const k = h ? h / img.height : w / img.width;
  const dw = img.width * k, dh = img.height * k;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rad(rot));
  ctx.scale((flip ? -1 : 1) * sx, sy);
  ctx.globalAlpha = alpha;
  setShadow(ctx, lift);
  ctx.drawImage(img, -dw * ax, -dh * ay, dw, dh);
  if (over && overAlpha > 0.01) {
    // cross-fade to a pre-tinted copy (canvas filters are far too slow to run per frame)
    ctx.shadowColor = 'transparent';
    ctx.globalAlpha = alpha * overAlpha;
    ctx.drawImage(over, -dw * ax, -dh * ay, dw, dh);
  }
  ctx.restore();
}

/** A filtered copy of a cut-out, made once. */
export function tinted(img, filter) {
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const x = c.getContext('2d');
  x.filter = filter;
  x.drawImage(img, 0, 0);
  return c;
}

// ---------- paper shapes ----------
export function pathOf(pts) {
  const p = new Path2D();
  pts.forEach(([x, y], i) => (i ? p.lineTo(x, y) : p.moveTo(x, y)));
  p.closePath();
  return p;
}

/** A piece of painted cardboard: shadow, raw kraft rim, painted face. */
export function paper(ctx, pts, o = {}) {
  const { fill = '#fff', rim = 4, rimColor = KRAFT, lift = 0.6, alpha = 1, stripes = null } = o;
  if (alpha <= 0 || pts.length < 3) return;
  const path = pathOf(pts);
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.lineJoin = 'round';
  setShadow(ctx, lift);
  ctx.fillStyle = rim > 0 ? rimColor : fill;
  ctx.fill(path);
  ctx.shadowColor = 'transparent';
  if (rim > 0) {
    ctx.strokeStyle = rimColor; ctx.lineWidth = rim * 2;
    ctx.stroke(path);
    ctx.fillStyle = fill;
    ctx.fill(path);
  }
  if (stripes) {
    ctx.clip(path);
    const [x0, x1, y0, y1] = bounds(pts);
    const sw = (x1 - x0) / stripes.length;
    stripes.forEach((c, i) => { ctx.fillStyle = c; ctx.fillRect(x0 + i * sw - 1, y0, sw + 2, y1 - y0); });
  }
  ctx.restore();
}

export function bounds(pts) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  return [x0, x1, y0, y1];
}

/** Move / rotate / scale a point list around the origin, then place it. */
export function place(pts, { x = 0, y = 0, rot = 0, s = 1, sx = 1, sy = 1 } = {}) {
  const c = Math.cos(rad(rot)), n = Math.sin(rad(rot));
  return pts.map(([px, py]) => {
    const qx = px * s * sx, qy = py * s * sy;
    return [x + qx * c - qy * n, y + qx * n + qy * c];
  });
}

/** Scissor-cut rectangle centred on the origin: corners never quite square. */
export function rectPts(w, h, seed = 1, j = 4) {
  const hw = w / 2, hh = h / 2;
  return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([x, y], i) => [x + hs(seed, i) * j, y + hs(seed, i + 9) * j]);
}

export function circlePts(r, seed = 1, j = 0.012, n = 56) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const rr = r * (1 + hs(seed, i) * j);
    out.push([Math.cos(a) * rr, Math.sin(a) * rr]);
  }
  return out;
}

export function starPts(r1, r2, n = 5, seed = 1, j = 0.06) {
  const out = [];
  for (let i = 0; i < n * 2; i++) {
    const a = (i / (n * 2)) * Math.PI * 2 - Math.PI / 2;
    const r = (i % 2 ? r2 : r1) * (1 + hs(seed, i) * j);
    out.push([Math.cos(a) * r, Math.sin(a) * r]);
  }
  return out;
}

/** Thick ribbon following a centre-line function p(s) → [x, y]. */
export function ribbonPts(p, s0, s1, th, step = 6, taper = 0) {
  if (s1 - s0 < 1) return [];
  const left = [], right = [];
  const n = Math.max(2, Math.ceil((s1 - s0) / step));
  for (let i = 0; i <= n; i++) {
    const s = lerp(s0, s1, i / n);
    const [x, y] = p(s);
    const [xa, ya] = p(s - 1), [xb, yb] = p(s + 1);
    let tx = xb - xa, ty = yb - ya;
    const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
    const half = (th / 2) * (taper ? lerp(1 - taper, 1, i / n) : 1);
    left.push([x - ty * half, y + tx * half]);
    right.push([x + ty * half, y - tx * half]);
  }
  return left.concat(right.reverse());
}

/** Straight strip between two points, optionally tapered and scissor-wobbled. */
export function stripPts(x0, y0, x1, y1, w0, w1 = w0, seed = 1, j = 2) {
  let nx = -(y1 - y0), ny = x1 - x0;
  const l = Math.hypot(nx, ny) || 1; nx /= l; ny /= l;
  return [
    [x0 + nx * w0 / 2, y0 + ny * w0 / 2], [x1 + nx * w1 / 2, y1 + ny * w1 / 2],
    [x1 - nx * w1 / 2, y1 - ny * w1 / 2], [x0 - nx * w0 / 2, y0 - ny * w0 / 2],
  ].map(([x, y], i) => [x + hs(seed, i) * j, y + hs(seed, i + 5) * j]);
}

/** Sine wave centre-line travelling along a direction. */
export function waveLine(x0, y0, angDeg, wavelength, amp, phase = 0) {
  const c = Math.cos(rad(angDeg)), n = Math.sin(rad(angDeg));
  return (s) => {
    const o = amp * Math.sin((2 * Math.PI * s) / wavelength + phase);
    return [x0 + c * s - n * o, y0 + n * s + c * o];
  };
}

/** Paper arrow head pointing along angDeg, tip at the origin. */
export function arrowPts(size, seed = 1) {
  return [[0, 0], [-size * 1.15, -size * 0.72], [-size * 0.8, 0], [-size * 1.15, size * 0.72]]
    .map(([x, y], i) => [x + hs(seed, i) * 1.5, y + hs(seed, i + 4) * 1.5]);
}

export function string(ctx, x, y0, y1, alpha = 1) {
  if (alpha <= 0) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  setShadow(ctx, 0.5);
  ctx.strokeStyle = '#efe6d2'; ctx.lineWidth = 4; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
  ctx.restore();
}

// ---------- lettering ----------
export const FONT = 'Ubuntu, "Ubuntu Sans", "Noto Sans", sans-serif';
export const fontOf = (size, weight = 800) => `${weight} ${size}px ${FONT}`;

export function textWidth(ctx, text, size, weight = 800) {
  ctx.save(); ctx.font = fontOf(size, weight);
  const w = ctx.measureText(text).width;
  ctx.restore();
  return w;
}

/** A word on its own scrap of painted card. x,y is the centre. */
export function chip(ctx, text, o) {
  const { x, y, size = 64, fill = '#fff6df', color = INK, rot = 0, seed = 1, s = 1, lift = 0.7, padX = 0.34, alpha = 1, stripes = null, outline = null } = o;
  if (s <= 0.01 || alpha <= 0) return 0;
  const tw = textWidth(ctx, text, size);
  const w = tw + size * padX * 2, h = size * 1.42;
  paper(ctx, place(rectPts(w, h, seed, size * 0.06), { x, y, rot, s }), { fill, lift, rim: Math.max(3, size * 0.055), alpha, stripes });
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y); ctx.rotate(rad(rot)); ctx.scale(s, s);
  ctx.font = fontOf(size); ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  const m = ctx.measureText('H');
  const base = (m.actualBoundingBoxAscent) / 2;
  if (outline) { ctx.strokeStyle = outline; ctx.lineWidth = size * 0.16; ctx.lineJoin = 'round'; ctx.strokeText(text, 0, base); }
  ctx.fillStyle = color;
  ctx.fillText(text, 0, base);
  ctx.restore();
  return w;
}

export async function loadImages(names, base = 'fig/') {
  const out = {};
  await Promise.all(names.map(async (n) => {
    const img = new Image();
    img.src = `${base}${n}.png`;
    try {
      await img.decode();
      out[n] = img;
    } catch {
      // not generated yet: an invisible stand-in keeps the rest of the film drawable
      console.warn('missing figure', n);
      const c = document.createElement('canvas');
      c.width = c.height = 4;
      out[n] = c;
    }
  }));
  return out;
}
