# Professional Reel QA Rubric

Use this rubric before setting `--agent-visual-review-pass` in `visual_qa.py`. Structural QA is necessary but not sufficient.

## Required Pass Conditions

- Format: final render is `1080x1920` for vertical reels. YouTube Shorts uploads support square or vertical aspect ratios and Shorts uploads support up to 1080p. URLs: https://support.google.com/youtube/answer/12779649?hl=en, https://support.google.com/youtube/answer/10059070?hl=en
- Opening: the first 3 seconds must communicate the content proposition; the first 6 seconds must contain a hook. URL: https://ads.tiktok.com/help/article/creative-best-practices?lang=en
- Safe zones: primary subjects stay in the action-safe center; text and critical information stay in the title-safe center and avoid bottom/right platform UI zones. URL: https://clickyapps.com/creator/video/guides/vertical-framing-safe-zones
- Captions/text: captions must be short, high-contrast, and readable on phone-sized playback; on-screen text must not sit in the bottom 20-25% unless reviewed as intentionally safe. URLs: https://ads.tiktok.com/help/article/creative-best-practices?lang=en, https://clickyapps.com/creator/video/guides/vertical-framing-safe-zones
- Visual variety: the reel must change visual treatment every few seconds through A-roll, B-roll, PiP, generated visuals, mock UI, screen capture, stacked clips, motion graphics, or text beats. This is a local pipeline rule derived from platform hook/transition guidance and OSS pipeline inspection, not a formal platform standard.
- Audio: narration is intelligible, not prompt-prefixed, and not buried under music. YouTube filming guidance emphasizes low echo/background noise for useful sound. URL: https://support.google.com/youtube/answer/12948118?co=YOUTUBE._YTVideoType%3Dshorts&hl=en
- Generated visuals: z-image outputs must look intentional, vertically composed, and segment-relevant. Reject generic filler, malformed images, fake logos, unreadable text, private data, or placeholder-looking art.
- Generated visual provenance: every `broll/generated/` timeline reference must map to a reviewed accepted item in `manifests/z-image-plan.json`.
- Asset truthfulness: real production runs use user-provided assets when the brief depends on a real person, product, brand, app, location, or voice. Disposable test inputs are test-only and must not become skill assumptions.

## Automatic Failure Conditions

- Any frame looks like a test harness, template placeholder, empty colored card, broken web page, loading page, or generic stock filler.
- Any text overlaps captions, PiP, platform UI danger zones, or other text.
- PiP is not circular when the plan calls for a talking-head bubble.
- Presenter face is awkwardly cropped, too soft, identity-drifted, or visibly lip-sync-broken.
- Generated imagery is used to avoid asking for required user assets.
- QA frames do not cover the full timeline, every PiP segment, every TEXT segment, and the final seconds.

## Review Notes Template

Record concrete notes, not “looks good.”

```text
Agent visual review notes:
- Opening hook:
- Safe-zone check:
- Caption readability:
- Visual variety:
- Generated visual quality:
- Presenter/PiP quality:
- Audio/TTS prefix:
- Rejected frames or fixes:
- Final decision:
```
