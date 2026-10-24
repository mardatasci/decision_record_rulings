# Development

How we work.

## Rulings

- **R-DEV-001 · Ruled by owner 2026-01-10:** run the tests before every push.
  · **Why:** CI minutes are limited. · **Covers:** every worker.
  · **Paths:** `src/**/*.js`, `src/app.js` · **Tests:** `tests/dev.test.js`, `scripts/pre-push.sh`
  **Replaced 2026-03-01 → R-DEV-002:** a pre-push hook runs them now.
- **R-DEV-002 · Ruled by owner 2026-03-01:** a pre-push hook runs the tests.
  · **Replaces:** R-DEV-001 · **Paths:** `scripts/pre-push.sh`

**R-DEV-003 · Parked by owner 2026-04-02:** a staging environment, until
we have paying users.

**R-DEV-004 · Asked by owner 2026-05-05:** keep single-letter modules
small. · **Paths:** `src/?.js`
