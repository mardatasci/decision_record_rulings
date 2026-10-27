# Reference checker

A reference implementation of the owner-rulings checker described in the guides.

> **Disclaimer:** This code is provided as is, without warranty of any kind. Review it before you use it, and use it at your own discretion and risk. The author is not responsible for any outcome of using it. See the [MIT license](../LICENSE).

## Using it

1. Copy `scripts/check_rulings.py` and `tests/` into your repo.
2. Copy `docs/rulings.schema.json` into your `docs/` and change the area list (`x-areas`, the ID pattern and the `doc` enum) to your own areas. Optionally set `x-area-paths` to map each area to the code it governs, e.g. `"BILLING": ["src/billing/**"]`. Add `"x-quotes-since": "YYYY-MM-DD"` set to the day your repo adopts the quote rule; the shipped schema doesn't set it.
3. Run `python3 scripts/check_rulings.py` from your repo root. Options: `--root <dir>` (default: current directory), `--json`, and the lookups `--for <file>` (may repeat), `--area <AREA>` and `--id <R-ID>` (one kind per call).

It skips `README.md` and `RULINGS.md` in `docs/` and in `docs/history/`, and also reads every other `.md` file in `docs/history/` as a history file. It prints, in this order: the errors, then a note if x-quotes-since is not set, a note for every in-force ruling (Ruled, not replaced) with neither Tests nor Enforced, a line `Enforcement: T tested, V review-only, U not enforced (of K in-force rulings)`, and the summary: `N rulings in M docs, E errors`, or `N rulings in M docs (H history files), E errors` when there are history files. N counts every ruling, in area docs and history files; M counts area docs only. A ruling counts as tested only if it has Tests and none of its Tests items has an error; one with both Tests and Enforced counts as tested, and each ID counts once. Notes never fail the build. It exits with 1 if there are errors, else 0.

A Tests item must be a file outside `docs/`: a directory or a file in `docs/` is an error, and a Tests glob ignores the files it matches in `docs/`. Each Tests file must mention the ruling's ID in any case, with `-` or `_` between the parts (`R-BILLING-004`, `r_billing_004`), not inside a longer name or number (`R-BILLING-0042` doesn't count). `Enforced` must start with `review`, in any case.

Area docs hold only rulings in force. A replaced ruling moves, unchanged, to `docs/history/<name>.md` for its area doc `docs/<name>.md`, with its `Replaced YYYY-MM-DD → R-…:` marker on the line right after it; the new ruling in the area doc lists `Replaces: R-…`. A replaced ruling left in an area doc is an error, and so is a ruling in a history file without a Replaced marker. A history file must match an area doc in `x-areas`. A ruling sits in its area's doc or that doc's history file, and IDs are unique across both, so the next free number is counted across the two. Coverage counts only in-force rulings, never replaced ones. The Paths and Tests of a replaced ruling are not checked on disk: history is never reworded, so it must not fail when code moves. Its Source still is.

`Source` is optional: exactly one file, not a glob, in `docs/owner-words/`. It must exist, resolve (after symlinks) to a file in `docs/owner-words/`, and mention the ruling's ID, matched the same way as Tests. An owner-words file keeps the owner's longer context in their exact words, add-only, under headings like `## R-BILLING-004 · 2026-02-03`.

`x-quotes-since` is optional. If set, it must be a real date, not in the future. Every ruling dated on or after it, of any kind, in area docs or history files, must have a quoted decision: it starts with `"` or `“` and ends with `"` or `”`, optionally followed by one period, and has at least one non-space character between the quotes. Its `Why`, if present, must be quoted the same way. Older rulings aren't checked. Without `x-quotes-since`, the checker prints a note that quotes aren't checked.

Fields go in this order: Why, Covers, Paths, Replaces, Tests, Enforced, Source.

Lookups read only the docs, never walk the repo, and take a fraction of a second. Run them from the repo root, or pass `--root <dir>`; a relative `--for` path is relative to the root. If there's no `docs/rulings.schema.json` or `docs/` there, a lookup says so and exits with 2 instead of finding nothing.

- `--for <file>` prints the rulings whose Paths match that file, plus the rulings of the areas whose `x-area-paths` match it.
- `--area <AREA>` prints the rulings in force of an area.
- `--for` and `--area` print only rulings in force: in an area doc, not a history file, and not replaced. They print every kind: Ruled ones bind; Parked and Asked ones are shown for context, with their kind.
- `--id <R-ID>` prints one ruling wherever it is, including a replaced one in a history file.
- Lookups print a ruling's quote, then its other fields. They show its Source, so an agent knows where the owner's words are.

Each can be combined with `--json`. In JSON, `doc` is the ruling's area doc and `file` is the file it actually sits in, the area doc or its history file. If the docs have problems the docs alone show, a lookup warns on stderr with their count and still prints. Those are: duplicate IDs, broken Replaced links, bad dates, unknown areas, a ruling in the wrong file (another area's doc, a replaced ruling left in an area doc, or a ruling in a history file without a Replaced marker), missing owner quotes (an unquoted decision or Why on a ruling dated on or after x-quotes-since), malformed rulings, fields and Replaced markers (including an Enforced that doesn't start with `review`, and a Source that isn't one backtick-quoted file in `docs/owner-words/`), unclosed code fences, and schema problems (area lists that disagree, a bad x-area-paths, a bad x-quotes-since, a doc without an area, an area without a doc, a history file without an area doc). Lookups never check files on disk; the full check does. Exit codes: 0; 1 when `--id` finds nothing; 2 on a usage error or when no rulings are found at the root.

Globs in Paths and Tests match files on disk (skipping `.git` and `node_modules`), so a glob that only matches gitignored build output passes locally but fails in CI.

Needs Python 3.8 or later; no dependencies (standard library only). Run its tests from this folder with `python3 -m unittest discover -s tests`.

Running `python3 scripts/check_rulings.py` inside this folder reports missing area docs, because it ships only the schema, not area docs. Run it in your own repo, or against a fixture: `python3 scripts/check_rulings.py --root tests/fixtures/valid`.
