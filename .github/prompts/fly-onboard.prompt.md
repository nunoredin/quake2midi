---
description: Start a session by reading the repo guidelines and the last handoff
name: fly-onboard
agent: ask
---

# Onboard

Read the repo's rules and where the last session stopped, then say what you
found. Do not write code.

1. Read `AGENTS.md`. It is the contract for this repo.
2. Read `.github/handoff.md` if it exists. If it does not, say so — that means
   this is the first session.
3. Check `git status` and `git log --oneline -10`.
4. Answer this: is `.venv` present, and does `.venv/bin/python -c "import mido"`
   succeed? If not, the next step is `/fly-setup`.

Reply in three short blocks:

**Repo** — one sentence on what this is.
**Now** — where the last session stopped, and any uncommitted work.
**Next** — what to do next, or ask what the participant wants to work on.

Cite file paths. Do not paste large files.