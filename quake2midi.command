#!/bin/bash
# quake2midi launcher for macOS. Double-click to run the bridge.
# Mirrors quake2midi.bat: checks the venv and the MIDI ports, then runs
# scripts/run.py and leaves this window open so you can read the output.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || {
  echo " [fail] could not cd to repo root"
  read -r -p "Press Return to close."
  exit 1
}

VPY="$ROOT/.venv/bin/python"

if [ ! -x "$VPY" ]; then
  echo " [fail] missing .venv. Run: python3 scripts/setup.py"
  echo
  read -r -p "Press Return to close."
  exit 1
fi

echo " Repo: $ROOT"
echo

echo " MIDI destinations:"
"$VPY" "$ROOT/scripts/run.py" --list-ports || {
  echo
  echo " [fail] no MIDI destination. Enable the IAC Driver in Audio MIDI"
  echo "        Setup, or see AGENTS.md under 'Before you start'."
  echo
  read -r -p "Press Return to close."
  exit 1
}
echo

echo " Starting the bridge. Ctrl+C to stop."
echo " Status page: http://127.0.0.1:5446/"
echo

"$VPY" "$ROOT/scripts/run.py" "$@"
ERR=$?

echo
if [ "$ERR" -ne 0 ]; then
  echo " Bridge exited with code $ERR. Scroll up."
fi
read -r -p "Press Return to close."
exit "$ERR"
