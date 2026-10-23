Set up owner rulings in this repo as described in the attached write-up. Work one step at a time and wait for my 
approval between steps:

1. Inventory the docs and list every decision you find, with any that conflict. Don't change anything yet.
2. Create docs/README.md, docs/development.md (the ruling format and the cross-cutting rulings) and one docs/<area>.md per area, and propose the area list to me.
3. Write each decision I confirm as a ruling with an ID. Mark outdated statements "Replaced →"; never delete.
4. Make CLAUDE.md short: @docs/development.md plus a "Never miss these" list.
5. Add docs/rulings.schema.json, scripts/check-rulings.mjs with tests on sample docs only, and an npm run check:rulings script.
6. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate.
7. Create the /ruling skill in .claude/skills/ruling/SKILL.md.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code 
before asking about something that may already be settled.
