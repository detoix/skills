---
name: animated-broll-boards
description: Create original, high-quality animated HTML/CSS/JS B-roll motion scenes for reels, Shorts, and video explainers. Use when Codex needs custom art-directed synthetic UI, kinetic typography, abstract explainers, process visuals, diagrams, dashboards, maps, comparisons, or motion-graphic B-roll recorded as video instead of static PNG.
---

# Animated B-roll Boards

This skill is an art-direction workflow, not a template generator.

Use it to create a custom animated scene for a specific reel segment. The agent must design the visual idea, composition, typography, and motion language, then write dedicated project-local `HTML/CSS/JS`.

## Hard Rules

- No fallback mode.
- No template mode.
- No static PNG UI boards.
- No Pillow-generated production boards.
- Do not use fixed component/layout generators as the creative output.
- Narrative labels like `checklist`, `timeline`, `process-flow`, or `comparison` are intent hints only; they are not layout instructions.
- Every accepted board must have a real visual metaphor and custom motion beats.
- Preserve user-facing copy exactly as provided in `copy_blocks`, including Unicode, accents, diacritics, casing, punctuation, and non-Latin scripts. ASCII-only defaults apply only to code identifiers and filenames, not visible text.

## Workflow

1. Write `<project-dir>\broll\boards\<board-id>\board-creative-brief.json`.
   It must include:
   - `intent`
   - `audience`
   - `visual_metaphor`
   - `art_direction`
   - `composition`
   - `motion_beats`
   - `copy_blocks`
   - `avoid`
   - `acceptance_notes`
   Optional:
   - `format`: `vertical` or `landscape`
   - `duration`
   - `narrative_intent`
   - `preset`
2. Initialize the board contract:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\create_board.mjs `
     --project-dir <project-dir> `
     --board-id <board-id> `
     --data-json <project-dir>\broll\boards\<board-id>\board-creative-brief.json
   ```
3. Replace the generated `index.html` shell with a custom scene.
   - Use bespoke HTML/CSS/JS for that segment.
   - Use motion primitives such as line drawing, masking, stagger, parallax, count-up, path movement, morphing, scroll-free camera moves, or state transitions.
   - Keep text readable at phone scale.
4. Re-run the initializer with the same arguments so `board-manifest.json` records the final `scene_hash`. The initializer must not overwrite an existing `index.html`.
5. Run QA:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\qa_board.mjs `
     --project-dir <project-dir> `
     --board-id <board-id>
   ```
6. Render:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\render_board.mjs `
     --project-dir <project-dir> `
     --board-id <board-id>
   ```
7. Record the accepted board in `manifests\selected-visuals.json` with:
   - `source_type: "animated-board"`
   - `creative_concept`
   - `visual_metaphor`
   - `motion_summary`
   - `local_path: "broll/boards/<board-id>/<board-id>.webm"`

## Output Contract

- Creative brief: `<project-dir>\broll\boards\<board-id>\board-creative-brief.json`
- HTML scene: `<project-dir>\broll\boards\<board-id>\index.html`
- Manifest: `<project-dir>\broll\boards\<board-id>\board-manifest.json`
- Preview screenshot: `<project-dir>\broll\boards\<board-id>\preview.png`
- Clip: `<project-dir>\broll\boards\<board-id>\<board-id>.webm`

## Design Standard

- The board must look like a finished modern motion-design shot, not a dashboard template.
- Use topic-specific metaphor and composition, not generic card stacks.
- Prefer real visual systems: blueprints transforming into modules, production lanes, dependency paths, editorial proof marks, signal/risk interfaces, material flows, kinetic headline reveals.
- Use strong hierarchy, modern spacing, responsive-safe dimensions, and controlled easing.
- Avoid 2000s traits: bevels, clipart, heavy outlines, random gradients, generic rounded cards, tiny copy, fake app chrome, weak spacing.

## Failure Rules

QA must fail when:

- the starter shell is still present
- placeholder/test/template copy appears
- old template classes appear, such as `.flow`, `.checklist`, `.timeline`, `.matrix`, `.myth`
- there are fewer than four animated elements
- sampled frames show insufficient change
- text clips, overlaps, or is too small
- creative brief lacks `visual_metaphor` or `motion_beats`
- output is a static still or PNG for an abstract UI/motion board

## Resources

- Contract initializer: [scripts/create_board.mjs](scripts/create_board.mjs)
- Renderer: [scripts/render_board.mjs](scripts/render_board.mjs)
- QA: [scripts/qa_board.mjs](scripts/qa_board.mjs)
- Art-direction references: [references/presets.md](references/presets.md), [references/components.md](references/components.md)
