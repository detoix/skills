# Render and delivery

## Preview

Run `node tools/preview.mjs` from the project and open the local URL it prints. Space plays, and `?t=123` starts at that time in seconds.

## Render (`tools/render.mjs`)

Use Node.js 22 or newer, Chromium or Chrome, and FFmpeg. The renderer and layout check use `CHROME` if set to an executable name or path. Otherwise they look for a browser on `PATH` and in standard system or Playwright cache locations.

Headless Chromium draws the frames (`--workers` pages, 4 by default) and the film is written as H.264 chunks of `--chunk` seconds (2 by default), each starting with its own key frame; FFmpeg joins them with the mix without encoding again.

- Encoder: `--encoder webcodecs` (the default) encodes in the page, so no frame leaves the browser as an image (`--bitrate` in Mb/s); a browser without an H.264 encoder falls back to `x264`. `--encoder x264` (CPU, `--crf`) and `--encoder vaapi` (`--vaapi-device`, `--qp`) encode JPEG frames with FFmpeg. The browser draws on the GPU; `--gpu off` draws without it where a headless GPU misbehaves. On a new machine, render a section and look at it before a full render.
- If WebCodecs slows on long renders and the machine supports VAAPI H.264 at the target resolution, test a short section with `--encoder vaapi --qp 20 --workers 8`. Treat eight workers as a starting point and adjust to measured throughput and memory use. If Chromium stalls while drawing, add `--gpu off` to draw on the CPU and keep VAAPI for encoding. If VAAPI is unavailable, use WebCodecs or x264.
- `--from A --to B` renders a section; `--stills t1,t2` PNG stills; `--out out/<slug>_vN.mp4`.
- A picture fix: `--patch out/<slug>_vN.mp4 --from A --to B --out out/<slug>_vN+1.mp4` draws again only the chunks between A and B and copies the others; the sound is the current mix. After new takes change the timeline's length, render in full.
- `--page <file.html>` renders another page of `film/` with the same render API; `--stills-dir` and `--prefix` name its stills. The thumbnail: `--page thumb.html --stills 0 --stills-dir out/thumb --prefix thumb`. A short: `--page "short.html?name=<name>" --audio film/short_<name>/mix.wav`.
- Before a full render, run `node tools/qa_layout.mjs` (text cut by the apron or the frame, text on text, images over text, empty stages, labels too short to read; look at each hit on a still: bounding boxes and transitions raise false alarms).
- `tools/exclusive.sh "<name>" -- <command>` times a render. To pause a competing job, pass `--pause-pid PID` and, optionally, `--pause-timing "<activity name>"` before `--`; it resumes that process when the command exits.

## After the render

1. `ffprobe` the file: 1920×1080, 30 fps, audio and video of the same length.
2. Loudness and true peak measured on the MP4: about -14 LUFS, under -1 dBTP (see audio reference).
3. Stills from the final file at every fixed place (`ffmpeg -ss t -i out/… -frames:v 1`), a contact sheet, look at them.
4. `python3 tools/srt.py && python3 tools/chapters.py` → subtitles and `out/youtube.txt` (chapters shift whenever takes change length).
5. Thumbnail: `film/thumb.html` draws one thumbnail with the film's own figures, palette and maps; render it as a still and scale to 1280×720 JPEG (`out/thumb.jpg`). One thumbnail per film, no A/B variants. Its words add to the title, they don't repeat it.
6. Update the project `README.md` with the version and what changed; `timings.md` keeps the timings.
