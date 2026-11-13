// Przejścia: dobierz je do świata filmu, usuń niepasujące, dopisz własne (references/visuals.md). Każde zasłania cały kadr dokładnie w T (wtedy podmienia się plan),
// a potem odsłania nowy plan. Czysta funkcja czasu S, jak reszta sceny.
//   fala      woda z pianą i ławicą śledzi, wznosi się od dołu i wychodzi górą
//   zagiel    pasiasty żagiel przechodzi przez scenę od lewej do prawej
//   pergamin  arkusz rozwija się z rolki od góry; zwija się z powrotem
//   cegly     mur układa się od dołu; potem cegły spadają od góry
//   plomienie papierowy ogień wznosi się od dołu i opada
//   pieczec   woskowa pieczęć rośnie ze środka; odsłania okrągła dziura
//   kurtyna   teatralna kurtyna z lambrekinem zasuwa się z obu stron
//   deska     deska na sznurkach spada z góry ze sprężystym lądowaniem
//   paski     paski papieru przesuwają się przez kadr; neutralne, do filmów i cięć bez własnego gestu
import { W, H, KRAFT, INK, clamp, lerp, seg, ease, hash, hs, paper, place, rectPts, circlePts, cut, fontOf } from './engine.js';
import { COL, hang, strings, withCard, cardFace, wipe } from './stage.js';

/** Czas domknięcia i otwarcia dla krótkich cięć w scenie (s). */
const DEFAULT = { close: 0.42, open: 0.48, hold: 0 };

/** Dźwięk przejścia: nazwy z tools/build_audio.py make_sfx. add(t, nazwa, głośność). */
export function transitionSound(add, tr) {
  const { T, kind, close = DEFAULT.close, hold = 0, open = DEFAULT.open } = tr;
  const t0 = T - hold - close;
  const big = hold > 0 ? 1 : 0.6;
  if (kind === 'fala') { add(t0, 'whoosh', 0.8 * big); add(T + 0.05, 'swish', 0.5 * big); }
  if (kind === 'zagiel') { add(t0, 'whoosh', 0.7 * big); add(t0 + close * 0.7, 'swish', 0.5 * big); add(T + open * 0.2, 'whoosh', 0.5 * big); }
  if (kind === 'pergamin') { add(t0, 'slide_down', 0.6 * big); add(T + 0.02, 'swish', 0.5 * big); }
  if (kind === 'cegly') {
    const n = hold > 0 ? 7 : 4;
    for (let i = 0; i < n; i++) add(t0 + (i / n) * close, 'thud_soft', 0.35 * big);
    add(T + 0.04, 'clay', 0.6 * big); add(T + open * 0.4, 'thud_soft', 0.4 * big);
  }
  if (kind === 'plomienie') { add(t0, 'rise', 0.8 * big); add(t0 + close * 0.4, 'whoosh', 0.5 * big); add(T + 0.05, 'swish', 0.4 * big); }
  if (kind === 'pieczec') { add(t0 + close * 0.55, 'stamp', 0.8 * big); add(T + 0.03, 'swish', 0.4 * big); }
  if (kind === 'kurtyna') { add(t0, 'slide_down', 0.7 * big); add(t0 + close * 0.9, 'thud_soft', 0.4 * big); add(T + 0.02, 'whoosh', 0.5 * big); }
  if (kind === 'deska') { add(t0, 'slide_down', 0.5 * big); add(t0 + close * 0.85, 'thud_soft', 0.6 * big); add(T + 0.03, 'swish', 0.4 * big); }
  if (kind === 'paski') { add(t0, 'swish', 0.5 * big); add(T + 0.03, 'swish', 0.4 * big); }
}

/** Rysuje przejście. tr = { T, kind, seed, close, hold, open, title, sub }. */
export function transition(ctx, S, tr, tex, img) {
  const { T, kind, seed = 1, close = DEFAULT.close, hold = 0, open = DEFAULT.open } = tr;
  const t0 = T - hold - close;
  if (S < t0 || S > T + open) return;
  const p = ease.inOut(seg(S, t0, t0 + close));
  const q = ease.inOut(seg(S, T, T + open));
  ctx.save();
  ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ({ fala, zagiel, pergamin, cegly, plomienie, pieczec, kurtyna, deska, paski }[kind])(ctx, S, p, q, seed, tex, img, tr);
  ctx.restore();
  if (tr.title) chapterCard(ctx, S, tr, t0 + close * 0.55);
}

// Karta rozdziału: spada na sznurkach, gdy przejście się domyka, wylatuje przy otwarciu.
function chapterCard(ctx, S, tr, t0) {
  const b = Math.floor(S * 7.5 + 1e-4);
  const c = hang(S, b, { x: 960, y: 470, w: 1240, h: 300, t0, t1: tr.T - 0.1, seed: tr.seed, swing: 1.4 });
  if (!c) return;
  strings(ctx, c);
  withCard(ctx, c, () => {
    cardFace(ctx, c, COL.cream, tr.seed + 7, 7);
    paper(ctx, rectPts(c.w - 44, c.h - 44, tr.seed + 8, 3), { fill: COL.cream, rim: 2, rimColor: COL.terracotta, lift: 0 });
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    if (tr.sub) { ctx.font = fontOf(36); ctx.fillStyle = COL.kraftDark; ctx.fillText(tr.sub, 0, -82); }
    let size = 92;
    ctx.font = fontOf(size);
    while (ctx.measureText(tr.title).width > c.w - 110) { size -= 4; ctx.font = fontOf(size); }
    ctx.fillStyle = COL.terracotta; ctx.fillText(tr.title, 0, tr.sub ? 22 : 6);
  });
}

function brush(ctx, tex, alpha = 0.4) {
  if (!tex) return;
  ctx.save(); ctx.clip(); ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = alpha; ctx.drawImage(tex.brush, 0, 0, W, H); ctx.restore();
}

// ---------- fala ----------
function waveEdge(y, amp, wl, ph, x0 = -60, x1 = W + 60) {
  const pts = [];
  for (let x = x0; x <= x1; x += 26) pts.push([x, y + amp * Math.sin(x / wl + ph) + amp * 0.35 * Math.sin(x / (wl * 0.37) + ph * 1.7)]);
  return pts;
}
function fala(ctx, S, p, q, seed, tex, img) {
  const roll = Math.floor(S * 15) / 15 * 2.4;
  // górna krawędź podnosi się aż za kadr, dolna rusza dopiero po T
  const top = lerp(H + 160, -240, p);
  const bottom = lerp(H + 260, -320, q);
  const layers = [[COL.egyptian, 0, 26, 110, 0], [COL.blue, 70, 22, 90, 1.7], [COL.night2, 170, 18, 130, 3.1]];
  layers.forEach(([fill, off, amp, wl, ph], i) => {
    const up = waveEdge(top + off, amp, wl, ph + roll + seed);
    const lowY = Math.max(bottom + off * 0.6, -400);
    const low = q > 0 ? waveEdge(lowY, amp, wl, ph - roll + seed).reverse() : [[W + 80, H + 300], [-80, H + 300]];
    const poly = [...up, ...low];
    paper(ctx, poly, { fill, rim: i === 0 ? 7 : 4, rimColor: i === 0 ? '#e9efee' : '#c8d3d8', lift: 0.8 });
    ctx.save(); ctx.beginPath(); poly.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); brush(ctx, tex, 0.35); ctx.restore();
  });
  // ławica śledzi w środku wody
  if (img && img.herring) {
    const clipTop = top + 40, clipBottom = bottom;
    for (let i = 0; i < 26; i++) {
      const dir = i % 3 === 0 ? -1 : 1;
      const speed = 620 + hash(i + seed, 3) * 520;
      const span = W + 700;
      const x = ((hash(i + seed, 4) * span + dir * S * speed) % span + span) % span - 350;
      const y = 60 + hash(i + seed, 5) * (H - 120) + Math.sin(S * 3 + i) * 10;
      if (y < clipTop + 50 || y > clipBottom - 40) continue;
      cut(ctx, img.herring, { x, y, w: 150 + hash(i, 6) * 120, ay: 0.5, flip: dir > 0, lift: 0.5, rot: Math.sin(S * 4 + i) * 3 });
    }
  }
}

// ---------- żagiel ----------
function zagiel(ctx, S, p, q, seed, tex) {
  const belly = 170;
  const lead = lerp(-belly - 40, W + belly + 60, p);      // prawa krawędź idzie w prawo aż za kadr
  const tail = lerp(-belly - 60, W + belly + 60, q);      // lewa krawędź rusza po T
  const edge = (X, sign) => {
    const pts = [];
    for (let y = -40; y <= H + 40; y += 30) {
      const u = (y + 40) / (H + 80);
      pts.push([X + sign * belly * Math.sin(Math.PI * u) + Math.sin(y / 70 + S * 9) * 5, y]);
    }
    return pts;
  };
  const right = edge(lead, 1), left = edge(tail, 1).reverse();
  const poly = q > 0 ? [...right, ...left] : [...right, [-300, H + 60], [-300, -60]];
  paper(ctx, poly, { fill: COL.cream, rim: 8, rimColor: KRAFT, lift: 1.8 });
  ctx.save();
  ctx.beginPath(); poly.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.clip();
  // pasy jadą razem z żaglem; lekkie wybrzuszenie jak na kodze
  const sw = 230, shift = lerp(-700, 500, p) + lerp(0, 700, q);
  for (let k = -3; k < 13; k += 2) {
    const x0 = shift + k * sw;
    ctx.beginPath();
    for (let y = -40; y <= H + 40; y += 30) { const u = (y + 40) / (H + 80); ctx.lineTo(x0 + 90 * Math.sin(Math.PI * u), y); }
    for (let y = H + 40; y >= -40; y -= 30) { const u = (y + 40) / (H + 80); ctx.lineTo(x0 + sw + 90 * Math.sin(Math.PI * u), y); }
    ctx.closePath(); ctx.fillStyle = COL.terracotta; ctx.fill();
  }
  // szwy
  ctx.strokeStyle = 'rgba(42,32,25,0.28)'; ctx.lineWidth = 3; ctx.setLineDash([16, 10]);
  for (let y = 120; y < H; y += 210) { ctx.beginPath(); ctx.moveTo(-100, y); ctx.lineTo(W + 100, y); ctx.stroke(); }
  ctx.setLineDash([]);
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.4; if (tex) ctx.drawImage(tex.brush, 0, 0, W, H);
  ctx.restore();
  // reja u góry
  paper(ctx, place(rectPts(W + 300, 46, seed, 3), { x: W / 2 - (1 - p) * (W + 400) + q * (W + 400), y: 22 }), { fill: COL.kraftDark, rim: 4, rimColor: '#3a2818', lift: 1.2 });
}

// ---------- pergamin ----------
function pergamin(ctx, S, p, q, seed, tex) {
  const y = lerp(-90, H + 110, p) - lerp(0, H + 330, q);    // krawędź z rolką: w dół, potem z powrotem w górę
  if (y < -100) return;
  const poly = [[-30, -100], [W + 30, -100], [W + 30, y], [-30, y]];
  paper(ctx, poly, { fill: '#ecdfc0', rim: 0, lift: 1.4 });
  ctx.save();
  ctx.beginPath(); ctx.rect(-30, -40, W + 60, y + 40); ctx.clip();
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.5; if (tex) ctx.drawImage(tex.brush, 0, 0, W, H);
  ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 0.55;
  // linie pisma markerem, bez prawdziwych liter
  ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.lineCap = 'round';
  for (let r = 0; r < 9; r++) {
    const ly = 110 + r * 100;
    ctx.beginPath();
    for (let x = 180; x < W - 180 - hash(r, seed) * 300; x += 22) { const yy = ly + Math.sin(x / 19 + r * 2) * 9 + hs(r * 31 + x, seed) * 4; x === 180 ? ctx.moveTo(x, yy) : ctx.lineTo(x, yy); }
    ctx.stroke();
  }
  ctx.restore();
  // rolka na krawędzi
  const g = ctx.createLinearGradient(0, y - 46, 0, y + 46);
  g.addColorStop(0, '#b89a6b'); g.addColorStop(0.45, '#f6ecd4'); g.addColorStop(1, '#a58657');
  ctx.save();
  ctx.fillStyle = g; ctx.strokeStyle = KRAFT; ctx.lineWidth = 6;
  ctx.shadowColor = 'rgba(20,12,6,0.4)'; ctx.shadowBlur = 16; ctx.shadowOffsetY = 12;
  ctx.fillRect(-30, y - 44, W + 60, 88);
  ctx.shadowColor = 'transparent'; ctx.strokeRect(-30, y - 44, W + 60, 88);
  ctx.restore();
}

// ---------- cegły ----------
const BW = 168, BH = 74;
const REDS = ['#9c3f2a', '#a8482f', '#8e3a26', '#b0533a', '#973c28'];
function cegly(ctx, S, p, q, seed, tex) {
  const rows = Math.ceil(H / BH) + 1;
  const pRaw = p, qRaw = q;
  // zaprawa pod ułożonymi rzędami
  const filled = pRaw * rows;
  const fallen = qRaw * rows * 1.05;
  ctx.fillStyle = '#cdbb98';
  const mortarTop = H - Math.floor(filled) * BH + 10;
  const mortarBottom = H + 40;
  if (q <= 0) ctx.fillRect(0, Math.max(-20, mortarTop), W, mortarBottom - mortarTop);
  for (let r = 0; r < rows; r++) {
    const y = H - (r + 1) * BH;
    const off = r % 2 ? -BW / 2 : 0;
    for (let c = 0; c < 13; c++) {
      const x = off + c * BW;
      const jitter = hash(r * 17 + c, seed);
      // układanie: rząd po rzędzie, każda cegła leci z góry
      const tIn = (r + jitter * 1.6) / (rows + 3);
      const kIn = clamp((pRaw - tIn) * (rows + 3) / 1.3);
      if (kIn <= 0) continue;
      const dy = (1 - ease.out(kIn)) * -240;
      // rozsypka: od góry, cegły spadają
      const tOut = ((rows - 1 - r) + jitter * 2) / (rows + 2) * 0.55;
      const kOut = clamp((qRaw - tOut) / (1 - tOut));
      if (kOut >= 1) continue;
      const fall = kOut * kOut * (H + 260);
      const rot = kOut * (hs(r + c * 3, seed) * 70);
      ctx.save();
      ctx.translate(x + BW / 2 + hs(c, r) * 2, y + BH / 2 + dy + fall);
      ctx.rotate(rot * Math.PI / 180);
      ctx.fillStyle = REDS[(r * 7 + c * 3 + seed) % REDS.length];
      ctx.strokeStyle = '#e6d9bd'; ctx.lineWidth = 5;
      if (kOut > 0) { ctx.shadowColor = 'rgba(20,12,6,0.45)'; ctx.shadowBlur = 8; ctx.shadowOffsetY = 8; }
      ctx.fillRect(-BW / 2, -BH / 2, BW, BH);
      ctx.shadowColor = 'transparent';
      ctx.strokeRect(-BW / 2, -BH / 2, BW, BH);
      ctx.restore();
    }
  }
}

// ---------- płomienie ----------
function plomienie(ctx, S, p, q, seed, tex) {
  const flick = Math.floor(S * 15);
  const COLS = ['#6f2c1d', '#b8432f', '#e0702f', '#f2a83b', '#f7d36b'];
  const level = lerp(-60, H + 340, p) - lerp(0, H + 520, q);   // wysokość ognia od dołu
  COLS.forEach((fill, l) => {
    const h = level - l * 110;
    if (h <= -40) return;
    const pts = [[-60, H + 60]];
    const n = 26;
    for (let i = 0; i <= n; i++) {
      const x = -60 + (i / n) * (W + 120);
      const tip = i % 2 === 0;
      const v = tip ? 80 + 170 * hash(i * 13 + l * 5 + seed, flick) : -30 + 60 * hash(i * 7 + l, flick);
      pts.push([x + hs(i + l, flick) * 16, H - h - v]);
    }
    pts.push([W + 60, H + 60]);
    paper(ctx, pts, { fill, rim: l === 0 ? 6 : 0, rimColor: '#3a1a10', lift: l === 0 ? 1 : 0 });
  });
}

// ---------- pieczęć ----------
function sealPts(r, seed) {
  const pts = [];
  const n = 96;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const k = 1 + 0.035 * Math.sin(a * 7 + seed) + 0.02 * Math.sin(a * 17 + seed * 3) + 0.012 * hs(i, seed);
    pts.push([W / 2 + Math.cos(a) * r * k, H / 2 + Math.sin(a) * r * k]);
  }
  return pts;
}
function pieczec(ctx, S, p, q, seed, tex) {
  const R = Math.hypot(W, H) / 2 + 170;
  const r = lerp(0, R, p);
  const hole = lerp(0, R + 40, q);
  const RED = '#8e2a1e';
  ctx.save();
  ctx.beginPath();
  sealPts(r, seed).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath();
  if (hole > 1) { const h = sealPts(hole, seed + 3); h.reverse().forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); }
  ctx.fillStyle = RED;
  ctx.shadowColor = 'rgba(20,10,5,0.55)'; ctx.shadowBlur = 24; ctx.shadowOffsetY = 12;
  ctx.fill('evenodd');
  ctx.shadowColor = 'transparent';
  ctx.clip('evenodd');
  // wytłoczone pierścienie i kropki: bez liter
  const ringR = Math.min(r, 470);
  if (ringR > 40) {
    ctx.strokeStyle = '#6f1f15'; ctx.lineWidth = 16;
    ctx.beginPath(); ctx.arc(W / 2 + 4, H / 2 + 5, ringR * 0.86, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = '#b34a38'; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.arc(W / 2 - 3, H / 2 - 3, ringR * 0.86, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2;
      ctx.fillStyle = '#b34a38';
      ctx.beginPath(); ctx.arc(W / 2 + Math.cos(a) * ringR * 0.72, H / 2 + Math.sin(a) * ringR * 0.72, 9, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.35; if (tex) ctx.drawImage(tex.brush, 0, 0, W, H);
  ctx.restore();
}

// ---------- kurtyna ----------
const FOLDS = ['#8e2f22', '#a43a2a', '#7a281d', '#993426'];
function curtainSide(ctx, S, width, side, seed) {
  // side: -1 lewa (rośnie w prawo), 1 prawa (rośnie w lewo)
  const n = 10;
  const fw = (W / 2 + 80) / n;
  const k = width / (W / 2 + 80);
  for (let i = n - 1; i >= 0; i--) {
    const x0 = i * fw * k - 18, x1 = (i + 1) * fw * k + 18;
    const pts = [];
    for (let y = -30; y <= H + 30; y += 60) pts.push([x0 + Math.sin(y / 170 + i * 1.3 + seed) * 7, y]);
    for (let y = H + 30; y >= -30; y -= 60) pts.push([x1 + Math.sin(y / 170 + (i + 1) * 1.3 + seed) * 7, y]);
    const q = side < 0 ? pts : pts.map(([x, y]) => [W - x, y]);
    paper(ctx, q, { fill: FOLDS[(i + seed) % FOLDS.length], rim: i === n - 1 ? 5 : 0, rimColor: '#e8b23a', lift: i === n - 1 ? 1.3 : 0.2 });
  }
}
function kurtyna(ctx, S, p, q, seed) {
  const full = W / 2 + 80;
  const width = lerp(0, full, p) * (1 - q);
  if (width > 1) {
    curtainSide(ctx, S, width, -1, seed);
    curtainSide(ctx, S, width, 1, seed + 1);
  }
  // lambrekin z frędzlą: opada z zamknięciem, unosi się z otwarciem
  const v = 120 * ease.out(Math.min(1, p * 2)) * (1 - ease.in(Math.min(1, q * 1.4)));
  if (v > 1) {
    const pts = [[-20, -20], [W + 20, -20]];
    for (let x = W + 20; x >= -20; x -= 40) pts.push([x, v - 14 + 22 * Math.abs(Math.sin((x / 160) * Math.PI))]);
    paper(ctx, pts, { fill: '#7a281d', rim: 6, rimColor: '#e8b23a', lift: 1.4 });
  }
}

// ---------- paski ----------
// Paski papieru (stage.js → wipe); przy karcie rozdziału stoją zamknięte przez cały czas jej wiszenia.
function paski(ctx, S, p, q, seed, tex, img, tr) {
  const { T, hold = 0, close = DEFAULT.close, open = DEFAULT.open } = tr;
  const covered = T - hold;
  // Map the two durations independently onto wipe's complete close/open cycle.
  const time = S < covered
    ? lerp(-1.05, 0, seg(S, covered - close, covered))
    : S <= T ? 0 : lerp(0, 1.3, seg(S, T, T + open));
  wipe(ctx, time, 0, seed, tex, 1);
}

// ---------- deska ----------
function deska(ctx, S, p, q, seed, tex, img, tr) {
  const up = ease.back(p);
  const y = lerp(-H - 120, -24, up) - ease.in(q) * (H + 300);
  const poly = place(rectPts(W + 90, H + 90, seed, 6), { x: W / 2, y: y + H / 2 + 30 });
  paper(ctx, poly, { fill: '#a97f53', rim: 9, rimColor: '#5a3e28', lift: 1.8 });
  ctx.save();
  ctx.beginPath(); poly.forEach(([x, yy], k) => (k ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy))); ctx.closePath(); ctx.clip();
  ctx.strokeStyle = 'rgba(60,40,22,0.55)'; ctx.lineWidth = 4;
  for (let r = 1; r < 6; r++) { const ly = y + r * (H / 6) + 30; ctx.beginPath(); ctx.moveTo(-40, ly + hs(r, seed) * 5); ctx.lineTo(W + 40, ly - hs(r, seed) * 5); ctx.stroke(); }
  // ćwieki na końcach desek i wypalony znak kupiecki, inny przy każdym ziarnie
  ctx.fillStyle = '#3a2716';
  for (let r = 0; r < 6; r++) [84, W - 84].forEach((x, i) => { ctx.beginPath(); ctx.arc(x + hs(r + i * 7, seed) * 10, y + (r + 0.5) * (H / 6) + 30, 10, 0, 7); ctx.fill(); });
  ctx.save(); ctx.translate(W / 2, y + H / 2 + 30); ctx.rotate((hs(2, seed) * 4 * Math.PI) / 180);
  ctx.strokeStyle = 'rgba(44,27,14,0.82)'; ctx.lineWidth = 24; ctx.lineJoin = 'miter'; ctx.lineCap = 'butt';
  const side = hs(5, seed) > 0 ? 1 : -1;
  ctx.beginPath(); ctx.moveTo(0, 260); ctx.lineTo(0, -260); ctx.lineTo(side * -120, -130); ctx.lineTo(side * 100, -130);
  ctx.moveTo(-96, 260); ctx.lineTo(96, 260); ctx.moveTo(0, 40); ctx.lineTo(side * 110, 150); ctx.moveTo(0, 150); ctx.lineTo(side * -110, 40);
  ctx.stroke(); ctx.restore();
  ctx.globalCompositeOperation = 'multiply'; ctx.globalAlpha = 0.55; if (tex) ctx.drawImage(tex.brush, 0, 0, W, H);
  ctx.restore();
  // sznurki
  ctx.strokeStyle = '#efe6d2'; ctx.lineWidth = 5;
  [W * 0.28, W * 0.72].forEach((x) => { ctx.beginPath(); ctx.moveTo(x, -40); ctx.lineTo(x, y + 60); ctx.stroke(); });
}
