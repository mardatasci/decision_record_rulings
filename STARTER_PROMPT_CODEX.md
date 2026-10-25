Kit location: https://github.com/mardatasci/decision_record_rulings (branch main)
(To use a local clone instead, replace everything after "Kit location:" with its absolute path before pasting.)

Set up owner rulings in this repo using the kit above. Before you start:

- If the current directory is the kit itself (it contains STARTER_PROMPT_CODEX.md and reference/scripts/check_rulings.py), stop, ask me for the path to the target repo and work there. Never set up rulings inside the kit.
- If the kit location is a local path, use it. Otherwise shallow-clone it into a new temporary directory outside this repo (`mktemp -d`, then `git clone --depth 1 --branch main <kit location> <that dir>`) and use that clone as the kit. Keep it until the last step is approved, then delete only that directory. If cloning isn't possible, stop and ask me for the path to a local clone. Read CODEX_RULINGS-GUIDE.md from the kit first; it describes the whole setup.
- Before changing anything, check whether this repo already has AGENTS.md, docs/, scripts/, tests/ or CI config. Merge into existing files instead of overwriting them, and show me the proposed changes to any existing file before writing it. If tests/ or scripts/ already exist, ask me before placing the checker files there.

Work one step at a time and wait for my approval between steps:

1. Inventory the docs and list every decision you find, with any that conflict. Don't change anything yet.
2. Propose the area list. After I approve it, create or update (merge into, never replace) docs/README.md, docs/development.md (the ruling format, the "Recording a ruling" procedure and the cross-cutting rulings) and one docs/<area>.md per approved area.
3. Write each decision I confirm as a ruling with an ID. Mark outdated statements "Replaced →"; never delete.
4. Make AGENTS.md short: pointers to docs/README.md and docs/development.md, plus a "Never miss these" list. Propose folder AGENTS.md files for high-risk folders.
5. Copy the checker from the kit; don't write one from scratch: reference/scripts/check_rulings.py into scripts/, the contents of reference/tests/ into tests/ (so you end up with tests/test_check_rulings.py and tests/fixtures/), and reference/docs/rulings.schema.json into docs/. Then edit only x-areas, the ID pattern and the doc enum for this repo. Its tests run on sample docs only. Keep the test folder and script folder as siblings: the copied test finds the script at ../scripts/check_rulings.py. If I choose another location, update the CI command and any later references to match. Every top-level docs/*.md other than README.md must be an area in x-areas; for each existing doc that isn't, ask me whether to make it an area or move it to a subfolder such as docs/notes/. If the repo has a JS/TS test runner, linter or type-checker, exclude tests/fixtures/ from it and show me the change. Then run python3 scripts/check_rulings.py and python3 -m unittest discover -s tests and show me both outputs.
6. Add the checker to CI as its own last step with if: ${{ !cancelled() }}, not inside the deploy gate. Also run python3 -m unittest discover -s tests in CI so the checker's own tests run.

Only I make rulings. Never turn your own suggestion into one. Ask me one question at a time, and check the code before asking about something that may already be settled.