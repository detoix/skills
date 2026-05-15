# B-Roll Section Library

Use this as a non-preferential menu of B-roll layout patterns. It does not define segment types. Every segment is still `A_ROLL` or `B_ROLL`.

## Contract

`B_ROLL` entries use:

- `layout`: `fullscreen`, `stack2`, `stack3`, or `grid4`
- `panels[]`: each panel is either `kind: "broll"` or `kind: "presenter"`
- `source_type`: required only on `kind: "broll"` panels

Allowed B-roll panel source_type values:

- `synthetic-motion`
- `stock`
- `webpage`
- `generated-image`
- `screen-record`
- `manual`

Presenter panels and overlays never count toward source diversity.

## Patterns

| Pattern | Contract shape | Best use | Risks |
| --- | --- | --- | --- |
| Fullscreen B-roll | `layout: fullscreen` with one `broll` panel | texture, proof, product context, webpage capture, generated visual | weak source match; center-crop loss |
| Fullscreen with presenter overlay | `layout: fullscreen` with one `broll` panel and one `presenter` panel role `overlay` | keep human presence over proof/demo/context | presenter/captions collision; overlay crop |
| Stack of 2 | `layout: stack2` with two panels | before/after, claim/evidence, presenter plus demo | small details can become unreadable |
| Stack of 3 | `layout: stack3` with three panels | rapid examples, multi-source proof, contrast montage | captions and faces compete for vertical space |
| Grid of 4 | `layout: grid4` with four panels | categories, alternatives, evidence board, examples at scale | dense UI/text becomes unreadable |
| Still motion | `kind: broll` panel with `treatment: still_motion` | generated/manual stills needing motion | source must be high-resolution enough |
| Synthetic motion | `kind: broll`, `source_type: synthetic-motion` | custom boards, diagrams, kinetic typography, local synthetic UI | must not look like a template/test harness |

## Selected Visuals

Every accepted non-presenter visual should be recorded in `manifests/selected-visuals.json`. Source diversity is counted only from accepted B-roll assets that correspond to `kind: "broll"` panels. Presenter panels are not source types.

```json
{
  "target_duration_seconds": 60,
  "items": [
    {
      "segment_id": "S03",
      "section_pattern": "fullscreen-webpage",
      "source_type": "webpage",
      "source_url": "https://example.com/page",
      "local_path": "broll/S03_demo.mp4",
      "accepted": true,
      "duration_seconds": 6,
      "reason": "Shows the exact UI the narration is explaining.",
      "risk": "none"
    }
  ]
}
```

For board-created synthetic-motion clips, include the board creative metadata:

```json
{
  "segment_id": "S03",
  "section_pattern": "synthetic-motion-capture",
  "source_type": "synthetic-motion",
  "local_path": "broll/boards/S03_process/S03_process.webm",
  "duration_seconds": 6,
  "creative_concept": "Blueprint transforms into modular assembly",
  "visual_metaphor": "A technical floorplan draws itself, then separates into moving prefab modules.",
  "motion_summary": "Line draw, module split, staggered labels, final assembly lockup.",
  "accepted": true,
  "reason": "Explains the process with a custom animated scene rather than a template board.",
  "risk": "synthetic explanatory motion graphic"
}
```

## Guardrails

- Generated visuals and generic stock are illustrative unless the user explicitly accepts them as factual stand-ins.
- Verified webpage, app, documentation, or source captures are preferred when the visual itself is evidence.
- Reused `canonical_id` values are duplicates even if filenames differ.
- Keep critical text, faces, captions, and CTAs inside platform-safe central areas.
- Inspect final frames because panel layouts can become unreadable after scaling.
