---
description: Set up this repo: venv, dependencies, MIDI port check
name: fly-setup
agent: agent
---

# Set up quake2midi

Goal: leave a fresh clone ready to run. When you finish, `.venv` exists, the
dependencies are installed, and the participant knows which MIDI port to send
to. One script does the work, so run it and check the result.

## Steps

1. Check the prerequisite. Python must be 3.11 or newer.

   ```
   python3 --version
   ```

   On Windows, `py -3 --version` also works. On macOS and Linux, use
   `python3`. If Python is missing or older than 3.11, tell the participant
   to install it from https://www.python.org/downloads/, and stop.

2. Run the setup script from the repo root. Use the interpreter from step 1.

   ```
   python3 scripts/setup.py
   ```

   The script creates `.venv` and installs `mido` and `python-rtmidi` into
   it. It skips what is already present, so it is safe to run twice.

3. Check the result. All of these must be true:

   - `.venv` exists in the repo root.
   - `.venv/bin/python -c "import mido"` (or `.venv\Scripts\python.exe`)
     succeeds.
   - The script's last line starts with `Done.`

4. List the MIDI destinations and tell the participant which to use.

   ```
   .venv/bin/python scripts/run.py --list-ports
   ```

   If the list is empty, MIDI is not set up yet. Point them at the note in
   `AGENTS.md` under "Before you start": enable the IAC Driver on macOS,
   `snd-virmidi` on Linux, or loopMIDI on Windows. Do not invent a port.

5. Tell the participant how to run the bridge, which also serves a status
   page at http://127.0.0.1:5446/:

   - Windows: double-click `quake2midi.bat` in the repo root.
   - macOS and Linux: run `.venv/bin/python scripts/run.py`.

   Add `--dry-run` to print the notes instead of sending them.

## If it fails

Show the participant the `[fail]` line and stop. The usual causes:

- No internet connection. The feed and the install both use it.
- Python older than 3.11.
- `python-rtmidi` build failure, usually a missing build toolchain.
- Port 5446 held by another program. That affects only step 5. Do not stop
  a process you did not start.

Fix the cause and run step 2 again.

## Rules

- Use the repo `.venv`. Do not install packages into the system Python.
- Do not edit the files under `q2m/` to make setup succeed.
- Do not read or print `.env`. Setup does not need it.