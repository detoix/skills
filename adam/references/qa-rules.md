# Adam QA Rules

Run this check before presenting `script.json` and `manifests/visual-plan.json` for creative review.

## Host Fit

Reject if:

- the script has no clear hook
- the opening takes too long to reach the point
- Adam sounds like a fictional character instead of a general host
- the script sounds like generic AI prose
- the episode lacks a concrete viewer payoff
- the ending is a generic subscribe/follow CTA when a topic-specific CTA would fit

## Script Contract

Reject if:

- `script.json` lacks required top-level keys
- B-roll panels use `source` instead of `source_type`
- any `A_ROLL` segment includes B-roll-only fields
- `tts_chunks[].segment_ids` do not map to existing segments
- `voice_text` diverges substantially from `narration`
- timings have gaps or non-positive durations
- any static `A_ROLL` segment exceeds 20 seconds
- pattern interrupts are more than 15 seconds apart

## Visual Plan Contract

Reject if:

- a B-roll script segment lacks a matching visual-plan scene
- scene `type` differs from the script segment `type`
- B-roll scene panels lack `source_type`
- visual ideas are too vague to produce
- generated images are used as factual proof
- synthetic-motion concepts look like generic templates

## Validation Commands

Validate script:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --script <project-dir>\script.json `
  --format <vertical-or-landscape> `
  --mode script
```

Validate creative gate after `script.json`, `manifests/visual-plan.json`, and `manifests/creative-review-request.json` exist:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --mode creative-gate
```
