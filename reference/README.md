# Reference checker

A reference implementation of the owner-rulings checker described in the guides.

> **Disclaimer:** This code is provided as is, without warranty of any kind. Review it before you use it, and use it at your own discretion and risk. The author is not responsible for any outcome of using it. See the [MIT license](../LICENSE).

## Using it

1. Copy `scripts/check_rulings.py` and `tests/` into your repo.
2. Copy `docs/rulings.schema.json` into your `docs/` and change the area list (`x-areas`, the ID pattern and the `doc` enum) to your own areas.
3. Run `python3 scripts/check_rulings.py` from your repo root. Options: `--root <dir>` (default: current directory) and `--json`.

Globs in Paths and Tests match files on disk (skipping `.git` and `node_modules`), so a glob that only matches gitignored build output passes locally but fails in CI.

Needs Python 3.8 or later; no dependencies (standard library only). Run its tests from this folder with `python3 -m unittest discover -s tests`.

In a JavaScript project you can add a `package.json` script that calls `python3 scripts/check_rulings.py`.

Running `python3 scripts/check_rulings.py` inside this folder reports missing area docs, because it ships only the schema, not area docs. Run it in your own repo, or against a fixture: `python3 scripts/check_rulings.py --root tests/fixtures/valid`.
