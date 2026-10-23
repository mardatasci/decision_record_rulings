Set up owner rulings in this repo as described in the attached write-up. Work one step at a time and wait for my approval between steps:

1. Inventory the docs and list every decision you find, with any that conflict. Don't change anything yet.
2. Create docs/README.md, docs/development.md (the ruling format, the "Recording a ruling" procedure and the cross-cutting rulings) and one docs/<area>.md per area and propose the area list to me.
3. Write each decision I confirm as a ruling with an ID. Mark outdated statements "Replaced →"; never delete.
4. Make AGENTS.md short: pointers to docs/README.md and docs/development.md, plus a "Never miss these" list. Propose folder AGENTS.md files for high-risk folders.
5. Add docs/rulings.schema.json, scripts/check-rulings.mjs with tests on sample docs only, and an npm run check:rulings script.
6. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code before asking about something that may already be settled.