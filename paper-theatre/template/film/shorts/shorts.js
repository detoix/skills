// Vertical shorts, 1080×1920: one createShort per film, a composition per short (film.json -> shorts).
// The voice, music and timeline come from tools/build_shorts.py (film/short_<name>/timeline.json): word times
// in tl.lines[].words, the closing card from tl.outro_start. Compose for portrait: figures and maps fill the
// frame; text stays clear of the platform's interface (see references/shorts.md).
import { stepped, boilStep } from '../engine.js';

export const W = 1080, H = 1920;
export const FONTS = [];   // [family, url relative to film/] for type the shorts bring along, loaded before the first frame
export const FIGURES = {
  // name: ['figure', ...],   the cut-outs each short draws, from film/fig/
};

/** Sound cues of a short for tools/build_shorts.py: [{ t, name, gain }], like a scene's soundCues. */
export function soundCues(tl) {
  return [];
}

export function createShort(name, tl, img, tex) {
  return {
    draw(ctx, t) {
      const S = stepped(t), b = boilStep(S);
      ctx.reset();
      ctx.fillStyle = '#2c2118'; ctx.fillRect(0, 0, W, H);
      // draw the composition of short `name` at stepped time S (boil step b)
    },
  };
}
