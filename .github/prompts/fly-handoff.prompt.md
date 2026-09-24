---
description: Write the handoff and offer to commit
name: fly-handoff
agent: agent
---

# Hand off

Write the session state to `.github/handoff.md`, overwriting the previous one.
It is gitignored, so it stays local.

Use exactly these headings:

```
# handoff

| Field | Value |
|-------|--------|
| **Date** | <today> |
| **HEAD** | <short hash from git rev-parse --short HEAD> |
| **Active focus** | <one line> |
| **Next session** | <one line> |

## TL;DR

1. <the few things that matter, numbered>

## Uncommitted work

<what git status shows, and whether it should be committed>

## Next

<what to pick up next time, and any open question>
```

Rules:

- Say what is true. If something was not verified, write that it was not.
- Never copy a secret into this file. Name `.env`; do not quote it.
- Then show `git status --short` and suggest a commit message. **Ask the
  participant to run the commit.** Do not commit for them.