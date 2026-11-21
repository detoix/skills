# Cut-outs and scenes

## Cut-outs

- A cut-out of anything that exists or existed — a person, a place, an object, a species — starts from its reference: a portrait, photograph, drawing or plan of the right period (Wikimedia Commons and Wikipedia hold most), saved in `research/ref/` with its source and listed in `prompts/refs.json` (`{"name": ["research/ref/…"]}`). Generic or invented things (a crowd, a meadow, a legend) need none.
- One prompt file per group in `prompts/`: the text of `_style.txt` first, then one numbered asset per line with its file name and visual requirements. An asset with a reference gets a prompt of its own and the reference attached, the prompt saying the image guides shape, proportions, colour and identifying details while the style stays the cut-out's.
- Generate with Codex imagegen (`codex exec -c model_reasoning_effort=low -s workspace-write --skip-git-repo-check -C . "$(cat prompts/<set>.txt)" [-i research/ref/<file>]`), several sets in parallel. `-i` takes several files, so it goes after the prompt; before it, it swallows the prompt as another image and Codex waits for a prompt on stdin.
- `tools/raw_sheet.py` makes two sheets: all cut-outs (style, alpha, consistency) and each referenced cut-out beside its references. Compare them before animation: silhouette, proportions, construction, component count, attachments, colouring, face and dress, and the identifying details discussed in narration.
- A setting shows the time of the scene: vegetation, land use, buildings and dress of that moment, not of today. A site shown as it looks now is labelled as today.
- Stylisation may simplify surface treatment but must preserve the evidence-bearing structure. If the evidence does not support a visible detail, omit it or mark the reconstruction rather than inventing a factual feature. Imagegen invents such details on its own, most often heraldry, flags and national colours: the style forbids emblems an asset does not name, a prompt names one only when a source of the period shows it, and the contact sheets are checked for them.
- Check the assembled object and any separate close-up as the same construction. After replacing an asset, revisit anchors, labels and actions against its new proportions.
- `tools/prep_figures.py` → `film/fig/<name>.png` + `meta.json`; big sets and maps get more pixels (`film.json` → `figures`).
- `tools/grid.py name …` draws a 10 % grid over figures to read anchor points (hands, heads, the spot where a label goes).

## Scenes (`film/scenes/sN.js`)

Each scene module exports:

- `FIGURES` — cut-out names it uses
- `anchors(tl)` — its cue times from `anchorsOf(tl)`: `L.sN_MM.start/.end`, `wt('sN_MM', 'prefix')` (start of the first word beginning with prefix)
- `soundCues(tl)` — `{ t, name, gain }` for every visible action (names from `tools/build_audio.py` `make_sfx`: pop, swish, whoosh, slide_down, thud, thud_soft, stamp, clay, strips, rise, glint, …)
- `createScene(tl, img, tex)` → `{ draw(ctx, S, t, b), overlay(ctx, S) }`; `draw` picks the current set with `setIndex(S, cuts)`, `overlay` draws the transitions between sets

Add the module to `film/film.js` (`MODULES`) and the eras of the timeline rail to `ERAS` there; the rail's span of years is `film/config.js` → `RAIL_YEARS`.

Library (`film/kit.js`, `film/stage.js`, `film/geo.js`): `piece` (a cut-out that pops in, boils, hops), `label` (a word card), `hang`/`picCard` (cards on strings), `backdrop`, `landscape`, `frescoRoom`, `nightSky`, `seaSet`, `board`, `mapView`/`areaOn`/`lineOn`/`camera`/`km` (maps from coordinates) with `pin`/`trail`/`along` at `view.pt([lon, lat])`, `mapAt` (a map cut-out, only after geographic verification), `yearCard`, `sparkle`, `stamp`, `flames`, `beads`, `glow`, `wipe`. The drawing helpers do not validate the geography or the evidence behind an asset.

## Transitions (`film/transitions.js`)

A cut is a moment of the film, so it varies in both picture and sound.

- Choose the set with the art direction. The paper strips (`paski`) are a neutral option, and gestures from the film's world add character: what its people handle and what surrounds them (a wave with herrings, a sail, a wall going up, a wax seal). Add kinds to `film/transitions.js` as the film needs them.
- Picture: never the same kind at consecutive cuts, and no kind dominates the film. Each one covers the whole frame at `T`, the set changes under it, and it uncovers the new set just before the line starts. Cuts inside a scene are short (`cutsOf` in each scene); a chapter change is longer and holds a title card (`film/film.js` → `CHAPTERS`: supply a kind and a title for each scene after the first).
- Sound: each kind has its own effects, matching its material (`transitionSound`), called from the scene's `soundCues` for every cut. A chapter change also gets a musical gesture from the library, in an order without repeats (`film.json` → `music.transitions`).
- The user approves the set at the pilot, with sound on.

## Maps — check them like facts

- Build factual maps from sourced geographic geometry and coordinates: `tools/geodata.py` cuts Natural Earth to the film's window (`film.json` → `map`; wider than the widest view, or the view runs off the painted map) and `film/geo.js` draws it in one projection for coastlines, water, borders, pins, areas, lines, camera moves and zooms.
- A line or area known only from a published map (a frontier, an ice limit, a coastline of the past) is read off that figure with `tools/georef.py`: control points of known coordinates spread over the figure, an affine fit, the residuals kept in the module's header and the precision said on screen ("simplified, after …").
- Apply the agreed painted-paper treatment to the verified geometry. An attractive generated map or a grid measured over it does not establish that its geography is true; generated backgrounds require geographic verification before factual use.
- Check topology and relative position as well as pin placement: land and water connections, river flow, coastlines, islands and the relevant extent of the view. Date political boundaries and explain the use of modern reference geography where relevant.
- Routes follow sourced or geographically plausible travel corridors. Distinguish an uncertain route or location visibly and in narration; do not turn a hypothesis into a precise-looking established path.
- Keep a shared path for its line and moving cargo, so animation follows the checked waypoints rather than interpolating across unrelated terrain.
- Render and inspect the whole map and detailed views after every geographic change. Validate the underlying geometry separately from the correctness of pins and labels.

## Subject-specific art direction

- Define a coherent palette, type hierarchy, ornament, transitions and musical character for the subject before the pilot. The shared identity is the material and movement of the paper theatre, not a fixed period, font, instrument or decorative motif.
- Adapt the template's stage, typography and score to that direction. Carry it through title cards, scene changes, labels and requested vertical exports; check legibility at the intended output size.
- Use the pilot to approve representative typography, a scene transition and the relationship of music to narration. Do not inherit a previous project's complete treatment without checking whether it fits the new subject.

## Control stills

`node tools/render.mjs --stills t1,t2,…` → `out/stills/t_*.png`; `tools/sheet.py` makes a contact sheet. Check at every scene's busiest moments, every map, every label against the narration at that second.
