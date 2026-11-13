#!/usr/bin/env bash
# exclusive.sh <name> [--pause-pid PID] [--pause-timing NAME] -- <command ...>
# Times a command and optionally pauses one explicitly identified competing process.
set -euo pipefail
usage() { echo 'usage: exclusive.sh <name> [--pause-pid PID] [--pause-timing NAME] -- <command ...>' >&2; exit 2; }
[ "$#" -ge 3 ] || usage
name="$1"; shift
pid=""; activity=""; paused=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pause-pid) [ "$#" -ge 2 ] || usage; pid="$2"; shift 2 ;;
    --pause-timing) [ "$#" -ge 2 ] || usage; activity="$2"; shift 2 ;;
    --) shift; break ;;
    *) usage ;;
  esac
done
[ "$#" -gt 0 ] || usage
[[ -z "$pid" || "$pid" =~ ^[1-9][0-9]*$ ]] || usage
[[ -z "$activity" || -n "$pid" ]] || usage
cd "$(dirname "$0")/.."
resume() {
  if [ "$paused" -eq 1 ]; then
    kill -CONT "$pid" 2>/dev/null || true
    if [ -n "$activity" ]; then python3 tools/clock.py resume "$activity" || true; fi
  fi
}
trap resume EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -n "$pid" ]; then
  kill -STOP "$pid"
  paused=1
  if [ -n "$activity" ]; then python3 tools/clock.py pause "$activity" --note "paused for: $name"; fi
fi
python3 tools/clock.py run "$name" -- "$@"
