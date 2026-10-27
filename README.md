# Owner rulings

Decision records that people and AI coding agents follow.

A **ruling** is a decision made by the project owner, written into the doc for the area it decides. Once it's written, it is applied, never asked about again, and never deleted.

- **The owner decides.** Everyone else is a worker: people, Claude Code, Codex and their subagents. Workers investigate, propose, build and report. They never make or change a ruling.
- **Rulings live in the area docs.** There's no file per decision. Read `docs/billing.md` and you get every billing rule at once.
- **Area docs hold only rulings in force.** An agent reading one sees only rules that apply.
- **Nothing is deleted.** An overturned ruling moves, unchanged, to the area's history file, `docs/history/billing.md`, with a `Replaced →` marker that points to the ruling that replaces it. A ruling followed by a `Replaced →` marker is history, not in force.
- **The owner's words are kept.** When a ruling condenses what the owner said, the exact words go in `docs/statements/billing.md`, which is only ever added to. The ruling links them with `Source`.
- **Rulings are enforced.** A ruling that code could break gets a test named after it; a judgment call is marked `Enforced: review` and checked in review. Before editing a file, an agent runs `python3 scripts/check_rulings.py --for <file>` to see every ruling that applies to it.
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
| [`CLAUDE_RULINGS-GUIDE.md`](CLAUDE_RULINGS-GUIDE.md) | The full write-up for **Claude Code**: `CLAUDE.md` with `@docs/development.md`, plus a `/ruling` skill that follows the "Recording a ruling" procedure in `docs/RULINGS.md`. |
| [`CODEX_RULINGS-GUIDE.md`](CODEX_RULINGS-GUIDE.md) | The same system for **Codex**: a short `AGENTS.md`, folder-level `AGENTS.md` files as a safety layer for a few high-risk folders, and the "Recording a ruling" procedure in `docs/RULINGS.md`. |
| [`STARTER_PROMPT_CLAUDE.md`](STARTER_PROMPT_CLAUDE.md) | The prompt to paste into **Claude Code**, opened in your target repo (new or existing), to set this up one approved step at a time. It tells the agent where to find this repo. |
| [`STARTER_PROMPT_CODEX.md`](STARTER_PROMPT_CODEX.md) | The same prompt for **Codex**. |
| [`reference/`](reference/) | A reference checker: `scripts/check_rulings.py`, its schema, tests and sample docs. Copy it into your repo and change the area list. |

Each guide covers the file layout, the ruling format and its fields, the validity rules the checker enforces, the JSON schema, the checker and its CI step, and the order of work for adopting it.

## How to use it

1. Open your target repo (new or existing) in Claude Code or Codex. Don't run the prompt from inside this repo.
2. Paste the matching starter prompt: `STARTER_PROMPT_CLAUDE.md` or `STARTER_PROMPT_CODEX.md`. No attachment is needed; the agent clones this repo into a temporary directory, or uses your local clone if you set the prompt's `Owner-rulings repo:` line to its path.
3. Approve each step as it goes. The agent inventories your existing docs first, then asks you to settle conflicts one at a time. Only you make rulings.

## Credits

This system grew out of the decision rulings in [Task Coach](https://github.com/taskcoach/taskcoach)'s [`docs/DEVELOPMENT.md`](https://github.com/taskcoach/taskcoach/blob/master/docs/DEVELOPMENT.md), shown to me by [Réal Carbonneau](https://github.com/realcarbonneau). Task Coach records decisions inline as "ruled by the decider" with a date; this repo builds on that with IDs, area docs, replacement links, a schema and a CI checker.

This system also borrows the ADR idea from Michael Nygard's ["Documenting Architecture Decisions"](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (2011), the stable IDs and validator from [Agent Decision Records](https://github.com/me2resh/agent-decision-record) by me2resh (ideas adapted; AgDR is licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)), and the idea that each rule names the files it applies to from Actual AI's ["ADRs for Coding Agents: Architectural Context, Optimized"](https://actual.ai/blog/agent-optimized-adrs).

## License

[MIT](LICENSE). Use it, copy it, adapt it and share it. Pasting a prompt or snippet into your own project needs no credit.

The reference checker in `reference/` is provided as is, without warranty of any kind. Review it and use it at your own discretion and risk; I'm not responsible for any outcome of using it.
