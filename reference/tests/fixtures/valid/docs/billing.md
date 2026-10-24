# Billing

- **R-BILLING-001 · Ruled by owner 2026-02-01:** prices are in cents.
  **Replaced 2026-06-01 → R-BILLING-003:** merged into one money rule.
- **R-BILLING-002 · Ruled by owner 2026-02-02:** round half to even.
  **Replaced 2026-06-01 → R-BILLING-003:** merged into one money rule.
- **R-BILLING-003 · Ruled by owner 2026-06-01:** money is integer cents,
  rounded half to even. · **Replaces:** R-BILLING-001, R-BILLING-002
  · **Paths:** `src/lib/money.js`
