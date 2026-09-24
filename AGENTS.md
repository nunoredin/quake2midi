# AGENTS.md

Guidance for AI assistants working in **quake2midi**. This file is the
contract. Keep it under 150 lines; procedures belong in the `fly-*` prompts.

## What this is

quake2midi turns live earthquakes into MIDI. It polls the EMSC /
SeismicPortal FDSN feed, keeps the events worth playing, and maps each one
to MIDI notes on a local port. One event in, one musical gesture out. The
piece lives in `q2m/`. There are no lessons in this repo.

## Before you start

- Python **3.11+** on `PATH` and [Git](https://git-scm.com/).
- A MIDI destination. On macOS use the IAC Driver
  (Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver → enable
  "Device is online"). On Linux use a virtual port (`snd-virmidi`) or
  `mido`'s default. On Windows install
  [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
- An OpenRouter API key, only if you use the assistant's model features.
  Copy `.env.example` to `.env` and paste the key after
  `OPENROUTER_API_KEY=`. `.env` is gitignored; never commit it.

## Setup

1. Open this folder in VS Code.
2. In Copilot Chat, run `/fly-setup`. It creates `.venv`, installs
   `mido` and `python-rtmidi`, and checks for a MIDI port.
3. Start the bridge with `.venv/bin/python scripts/run.py` (macOS / Linux)
   or `quake2midi.bat` (Windows).

## How to reply

- Lead with the answer. No preamble, no restating the question.
- Short by default. Complete sentences. Expand only when a decision needs
  evidence.
- Cite paths. Do not paste large files or tool traces.

## Ask before acting

- Use `/fly-confirm-align` whenever the participant is describing a goal or
  brainstorming. Agree on the goal in chat, then stop.
- Use `/fly-plan` before a change that touches more than one or two files.
- Ask when two or more reasonable options exist and the choice matters. Put
  the question in Copilot chat, not buried in prose. Mark a recommended
  option.

## Session workflow

`fly-onboard` → `fly-confirm-align` → `fly-plan` → *build* →
`fly-review-session` → `fly-handoff`

| Prompt | Use it when |
|---|---|
| `/fly-setup` | Once, to install and check the MIDI port |
| `/fly-onboard` | At the start of a session, to catch up on where you left off |
| `/fly-confirm-align` | You are describing a goal, and want the assistant to check its understanding first |
| `/fly-plan` | A change will touch more than a couple of files |
| `/fly-review-session` | Before closing the session, to audit what was built |
| `/fly-handoff` | To write the handoff and get a suggested commit message |

The prompts live in `.github/prompts/` and run with a leading slash in
Copilot Chat. The handoff is `.github/handoff.md`, gitignored.

## Layout

- `scripts/run.py` — the bridge: poll the feed, map, send MIDI
- `scripts/setup.py` — creates `.venv` and installs dependencies
- `q2m/` — the package
  - `quakes.py` — the live EMSC / SeismicPortal FDSN fetch
  - `mapping.py` — quake → MIDI notes (magnitude, depth, distance)
  - `midi.py` — port selection and note output
  - `core.py` — the polling loop and the dedupe of seen events
  - `state.py` — the JSON status file and the small HTTP status page
- `.env` — the OpenRouter API key. Gitignored.

## Rules

- Use the repo `.venv`. Never install into the system Python.
- Never read, print, or commit the contents of `.env`. Point at the path
  instead. `.env.example` shows the key name only.
- HTTP is `127.0.0.1:5446` only. Leave 5440, 5442, and 5444 alone; those
  belong to SkyArena.
- Send MIDI to a local port only. Never assume a hardware port exists;
  list the available ports and say which one you used.
- Surgical changes. Touch only what the task needs, and match the existing
  style. No drive-by refactors.
- Python follows Google style: 80 columns, 4 spaces, Google docstrings.
  `ruff` is configured in `pyproject.toml`.
- Verify before calling anything done. Run the command; do not assume.
- The participant owns `git commit`. Suggest a message; do not commit.
- Third-party sources: see [`NOTICE`](NOTICE).

## Verify

There is no test suite. The checks that exist:

- `.venv/bin/python scripts/run.py --list-ports` lists MIDI destinations.
- `.venv/bin/python scripts/run.py --once --dry-run` fetches the feed once,
  prints the notes it would send, and exits. No MIDI needed.
- `.venv/bin/python scripts/run.py` runs the bridge; open
  http://127.0.0.1:5446/ to see the last events and the notes sent.
- `.venv/bin/python -m pip install ruff`, then `python -m ruff check .`
  lints the Python. Setup does not install `ruff`; install it when needed.
- `git status` shows nothing unexpected.

## Data

The only source is the EMSC / SeismicPortal FDSN feed at
`https://www.seismicportal.eu/fdsnws/event/1/query`, polled every 8 seconds
with a 20-minute lookback. Nothing is stored; events are deduped by id for
the life of the process. Details in [`NOTICE`](NOTICE).