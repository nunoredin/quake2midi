---
description: Review everything built this session before closing it out
name: fly-review-session
agent: ask
---

# Review the session

Before writing the handoff, look back over everything this session changed and
report honestly. Read, do not rewrite.

1. `git status` and `git diff` — every file touched, including untracked ones.
2. For each change, ask: does it do what the participant asked for?
3. Flag anything that looks like a check was weakened to get a green result —
   a deleted validation, a loosened comparison, a command run with a bypass
   flag, a failing step skipped, a live fetch replaced by a cached fixture.
4. Confirm nothing secret was written into a tracked file. `.env` must stay
   gitignored.

Reply with:

- **Changed** — the files and what changed, one line each.
- **Concerns** — anything wrong or unverified, most important first. Say "none"
  if there are none.
- **Not verified** — what you did not actually run or see working.

Do not fix anything in this reply. Report, then ask whether to fix.