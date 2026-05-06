# B-Roll Section Library

Use this as a non-preferential menu of section patterns. Pick and mix by segment intent, assets, factual risk, platform safe zones, and visual variety. Do not always choose Pexels, z-image, presenter overlays, webpage capture, animated boards, custom HTML, or any single layout.

## Selection Rule

Choose the pattern that does the communication job fastest:

- Explain: clarify a concept, term, mechanism, or sequence.
- Prove: show source material, documentation, UI, measurement, or real-world evidence.
- Compare: place alternatives, before/after, myth/fact, or mistake/fix side by side.
- Demonstrate: show a process, product, behavior, website, or workflow in action.
- Reset attention: change rhythm, scale, layout, color, camera treatment, or subject.
- Show scale: use grids, maps, counters, timelines, or multiple examples.
- Show process: use steps, checklist, countdown, path, or timeline.
- Create emotional texture: use cinematic stock, generated mood imagery, or presenter reaction.

For reels over 45 seconds, use at least three accepted section patterns unless the brief intentionally calls for a constrained visual language. Record that exception as `single_pattern_reason`.

## Patterns

| Pattern | Composer primitive | Best use | Required assets | Risks / avoid when |
| --- | --- | --- | --- | --- |
| Fullscreen stock/manual footage | `B-ROLL` | Texture, pacing, physical context, behavior, nature, human action | Reviewed video | Weak factual match; repeated provider IDs; important subject gets center-cropped |
| Fullscreen webpage/app capture | `B-ROLL` | Proof, walkthrough, visible interface, documentation | Browser recording or screen capture | UI language mismatch; credentials; tiny text; cookie popups |
| Fullscreen generated still with motion | `STILL_MOTION` or pre-rendered `B-ROLL` | Abstract concept, mood, cinematic bridge, privacy-safe synthetic scene | Accepted generated/local still | Treat as illustrative unless user accepts synthetic factual stand-in |
| PIP presenter over visual | `PIP` | Keep human presence while demonstrating website, stock, generated visual, or custom HTML | Background clip + synced presenter overlay | Presenter loop risk; bubble collides with captions/UI; background too busy |
| Split presenter/demo | `SPLIT_2` | Presenter on one half, proof/demo/B-roll on other half | Two clips or stills | Both halves become too small; use only when each panel is legible |
| Stack of 2 | `STACK_2` | Before/after, claim/evidence, problem/solution, this/that | Two clips/stills | Avoid if both clips need fine detail or vertical-native framing |
| Stack of 3 | `STACK_3` | Rapid examples, multi-source proof, contrast montage | Three clips/stills | Avoid if captions/PiP need the same vertical space |
| Grid of 4 | `GRID_4` | Category montage, evidence board, alternatives, examples at scale | Four clips/stills | Avoid for dense UI or text-heavy assets |
| Animated board capture | `B-ROLL`, `PIP`, `SPLIT_2`, `STACK_2`, or `GRID_4` | Custom art-directed synthetic UI, kinetic typography, abstract process, map, proof, or metaphor scene | `animated-broll-boards` `.webm` clip | Must be labeled/recorded as synthetic; reject template/card-stack outputs; avoid if real proof or exact real UI is required |
| Custom HTML capture | `B-ROLL`, `PIP`, `SPLIT_2`, `STACK_2`, or `GRID_4` | Bespoke fake UI or motion scene not covered by `animated-broll-boards` | Local HTML recorded with browser recorder | Must be labeled/recorded as local/synthetic; avoid real brands/credentials unless requested |
| Receipt/document highlight | `B-ROLL` or `STILL_MOTION` | Source proof, quote, table, screenshot, article, documentation | Screenshot or capture | Tiny text; source must be real if used as evidence |
| Kinetic text/number beat | `TEXT` or custom HTML capture | Stat, definition, warning, myth, CTA, transition | Background visual + short text | Do not replace word-level spoken captions; keep copy short |
| Before/after | `SPLIT_2`, `STACK_2`, or `B-ROLL` | Transformation, correction, improvement | Two related visuals | Must be visually comparable; avoid misleading synthetic before/after |
| Myth/fact or mistake/fix | `SPLIT_2`, `STACK_2`, `TEXT`, or custom HTML | Education, debunking, risk framing | Text/visual pair | Do not overcrowd; keep labels large |
| Step-by-step/checklist/countdown | custom HTML capture, `TEXT`, `STACK_2`, `STACK_3` | Process and retention pacing | HTML/graphic assets or background clips | Avoid long paragraphs; use one step per beat |
| Map/path/timeline | custom HTML capture or screen capture | Geography, history, sequence, process | Local HTML, map capture, or graphic | Avoid implying exact real location if synthetic |
| Zoomed detail | `STILL_MOTION`, `B-ROLL`, or custom HTML | Highlight detail within image/UI/document | High-resolution still/capture | Source must have enough resolution; avoid scaling beyond useful clarity |
| Product-in-use/process | `B-ROLL`, `PIP`, `SPLIT_2` | Demonstration, service, ecommerce, how-to | Real footage, stock, or generated illustrative scene | Generic stock is not proof of a specific product |
| Reaction/reference | `PIP` or `SPLIT_2` | Presenter reacts to page, claim, comment, or example | Presenter + reference visual | Avoid using third-party content without reason/context |
| Seamless loop ending | any primitive | Rewatchability, closing callback | Last frame/action tied to opening | Do not force it if it confuses the message |

## Manifest Fields

Every accepted non-presenter visual should be recorded in `manifests/selected-visuals.json`:

```json
{
  "target_duration_seconds": 60,
  "items": [
    {
      "segment_id": "S03",
      "section_pattern": "split-presenter-demo",
      "source_type": "webpage",
      "canonical_id": "https://example.com/page#section",
      "source_url": "https://example.com/page",
      "local_path": "broll/S03_demo.mp4",
      "accepted": true,
      "reason": "Shows the exact UI the narration is explaining.",
      "risk": "none"
    }
  ]
}
```

For animated board clips, use this shape:

```json
{
  "segment_id": "S03",
  "section_pattern": "animated-board-capture",
  "source_type": "animated-board",
  "canonical_id": "S03_process",
  "local_path": "broll/boards/S03_process/S03_process.webm",
  "creative_concept": "Blueprint transforms into modular assembly",
  "visual_metaphor": "A technical floorplan draws itself, then separates into moving prefab modules.",
  "motion_summary": "Line draw, module split, staggered labels, final assembly lockup.",
  "accepted": true,
  "reason": "Explains the process with a custom animated scene rather than a template board.",
  "risk": "synthetic explanatory motion graphic"
}
```

Use `single_pattern_reason` only when a reel over 45 seconds deliberately uses fewer than three section patterns.

## Guardrails

- Generated visuals and generic stock are illustrative unless the user explicitly accepts them as synthetic/non-factual.
- Use `animated-broll-boards` instead of ad hoc static PNG/Pillow boards for production abstract UI, checklist, timeline, comparison, map, logistics, cost/risk, process, and dashboard-style B-roll.
- Do not treat checklist, timeline, process-flow, or map as animated-board layout names. They are narrative intents; the accepted board must have a custom creative concept, visual metaphor, and motion summary.
- Verified webpage, app, documentation, or source captures are preferred when the visual itself is evidence.
- Reused `canonical_id` values are duplicates even if filenames differ.
- Keep critical text, faces, captions, and CTAs inside platform-safe central areas.
- Inspect final frames because panel layouts can become unreadable after scaling.
