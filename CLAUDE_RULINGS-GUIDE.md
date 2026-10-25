# Owner rulings: decision records that people and Claude follow

## The idea

A ruling is a decision made by the project owner, written into the doc for the area it decides. Once written, it is applied, never asked again, and never deleted.

- The owner decides. Everyone else is a worker: people, Claude Code and its subagents. Workers investigate, propose, build and report. They never make or change a ruling.
- Rulings live inside the area docs. There's no file per decision. You read the area doc, say docs/billing.md, and get every billing rule at once.
- Nothing is deleted. A ruling that is overturned stays in place and gets a "Replaced →" marker pointing to the new one.
- A checker runs in CI, so a broken or invented ruling fails the build.

## File layout

```text
CLAUDE.md                        # short entry point; loads docs/development.md with @import
docs/README.md                   # index of every area doc
docs/development.md              # cross-cutting rulings + the ruling format
docs/<area>.md                   # one doc per area: ai.md, billing.md, security.md, ui.md …
docs/rulings.schema.json         # machine-readable schema + the fixed list of areas
scripts/check_rulings.py         # the checker
tests/test_check_rulings.py      # its tests (on sample docs, not the real ones)
.claude/skills/ruling/SKILL.md   # /ruling: how Claude records a new ruling
```

## How Claude finds the rulings

- CLAUDE.md is loaded into every session, including subagents, so it stays short. It loads the format and the cross-cutting rulings with one line, @docs/development.md, and has a "Never miss these" list for the few rules every session must see, such as safety rules.
- Area rulings are read on demand. CLAUDE.md says: "Before working on an area, find its doc in docs/README.md and read it; its rulings apply."
- The Paths field says when. An agent about to edit a file listed in a ruling's Paths reads that ruling first.
- "The repository is the memory." Claude keeps no private memory notes outside the repo; anything worth keeping is written into docs/.

Example CLAUDE.md:

```markdown
# Claude Code entry point

This file stays short. The working standards live in `docs/development.md`,
loaded below. The index of every area doc is `docs/README.md`.

@docs/development.md

## Never miss these

- Nothing is ever placed outside this repository. The repository is the memory.
- After every push, watch the CI run and report what it said.
- Never look at a secret's value: not in a secrets manager, command output,
  environment variables, files or logs. If a step needs one, stop and tell
  the owner.

## Before working on an area

Find its doc in `docs/README.md` and read it; its rulings apply.
```

## The format

```markdown
**R-<AREA>-<NNN> · Ruled by owner YYYY-MM-DD:** the decision.
· **Why:** … · **Covers:** … · **Paths:** `src/…`
· **Replaces:** R-<AREA>-<NNN> · **Tests:** `tests/….test.js`
```

| Field | Required | Rule |
| --- | --- | --- |
| ID | yes | `R-<AREA>-<NNN>`. The area must be in the schema's list, and each area is one doc. Each new ruling takes the next free number in its doc. Never reused, never renumbered. |
| Kind | yes | Ruled by owner (a decision), Parked by owner (deferred on purpose) or Asked by owner (a request). |
| Date | yes | The day the owner decided. |
| Decision | yes | One or two sentences, in the owner's words. |
| Why | no | The reason, only if the owner gave one. |
| Covers | no | What it applies to, in words. |
| Paths | no | Files or globs it governs. An agent editing them reads this ruling first. |
| Replaces | no | The ID(s) of the ruling(s) it replaces. |
| Tests | no | Test files that check it. |

When a ruling is replaced, the old one stays, with this marker on the line right after it:

```markdown
**Replaced YYYY-MM-DD → R-<AREA>-<NNN>:** short note
```

An example:

```markdown
- **R-SECURITY-001 · Ruled by owner 2026-01-15:** never look at secret
  values. No worker may see a secret's value: not in a secrets manager,
  command output, environment variables, files or logs. · **Covers:**
  every worker.
```

## The validity rules (what the checker enforces)

1. The ID is unique across docs/.
2. Every ID in Replaces exists, and that ruling carries a Replaced → marker pointing back. The link must go both ways.
3. Every file in Paths or Tests exists; a glob must match at least one file, and nothing may point outside the repo.
4. Dates are real and not in the future.
5. The area is in the schema's list, and the ruling sits in that area's doc.

It also flags anything that looks like a ruling but is malformed, like R-DEV-21 or a missing ID, instead of silently skipping it. And it keeps the schema from going stale: every doc in docs/ must have an area, and every area must have a doc.

## The schema (shortened; list your own areas)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Owner ruling",
  "x-areas": {
    "AI": "docs/ai.md",
    "BILLING": "docs/billing.md",
    "DEV": "docs/development.md",
    "SECURITY": "docs/security.md",
    "UI": "docs/ui.md"
  },
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "kind", "date", "decision", "doc"],
  "properties": {
    "id": { "$ref": "#/$defs/rulingId" },
    "kind": { "enum": ["ruled", "parked", "asked"] },
    "date": { "$ref": "#/$defs/date" },
    "doc": { "enum": ["docs/ai.md", "docs/billing.md", "docs/development.md", "docs/security.md", "docs/ui.md"] },
    "line": { "type": "integer", "minimum": 1 },
    "decision": { "type": "string", "minLength": 1 },
    "why": { "type": "string", "minLength": 1 },
    "covers": { "type": "string", "minLength": 1 },
    "paths": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "type": "string" } },
    "replaces": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "#/$defs/rulingId" } },
    "replacedBy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "date"],
      "properties": {
        "id": { "$ref": "#/$defs/rulingId" },
        "date": { "$ref": "#/$defs/date" }
      }
    },
    "tests": { "type": "array", "minItems": 1, "items": { "type": "string" } }
  },
  "$defs": {
    "rulingId": { "type": "string", "pattern": "^R-(AI|BILLING|DEV|SECURITY|UI)-[0-9]{3}$" },
    "date": { "type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" }
  }
}
```

The area list appears three times: x-areas, the ID pattern and the doc list. The checker fails if they disagree, so nobody can invent an area.

## The checker

`python3 scripts/check_rulings.py` (Python 3.8 or later, standard library only):

- Reads every docs/*.md except README.md, skipping code blocks.
- Pulls out each ruling, from its bold lead-in to the next blank line, list item, heading or lead-in, and splits it into the fields.
- Applies the five rules and prints `docs/x.md:LINE  R-ID  message` for each problem, then N rulings in M docs, E errors. It exits with 1 if there are errors.
- --json prints the extracted rulings, which match the schema.
- Has its own tests that run against sample doc folders, never the real docs.

A reference implementation is in `reference/` of the owner-rulings repo, https://github.com/mardatasci/decision_record_rulings (or take the same files from a local clone of it); copy `scripts/check_rulings.py`, `tests/` (with `fixtures/`) and `docs/rulings.schema.json` rather than writing your own, then change the area list in the schema's three places (x-areas, the ID pattern, the doc enum).

In CI it's its own step, at the end of the job, so it always runs and never hides other checks. Its own tests run in the step just before it:

```yaml
- name: Rulings checker tests pass
  run: python3 -m unittest discover -s tests

- name: Owner rulings are well-formed
  if: ${{ !cancelled() }}
  run: python3 scripts/check_rulings.py
```

The step needs Python; GitHub-hosted runners already have it. It is deliberately not in the repo's main check, which also gates deploys; a typo in a doc shouldn't block a production deploy.

## Recording a new ruling: the /ruling skill

Claude Code finds skills in .claude/skills/ automatically. The owner types /ruling, or just says "record this" or "that's a ruling", and Claude follows it. Full file, .claude/skills/ruling/SKILL.md:

```markdown
---
name: ruling
description: Record an owner decision as a ruling in the right docs/ area doc - next free ID, replacements linked both ways, rulings checker run. Use when the owner rules, decides, parks or asks for something to be recorded ("record this", "that's a ruling", "park it").
---

# Record a ruling

The format and validity rules are in `docs/development.md`, section
"Rulings". Read it first. It is the rule; this skill is only the procedure.

## Who makes a ruling

Only the owner. Record a ruling only when the owner has decided, parked or
asked for something in this conversation, in the owner's words. Never turn a
worker's proposal, a subagent's finding or your own recommendation into a
ruling. If it is unclear whether the owner decided, ask. Only the owner
parks, and says so explicitly.

## Steps

1. Confirm. Say back the decision in one or two plain sentences, its kind
   (Ruled, Parked or Asked), today's date, the area doc, and any earlier
   ruling it replaces. Wait for the owner's yes.
2. Area. Pick it from `x-areas` in `docs/rulings.schema.json`. If none fits,
   stop and ask. Never invent an area.
3. ID. Take the next free number in that doc. Never reuse or renumber.
4. Place it next to related rulings in that doc.
5. Write it in the owner's words. Add Why, Covers, Paths or Tests only if
   the owner gave them or you checked them (paths exist, tests are real).
6. Replacements. Add `· **Replaces:** R-…` to the new ruling and
   `**Replaced YYYY-MM-DD → R-<new>:** note` on the line right after the old
   one. Never delete or reword the old ruling. If it contradicts a ruling
   the owner didn't mention, stop and ask.
7. Search docs/ for other statements it makes wrong; list them and ask
   before marking each one "Replaced →". Never delete.
8. Run `python3 scripts/check_rulings.py`, fix only what you wrote, show the output.
9. Stop. Do not commit unless the owner asks.
```

## How we set it up (order of work)

1. Inventory every doc. Resolve conflicting decisions with the owner, one at a time.
2. Propose the areas and get the owner's approval, then create docs/README.md, docs/development.md and one doc per approved area.
3. Write each confirmed decision into its area doc as a ruling with an ID, and mark outdated statements "Replaced →" rather than deleting them.
4. Slim CLAUDE.md so it points to docs/.
5. Copy the schema, the checker and its tests from reference/, then add CI, then the /ruling skill.

Starter prompt to paste into Claude Code:

```text
Kit location: https://github.com/mardatasci/decision_record_rulings (branch main)
(To use a local clone instead, replace everything after "Kit location:" with its absolute path before pasting.)

Set up owner rulings in this repo using the kit above. Before you start:

- If the current directory is the kit itself (it contains STARTER_PROMPT_CLAUDE.md and reference/scripts/check_rulings.py), stop, ask me for the path to the target repo and work there. Never set up rulings inside the kit.
- If the kit location is a local path, use it. Otherwise shallow-clone it into a new temporary directory outside this repo (`mktemp -d`, then `git clone --depth 1 --branch main <kit location> <that dir>`) and use that clone as the kit. Keep it until the last step is approved, then delete only that directory. If cloning isn't possible, stop and ask me for the path to a local clone. Read CLAUDE_RULINGS-GUIDE.md from the kit first; it describes the whole setup.
- Before changing anything, check whether this repo already has CLAUDE.md, docs/, scripts/, tests/, .claude/skills/ or CI config. Merge into existing files instead of overwriting them, and show me the proposed changes to any existing file before writing it. If tests/ or scripts/ already exist, ask me before placing the checker files there.

Work one step at a time and wait for my approval between steps:

1. Inventory the docs and list every decision you find, with any that conflict. Don't change anything yet.
2. Propose the area list. After I approve it, create docs/README.md, docs/development.md (the ruling format and the cross-cutting rulings) and one docs/<area>.md per approved area.
3. Write each decision I confirm as a ruling with an ID. Mark outdated statements "Replaced →"; never delete.
4. Make CLAUDE.md short: @docs/development.md plus a "Never miss these" list.
5. Copy the checker from the kit; don't write one from scratch: reference/scripts/check_rulings.py into scripts/, the contents of reference/tests/ into tests/ (so you end up with tests/test_check_rulings.py and tests/fixtures/), and reference/docs/rulings.schema.json into docs/. Then edit only x-areas, the ID pattern and the doc enum for this repo. Its tests run on sample docs only. Keep the test folder and script folder as siblings: the copied test finds the script at ../scripts/check_rulings.py. If I choose another location, update the CI command and any later references to match. Every top-level docs/*.md other than README.md must be an area in x-areas; for each existing doc that isn't, ask me whether to make it an area or move it to a subfolder such as docs/notes/. If the repo has a JS/TS test runner, linter or type-checker, exclude tests/fixtures/ from it and show me the change. Then run python3 scripts/check_rulings.py and python3 -m unittest discover -s tests and show me both outputs.
6. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate. Also run python3 -m unittest discover -s tests in CI so the checker's own tests run.
7. Create the /ruling skill in .claude/skills/ruling/SKILL.md.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code before asking about something that may already be settled.
```
