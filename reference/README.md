# Reference checker

A reference implementation of the owner-rulings checker described in the guides.

> **Disclaimer:** This code is provided as is, without warranty of any kind. Review it before you use it, and use it at your own discretion and risk. The author is not responsible for any outcome of using it. See the [MIT license](../LICENSE).

## Using it

1. Copy `scripts/check-rulings.mjs` and `tests/` into your repo.
2. Copy `docs/rulings.schema.json` into your `docs/` and change the area list (`x-areas`, the ID pattern and the `doc` enum) to your own areas.
3. Add `"check:rulings": "node scripts/check-rulings.mjs"` to your `package.json` scripts.
4. Run `npm run check:rulings`. Options: `--root <dir>` (default: current directory) and `--json`.

Globs in Paths and Tests match files on disk (skipping `.git` and `node_modules`), so a glob that only matches gitignored build output passes locally but fails in CI.

Needs Node 20 or later; no dependencies. Run its tests with `npm test`.

Running `npm run check:rulings` inside this folder reports missing area docs, because it ships only the schema, not area docs. Run it in your own repo, or against a fixture: `node scripts/check-rulings.mjs --root tests/fixtures/valid`.
