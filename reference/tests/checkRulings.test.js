// Tests for scripts/check-rulings.mjs. They run only against the sample
// repos in tests/fixtures/, never against real docs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkRulings, formatError } from '../scripts/check-rulings.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = (name) => path.join(here, 'fixtures', name);
const script = path.join(here, '..', 'scripts', 'check-rulings.mjs');

/** Runs the checker on a fixture and returns its problem lines. */
function problems(name) {
  return checkRulings(fixture(name)).errors.map(formatError);
}

test('valid fixture: every field, a replaced pair, globs, npm run -> 0 errors', () => {
  const { rulings, errors, docCount } = checkRulings(fixture('valid'));
  assert.deepEqual(errors, []);
  assert.equal(docCount, 2);
  assert.equal(rulings.length, 7);
});

test('valid fixture: --json shape matches the schema', () => {
  const { rulings } = checkRulings(fixture('valid'));
  const byId = Object.fromEntries(rulings.map((r) => [r.id, r]));

  assert.deepEqual(byId['R-DEV-001'], {
    id: 'R-DEV-001',
    kind: 'ruled',
    date: '2026-01-10',
    doc: 'docs/development.md',
    line: 7,
    decision: 'run the tests before every push.',
    why: 'CI minutes are limited.',
    covers: 'every worker.',
    paths: ['src/**/*.js', 'package.json'],
    replacedBy: { id: 'R-DEV-002', date: '2026-03-01' },
    tests: ['tests/dev.test.js', 'npm run lint'],
  });
  assert.deepEqual(byId['R-DEV-002'], {
    id: 'R-DEV-002',
    kind: 'ruled',
    date: '2026-03-01',
    doc: 'docs/development.md',
    line: 11,
    decision: 'a pre-push hook runs the tests.',
    paths: ['scripts/pre-push.sh'],
    replaces: ['R-DEV-001'],
  });
  assert.deepEqual(byId['R-DEV-003'], {
    id: 'R-DEV-003',
    kind: 'parked',
    date: '2026-04-02',
    doc: 'docs/development.md',
    line: 14,
    decision: 'a staging environment, until we have paying users.',
  });
  assert.equal(byId['R-DEV-004'].kind, 'asked');
  assert.deepEqual(byId['R-DEV-004'].paths, ['src/?.js']);
  assert.deepEqual(byId['R-BILLING-003'].replaces, ['R-BILLING-001', 'R-BILLING-002']);
  assert.deepEqual(byId['R-BILLING-001'].replacedBy, { id: 'R-BILLING-003', date: '2026-06-01' });

  // Check every object against the fixture's own schema (the parts we use).
  const schema = JSON.parse(fs.readFileSync(path.join(fixture('valid'), 'docs/rulings.schema.json'), 'utf8'));
  const idRe = new RegExp(schema.$defs.rulingId.pattern);
  const dateRe = new RegExp(schema.$defs.date.pattern);
  const allowed = Object.keys(schema.properties);
  for (const r of rulings) {
    for (const k of schema.required) assert.ok(k in r, `${r.id} lacks ${k}`);
    for (const k of Object.keys(r)) assert.ok(allowed.includes(k), `${r.id} has unknown key ${k}`);
    assert.match(r.id, idRe);
    assert.match(r.date, dateRe);
    assert.ok(schema.properties.kind.enum.includes(r.kind));
    assert.ok(schema.properties.doc.enum.includes(r.doc));
    assert.ok(Number.isInteger(r.line) && r.line >= 1);
    assert.ok(r.decision.length > 0);
    for (const k of ['paths', 'replaces', 'tests']) {
      if (k in r) assert.ok(Array.isArray(r[k]) && r[k].length > 0, `${r.id}.${k}`);
    }
    for (const id of r.replaces || []) assert.match(id, idRe);
    if (r.replacedBy) {
      assert.deepEqual(Object.keys(r.replacedBy), ['id', 'date']);
      assert.match(r.replacedBy.id, idRe);
    }
  }
});

const failures = {
  'duplicate-id': ['docs/development.md:5  R-DEV-001  duplicate ID; first defined at docs/development.md:3'],
  'replaces-one-way': [
    'docs/development.md:5  R-DEV-002  Replaces R-DEV-001, but R-DEV-001 has no "Replaced → R-DEV-002" marker',
    'docs/development.md:7  R-DEV-003  Replaces R-DEV-009, which does not exist',
  ],
  'replaced-one-way': [
    'docs/development.md:4  R-DEV-001  Replaced → R-DEV-002, but R-DEV-002 does not list R-DEV-001 in Replaces',
  ],
  'missing-path': [
    'docs/development.md:3  R-DEV-001  Paths item "src/nope.js" does not exist',
    'docs/development.md:3  R-DEV-001  Tests item "tests/nope.test.js" does not exist',
  ],
  'glob-no-match': ['docs/development.md:3  R-DEV-001  Paths glob "src/**/*.ts" matches no files'],
  'path-outside-root': ['docs/development.md:3  R-DEV-001  Paths item "../valid/package.json" points outside the repo'],
  'unknown-npm-script': ['docs/development.md:3  R-DEV-001  Tests uses "npm run nope" but package.json has no "nope" script'],
  'impossible-date': ['docs/development.md:3  R-DEV-001  date 2026-02-30 is not a real calendar date'],
  'future-date': ['docs/development.md:3  R-DEV-001  date 2999-01-01 is in the future'],
  'wrong-doc': ['docs/development.md:3  R-BILLING-001  area BILLING belongs in docs/billing.md, not docs/development.md'],
  'unknown-area': ["docs/development.md:3  R-FOO-001  area FOO is not in the schema's x-areas"],
  'malformed-id': ['docs/development.md:3  R-DEV-21  malformed ruling ID "R-DEV-21"; expected R-AREA-NNN'],
  'missing-id': [
    'docs/development.md:3  -  ruling lead-in has no ID; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**',
  ],
  'malformed-lead-in': [
    'docs/development.md:3  R-DEV-001  unknown kind "Decided by owner"; expected Ruled, Parked or Asked',
    'docs/development.md:5  R-DEV-002  date "2026-1-5" is not YYYY-MM-DD',
  ],
  'schema-disagree': [
    'docs/rulings.schema.json:1  -  area lists disagree: $defs.rulingId.pattern has extra UI compared with x-areas',
    'docs/rulings.schema.json:1  -  area lists disagree: properties.doc.enum is missing docs/billing.md compared with x-areas',
  ],
  'doc-without-area': ['docs/extra.md:1  -  docs/extra.md has no area in x-areas'],
  'area-without-doc': ['docs/rulings.schema.json:1  -  area BILLING: docs/billing.md does not exist'],
  // A wrapped line starting with ordinary bold continues the ruling.
  'wrapped-bold': ['docs/development.md:3  R-DEV-001  Paths item "src/nope.js" does not exist'],
  'unknown-field': [
    'docs/development.md:3  R-DEV-001  unknown field "**Paths**:"',
    'docs/development.md:3  R-DEV-001  unknown field "**paths:**"',
    'docs/development.md:3  R-DEV-001  unknown field "**Path:**"',
    'docs/development.md:3  R-DEV-001  unknown field "**Test:**"',
  ],
  'lookalike-in-body': [
    'docs/development.md:3  R-DEV-7  malformed ruling ID "R-DEV-7"; expected R-AREA-NNN',
    'docs/development.md:4  R-DEV-21  malformed ruling ID "R-DEV-21"; expected R-AREA-NNN',
    'docs/development.md:5  R-DEV-002  malformed ruling lead-in; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:** at the start of a line',
  ],
  'unclosed-fence': ['docs/development.md:5  -  unclosed code fence'],
  'glob-syntax': [
    'docs/development.md:3  R-DEV-001  Paths item "src\\app.js" must use / separators',
    'docs/development.md:3  R-DEV-001  Paths glob "src/{a,b}/*.js" uses unsupported glob syntax ({} and [] are not supported)',
    'docs/development.md:3  R-DEV-001  Paths glob "src/[ab]*.js" uses unsupported glob syntax ({} and [] are not supported)',
    'docs/development.md:3  R-DEV-001  Tests item "tests\\x.test.js" must use / separators',
  ],
  'colon-outside-lead-in': [
    'docs/development.md:3  -  ruling lead-in has no ID; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**',
    'docs/development.md:5  -  ruling lead-in "**Ruled by owner 2026-01-11**:" has no ID or does not start the line',
  ],
  'replaced-after-malformed': [
    'docs/development.md:3  R-DEV-21  malformed ruling ID "R-DEV-21"; expected R-AREA-NNN',
    'docs/development.md:4  -  Replaced marker follows a malformed ruling; fix the ruling above it',
  ],
  'missing-docs': [
    'docs/  -  docs/ folder not found',
    'docs/rulings.schema.json:1  -  schema file not found',
  ],
  'replaced-misplaced': [
    'docs/development.md:5  -  Replaced marker must be on the line right after the ruling it replaces',
    'docs/development.md:6  R-DEV-002  Replaces R-DEV-001, but R-DEV-001 has no "Replaced → R-DEV-002" marker',
  ],
  'replaced-duplicate': ['docs/development.md:5  R-DEV-001  ruling has more than one Replaced marker'],
  'replaced-future-date': ['docs/development.md:4  R-DEV-001  Replaced marker date 2999-01-01 is in the future'],
  'self-replace': ['docs/development.md:3  R-DEV-001  ruling replaces itself'],
  'empty-field': ['docs/development.md:3  R-DEV-001  Why is empty'],
  'unquoted-item': ['docs/development.md:3  R-DEV-001  Paths items must be backtick-quoted, e.g. `src/x.js`'],
  'npm-test-item': ['docs/development.md:3  R-DEV-001  Tests item "npm test" must be a file or "npm run <script>"'],
  'npm-run-no-package-json': [
    'docs/development.md:3  R-DEV-001  Tests uses "npm run lint" but package.json is missing or unreadable',
  ],
  'absolute-path': ['docs/development.md:3  R-DEV-001  Paths item "/etc/hosts" points outside the repo'],
  'glob-dotdot': ['docs/development.md:3  R-DEV-001  Paths item "src/../../*.js" points outside the repo'],
  'missing-schema': ['docs/rulings.schema.json:1  -  schema file not found'],
};

for (const [name, expected] of Object.entries(failures)) {
  test(`fails: ${name}`, () => {
    assert.deepEqual(problems(name), expected);
  });
}

test('rulings inside fenced code blocks are ignored', () => {
  const { rulings, errors } = checkRulings(fixture('fenced-code'));
  assert.deepEqual(errors, []);
  assert.deepEqual(rulings.map((r) => r.id), ['R-DEV-001']);
});

test("the guide's R-SECURITY-001 example parses", () => {
  const { rulings, errors } = checkRulings(fixture('guide-example'));
  assert.deepEqual(errors, []);
  assert.deepEqual(rulings, [
    {
      id: 'R-SECURITY-001',
      kind: 'ruled',
      date: '2026-01-15',
      doc: 'docs/security.md',
      line: 3,
      decision:
        "never look at secret values. No worker may see a secret's value: not in a secrets manager, command output, environment variables, files or logs.",
      covers: 'every worker.',
    },
  ]);
});

test('future date: "today" is the date at UTC+14', () => {
  // The fixture's ruling is dated 2026-01-15, which starts at UTC+14 at 2026-01-14T10:00Z.
  const at = (iso) => checkRulings(fixture('date-boundary'), { now: new Date(iso) }).errors.map(formatError);
  assert.deepEqual(at('2026-01-14T10:00:00.000Z'), []);
  assert.deepEqual(at('2026-01-14T09:59:59.999Z'), [
    'docs/development.md:3  R-DEV-001  date 2026-01-15 is in the future',
  ]);
});

test('symlinks that point outside the repo are rejected', { skip: process.platform === 'win32' }, () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'check-rulings-'));
  try {
    const repo = path.join(tmp, 'repo');
    fs.cpSync(fixture('symlink-escape'), repo, { recursive: true });
    fs.writeFileSync(path.join(tmp, 'outside.js'), '');
    fs.symlinkSync(path.join(tmp, 'outside.js'), path.join(repo, 'src', 'link.js'));
    fs.symlinkSync('ok.js', path.join(repo, 'src', 'inside.js'));
    assert.deepEqual(checkRulings(repo).errors.map(formatError), [
      'docs/development.md:3  R-DEV-001  Paths item "src/link.js" points outside the repo',
      'docs/development.md:3  R-DEV-001  Paths glob "src/**/*.js" matches "src/link.js", which points outside the repo',
    ]);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('CLI: exit codes and summary line', () => {
  const ok = execFileSync(process.execPath, [script, '--root', fixture('valid')], { encoding: 'utf8' });
  assert.equal(ok, '7 rulings in 2 docs, 0 errors\n');

  const bad = spawnSync(process.execPath, [script, '--root', fixture('missing-path')], { encoding: 'utf8' });
  assert.equal(bad.status, 1);
  assert.equal(
    bad.stdout,
    [...failures['missing-path'], '1 rulings in 2 docs, 2 errors', ''].join('\n'),
  );

  const json = spawnSync(process.execPath, [script, '--root', fixture('valid'), '--json'], { encoding: 'utf8' });
  assert.equal(json.status, 0);
  assert.deepEqual(JSON.parse(json.stdout), checkRulings(fixture('valid')).rulings);
  assert.equal(json.stderr, '7 rulings in 2 docs, 0 errors\n');
});
