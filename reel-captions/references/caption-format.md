# Caption Format

## `words.json`

`words.json` is a list of word records:

```json
[
  {"word": "Sarna", "start": 0.12, "end": 0.42, "score": 0.98}
]
```

Required fields are `word`, `start`, and `end`. `score` is optional.

## ASS Output

The script writes one ASS dialogue event for each active word. Each event displays the active word inside its short phrase window, using ASS override tags to color the active word.

Default vertical placement uses ASS alignment 2 with a bottom margin around 420 px on a 1080x1920 canvas. This keeps captions above common platform UI and above bottom-centered PiP bubbles.

## Transcript Policy

For `script.json`, captions are generated from `segments[].narration`, mapped through `tts_chunks[].segment_ids`. Alignment may normalize text for matching, but the caption words preserve the approved narration text.
