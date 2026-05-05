# Short-Form Reel Practices

Research inputs fetched during the May 5, 2026 pipeline update.

## Tutorials, Guides, And Platform Docs

1. YouTube Help: Shorts can be uploaded as vertical videos, Shorts creation supports preview plus text-to-speech/effects, and uploads support up to 1080p. URL: https://support.google.com/youtube/answer/10059070?hl=en
2. YouTube Help: desktop Shorts uploads accept short-video files up to 3 minutes with square or vertical aspect ratio. URL: https://support.google.com/youtube/answer/12779649?hl=en
3. YouTube Help: mobile filming guidance says to shoot vertically, use soft even lighting, record in a low-echo/noise space, and plan needed screen recordings or extra footage. URL: https://support.google.com/youtube/answer/12948118?co=YOUTUBE._YTVideoType%3Dshorts&hl=en
4. YouTube Help: Shorts editing guidance recommends on-screen text for context/accessibility, voiceover for added context, and timeline review before publishing. URL: https://support.google.com/youtube/answer/13380879?hl=en
5. YouTube Help: upload tips recommend test uploads and a maintainable posting schedule. URL: https://support.google.com/youtube/answer/12921536?hl=en-GB
6. TikTok Ads Help: creative guidance recommends vertical 9:16, sound/music, UI safe-zone visibility, people on camera, a hook, content proposition in the first 3 seconds, captions/text overlays at 5-10 words per second, transitions/graphics, CTA, and continuous testing. URL: https://ads.tiktok.com/help/article/creative-best-practices?lang=en
7. TikTok Creative Center: the accelerator playbook covers assets, creative formula, production/post-production, audio, music, non-music audio, and voiceover. URL: https://ads.tiktok.com/business/creativecenter/quicktok/online/tiktok_creative_accelerator/pc/en
8. Meta Newsroom: Instagram introduced a Best Practices education hub covering creation, engagement, reach, monetization, and guidelines. URL: https://about.fb.com/news/2024/10/best-practices-education-hub-creators-instagram/
9. Kreatli safe-zone guide: for 1080x1920 vertical videos, keep critical text/logos/CTAs inside platform safe zones; sample margins include about 108 px top and 320 px bottom for Reels, central 4:5 for Shorts, and about 130 px top/250 px bottom/60 px side for TikTok. URL: https://kreatli.com/guides/safe-zone-guide
10. ClickyApps vertical framing guide: keep custom text out of the bottom 20-25%, avoid the right-edge action-button zone, center subjects, and validate with a safe-zone overlay before export. URL: https://clickyapps.com/creator/video/guides/vertical-framing-safe-zones
11. Edicion Video Pro 9:16 guide: practical tips place main text between 20-70% from top, captions around 65-70% from top, CTAs no lower than 75%, and recommend 1080x1920 output. URL: https://edicionvideopro.com/en/editing-techniques/916-aspect-ratio-guide-vertical-video-for-tiktok-reels/
12. FetchSub safe-zone checker: validates whether TikTok, Instagram Reels, or YouTube Shorts UI overlays cover text or faces. URL: https://fetchsubb.vercel.app/safe-zone

## Open-Source Project Inspection

1. OpenMontage: agentic video production uses structured pipelines, real-footage retrieval, Remotion composition, word-level subtitles, ffprobe validation, frame sampling, audio analysis, delivery-promise verification, and subtitle checks. URL: https://github.com/calesthio/OpenMontage
2. VidPipe: recording-to-social pipeline includes Whisper transcription, silence removal, karaoke captions, caption burning, shorts extraction, face detection, review app, and platform-specific post outputs. URL: https://github.com/htekdev/vidpipe
3. FunClip: local open-source clipping combines ASR, transcript segment selection, speaker/text selection, subtitles, and LLM-assisted clipping. URL: https://github.com/modelscope/FunClip
4. Short Video Maker: automated short-form tool combines text-to-speech, automatic captions, background videos, music, MCP, and REST generation from text inputs. URL: https://github.com/gyoridavid/short-video-maker
5. VANTA: Remotion-based video engine integrates voice cloning, talking-head avatars, animated captions, timeline editing, transitions, motion graphics, background removal, and local/open-source components. URL: https://github.com/itsjwill/vanta
6. Videogrep: automatic supercut workflow uses subtitle/transcript tracks and can export WebVTT alongside rendered cuts. URL: https://github.com/antiboredom/videogrep
7. video-editing-skill: OpenClaw skill shows a compact speech-recognition, sentence-splitting, subtitle-burning, clip-merging, and Remotion timeline approach. URL: https://github.com/maxazure/video-editing-skill

## Local Rules Derived From Research

- Open with a visible proposition in the first 3 seconds and a clear hook within the first 6 seconds.
- For reels, render `1080x1920`, keep faces and critical text in the center safe zone, and keep custom text out of bottom/right UI collision areas.
- Use short burned-in captions on ordinary timeline entries; reserve `TEXT` entries for keyword beats, section turns, or CTAs.
- Use visual changes every few seconds: A-roll, PiP, stacked clips, B-roll, mock UI, generated imagery, or full-screen text beats.
- Treat frame QA as a required production stage. A completed MP4 is not deliverable until duration, resolution, captions, PiP, text clipping, blank frames, visual variety, asset categories, and TTS prefix status are recorded.
- Prefer structured manifests over ad hoc review notes: asset intake, TTS chunks, timeline validation, frame extraction, QA report, and iteration log.

## Research-To-Implementation Requirements

- Production asset intake must be explicit. The pipeline should ask for a user asset root and must not silently reuse previous test inputs for production renders.
- Generated visuals are a separate source class, not a fallback excuse. Use `z-image-turbo` when a generated still is the strongest creative source for a segment; reject generic or placeholder-looking images.
- The composer must accept reviewed still images so generated visuals can be used directly in `B-ROLL`, `TEXT` backgrounds, and other visual layers.
- Structural QA cannot pass a reel by itself. Human/aesthetic review is mandatory because automatic checks can miss cheap-looking visuals, poor art direction, bad pacing, and weak creative fit.
- QA reports must distinguish "mechanically valid" from "professionally acceptable".
