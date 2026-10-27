# Reference checker

A reference implementation of the owner-rulings checker described in the guides.

> **Disclaimer:** This code is provided as is, without warranty of any kind. Review it before you use it, and use it at your own discretion and risk. The author is not responsible for any outcome of using it. See the [MIT license](../LICENSE).

## Using it

1. Copy `scripts/check_rulings.py` and `tests/` into your repo.
2. Copy `docs/rulings.schema.json` into your `docs/` and change the area list (`x-areas`, the ID pattern and the `doc` enum) to your own areas. Optionally set `x-area-paths` to map each area to the code it governs, e.g. `"BILLING": ["src/billing/**"]`.
3. Run `python3 scripts/check_rulings.py` from your repo root. Options: `--root <dir>` (default: current directory), `--json`, and the lookups `--for <file>` (may repeat), `--area <AREA>` and `--id <R-ID>` (one kind per call).

It skips `docs/README.md` and `docs/RULINGS.md`. It prints, in this order: the errors, a note for every in-force ruling (Ruled, not replaced) with neither Tests nor Enforced, a line `Enforcement: T tested, V review-only, U not enforced (of K in-force rulings)`, and the summary `N rulings in M docs, E errors`. A ruling counts as tested only if it has Tests and none of its Tests items has an error; one with both Tests and Enforced counts as tested, and each ID counts once. Notes never fail the build. It exits with 1 if there are errors, else 0.

A Tests item must be a file outside `docs/`: a directory or a file in `docs/` is an error, and a Tests glob ignores the files it matches in `docs/`. Each Tests file must mention the ruling's ID in any case, with `-` or `_` between the parts (`R-BILLING-004`, `r_billing_004`), not inside a longer name or number (`R-BILLING-0042` doesn't count). `Enforced` must start with `review`, in any case.

Lookups read only the docs, never walk the repo, and take a fraction of a second. Run them from the repo root, or pass `--root <dir>`; a relative `--for` path is relative to the root. If there's no `docs/rulings.schema.json` or `docs/` there, a lookup says so and exits with 2 instead of finding nothing.

- `--for <file>` prints the rulings whose Paths match that file, plus the rulings of the areas whose `x-area-paths` match it.
- `--area <AREA>` prints the rulings of an area.
- `--for` and `--area` print the rulings not replaced, of any kind: Ruled ones bind; Parked and Asked ones are shown for context, with their kind.
- `--id <R-ID>` prints one ruling, even if it was replaced.

Each can be combined with `--json`. If the docs have problems the docs alone show (duplicate IDs, broken Replaced links, bad dates, wrong areas, malformed rulings), a lookup warns on stderr and still prints. Exit codes: 0; 1 when `--id` finds nothing; 2 on a usage error or when no rulings are found at the root.

Globs in Paths and Tests match files on disk (skipping `.git` and `node_modules`), so a glob that only matches gitignored build output passes locally but fails in CI.

Needs Python 3.8 or later; no dependencies (standard library only). Run its tests from this folder with `python3 -m unittest discover -s tests`.

Running `python3 scripts/check_rulings.py` inside this folder reports missing area docs, because it ships only the schema, not area docs. Run it in your own repo, or against a fixture: `python3 scripts/check_rulings.py --root tests/fixtures/valid`.
