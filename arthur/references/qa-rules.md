# Arthur QA Rules

Run this check before presenting `script.json` for creative review.

## Character Fit

Reject if:

- the script sounds like tech news
- the script sounds motivational
- the script is only a summary with no historical reframing
- the Singularity is explained too clearly
- Arthur sounds angry, villainous, cute, or theatrical
- there is no specific recovered artifact, event, product, trend, or behavior
- the ending resolves too cleanly

## Script Contract

Reject if:

- `script.json` lacks required top-level keys
- B-roll panels use `source` instead of `source_type`
- any `A_ROLL` segment includes B-roll-only fields
- `tts_chunks[].segment_ids` do not map to existing segments
- `voice_text` diverges substantially from `narration`
- timings have gaps or non-positive durations

## Visual Contract

Reject if:

- a B-roll script segment lacks `layout` or `panels`
- B-roll segment panels lack `source_type`
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

Validate creative gate after `script.json` and `manifests/creative-review-request.json` exist:

```powershell
python C:\Users\kdeptula\skills\youtube-autopipeline\scripts\pipeline_check.py `
  --project-dir <project-dir> `
  --mode creative-gate
```
