# Owner rulings: decision records that people and Claude follow

## The idea

A ruling is a decision made by the project owner, written into the doc for the area it decides. Once written, it is applied, never asked again, and never deleted.

- The owner decides. Everyone else is a worker: people, Claude Code and its subagents. Workers investigate, propose, build and report. They never make or change a ruling.
- Rulings live inside the area docs. There's no file per decision. You read the area doc, say docs/billing.md, and get every billing rule at once.
- Nothing is deleted. A ruling that is overturned stays in place and gets a "Replaced →" marker pointing to the new one. A ruling followed by a `Replaced →` marker is history, not in force.
- Rulings are enforced. A ruling that code could break gets a test named after it; a judgment call no test can check is marked `Enforced: review` and checked in review.
- A checker runs in CI, so a broken or invented ruling fails the build.

## File layout

```text
CLAUDE.md                        # short entry point; loads docs/development.md with @import
docs/README.md                   # index of every area doc
docs/development.md              # cross-cutting rulings only; loaded every session
docs/RULINGS.md                  # the ruling format, its fields and the recording procedure
docs/<area>.md                   # one doc per area: ai.md, billing.md, security.md, ui.md …
docs/rulings.schema.json         # machine-readable schema + the fixed list of areas
scripts/check_rulings.py         # the checker
tests/test_check_rulings.py      # its tests (on sample docs, not the real ones)
tests/…                          # the tests that enforce rulings: ordinary tests
.claude/skills/ruling/SKILL.md   # /ruling: how Claude records a new ruling
```

## How Claude finds the rulings

- CLAUDE.md is loaded into every session, including subagents, so it stays short. It loads the cross-cutting rulings with one line, @docs/development.md, and has a "Never miss these" list for the few rules every session must see, such as safety rules. docs/development.md is loaded every session too, so it holds only the cross-cutting rulings.
- The format and the recording procedure are in docs/RULINGS.md. Only the /ruling skill reads it, when a ruling is recorded.
- Area rulings are read on demand. CLAUDE.md says: "Before working on an area, find its doc in docs/README.md and read it; its rulings apply."
- Before editing a file, Claude runs `python3 scripts/check_rulings.py --for <file>` from the repo root. It prints every ruling not replaced whose Paths match that file, plus every ruling not replaced of the areas whose x-area-paths match it. Ruled ones bind; Parked and Asked ones are shown for context. It reads only the docs, so it takes a fraction of a second.
- "The repository is the memory." Claude keeps no private memory notes outside the repo; anything worth keeping is written into docs/.

Example CLAUDE.md:

```markdown
# Claude Code entry point

This file stays short. The cross-cutting rulings live in
`docs/development.md`, loaded below; the ruling format and the procedure for
recording one are in `docs/RULINGS.md`. The index of every area doc is
`docs/README.md`.

@docs/development.md

## Never miss these

- Nothing is ever placed outside this repository. The repository is the memory.
- After every push, watch the CI run and report what it said.
- Never look at a secret's value: not in a secrets manager, command output,
  environment variables, files or logs. If a step needs one, stop and tell
  the owner.

## Before working on an area

Find its doc in `docs/README.md` and read it; its rulings apply. Before
editing a file, run `python3 scripts/check_rulings.py --for <file>` from the
repo root; every Ruled ruling it prints applies.

## Before calling a change done

Run `--for` on each changed file and check the diff against every printed
ruling marked `Enforced: review`; run the tests listed in Tests.
```

## The format

The format, the field table and the recording procedure go in docs/RULINGS.md. The checker skips that file, like docs/README.md.

```markdown
**R-<AREA>-<NNN> · Ruled by owner YYYY-MM-DD:** the decision.
· **Why:** … · **Covers:** … · **Paths:** `src/…`
· **Replaces:** R-<AREA>-<NNN> · **Tests:** `tests/….test.js`
· **Enforced:** review
```

| Field | Required | Rule |
| --- | --- | --- |
| ID | yes | `R-<AREA>-<NNN>`. The area must be in the schema's list, and each area is one doc. Each new ruling takes the next free number in its doc. Never reused, never renumbered. |
| Kind | yes | Ruled by owner (a decision), Parked by owner (deferred on purpose) or Asked by owner (a request). |
| Date | yes | The day the owner decided. |
| Decision | yes | One or two sentences, in the owner's words, or a condensed wording the owner approved. |
| Why | no | The reason, only if the owner gave one. |
| Covers | no | What it applies to, in words. |
| Paths | no | Files or globs it governs. `--for` prints this ruling for any file they match. |
| Replaces | no | The ID(s) of the ruling(s) it replaces. |
| Tests | no | Test files that would fail if code broke it. Each must mention the ruling's ID, in any case, with `-` or `_` between the parts, e.g. `R-BILLING-004` or `R_BILLING_004`; for a glob, at least one matched file must. A directory or a file in docs/ is not a valid Tests item. |
| Enforced | no | `review` (any case), optionally followed by a note. For a judgment call no test can check; it is checked in review. |

Name a test after the ruling it enforces, e.g. `test_R_BILLING_004_invoices_are_never_deleted`, so a failure names the broken ruling. Test names can't contain hyphens, so the ID is written with underscores. The test must fail if code breaks the rule. Don't write a regex or text-matching check that pretends to enforce a judgment call; mark that ruling `Enforced: review` instead.

A ruling may have both Tests and `Enforced: review`: a test covers part of it and review covers the rest. It counts as tested, as long as its Tests pass the checker.

When a ruling is replaced, the old one stays, with this marker on the line right after it:

```markdown
**Replaced YYYY-MM-DD → R-<AREA>-<NNN>:** short note
```

A ruling followed by a `Replaced →` marker is history, not in force.

An example:

```markdown
- **R-SECURITY-001 · Ruled by owner 2026-01-15:** never look at secret
  values. No worker may see a secret's value: not in a secrets manager,
  command output, environment variables, files or logs. · **Covers:**
  every worker.
```

A ruling enforced by a test:

```markdown
- **R-BILLING-004 · Ruled by owner 2026-02-03:** invoices are never
  deleted, only voided. · **Paths:** `src/billing/**` · **Tests:**
  `tests/test_billing_rulings.py`
```

A judgment call, checked in review:

```markdown
- **R-UI-002 · Ruled by owner 2026-02-10:** error messages tell the user
  what to do next, not only what went wrong. · **Enforced:** review
```

## The validity rules (what the checker enforces)

1. The ID is unique across docs/.
2. Every ID in Replaces exists, and that ruling carries a Replaced → marker pointing back. The link must go both ways.
3. Every file in Paths or Tests exists; a glob must match at least one file, and nothing may point outside the repo. A Tests item must be a file outside docs/: a directory or a file in docs/ is an error, and a Tests glob ignores the files it matches in docs/.
4. Dates are real and not in the future.
5. The area is in the schema's list, and the ruling sits in that area's doc.
6. Every file in Tests mentions the ruling's ID, in any case, with `-` or `_` between the parts, e.g. `R-BILLING-004` or `R_BILLING_004`; for a glob, at least one matched file does. The ID must stand alone: `R-BILLING-0042` doesn't mention R-BILLING-004.
7. Enforced, if present, starts with the word `review`, in any case.
8. Every key in x-area-paths is an area, and every path in it exists; a glob must match at least one file, and nothing may point outside the repo.

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
  "x-area-paths": { "BILLING": ["src/billing/**"] },
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
    "tests": { "type": "array", "minItems": 1, "items": { "type": "string" } },
    "enforced": { "type": "string", "pattern": "^[Rr][Ee][Vv][Ii][Ee][Ww]\\b" }
  },
  "$defs": {
    "rulingId": { "type": "string", "pattern": "^R-(AI|BILLING|DEV|SECURITY|UI)-[0-9]{3}$" },
    "date": { "type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" }
  }
}
```

The area list appears three times: x-areas, the ID pattern and the doc list. The checker fails if they disagree, so nobody can invent an area.

x-area-paths is optional. It maps each area to the code it governs, so `--for` can find an area's rulings from a file path.

## The checker

`python3 scripts/check_rulings.py` (Python 3.8 or later, standard library only):

- Reads every docs/*.md except README.md and RULINGS.md, skipping code blocks.
- Pulls out each ruling, from its bold lead-in to the next blank line, list item, heading or lead-in, and splits it into the fields.
- Applies the validity rules and prints `docs/x.md:LINE  R-ID  message` for each problem. It exits with 1 if there are errors.
- Reports coverage. It prints a note for every in-force ruling (Ruled, not replaced) with neither Tests nor Enforced, and a line `Enforcement: T tested, V review-only, U not enforced (of K in-force rulings)`. A ruling counts as tested only if it has Tests and none of its Tests items has an error; one with both Tests and Enforced counts as tested. Each ID counts once. Notes never fail the build; that's the owner's choice, and it can be made strict later.
- Prints, in this order: the errors, the notes, the Enforcement line, and the summary N rulings in M docs, E errors.
- --json prints the extracted rulings, which match the schema.
- Looks rulings up. These read only the docs, never walk the repo, and take a fraction of a second. Run them from the repo root, or pass `--root <dir>`; a relative `--for` path is relative to the root. If docs/rulings.schema.json is missing or unreadable there, or there's no docs/, a lookup says so and exits with 2 instead of finding nothing.
  - `--for <file>` prints the rulings whose Paths match that file, plus the rulings of the areas whose x-area-paths match it. It may be repeated.
  - `--area <AREA>` prints the rulings of an area.
  - `--for` and `--area` print the rulings not replaced, of any kind: Ruled ones bind; Parked and Asked ones are shown for context, with their kind.
  - `--id <R-ID>` prints one ruling, even if it was replaced.
  - Use one per call. Each can be combined with --json. If the docs have problems the docs alone show (duplicate IDs, broken Replaced links, bad dates, wrong areas, malformed rulings), a lookup warns on stderr and still prints.
  - Exit codes: 0; 1 when `--id` finds nothing; 2 on a usage error or when no rulings are found at the root.
- Has its own tests that run against sample doc folders, never the real docs.

A reference implementation is in `reference/` of the owner-rulings repo, https://github.com/mardatasci/decision_record_rulings (or take the same files from a local clone of it); copy `scripts/check_rulings.py`, `tests/` (with `fixtures/`) and `docs/rulings.schema.json` rather than writing your own, then change the area list in the schema's three places (x-areas, the ID pattern, the doc enum) and set x-area-paths.

In CI it's its own step, at the end of the job, so it always runs and never hides other checks. Its own tests run in the step just before it:

```yaml
- name: Rulings checker tests pass
  run: python3 -m unittest discover -s tests

- name: Owner rulings are well-formed
  if: ${{ !cancelled() }}
  run: python3 scripts/check_rulings.py
```

The step needs Python; GitHub-hosted runners already have it. It is deliberately not in the repo's main check, which also gates deploys; a typo in a doc shouldn't block a production deploy.

The tests that enforce rulings are ordinary tests in the repo's main test suite, so a change that breaks a ruling fails like any other broken test. They therefore do gate deploys, on purpose: a build that breaks a ruling shouldn't ship. Only the format checker stays outside the deploy gate.

## Recording a new ruling: the /ruling skill

The procedure lives in docs/RULINGS.md, in its section "Recording a ruling", next to the format, so there is one copy for every tool. That section holds these steps:

1. Confirm. Say back the decision, its kind (Ruled, Parked or Asked), today's date, the area doc, and any earlier ruling it replaces. If the owner's words fit in one or two sentences, use them as is. Otherwise propose a condensed wording; the owner's approval of that wording makes it the ruling's text. Wait for the owner's yes.
2. Area. Pick it from `x-areas` in `docs/rulings.schema.json`. If none fits, stop and ask. Never invent an area.
3. ID. Take the next free number in that doc. Never reuse or renumber.
4. Place it next to related rulings in that doc.
5. Write it. Add Why, Covers or Paths only if the owner gave them or you checked them (paths exist).
6. Enforcement. For a Ruled ruling, propose either a test that would fail if code broke it, named after the ID (`test_R_BILLING_004_…`), or `· **Enforced:** review` if it is a judgment call no test can check. Wait for the owner's yes. Write the test, run it, and link it with `· **Tests:**`.
7. Replacements. Add `· **Replaces:** R-…` to the new ruling and `**Replaced YYYY-MM-DD → R-<new>:** note` on the line right after the old one. Never delete or reword the old ruling. If it contradicts a ruling the owner didn't mention, stop and ask.
8. Search docs/ for other statements it makes wrong. List them all in one numbered message and ask once; the owner may answer "all" or "all except #n". Mark each approved one "Replaced →". Never delete.
9. Run `python3 scripts/check_rulings.py` and the new test, fix only what you wrote, and show the output.
10. Stop. Do not commit unless the owner asks.

Only the owner makes rulings. A worker's proposal never becomes a ruling, and "the owner doesn't remember" never means "parked".

Claude Code finds skills in .claude/skills/ automatically. The owner types /ruling, or just says "record this" or "that's a ruling", and Claude follows it. The skill only points to that section. Full file, .claude/skills/ruling/SKILL.md:

```markdown
---
name: ruling
description: Record an owner decision as a ruling in the right docs/ area doc - next free ID, a test or review proposed to enforce it, replacements linked both ways, rulings checker run. Use when the owner rules, decides, parks or asks for something to be recorded ("record this", "that's a ruling", "park it").
---

# Record a ruling

## Who makes a ruling

Only the owner. Record a ruling only when the owner has decided, parked or
asked for something in this conversation, in the owner's words. Never turn a
worker's proposal, a subagent's finding or your own recommendation into a
ruling. If it is unclear whether the owner decided, ask. Only the owner
parks, and says so explicitly.

## Steps

Read `docs/RULINGS.md` and follow its section "Recording a ruling" step by
step.
```

## How we set it up (order of work)

1. Inventory every doc. Resolve conflicting decisions with the owner, one at a time.
2. Propose the areas, with the code each one governs (x-area-paths), and get the owner's approval, then create docs/README.md, docs/development.md (cross-cutting rulings only) and one doc per approved area.
3. Write each confirmed decision into its area doc as a ruling with an ID, and mark outdated statements "Replaced →" rather than deleting them.
4. For each Ruled ruling, propose a test that would fail if code broke it, or Enforced: review for a judgment call. One at a time; the owner approves each.
5. Copy the schema, the checker and its tests from reference/, and create docs/RULINGS.md (the format and the recording procedure).
6. Slim CLAUDE.md so it points to docs/, and add the --for rule.
7. Add CI.
8. Create the /ruling skill.

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
2. Propose the area list, with the code each area governs (x-area-paths). After I approve it, create or update (merge into, never replace) docs/README.md, docs/development.md (the cross-cutting rulings only) and one docs/<area>.md per approved area.
3. Write each decision I confirm as a ruling with an ID. Mark outdated statements "Replaced →"; never delete.
4. For each Ruled ruling, propose a test that would fail if code broke it (named after the ruling's ID) or Enforced: review for a judgment call, one at a time. After I approve one, write it and link it.
5. Copy the checker from the kit; don't write one from scratch: reference/scripts/check_rulings.py into scripts/, the contents of reference/tests/ into tests/ (so you end up with tests/test_check_rulings.py and tests/fixtures/), and reference/docs/rulings.schema.json into docs/. Then edit only x-areas, the ID pattern and the doc enum for this repo, and add the x-area-paths I approved. Its tests run on sample docs only. Keep the test folder and script folder as siblings: the copied test finds the script at ../scripts/check_rulings.py. If I choose another location, update the CI command and any later references to match. Every top-level docs/*.md other than README.md and RULINGS.md must be an area in x-areas; for each existing doc that isn't, ask me whether to make it an area or move it to a subfolder such as docs/notes/. Create docs/RULINGS.md with the ruling format, the field table and the section "Recording a ruling" (the recording procedure) from the guide; keep docs/development.md to the cross-cutting rulings only. If the repo has a JS/TS test runner, linter or type-checker, exclude tests/fixtures/ from it and show me the change. Then run python3 scripts/check_rulings.py and python3 -m unittest discover -s tests and show me both outputs.
6. Make CLAUDE.md short: @docs/development.md, a "Never miss these" list, and the --for and review rules from the guide's example CLAUDE.md.
7. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate. Also run python3 -m unittest discover -s tests in CI so the checker's own tests run. Make sure the repo's existing test suite runs the ruling tests; they're ordinary tests and gate deploys like any other test. Only the format checker stays outside the deploy gate.
8. Create the /ruling skill in .claude/skills/ruling/SKILL.md as shown in the guide; it points to the section "Recording a ruling" in docs/RULINGS.md.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code before asking about something that may already be settled.
```
