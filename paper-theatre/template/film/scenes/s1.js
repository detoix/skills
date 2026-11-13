// Scene 1: what happens on stage, beat by beat.
// Every time comes from the narration: anchors() turns line starts and word times into the scene's cues.
import { COL, INK, anchorsOf, label, setIndex, backdrop } from '../kit.js';
import { apron } from '../stage.js';
import { transition, transitionSound } from '../transitions.js';

export const FIGURES = [];   // cut-outs this scene uses: film/fig/<name>.png (tools/prep_figures.py)

export function anchors(tl) {
  const { L, wt } = anchorsOf(tl);   // L.s1_01.start / .end, wt('s1_01', 'słowo') = when that word starts
  const A = {};
  A.title = L.s1_01 ? L.s1_01.start + 0.3 : 0.5;
  return { L, A };
}

/** Cuts between this scene's sets: a different kind each time, from the film's world (references/visuals.md). */
function cutsOf(A) {
  return [];   // e.g. [{ T: A.w1, kind: 'paski', seed: 10 }, { T: A.w2, kind: 'pergamin', seed: 11 }]
}

export function soundCues(tl) {
  const { A } = anchors(tl);
  const c = [];
  const add = (t, name, gain = 1) => c.push({ t: Math.max(0, +t.toFixed(3)), name, gain });
  add(A.title, 'pop', 0.6);
  cutsOf(A).forEach((tr) => transitionSound(add, tr));
  return c;
}

export function createScene(tl, img, tex) {
  const { A } = anchors(tl);

  function openingSet(ctx, S, b) {
    backdrop(ctx, '#8a6440', tex, 0.6);
    label(ctx, '{{TITLE}}', S, { x: 960, y: 480, t0: A.title, size: 72, seed: 1, style: { fill: COL.gold, color: INK } });
  }

  const sets = [openingSet];
  const CUTS = cutsOf(A);
  const cuts = () => CUTS.map((c) => c.T);

  function draw(ctx, S, t, b) {
    sets[setIndex(S, cuts())](ctx, S, b);
    apron(ctx, S);
  }

  function overlay(ctx, S) {
    CUTS.forEach((c) => transition(ctx, S, c, tex, img));
  }

  return { draw, overlay };
}
