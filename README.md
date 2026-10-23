# Owner rulings

Decision records that people and AI coding agents follow.

A **ruling** is a decision made by the project owner, written into the doc for the area it decides. Once it's written, it is applied, never asked about again, and never deleted.

- **The owner decides.** Everyone else is a worker: people, Claude Code, Codex and their subagents. Workers investigate, propose, build and report. They never make or change a ruling.
- **Rulings live in the area docs.** There's no file per decision. Read `docs/billing.md` and you get every billing rule at once.
- **Nothing is deleted.** An overturned ruling stays in place and gets a `Replaced →` marker that points to the ruling that replaces it.
- **A checker runs in CI.** A broken or invented ruling fails the build.

A ruling looks like this:

```markdown
- **R-SECURITY-001 · Ruled by owner 2026-01-15:** never look at secret
  values. No worker may see a secret's value: not in a secrets manager,
  command output, environment variables, files or logs. · **Covers:**
  every worker.
```

## What's in this repo

| File | What it is |
|------|------------|
| [`CLAUDE_RULINGS-GUIDE.md`](CLAUDE_RULINGS-GUIDE.md) | The full write-up for **Claude Code**: `CLAUDE.md` with `@docs/development.md`, plus a `/ruling` skill for recording new rulings. |
| [`CODEX_RULINGS-GUIDE.md`](CODEX_RULINGS-GUIDE.md) | The same system for **Codex**: a short `AGENTS.md`, folder-level `AGENTS.md` files for high-risk folders, and the "Recording a ruling" procedure in `docs/development.md`. |
| [`STARTER_PROMPT.md`](STARTER_PROMPT.md) | A prompt to paste into your agent to set this up in an existing repo, one approved step at a time. |

Each guide covers the file layout, the ruling format and its fields, the validity rules the checker enforces, the JSON schema, the checker and its CI step, and the order of work for adopting it.

## How to use it

1. Pick the guide for your agent.
2. Open your project in Claude Code or Codex, attach the guide, and paste the starter prompt. `STARTER_PROMPT.md` is written for Codex (`AGENTS.md`). The Claude version is at the end of `CLAUDE_RULINGS-GUIDE.md`.
3. Approve each step as it goes. The agent inventories your existing docs first, then asks you to settle conflicts one at a time. Only you make rulings.

## Credits

It borrows the ADR idea from Michael Nygard, the stable IDs and validator from [Agent Decision Records](https://github.com/me2resh/agent-decision-record), and the idea that each rule names the files it applies to from Actual AI's "agent-optimized ADRs".
