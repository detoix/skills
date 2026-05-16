# Arthur Visual Style

Arthur's visuals should feel like recovered records, forensic exhibits, archival traces, and documentary fragments from the pre-Singularity period.

## Visual Rules

For every B-roll segment in `script.json`:

- use `layout`
- use `panels[]`
- each B-roll panel must use `source_type`
- presenter panels must not include source fields
- visual ideas must be concrete enough to produce or select assets

## Source Strategy

Use the strongest source for the segment:

- `webpage` for real interfaces, documentation, public pages, or credibility.
- `screen-record` for workflows or interface behavior.
- `stock` for human behavior, public scenes, physical spaces, or texture.
- `generated-image` for controlled metaphor, mood, privacy-safe scenes, or impossible archival images.
- `synthetic-motion` for diagrams, archive boards, timelines, classifications, counters, and forensic UI.
- `web-evidence` for user/project-supplied local cropped proof images with `source_url` or `capture_source_url`.
- `manual` for other user-provided or project-local assets.

Do not use generic futurism as a substitute for evidence. Avoid fake proof.

## Arthur-Specific Visual Language

Prefer:

- archive cards
- restricted-file motifs
- timeline fragments
- classification labels
- evidence boards
- corrupted but readable metadata
- muted document textures
- interfaces treated as artifacts
- human-scale details

Avoid:

- shiny cyberpunk
- fantasy tavern steampunk
- generic robot imagery
- generic stock footage that proves nothing
- template-like dashboards
- dense unreadable text

## Presenter Use

Arthur may appear as A-roll or as a presenter panel, but not every B-roll needs presenter overlay. Keep presenter use aligned with the autopipeline B-roll presenter ratio requirements.
