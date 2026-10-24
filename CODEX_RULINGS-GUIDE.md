# Owner rulings: decision records that people and Codex follow

## The idea

A ruling is a decision made by the project owner, written into the doc for the area it decides. Once written, it is applied, never asked again, and never deleted.

- The owner decides. Everyone else is a worker: people and Codex. Workers investigate, propose, build and report. They never make or change a ruling.
- Rulings live inside the area docs. There's no file per decision. You read the area doc, say docs/billing.md, and get every billing rule at once.
- Nothing is deleted. A ruling that is overturned stays in place and gets a "Replaced →" marker pointing to the new one.
- A checker runs in CI, so a broken or invented ruling fails the build.

## File layout

```text
AGENTS.md                        # entry point Codex reads every session; short, points to docs/
<folder>/AGENTS.md               # optional: extra pointers for one folder (e.g. infra/AGENTS.md)
docs/README.md                   # index of every area doc
docs/development.md              # cross-cutting rulings + the ruling format
docs/<area>.md                   # one doc per area: ai.md, billing.md, security.md, ui.md …
docs/rulings.schema.json         # machine-readable schema + the fixed list of areas
scripts/check_rulings.py         # the checker
tests/test_check_rulings.py      # its tests (on sample docs, not the real ones)
```

## How Codex finds the rulings

- AGENTS.md is read automatically, but it can't load other files the way CLAUDE.md can. So it tells Codex what to read, and copies only the few rules that must never be missed.
- Keep AGENTS.md short. Codex reads only a limited amount of it (around 32 KB by default, adjustable in Codex's config), so long text at the bottom can be cut off. Put the pointers and the hard rules at the top.
- Folder-level AGENTS.md files apply when Codex works in that folder. They're Codex's way of doing the Paths field. For example, infra/AGENTS.md can say "Read docs/security.md before any change here."
- "The repository is the memory." Anything worth keeping goes into docs/, not into a chat or a private note.

Example top of AGENTS.md:

```markdown
## Documentation and owner rulings

- Before any work, read docs/README.md and docs/development.md.
- Rulings in docs/ apply and are not re-asked. Cross-cutting rulings are in
  docs/development.md; area rulings are in each area's doc. Read the doc for
  the area you are working in before acting. Only the owner may make, park
  or replace a ruling.
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
| Paths | no | Files or globs it governs. Mirror the important ones with a folder AGENTS.md. |
| Replaces | no | The ID(s) of the ruling(s) it replaces. |
| Tests | no | Test files or an npm run script that check it. |

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
3. Every file in Paths or Tests exists; a glob must match at least one file, and nothing may point outside the repo. npm run X must be a real script.
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

A reference implementation is in `reference/` of the owner-rulings repo; copy `scripts/check_rulings.py` and its tests rather than writing your own, then change the area list in the schema.

In CI it's its own step, at the end of the job, so it always runs and never hides other checks:

```yaml
- name: Owner rulings are well-formed
  if: ${{ !cancelled() }}
  run: python3 scripts/check_rulings.py
```

The step needs Python; GitHub-hosted runners already have it. It is deliberately not in the repo's main check, which also gates deploys; a typo in a doc shouldn't block a production deploy.

## Recording a new ruling

The procedure lives in docs/development.md, under the format, so it's in one place and Codex reads it whenever it reads that file. Add a short pointer in AGENTS.md: "To record a ruling, follow 'Recording a ruling' in docs/development.md." If your Codex version supports skills, the same text can also become a skill; check Codex's docs for the folder it uses.

The procedure:

1. Confirm. Say the decision back in plain words, with its kind, date and area doc, and wait for the owner's yes.
2. Area. Pick it from the schema's list. If none fits, stop and ask; never invent one.
3. ID. The next free number in that doc.
4. Place it next to related rulings.
5. Write it in the owner's words. Add Why, Covers, Paths or Tests only if the owner gave them or they've been checked.
6. Replacements. Link both ways. Never delete or reword the old ruling.
7. Other statements the ruling makes wrong. List them and ask before marking each one "Replaced →".
8. Check. Run python3 scripts/check_rulings.py and show the owner the result.
9. Stop. Never commit unless asked.

Only the owner makes rulings. A worker's proposal never becomes a ruling, and "the owner doesn't remember" never means "parked".

## How we set it up (order of work)

1. Inventory every doc. Resolve conflicting decisions with the owner, one at a time.
2. Write each decision into its area doc, and mark outdated statements "Replaced →" rather than deleting them.
3. Slim AGENTS.md so it points to docs/, keeping only the hard rules in it, and add folder AGENTS.md files for high-risk folders.
4. Add IDs, then the schema, then the checker, then CI, then the recording procedure.
