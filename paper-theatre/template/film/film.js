// The whole film as one pure function of time: scenes in order, the timeline rail on the apron, paper grain on top.
// Cardboard pieces move on twos (15 holds a second) and boil 7.5 times a second.
// Scene k starts at a transition just before its first line; everything inside hangs off the narration.
import { stepped, boilStep } from './engine.js';
import { grain, makeRail } from './stage.js';
import { transition, transitionSound } from './transitions.js';
import * as s1 from './scenes/s1.js';
// import * as s2 from './scenes/s2.js';  // one module per scene, in order

const MODULES = [s1];

export const FIGURES = [...new Set(MODULES.flatMap((m) => m.FIGURES))];

/** Seconds between a scene's transition and its first line (keep in step with tools/build_audio.py WIPE_LEAD). */
export const WIPE_LEAD = 0.55;

// Zmiana rozdziału: przejście zasłania kadr, karta z tytułem wisi w czasie gestu muzycznego, plan odsłania się tuż przed pierwszą kwestią.
const CHAPTERS = {
  // 2: ['fala', 'Chapter title'],   one entry per scene change: a kind from film/transitions.js and the title on its card
};
function chapterCut(scene, T) {
  const [kind, title] = CHAPTERS[scene] ?? [];
  if (!kind || !title?.trim()) throw new Error(`Scene ${scene}: add a transition kind and chapter title to CHAPTERS in film/film.js`);
  return { T, kind, title, seed: scene * 3 + 1, close: 0.75, hold: 1.55, open: 0.5 };
}

/** Wipe times between scenes: WIPE_LEAD before the first line of every scene after the first. */
export function sceneCuts(tl) {
  const cuts = [];
  const last = Math.max(...tl.lines.map((l) => l.scene));
  for (let k = 2; k <= last; k++) {
    const first = tl.lines.find((l) => l.scene === k);
    if (first) cuts.push({ scene: k, T: first.start - WIPE_LEAD });
  }
  return cuts;
}

function present(tl) {
  const have = new Set(tl.lines.map((l) => l.scene));
  return MODULES.map((m, i) => ({ m, n: i + 1 })).filter(({ n }) => have.has(n));
}

// For a date or date range, add [lineId, startYear, endYear, label].
const ERAS = [];
export function railCues(tl) {
  const L = Object.fromEntries(tl.lines.map((l) => [l.id, l]));
  return ERAS.filter(([id]) => L[id]).map(([id, a, b, label]) => ({ t: L[id].start + 0.2, a, b, label }));
}

/** Sound cues of every scene, for tools/build_audio.py. */
export function soundCues(tl) {
  const c = present(tl).flatMap(({ m }) => m.soundCues(tl));
  sceneCuts(tl).forEach(({ T, scene }) => transitionSound((t, name, gain) => c.push({ t: +Math.max(0, t).toFixed(3), name, gain }), chapterCut(scene, T)));
  railCues(tl).forEach(({ t }) => { c.push({ t: +t.toFixed(3), name: 'swish', gain: 0.35 }); c.push({ t: +(t + 0.9).toFixed(3), name: 'pop', gain: 0.35 }); });
  return c.sort((a, b) => a.t - b.t);
}

export function createFilm(tl, img, tex) {
  const cuts = sceneCuts(tl);
  const scenes = present(tl).map(({ m, n }) => {
    const sc = m.createScene(tl, img, tex);
    const c = cuts.find((x) => x.scene === n);
    const next = cuts.find((x) => x.scene > n);
    return { ...sc, n, from: c ? c.T : 0, to: next ? next.T : Infinity };
  });
  // the captions now go to YouTube as an SRT file (tools/srt.py); the stage keeps its own word cards
  const rail = makeRail(railCues(tl));

  function draw(ctx, t) {
    const S = stepped(t), b = boilStep(S);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
    const sc = scenes.find((s) => S >= s.from && S < s.to) || scenes[scenes.length - 1];
    sc.draw(ctx, S, t, b);
    rail(ctx, S, b);
    if (sc.overlay) sc.overlay(ctx, S);
    cuts.forEach(({ T, scene }) => transition(ctx, S, chapterCut(scene, T), tex, img));
    grain(ctx, S, tex);
  }

  return { duration: tl.duration, draw, cuts };
}
