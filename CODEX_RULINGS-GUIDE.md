# Owner rulings: decision records that people and Codex follow

## The idea

A ruling is a decision made by the project owner, written into the doc for the area it decides. Once written, it is applied, never asked again, and never deleted.

- The owner decides. Everyone else is a worker: people and Codex. Workers investigate, propose, build and report. They never make or change a ruling.
- Rulings live inside the area docs. There's no file per decision. You read the area doc, say docs/billing.md, and get every billing rule at once.
- Nothing is deleted. A ruling that is overturned stays in place and gets a "Replaced →" marker pointing to the new one. A ruling followed by a `Replaced →` marker is history, not in force.
- Rulings are enforced. A ruling that code could break gets a test named after it; a judgment call no test can check is marked `Enforced: review` and checked in review.
- A checker runs in CI, so a broken or invented ruling fails the build.

## File layout

```text
AGENTS.md                        # entry point Codex reads every session; short, points to docs/
<folder>/AGENTS.md               # optional safety layer for a high-risk folder (e.g. infra/AGENTS.md)
docs/README.md                   # index of every area doc
docs/development.md              # cross-cutting rulings only; read every session
docs/RULINGS.md                  # the ruling format, its fields and the recording procedure
docs/<area>.md                   # one doc per area: ai.md, billing.md, security.md, ui.md …
docs/rulings.schema.json         # machine-readable schema + the fixed list of areas
scripts/check_rulings.py         # the checker
tests/test_check_rulings.py      # its tests (on sample docs, not the real ones)
tests/…                          # the tests that enforce rulings: ordinary tests
```

## How Codex finds the rulings

- AGENTS.md is read automatically, but it can't load other files the way CLAUDE.md can. So it tells Codex what to read, and copies only the few rules that must never be missed.
- Keep AGENTS.md short. Codex reads only a limited amount of it (around 32 KB by default, adjustable in Codex's config), so long text at the bottom can be cut off. Put the pointers and the hard rules at the top.
- docs/development.md is read every session, so it holds only the cross-cutting rulings. The format and the recording procedure are in docs/RULINGS.md, read only when a ruling is recorded.
- Before editing a file, Codex runs `python3 scripts/check_rulings.py --for <file>` from the repo root. It prints every ruling not replaced whose Paths match that file, plus every ruling not replaced of the areas whose x-area-paths match it. Ruled ones bind; Parked and Asked ones are shown for context. It reads only the docs, so it takes a fraction of a second.
- `--for` is the primary per-file lookup. Folder-level AGENTS.md files are an extra safety layer for a few high-risk folders: Codex reads them when it works in that folder, so their must-not-miss rulings load even if it forgets to run `--for`. For example, infra/AGENTS.md can say "Read docs/security.md before any change here."
- "The repository is the memory." Anything worth keeping goes into docs/, not into a chat or a private note.

Example top of AGENTS.md:

```markdown
## Documentation and owner rulings

- Before any work, read docs/README.md and docs/development.md.
- Rulings in docs/ apply and are not re-asked. Cross-cutting rulings are in
  docs/development.md; area rulings are in each area's doc. Read the doc for
  the area you are working in before acting. Only the owner may make, park
  or replace a ruling.
- Before editing a file, run `python3 scripts/check_rulings.py --for <file>`
  from the repo root; every Ruled ruling it prints applies.
- Before calling a change done, run `--for` on each changed file and check
  the diff against every printed ruling marked `Enforced: review`; run the
  tests listed in Tests.
- To record a ruling, read docs/RULINGS.md.
- Stage only the files of the approved change, by name; never `git add -A`.

## Never miss these

- Never look at a secret's value: not in a secrets manager, command output,
  environment variables, files or logs. If a step needs one, stop and tell
  the owner.
- Do only the task that is assigned.
```

Example infra/AGENTS.md:

```markdown
Read docs/security.md before any change in this folder. Its rulings apply.
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
| Paths | no | Files or globs it governs. `--for` prints this ruling for any file they match. For a high-risk folder, also put its must-not-miss rulings in a folder AGENTS.md. |
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

## Recording a new ruling

The procedure lives in docs/RULINGS.md, in its section "Recording a ruling", next to the format, so there is one copy for every tool and Codex reads it only when recording a ruling. AGENTS.md has the pointer: "To record a ruling, read docs/RULINGS.md." If your Codex version supports skills, a skill can point to that section too; check Codex's docs for the folder it uses. That section holds these steps:

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

## How we set it up (order of work)

1. Inventory every doc. Resolve conflicting decisions with the owner, one at a time.
2. Propose the areas, with the code each one governs (x-area-paths), and get the owner's approval, then create docs/README.md, docs/development.md (cross-cutting rulings only) and one doc per approved area.
3. Write each confirmed decision into its area doc as a ruling with an ID, and mark outdated statements "Replaced →" rather than deleting them.
4. For each Ruled ruling, propose a test that would fail if code broke it, or Enforced: review for a judgment call. One at a time; the owner approves each.
5. Copy the schema, the checker and its tests from reference/, and create docs/RULINGS.md (the format and the recording procedure).
6. Slim AGENTS.md so it points to docs/, keeping only the hard rules in it, and add the --for rule. Add folder AGENTS.md files for a few high-risk folders as a safety layer.
7. Add CI.
