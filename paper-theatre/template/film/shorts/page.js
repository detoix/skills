// The page of a short for tools/render.mjs: the same API as the film (window.__info, __draw, __frame, __ready).
import { FPS, loadImages, makeTextures } from '../engine.js';
import { createShort, FIGURES, FONTS, W, H } from './shorts.js';

export async function boot(name) {
  if (!name) throw new Error('short.html needs ?name=<short>');
  const canvas = document.getElementById('c');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  for (const [family, url] of FONTS ?? []) document.fonts.add(await new FontFace(family, `url(${url})`).load());
  await document.fonts.ready;
  const tl = await (await fetch(`short_${name}/timeline.json`, { cache: 'no-store' })).json();
  const img = await loadImages(FIGURES[name] ?? []);
  const reel = createShort(name, tl, img, makeTextures());
  window.__info = { fps: FPS, frames: Math.round(tl.duration * FPS), duration: tl.duration, width: W, height: H };
  window.__draw = (t) => reel.draw(ctx, t);
  window.__frame = (i, type = 'image/png', quality = 0.95) => { reel.draw(ctx, i / FPS); return canvas.toDataURL(type, quality); };
  reel.draw(ctx, 0);
  window.__ready = true;
}
