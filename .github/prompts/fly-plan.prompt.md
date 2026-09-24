---
description: Write a plan before a large change
name: fly-plan
agent: plan
---

# Plan

Write a plan for the agreed work. Do not change any files yet.

Cover, in this order:

1. **Goal** — the outcome in one sentence.
2. **Files** — every file you expect to touch, and whether it is new or edited.
3. **Steps** — ordered, one action each, small enough to check off.
4. **Risks** — what could break, and what you are unsure about.
5. **Verify** — the commands that prove it works.

This repo has a small test suite, plus a few manual checks.

- `.venv/bin/python -m pytest` — the tests. No network, no MIDI port.
- `.venv/bin/python scripts/run.py --list-ports` — lists MIDI destinations.
- `.venv/bin/python scripts/run.py --once --dry-run` — fetches the feed once
  and prints the notes, no MIDI needed.
- `.venv/bin/python scripts/run.py` — runs the bridge and serves the status
  page at http://127.0.0.1:5446/.
- `git status` — confirm nothing unexpected is staged.

Keep the plan short enough to read in one sitting. Wait for approval before
executing.