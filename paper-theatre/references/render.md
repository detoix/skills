# Render and delivery

## Preview

Run `node tools/preview.mjs` from the project and open the local URL it prints. Space plays, and `?t=123` starts at that time in seconds.

## Render (`tools/render.mjs`)

Use Node.js 22 or newer, Chromium or Chrome, and FFmpeg. The renderer and layout check use `CHROME` if set to an executable name or path. Otherwise they look for a browser on `PATH` and in standard system or Playwright cache locations.

Headless Chromium draws frames (`--workers` pages in parallel), and FFmpeg encodes them with the mix.

- `--from A --to B` renders a section; `--stills t1,t2` PNG stills; `--out out/<slug>_vN.mp4`.
- `--page <file.html>` renders another page of `film/` with the same render API; `--stills-dir` and `--prefix` name its stills. The thumbnail: `--page thumb.html --stills 0 --stills-dir out/thumb --prefix thumb`.
- On Linux, `--encoder vaapi` encodes H.264 using a VAAPI device (`--vaapi-device`, `--qp 18`); otherwise libx264 medium CRF 19 on the CPU. When the CPU encoder takes most of the CPU, the drawing waits for it: with the GPU encoder, more workers pay off.
- Before a full render, run `node tools/qa_layout.mjs` (text cut by the apron or the frame, text on text, images over text, empty stages, labels too short to read; look at each hit on a still: bounding boxes and transitions raise false alarms) and time a 10 s section with the candidate settings (encoder × workers) and compare quality with SSIM against a lossless reference; too many workers can fail to start.
- `tools/exclusive.sh "<name>" -- <command>` times a render. To pause a competing job, pass `--pause-pid PID` and, optionally, `--pause-timing "<activity name>"` before `--`; it resumes that process when the command exits.

## After the render

1. `ffprobe` the file: 1920×1080, 30 fps, audio and video of the same length.
2. Loudness and true peak measured on the MP4: about -14 LUFS, under -1 dBTP (see audio reference).
3. Stills from the final file at every fixed place (`ffmpeg -ss t -i out/… -frames:v 1`), a contact sheet, look at them.
4. `python3 tools/srt.py && python3 tools/chapters.py` → subtitles and `out/youtube.txt` (chapters shift whenever takes change length).
5. Thumbnail: `film/thumb.html` draws one thumbnail with the film's own figures, palette and maps; render it as a still and scale to 1280×720 JPEG (`out/thumb.jpg`). One thumbnail per film, no A/B variants. Its words add to the title, they don't repeat it.
6. Update the project `README.md` with the version and what changed; `timings.md` keeps the timings.
