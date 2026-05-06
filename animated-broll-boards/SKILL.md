---
name: animated-broll-boards
description: Create high-quality animated HTML/CSS/JS B-roll boards for reels, Shorts, and video explainers. Use when Codex needs polished motion graphics, synthetic UI boards, checklists, timelines, comparisons, dashboards, process diagrams, logistics maps, metric beats, risk matrices, or other abstract/infographic B-roll that should be recorded as video instead of static PNG.
---

# Animated B-roll Boards

Use this skill to produce polished synthetic motion-graphic B-roll from local `HTML/CSS/JS`, then record it as `.webm` for timeline use.

## Workflow

1. Choose a board type and preset:
   - Board types: `hero-metric`, `comparison-split`, `checklist`, `process-flow`, `timeline`, `logistics-map`, `bar-comparison`, `risk-matrix`, `myth-fact`
   - Presets: `premium-saas`, `construction-tech`, `real-estate-premium`, `bold-reel`, `minimal-editorial`
2. Create the board:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\create_board.mjs `
     --project-dir <project-dir> `
     --board-id S03_process `
     --type process-flow `
     --preset construction-tech `
     --format vertical `
     --duration 6 `
     --title "Szybszy start" `
     --subtitle "Fundament i elementy domu powstają równolegle" `
     --items "Działka|Fabryka|Transport|Montaż"
   ```
3. Run board QA before recording:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\qa_board.mjs `
     --project-dir <project-dir> `
     --board-id S03_process
   ```
4. Render the board:
   ```powershell
   node C:\Users\kdeptula\skills\animated-broll-boards\scripts\render_board.mjs `
     --project-dir <project-dir> `
     --board-id S03_process
   ```
5. Add the `.webm` output to `timeline.json` as `B-ROLL`, `PIP`, `SPLIT_2`, `STACK_2`, or `GRID_4` input as appropriate.

## Output Contract

- HTML scene: `<project-dir>\broll\boards\<board-id>\index.html`
- Manifest: `<project-dir>\broll\boards\<board-id>\board-manifest.json`
- Preview screenshot: `<project-dir>\broll\boards\<board-id>\preview.png`
- Clip: `<project-dir>\broll\boards\<board-id>\<board-id>.webm`

Record accepted visuals in `manifests\selected-visuals.json`:

```json
{
  "section_pattern": "custom-html-capture",
  "source_type": "animated-board",
  "canonical_id": "<board-id>",
  "local_path": "broll/boards/<board-id>/<board-id>.webm",
  "risk": "synthetic explanatory motion graphic"
}
```

## Design Rules

- Treat every board as a finished motion-design scene, not a static infographic.
- Use real hierarchy: large headline, concise supporting copy, clear component structure, consistent spacing.
- Include visible motion: reveal, count-up, line draw, progress fill, stagger, parallax, or state transition.
- Keep critical text in vertical safe zones and readable on a phone.
- Prefer modern UI composition over clipart: typography, shapes, lines, grids, counters, labels, charts, paths.
- Default to `premium-saas`; use topic presets when they improve fit.

## Do Not

- Do not generate ad hoc static PNG UI boards for production reels.
- Do not use Pillow as the primary board design tool.
- Do not use bevels, clipart, heavy outlines, random gradients, tiny text, placeholder cards, or generic template-looking layouts.
- Do not imply a board is a real product, real app, real map, real dashboard, or real data source unless the user supplied that factual source.

## Failure Rules

Fail and revise when:

- screenshot or final frames look like a test harness, template, old infographic, or unfinished mockup
- text clips, overlaps, or is too small for phone playback
- the board has no visible animation
- output is static PNG/still for an abstract UI board without explicit user approval
- `.webm` output is missing, blank, wrong resolution, or materially wrong duration

## Resources

- Generator: [scripts/create_board.mjs](scripts/create_board.mjs)
- Renderer: [scripts/render_board.mjs](scripts/render_board.mjs)
- QA: [scripts/qa_board.mjs](scripts/qa_board.mjs)
- Presets: [references/presets.md](references/presets.md)
- Components: [references/components.md](references/components.md)
