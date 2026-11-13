#!/usr/bin/env bash
# new_film.sh <project-dir> "<Title>" <slug> <language> "<palette for the cut-outs>" ["<scene 1 title>"]
# Copies the paper-theatre template into a new, empty project folder and fills in the film's names.
set -euo pipefail
[ $# -ge 5 ] || { sed -n '2,3p' "$0"; exit 1; }
dir="$1"; title="$2"; slug="$3"; lang="$4"; palette="$5"; scene1="${6:-Opening}"
skill="$(cd "$(dirname "$0")/.." && pwd)"
if [ -e "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
  echo "$dir exists and is not empty" >&2; exit 1
fi
mkdir -p "$dir"
cp -r "$skill/template/." "$dir/"
mkdir -p "$dir/audio"
python3 - "$dir" "$title" "$slug" "$lang" "$palette" "$scene1" <<'EOF'
import html
import json
import re
import sys
from pathlib import Path

root, title, slug, lang, palette, scene1 = sys.argv[1:]
subs = {"TITLE": title, "SLUG": slug, "LANG": lang, "PALETTE": palette, "SCENE1": scene1}
placeholder = re.compile(r"\{\{(" + "|".join(subs) + r")\}\}")

def escape(value, suffix):
    if suffix == ".json":
        return json.dumps(value, ensure_ascii=False)[1:-1]
    if suffix == ".html":
        return html.escape(value)
    if suffix == ".js":
        return json.dumps(value, ensure_ascii=True)[1:-1].replace("'", "\\'")
    return value

for p in Path(root).rglob("*"):
    if p.is_file() and p.suffix in {".md", ".json", ".js", ".html", ".txt"}:
        source = p.read_text(encoding="utf-8")
        rendered = placeholder.sub(lambda match: escape(subs[match[1]], p.suffix), source)
        if rendered != source:
            p.write_text(rendered, encoding="utf-8")
EOF
chmod +x "$dir"/tools/*.sh
echo "created $dir — next: film.json \"voice_library\", then script.md"
