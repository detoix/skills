"""The film's own settings, read by the tools: film.json at the project root (see the skill's SKILL.md)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    return json.loads((ROOT / "film.json").read_text(encoding="utf-8"))
