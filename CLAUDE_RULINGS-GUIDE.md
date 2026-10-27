# Owner rulings: decision records that people and Claude follow

## The idea

A ruling is a decision made by the project owner, written into the doc for the area it decides. Once written, it is applied, never asked again, and never deleted.

- The owner decides. Everyone else is a worker: people, Claude Code and its subagents. Workers investigate, propose, build and report. They never make or change a ruling.
- Rulings live inside the area docs. There's no file per decision. You read the area doc, say docs/billing.md, and get every billing rule at once.
- Area docs hold only the rulings in force, so an agent reading one sees only rules that apply.
- Nothing is deleted. A ruling that is overturned moves, unchanged, to the area's history file, docs/history/<area>.md, with a "Replaced →" marker pointing to the new one. A ruling followed by a `Replaced →` marker is history, not in force.
- A ruling's decision is the owner's exact words, in quotes. AI never writes or rewords it. Approving AI rewrites all day causes drift and is more work, and it gets hard to recognise a ruling as your own or to trace your original thinking. A messy exact quote is easy to recognise as yours. The owner only checks that a quote is theirs.
- A ruling holds only the owner's words and facts the AI checked: Covers, Paths, Replaces, Tests, Enforced and Source, and the note on a Replaced marker. The AI never restates the decision in its own words.
- Longer context is kept word for word. When the owner said more than the quote, those words go in docs/owner-words/<area>.md, which is only ever added to, and the ruling links them with Source.
- Rulings are enforced. A ruling that code could break gets a test named after it; a judgment call no test can check is marked `Enforced: review` and checked in review.
- A checker runs in CI, so a broken or invented ruling fails the build.

## File layout

```text
CLAUDE.md                        # short entry point; loads docs/development.md with @import
docs/README.md                   # index of every area doc
docs/development.md              # cross-cutting rulings only; loaded every session
docs/RULINGS.md                  # the ruling format, its fields and the recording procedure
docs/<area>.md                   # one doc per area: ai.md, billing.md, security.md, ui.md …
docs/history/<area>.md           # that area's replaced rulings, each with its Replaced → marker
docs/owner-words/<area>.md       # the owner's exact words for that area; add-only
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
- Before editing a file, Claude runs `python3 scripts/check_rulings.py --for <file>` from the repo root. It prints every ruling in force whose Paths match that file, plus every ruling in force of the areas whose x-area-paths match it. Ruled ones bind; Parked and Asked ones are shown for context. It reads only the docs, so it takes a fraction of a second.
- `--for` shows only rulings in force, never a replaced one or one in a history file, so Claude sees only rules in force. A lookup shows a ruling's Source; Claude follows the ruling and opens its owner words in docs/owner-words/ only when the ruling is unclear.
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
**R-<AREA>-<NNN> · Ruled by owner YYYY-MM-DD:** "the owner's exact words."
· **Why:** "…" · **Covers:** … · **Paths:** `src/…`
· **Replaces:** R-<AREA>-<NNN> · **Tests:** `tests/….test.js`
· **Enforced:** review · **Source:** `docs/owner-words/<area>.md`
```

| Field | Required | Rule |
| --- | --- | --- |
| ID | yes | `R-<AREA>-<NNN>`. The area must be in the schema's list, and each area is one doc. Each new ruling takes the next free number, counted across its area doc and that doc's history file. Never reused, never renumbered. |
| Kind | yes | Ruled by owner (a decision), Parked by owner (deferred on purpose) or Asked by owner (a request). |
| Date | yes | The day the owner decided. |
| Decision | yes | The owner's exact words, in quotes, copied character for character. Never written or reworded by AI. |
| Why | no | The owner's reason in their words, in quotes, only if the owner gave one. |
| Covers | no | What it applies to, in words. |
| Paths | no | Files or globs it governs. `--for` prints this ruling for any file they match. |
| Replaces | no | The ID(s) of the ruling(s) it replaces. |
| Tests | no | Test files that would fail if code broke it. Each must mention the ruling's ID, in any case, with `-` or `_` between the parts, e.g. `R-BILLING-004` or `R_BILLING_004`; for a glob, at least one matched file must. A directory or a file in docs/ is not a valid Tests item. |
| Enforced | no | `review` (any case), optionally followed by a note. For a judgment call no test can check; it is checked in review. |
| Source | no | The owner-words file with the owner's longer context, word for word: one file, not a glob, in docs/owner-words/. It must mention the ruling's ID, matched the same way as Tests. |

The fields go in this order: Why, Covers, Paths, Replaces, Tests, Enforced, Source.

A quote starts with `"` or `“` and ends with `"` or `”`, optionally followed by one period. The checker requires it on every ruling dated on or after the schema's `x-quotes-since`, of any kind, in area docs and history files, and on its Why. Older rulings aren't checked and stay as they were: their original words can't be recovered. A ruling without quote marks was decided before x-quotes-since (or the repo hasn't set it). The quote needs at least one non-space character (rule 12). Quote marks alone don't prove the words are the owner's; the owner confirming the quote does.

Name a test after the ruling it enforces, e.g. `test_R_BILLING_004_invoices_are_never_deleted`, so a failure names the broken ruling. Test names can't contain hyphens, so the ID is written with underscores. The test must fail if code breaks the rule. Don't write a regex or text-matching check that pretends to enforce a judgment call; mark that ruling `Enforced: review` instead.

A ruling may have both Tests and `Enforced: review`: a test covers part of it and review covers the rest. It counts as tested, as long as its Tests pass the checker.

Area docs hold only the rulings in force. When a ruling is replaced, the old one moves from its area doc, docs/<area>.md, to that doc's history file, docs/history/<area>.md. It is never deleted and never reworded. This marker goes on the line right after it:

```markdown
**Replaced YYYY-MM-DD → R-<AREA>-<NNN>:** short note
```

A ruling followed by a `Replaced →` marker is history, not in force. The new ruling sits in the area doc and lists `Replaces: R-…`. The old ID stays taken: the next free number is counted across the area doc and its history file.

Longer context in the owner's exact words goes in docs/owner-words/<area>.md, one file per area doc. Entries are only appended, never edited or removed, even when a ruling is later replaced. An entry:

```markdown
## R-BILLING-004 · 2026-02-03

> exact words of the owner, as said
```

The ruling links it with `` · **Source:** `docs/owner-words/billing.md` ``. Workers follow the ruling and open the owner words only when the ruling is unclear.

An example:

```markdown
- **R-SECURITY-001 · Ruled by owner 2026-01-15:** "never look at secret
  values. No worker may see a secret's value: not in a secrets manager,
  command output, environment variables, files or logs." · **Covers:**
  every worker.
```

A ruling enforced by a test:

```markdown
- **R-BILLING-004 · Ruled by owner 2026-02-03:** "invoices are never
  deleted, only voided." · **Paths:** `src/billing/**` · **Tests:**
  `tests/test_billing_rulings.py`
```

A judgment call, checked in review:

```markdown
- **R-UI-002 · Ruled by owner 2026-02-10:** "error messages tell the
  user what to do next, not only what went wrong." · **Enforced:** review
```

## The validity rules (what the checker enforces)

1. The ID is unique across all area docs and history files.
2. Every ID in Replaces exists, and that ruling carries a Replaced → marker pointing back. The link must go both ways.
3. Every file in Paths or Tests exists; a glob must match at least one file, and nothing may point outside the repo. A Tests item must be a file outside docs/: a directory or a file in docs/ is an error, and a Tests glob ignores the files it matches in docs/. This rule and rule 6 skip replaced rulings: history is never reworded, so it must not fail when code moves. Their Source is still checked (rule 11).
4. Dates are real and not in the future.
5. The area is in the schema's list, and the ruling sits in that area's doc or that doc's history file.
6. Every file in Tests mentions the ruling's ID, in any case, with `-` or `_` between the parts, e.g. `R-BILLING-004` or `R_BILLING_004`; for a glob, at least one matched file does. The ID must stand alone: `R-BILLING-0042` doesn't mention R-BILLING-004.
7. Enforced, if present, starts with the word `review`, in any case.
8. Every key in x-area-paths is an area, and every path in it exists; a glob must match at least one file, and nothing may point outside the repo.
9. A replaced ruling sits in its history file: a ruling with a Replaced → marker left in an area doc is an error, and so is a ruling in a history file without one.
10. Every history file, docs/history/<name>.md, matches an area doc, docs/<name>.md, in x-areas.
11. Source, if present, is exactly one file, not a glob, in docs/owner-words/. It exists, resolves (after symlinks) to a file in docs/owner-words/, and mentions the ruling's ID, matched the same way as Tests. This holds for replaced rulings too.
12. If the schema sets `x-quotes-since`, it is a real date, not in the future. Every ruling dated on or after it, of any kind, in area docs or history files, has a quoted decision: it starts with `"` or `“` and ends with `"` or `”`, optionally followed by one period, and has at least one non-space character between the quotes. Its Why, if present, is quoted the same way. Older rulings aren't checked. Without `x-quotes-since`, the checker prints a note that quotes aren't checked.

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
  "x-quotes-since": "2026-10-26",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "kind", "date", "decision", "doc", "file", "line"],
  "properties": {
    "id": { "$ref": "#/$defs/rulingId" },
    "kind": { "enum": ["ruled", "parked", "asked"] },
    "date": { "$ref": "#/$defs/date" },
    "doc": { "enum": ["docs/ai.md", "docs/billing.md", "docs/development.md", "docs/security.md", "docs/ui.md"] },
    "file": { "type": "string", "pattern": "^docs/(history/)?[^/]+\\.md$" },
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
    "enforced": { "type": "string", "pattern": "^[Rr][Ee][Vv][Ii][Ee][Ww]\\b" },
    "source": { "type": "string", "pattern": "^docs/owner-words/[^/]+\\.md$" }
  },
  "$defs": {
    "rulingId": { "type": "string", "pattern": "^R-(AI|BILLING|DEV|SECURITY|UI)-[0-9]{3}$" },
    "date": { "type": "string", "format": "date", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" }
  }
}
```

The area list appears three times: x-areas, the ID pattern and the doc list. The checker fails if they disagree, so nobody can invent an area.

x-area-paths is optional. It maps each area to the code it governs, so `--for` can find an area's rulings from a file path.

x-quotes-since is the day the repo adopted the quote rule. Each repo sets its own date, at setup or upgrade. Rulings dated on or after it must be quoted (rule 12).

## The checker

`python3 scripts/check_rulings.py` (Python 3.8 or later, standard library only):

- Reads every docs/*.md except README.md and RULINGS.md, and every history file docs/history/*.md, where README.md and RULINGS.md are skipped too, skipping code blocks.
- Pulls out each ruling, from its bold lead-in to the next blank line, list item, heading or lead-in, and splits it into the fields.
- Applies the validity rules and prints `docs/x.md:LINE  R-ID  message` for each problem. It exits with 1 if there are errors.
- Checks quotes from x-quotes-since on (rule 12). If the schema has no x-quotes-since, it prints a note that quotes aren't checked.
- Reports coverage. It prints a note for every in-force ruling (Ruled, not replaced) with neither Tests nor Enforced, and a line `Enforcement: T tested, V review-only, U not enforced (of K in-force rulings)`. A ruling counts as tested only if it has Tests and none of its Tests items has an error; one with both Tests and Enforced counts as tested. Each ID counts once. Notes never fail the build; that's the owner's choice, and it can be made strict later.
- Prints, in this order: the errors, the notes, the Enforcement line, and the summary: `N rulings in M docs, E errors`, or `N rulings in M docs (H history files), E errors` when there are history files. N counts every ruling, in area docs and history files; M counts area docs only.
- --json prints the extracted rulings, which match the schema. `doc` is the area doc; `file` is the file the ruling actually sits in, the area doc or its history file.
- Looks rulings up. These read only the docs, never walk the repo, and take a fraction of a second. Run them from the repo root, or pass `--root <dir>`; a relative `--for` path is relative to the root. If docs/rulings.schema.json is missing or unreadable there, or there's no docs/, a lookup says so and exits with 2 instead of finding nothing.
  - `--for <file>` prints the rulings whose Paths match that file, plus the rulings of the areas whose x-area-paths match it. It may be repeated.
  - `--area <AREA>` prints the rulings in force of an area.
  - `--for` and `--area` print only rulings in force: in an area doc, not a history file, and not replaced. They print every kind: Ruled ones bind; Parked and Asked ones are shown for context, with their kind.
  - `--id <R-ID>` prints one ruling wherever it is, including a replaced one in a history file.
  - Lookups print a ruling's quote, then its other fields. They show its Source, so a worker knows where the owner's words are.
  - Use one per call. Each can be combined with --json. If the docs have problems the docs alone show, a lookup warns on stderr with their count and still prints. Those are: duplicate IDs, broken Replaced links, bad dates, unknown areas, a ruling in the wrong file (another area's doc, a replaced ruling left in an area doc, or a ruling in a history file without a Replaced marker), missing owner quotes (an unquoted decision or Why on a ruling dated on or after x-quotes-since), malformed rulings, fields and Replaced markers (including an Enforced that doesn't start with `review`, and a Source that isn't one backtick-quoted file in docs/owner-words/), unclosed code fences, and schema problems (area lists that disagree, a bad x-area-paths, a bad x-quotes-since, a doc without an area, an area without a doc, a history file without an area doc). Lookups never check files on disk; the full check does.
  - Exit codes: 0; 1 when `--id` finds nothing; 2 on a usage error or when no rulings are found at the root.
- Has its own tests that run against sample doc folders, never the real docs.

A reference implementation is in `reference/` of the owner-rulings repo, https://github.com/mardatasci/decision_record_rulings (or take the same files from a local clone of it); copy `scripts/check_rulings.py`, `tests/` (with `fixtures/`) and `docs/rulings.schema.json` rather than writing your own, then change the area list in the schema's three places (x-areas, the ID pattern, the doc enum), set x-area-paths, and add x-quotes-since: the day the repo adopts the quote rule (in setup, the date noted in step 1).

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

1. Confirm. Show the owner the exact words you'll quote, copied character for character from what they said, typos included. You may leave out surrounding words that aren't part of the decision, marked with …, but never change, add or reorder a word. Never propose a rewording. Also show its kind (Ruled, Parked or Asked), today's date, the area doc, and any earlier ruling it replaces. Ask "Is this quote yours, and is the area right?" and wait for the owner's yes.
2. Area. Pick it from `x-areas` in `docs/rulings.schema.json`. If none fits, stop and ask. Never invent an area.
3. ID. Take the next free number, counted across that doc and its history file. Never reuse or renumber.
4. Place it next to related rulings in that doc.
5. Write it. The decision is the quote; never restate it or add your own wording. Add Why only if the owner gave a reason, quoted in their words. Everything else you add is a fact you checked: Covers or Paths only if the owner gave them or you checked them (paths exist), and Replaces, Tests, Enforced and Source, and the note on a Replaced marker, as described here. Put longer surrounding context in docs/owner-words/<area>.md, word for word, under the ruling's ID and date, and link it with `` · **Source:** `docs/owner-words/<area>.md` ``.
6. Enforcement. For a Ruled ruling, propose either a test that would fail if code broke it, named after the ID (`test_R_BILLING_004_…`), or `· **Enforced:** review` if it is a judgment call no test can check. Wait for the owner's yes. Write the test, run it, and link it with `· **Tests:**`.
7. Replacements. Add `· **Replaces:** R-…` to the new ruling. Move the old ruling to docs/history/<area>.md (create it if needed), with `**Replaced YYYY-MM-DD → R-<new>:** note` on the line right after it. Never delete or reword the old ruling, and never edit owner words. If it contradicts a ruling the owner didn't mention, stop and ask.
8. Search docs/ for all text it makes wrong, rulings and other text. List it all in one numbered message and ask once; the owner may answer "all" or "all except #n". For each approved item: if it is a ruling, replace it as in step 7; if it is other text, correct it as approved. Never delete a ruling or an owner-words entry.
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

1. Inventory every doc. Resolve conflicting decisions with the owner, one at a time. Note today's date; it becomes x-quotes-since when the schema is created in step 5.
2. Propose the areas, with the code each one governs (x-area-paths), and get the owner's approval, then create docs/README.md, docs/development.md (cross-cutting rulings only) and one doc per approved area.
3. Write each confirmed decision into its area doc as a ruling with an ID. If the doc text is the owner's own words, quote it exactly. Otherwise date the ruling with its original decision date, and leave it unquoted only if that date is before x-quotes-since (the date noted in step 1); if it isn't, ask the owner to state the decision so it can be quoted. If a decision's original date isn't in the docs or git history, ask the owner; never guess. Show the owner each quote and ask whether it's theirs, as in recording step 1. Never present AI wording as the owner's. Put longer context in the owner's words in docs/owner-words/<area>.md and link it with Source. Rulings that are already outdated go into docs/history/<area>.md with Replaced → markers, each with the ruling in force that replaces it listing it in Replaces; if no ruling replaces one, ask the owner. Never delete them.
4. For each Ruled ruling, propose a test that would fail if code broke it, or Enforced: review for a judgment call. One at a time; the owner approves each.
5. Copy the schema, the checker and its tests from reference/, set x-quotes-since in the schema to the date noted in step 1, and create docs/RULINGS.md (the format and the recording procedure). Also check existing docs/history/ and docs/owner-words/ folders; if they hold files that aren't ruling history or owner words, ask the owner how to handle them (for example, move them to docs/notes/).
6. Slim CLAUDE.md so it points to docs/, and add the --for rule.
7. Add CI.
8. Create the /ruling skill.

Starter prompt to paste into Claude Code:

```text
Owner-rulings repo: https://github.com/mardatasci/decision_record_rulings (branch main)
(To use a local clone instead, replace everything after "Owner-rulings repo:" with its absolute path before pasting.)

Set up owner rulings in this repo using the owner-rulings repo above. Before you start:

- If the current directory is the owner-rulings repo itself (it contains STARTER_PROMPT_CLAUDE.md and reference/scripts/check_rulings.py), stop, ask me for the path to the target repo and work there. Never set up rulings inside the owner-rulings repo.
- If the owner-rulings repo location is a local path, use it. Otherwise shallow-clone it into a new temporary directory outside this repo (`mktemp -d`, then `git clone --depth 1 --branch main <owner-rulings repo location> <that dir>`) and use that clone. Keep it until the last step is approved, then delete only that directory. If cloning isn't possible, stop and ask me for the path to a local clone. Read CLAUDE_RULINGS-GUIDE.md from the owner-rulings repo first; it describes the whole setup.
- Before changing anything, check whether this repo already has CLAUDE.md, docs/, docs/history/, docs/owner-words/, scripts/, tests/, .claude/skills/ or CI config. If docs/history/ or docs/owner-words/ exist and hold files that aren't rulings history or owner words, ask me how to handle them (for example, move them to docs/notes/). Merge into existing files instead of overwriting them, and show me the proposed changes to any existing file before writing it. If tests/ or scripts/ already exist, ask me before placing the checker files there.

Work one step at a time and wait for my approval between steps:

1. Inventory the docs and list every decision you find, with any that conflict. Don't change anything yet. Note today's date; it becomes x-quotes-since when the schema is created in step 5.
2. Propose the area list, with the code each area governs (x-area-paths). After I approve it, create or update (merge into, never replace) docs/README.md, docs/development.md (the cross-cutting rulings only) and one docs/<area>.md per approved area.
3. Write each decision I confirm as a ruling with an ID. If the doc text is my own words, quote it exactly. Otherwise date the ruling with its original decision date, and leave it unquoted only if that date is before x-quotes-since (the date noted in step 1); if it isn't, ask me to state the decision so you can quote it. If a decision's original date isn't in the docs or git history, ask me; never guess. Show me each quote and ask whether it's mine, as in recording step 1. Never present your wording as mine. Put longer context in my exact words in docs/owner-words/<area>.md and link it with Source. Put rulings that are already outdated into docs/history/<area>.md with Replaced → markers, each with the ruling in force that replaces it listing it in Replaces; if no ruling replaces one, ask me. Never delete them.
4. For each Ruled ruling, propose a test that would fail if code broke it (named after the ruling's ID) or Enforced: review for a judgment call, one at a time. After I approve one, write it and link it.
5. Copy the checker from the owner-rulings repo; don't write one from scratch: reference/scripts/check_rulings.py into scripts/, the contents of reference/tests/ into tests/ (so you end up with tests/test_check_rulings.py and tests/fixtures/), and reference/docs/rulings.schema.json into docs/. Then edit only x-areas, the ID pattern and the doc enum for this repo, add the x-area-paths I approved, and add "x-quotes-since" set to the date noted in step 1. Its tests run on sample docs only. Keep the test folder and script folder as siblings: the copied test finds the script at ../scripts/check_rulings.py. If I choose another location, update the CI command and any later references to match. Every top-level docs/*.md other than README.md and RULINGS.md must be an area in x-areas; for each existing doc that isn't, ask me whether to make it an area or move it to a subfolder such as docs/notes/. docs/history/ may hold only history files of area docs (plus README.md and RULINGS.md) and docs/owner-words/ only owner words; for each existing file there that isn't one, ask me how to handle it, for example move it to docs/notes/. Create docs/RULINGS.md with the ruling format, the field table and the section "Recording a ruling" (the recording procedure) from the guide; keep docs/development.md to the cross-cutting rulings only. If the repo has a JS/TS test runner, linter or type-checker, exclude tests/fixtures/ from it and show me the change. Then run python3 scripts/check_rulings.py and python3 -m unittest discover -s tests and show me both outputs.
6. Make CLAUDE.md short: @docs/development.md, a "Never miss these" list, and the --for and review rules from the guide's example CLAUDE.md.
7. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate. Also run python3 -m unittest discover -s tests in CI so the checker's own tests run. Make sure the repo's existing test suite runs the ruling tests; they're ordinary tests and gate deploys like any other test. Only the format checker stays outside the deploy gate.
8. Create the /ruling skill in .claude/skills/ruling/SKILL.md as shown in the guide; it points to the section "Recording a ruling" in docs/RULINGS.md.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code before asking about something that may already be settled.
```
