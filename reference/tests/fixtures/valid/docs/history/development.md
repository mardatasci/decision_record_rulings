# Development: replaced rulings

- **R-DEV-001 · Ruled by owner 2026-01-10:** run the tests before every push.
  · **Why:** CI minutes are limited. · **Covers:** every worker.
  · **Paths:** `src/**/*.js`, `src/app.js` · **Tests:** `tests/dev.test.js`, `scripts/pre-push.sh`
  **Replaced 2026-03-01 → R-DEV-002:** a pre-push hook runs them now.
