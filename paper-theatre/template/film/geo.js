// Maps drawn from real coordinates (Natural Earth via tools/geodata.py → geodata.js), so every pin, route, area and
// line sits where it belongs. One projection for everything: equirectangular with x scaled by the cosine of the
// window's middle latitude. The static map is painted once into an offscreen canvas; a view (centre, zoom) places it
// on the stage and pt([lon, lat]) gives the screen point. Lines read off published figures come from tools/georef.py.
import { W, KRAFT, hash, lerp, ease, seg, paper, place, rectPts, circlePts, ribbonPts } from './engine.js';
import { COL } from './stage.js';
import { MAP } from './config.js';
import { BOX, LAND, LAKES, COUNTRY, RIVERS } from './geodata.js';

const KX = Math.cos((((BOX[1] + BOX[3]) / 2) * Math.PI) / 180);
const BASE = 120;   // px per degree of latitude in the painted canvas
const toBase = ([lon, lat]) => [(lon - BOX[0]) * KX * BASE, (BOX[3] - lat) * BASE];
const BW = Math.ceil((BOX[2] - BOX[0]) * KX * BASE), BH = Math.ceil((BOX[3] - BOX[1]) * BASE);

function basePath(ctx, pts) {
  ctx.beginPath();
  pts.forEach((p, i) => { const [x, y] = toBase(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.closePath();
}

function river(ctx, line, th) {
  const pts = line.map(toBase);
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = lens[lens.length - 1];
  const at = (s) => {
    s = Math.max(0, Math.min(total, s));
    let i = 1;
    while (i < lens.length - 1 && lens[i] < s) i++;
    const f = (s - lens[i - 1]) / Math.max(1e-6, lens[i] - lens[i - 1]);
    return [lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)];
  };
  paper(ctx, ribbonPts(at, 0, total, th, 6, 0.6), { fill: MAP.water, rim: 0, lift: 0.1 });
}

const painted = {};
/** The static map: sea, land with a cut-paper coast, patches on the land, lakes, rivers, the reference border. */
function paintMap(tex, border) {
  const c = document.createElement('canvas');
  c.width = BW; c.height = BH;
  const ctx = c.getContext('2d');
  ctx.fillStyle = MAP.sea;
  ctx.fillRect(0, 0, BW, BH);
  if (tex) { ctx.save(); ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.3; ctx.drawImage(tex.brush, 0, 0, BW, BH); ctx.restore(); }
  ctx.save();
  ctx.lineJoin = 'round';
  for (const r of LAND) { basePath(ctx, r); ctx.strokeStyle = KRAFT; ctx.lineWidth = 7; ctx.stroke(); }
  for (const r of LAND) { basePath(ctx, r); ctx.fillStyle = MAP.land; ctx.fill(); }
  ctx.restore();
  ctx.save();
  ctx.beginPath();
  for (const r of LAND) r.forEach((p, i) => { const [x, y] = toBase(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.clip();
  for (let i = 0; i < 700; i++) {
    const x = hash(i, 71) * BW, y = hash(i, 72) * BH, r = 7 + hash(i, 73) * 14;
    paper(ctx, place(circlePts(r, i, 0.22, 12), { x, y, sx: 1.4 }), { fill: hash(i, 74) > 0.5 ? MAP.land2 : MAP.land3, rim: 0, lift: 0, alpha: 0.7 });
  }
  if (tex) { ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.35; ctx.drawImage(tex.brush, 0, 0, BW, BH); }
  ctx.restore();
  for (const r of LAKES) { ctx.save(); basePath(ctx, r); ctx.strokeStyle = KRAFT; ctx.lineWidth = 3; ctx.stroke(); ctx.fillStyle = MAP.sea; ctx.fill(); ctx.restore(); }
  for (const ls of Object.values(RIVERS)) ls.forEach((l) => river(ctx, l, 4));
  if (border && COUNTRY.length) {
    ctx.save(); basePath(ctx, COUNTRY); ctx.setLineDash([10, 7]); ctx.strokeStyle = MAP.border; ctx.lineWidth = 3; ctx.stroke(); ctx.restore();
  }
  return c;
}

/**
 * A view of the map on a card: centre (lon, lat), zoom (px per degree of latitude on the stage), where it sits.
 * Returns { draw(ctx), pt([lon, lat]) → [x, y], clip(ctx, fn), k }. Keep every view inside BOX (film.json "map").
 */
export function mapView(tex, o) {
  const border = o.border ?? true;
  const key = border ? 'b' : 'n';
  if (!painted[key]) painted[key] = paintMap(tex, border);
  const { lon, lat, zoom, x = W / 2, y = 480, w = 1560, h = 880, rot = 0 } = o;
  const k = zoom / BASE;
  const [cx, cy] = toBase([lon, lat]);
  const r = (rot * Math.PI) / 180;
  const pt = ([lo, la]) => {
    const [bx, by] = toBase([lo, la]);
    const dx = (bx - cx) * k, dy = (by - cy) * k;
    return [x + dx * Math.cos(r) - dy * Math.sin(r), y + dx * Math.sin(r) + dy * Math.cos(r)];
  };
  const frameOf = (inset = 0) => place(rectPts(w - inset, h - inset, 7, 6), { x, y, rot });
  const pathFrame = (ctx, f) => { ctx.beginPath(); f.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py))); ctx.closePath(); };
  function draw(ctx) {
    const frame = frameOf();
    paper(ctx, frame, { fill: MAP.sea, rim: 8, rimColor: KRAFT, lift: 1.4 });
    ctx.save();
    pathFrame(ctx, frame); ctx.clip();
    ctx.translate(x, y); ctx.rotate(r); ctx.scale(k, k); ctx.translate(-cx, -cy);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(painted[key], 0, 0);
    ctx.restore();
  }
  /** Run fn with drawing clipped to the map card (areas and lines that run past its edge). */
  function clip(ctx, fn) {
    ctx.save(); pathFrame(ctx, frameOf(16)); ctx.clip(); fn(); ctx.restore();
  }
  return { draw, pt, clip, k };
}

/** An area over the map (ice, sea, territory): a filled lon/lat polygon with optional holes, faded in by k. */
export function areaOn(ctx, v, poly, k = 1, o = {}) {
  if (k <= 0.01) return;
  const { fill = COL.cream, edge = null, alpha = 0.8, holes = [] } = o;
  v.clip(ctx, () => {
    ctx.save(); ctx.globalAlpha = alpha * k;
    ctx.beginPath();
    for (const ring of [poly, ...holes]) {
      ring.forEach((p, i) => { const [x, y] = v.pt(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.closePath();
    }
    if (edge) { ctx.lineJoin = 'round'; ctx.strokeStyle = edge; ctx.lineWidth = 8; ctx.stroke(); }
    ctx.fillStyle = fill; ctx.fill('evenodd');
    ctx.restore();
  });
}

/** A line along a lon/lat polyline (a limit, a front, a border), drawn from 0 to 1 over [t0, t0 + d]. */
export function lineOn(ctx, S, v, line, t0, d = 1.4, o = {}) {
  if (S < t0) return;
  const { fill = COL.red, th = 9, dash = 0, alpha = 1 } = o;
  const pts = line.map((p) => v.pt(p));
  const n = Math.max(2, Math.ceil(pts.length * ease.inOut(seg(S, t0, t0 + d))));
  v.clip(ctx, () => {
    ctx.save(); ctx.globalAlpha = alpha; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    if (dash) ctx.setLineDash([dash, dash * 0.6]);
    for (const [c, wd] of [[COL.cream, th + 6], [fill, th]]) {
      ctx.strokeStyle = c; ctx.lineWidth = wd;
      ctx.beginPath(); pts.slice(0, n).forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py))); ctx.stroke();
    }
    ctx.restore();
  });
}

/** Great-circle distance in km: distance labels are computed from the coordinates, not typed. */
export function km([lo1, la1], [lo2, la2]) {
  const r = Math.PI / 180;
  const a = Math.sin(((la2 - la1) * r) / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(((lo2 - lo1) * r) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

/** A camera over the map: keys [[t, view]]; at time t it starts moving to view (lon, lat, zoom) over view.dur s. */
export function camera(S, keys) {
  let i = 0;
  for (let j = 0; j < keys.length; j++) if (S >= keys[j][0]) i = j;
  if (i === 0) return keys[0][1];
  const [t, v1] = keys[i], v0 = keys[i - 1][1];
  const q = ease.inOut(Math.min(1, (S - t) / (v1.dur ?? 1.4)));
  return { lon: lerp(v0.lon, v1.lon, q), lat: lerp(v0.lat, v1.lat, q), zoom: Math.exp(lerp(Math.log(v0.zoom), Math.log(v1.zoom), q)) };
}
