# Copilot instructions

The contract for this repository is [`AGENTS.md`](../AGENTS.md). Read it before
making changes — it covers what this project is, the reply contract, the rules,
and how to verify a change.

The short version:

- Lead with the answer; keep replies short; cite paths rather than pasting
  files.
- Use `/fly-confirm-align` before building anything non-trivial, and
  `/fly-plan` before a change that touches more than a couple of files.
- Use the repo `.venv`. Never install into the system Python.
- Never read, print, or commit the contents of `.env`.
- Send MIDI to a local port only; list the ports before choosing one.
- Verify by running the command, not by assuming.
- The participant owns `git commit`. Suggest a message; do not commit.