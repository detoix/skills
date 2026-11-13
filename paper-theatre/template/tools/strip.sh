#!/usr/bin/env bash
# strip.sh <video> <out.png> <start> [<start> ...]: one row of 10 frames (every 4th frame, 1.33 s) per start time
set -euo pipefail
video="$1"; out="$2"; shift 2
tmp="$(mktemp -d)"; i=0
for t in "$@"; do
  ffmpeg -loglevel error -y -ss "$t" -i "$video" -frames:v 1 -vf "select='not(mod(n\,4))',scale=240:-1,tile=10x1" -vsync 0 "$tmp/row_$(printf %02d $i).png"
  i=$((i+1))
done
ffmpeg -loglevel error -y -pattern_type glob -i "$tmp/row_*.png" -vf "tile=1x${i}" -frames:v 1 "$out"
rm -rf "$tmp"
