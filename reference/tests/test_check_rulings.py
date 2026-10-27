# Tests for scripts/check_rulings.py. They run only against the sample
# repos in tests/fixtures/, never against real docs.
#
# Run from the folder that contains tests/ and scripts/ (reference/ in this
# this repo, the repo root once copied): python3 -m unittest discover -s tests
# Each test's docstring is its name in the original JS suite.
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'scripts', 'check_rulings.py')
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))

import check_rulings as checker  # noqa: E402
from check_rulings import check_rulings, format_error, lookup_rulings, UsageError  # noqa: E402


def fixture(name):
    return os.path.join(HERE, 'fixtures', name)


def problems(name):
    """Runs the checker on a fixture and returns its problem lines."""
    return [format_error(e) for e in check_rulings(fixture(name))['errors']]


FAILURES = {
    'duplicate-id': ['docs/development.md:5  R-DEV-001  duplicate ID; first defined at docs/development.md:3'],
    'replaces-one-way': [
        'docs/development.md:5  R-DEV-002  Replaces R-DEV-001, but R-DEV-001 has no "Replaced → R-DEV-002" marker',
        'docs/development.md:7  R-DEV-003  Replaces R-DEV-009, which does not exist',
    ],
    'replaced-one-way': [
        'docs/history/development.md:4  R-DEV-001  Replaced → R-DEV-002, but R-DEV-002 does not list R-DEV-001 in Replaces',
    ],
    'missing-path': [
        'docs/development.md:3  R-DEV-001  Paths item "src/nope.js" does not exist',
        'docs/development.md:3  R-DEV-001  Tests item "tests/nope.test.js" does not exist',
    ],
    'glob-no-match': ['docs/development.md:3  R-DEV-001  Paths glob "src/**/*.ts" matches no files'],
    'path-outside-root': ['docs/development.md:3  R-DEV-001  Paths item "../valid/package.json" points outside the repo'],
    'impossible-date': ['docs/development.md:3  R-DEV-001  date 2026-02-30 is not a real calendar date'],
    'future-date': ['docs/development.md:3  R-DEV-001  date 2999-01-01 is in the future'],
    'wrong-doc': [
        'docs/development.md:3  R-BILLING-001  area BILLING belongs in docs/billing.md or docs/history/billing.md,'
        ' not docs/development.md',
    ],
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
    # A wrapped line starting with ordinary bold continues the ruling.
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
    'replaced-duplicate': ['docs/history/development.md:5  R-DEV-001  ruling has more than one Replaced marker'],
    'replaced-future-date': ['docs/history/development.md:4  R-DEV-001  Replaced marker date 2999-01-01 is in the future'],
    'self-replace': ['docs/development.md:3  R-DEV-001  ruling replaces itself'],
    'empty-field': ['docs/development.md:3  R-DEV-001  Why is empty'],
    'unquoted-item': ['docs/development.md:3  R-DEV-001  Paths items must be backtick-quoted, e.g. `src/x.js`'],
    # Tests items are files only; an npm command is just a path that does not exist.
    'npm-run-item': ['docs/development.md:3  R-DEV-001  Tests item "npm run lint" does not exist'],
    'absolute-path': ['docs/development.md:3  R-DEV-001  Paths item "/etc/hosts" points outside the repo'],
    'glob-dotdot': ['docs/development.md:3  R-DEV-001  Paths item "src/../../*.js" points outside the repo'],
    'missing-schema': ['docs/rulings.schema.json:1  -  schema file not found'],
    'enforced': [
        'docs/development.md:5  R-DEV-002  Enforced must start with "review"; link a test with Tests instead',
        'docs/development.md:7  R-DEV-003  Enforced must start with "review"; link a test with Tests instead',
    ],
    # Tests files must mention the ruling ID (any case, - or _ separators); a
    # glob needs one matching file outside docs/ that does; a directory or a
    # file in docs/ never counts; R-DEV-0080 does not mention R-DEV-008.
    'tests-mention': [
        'docs/development.md:7  R-DEV-003  Tests item "tests/other.test.js" does not mention R-DEV-003'
        ' (any case, - or _ separators, e.g. R_DEV_003)',
        'docs/development.md:11  R-DEV-005  Tests item "tests/glob/*.test.js" does not mention R-DEV-005'
        ' (any case, - or _ separators, e.g. R_DEV_005)',
        'docs/development.md:13  R-DEV-006  Tests item "tests/glob" is a directory; list test files',
        'docs/development.md:17  R-DEV-008  Tests item "tests/longer.test.js" does not mention R-DEV-008'
        ' (any case, - or _ separators, e.g. R_DEV_008)',
        'docs/development.md:19  R-DEV-009  Tests item "docs/billing.md" points into docs/; list a test file',
        'docs/development.md:21  R-DEV-010  Tests item "docs/*.md" points into docs/; list a test file',
        'docs/development.md:23  R-DEV-011  Tests item "**/mixed.txt" does not mention R-DEV-011'
        ' (any case, - or _ separators, e.g. R_DEV_011)',
    ],
    'area-paths-bad': [
        'docs/rulings.schema.json:1  -  x-area-paths: area FOO is not in x-areas',
        'docs/rulings.schema.json:1  -  x-area-paths: area DEV must map to a non-empty list of non-empty strings',
        'docs/rulings.schema.json:1  -  x-area-paths BILLING item "app/nope.py" does not exist',
        'docs/rulings.schema.json:1  -  x-area-paths BILLING glob "lib/**/*.rb" matches no files',
    ],
    'area-paths-nonobject': [
        'docs/rulings.schema.json:1  -  x-area-paths must be an object mapping areas to lists of paths',
    ],
    'area-paths-items': [
        'docs/rulings.schema.json:1  -  x-area-paths BILLING item "/etc/hosts" points outside the repo',
        'docs/rulings.schema.json:1  -  x-area-paths BILLING item "../valid/docs" points outside the repo',
        'docs/rulings.schema.json:1  -  x-area-paths BILLING glob "src/{a,b}/*.py" uses unsupported glob syntax'
        ' ({} and [] are not supported)',
    ],
    'replaced-dangling': ['docs/history/development.md:4  R-DEV-001  Replaced → R-DEV-009, which does not exist'],
    # Replaced rulings live in docs/history/<name>.md, rulings in force in docs/<name>.md.
    'history-replaced-in-area': [
        'docs/development.md:3  R-DEV-001  replaced ruling must move to docs/history/development.md',
    ],
    'history-unreplaced': [
        'docs/history/development.md:3  R-DEV-001  ruling in history has no Replaced marker;'
        ' rulings in force belong in docs/development.md',
    ],
    'history-orphan': ['docs/history/extra.md:1  -  docs/history/extra.md has no area doc docs/extra.md in x-areas'],
    'history-wrong-area': [
        'docs/history/development.md:3  R-BILLING-001  area BILLING belongs in docs/billing.md or'
        ' docs/history/billing.md, not docs/history/development.md',
    ],
    # IDs are unique across area docs and history files. R-DEV-002's Replaces
    # resolves to the first R-DEV-001, which has no marker.
    'history-duplicate-id': [
        'docs/development.md:5  R-DEV-002  Replaces R-DEV-001, but R-DEV-001 has no "Replaced → R-DEV-002" marker',
        'docs/history/development.md:3  R-DEV-001  duplicate ID; first defined at docs/development.md:3',
    ],
    # Source: one file in docs/statements/ that mentions the ruling's ID.
    'source': [
        'docs/development.md:5  R-DEV-002  Source item "docs/statements/nope.md" does not exist',
        'docs/development.md:7  R-DEV-003  Source must be a file in docs/statements/',
        'docs/development.md:9  R-DEV-004  Source must be a file, not a glob',
        'docs/development.md:11  R-DEV-005  Source must be one file',
        'docs/development.md:14  R-DEV-006  Source "docs/statements/other.md" does not mention R-DEV-006',
        'docs/development.md:16  R-DEV-007  Source "docs/statements/folder.md" is a directory;'
        ' list a file in docs/statements/',
    ],
    # Source shapes: unquoted, empty item, `..`, a leading ./, a nested folder.
    'source-shapes': [
        'docs/development.md:3  R-DEV-001  Source must be backtick-quoted, e.g. `docs/statements/billing.md`',
        'docs/development.md:5  R-DEV-002  Source has an empty item',
        'docs/development.md:7  R-DEV-003  Source must be a file in docs/statements/',
        'docs/development.md:9  R-DEV-004  Source must be a file in docs/statements/',
        'docs/development.md:11  R-DEV-005  Source must be a file in docs/statements/',
    ],
    # A marked ruling left in the area doc and an unmarked one in a history file.
    'history-misplaced': [
        'docs/development.md:3  R-DEV-001  replaced ruling must move to docs/history/development.md',
        'docs/history/development.md:3  R-DEV-003  ruling in history has no Replaced marker;'
        ' rulings in force belong in docs/development.md',
    ],
    # A replaced ruling's Source is still checked on disk.
    'history-source': [
        'docs/history/development.md:3  R-DEV-001  Source item "docs/statements/nope.md" does not exist',
        'docs/history/development.md:6  R-DEV-003  Source "docs/statements/development.md" does not mention R-DEV-003',
    ],
    # History files are parsed like area docs: a marker must follow its ruling
    # directly, fenced code is skipped, lookalikes and unclosed fences are errors.
    'history-marker-gap': [
        'docs/development.md:3  R-DEV-002  Replaces R-DEV-001, but R-DEV-001 has no "Replaced → R-DEV-002" marker',
        'docs/history/development.md:3  R-DEV-001  ruling in history has no Replaced marker;'
        ' rulings in force belong in docs/development.md',
        'docs/history/development.md:5  -  Replaced marker must be on the line right after the ruling it replaces',
    ],
    'history-fenced-code': ['docs/history/development.md:13  R-DEV-7  malformed ruling ID "R-DEV-7"; expected R-AREA-NNN'],
    'history-unclosed-fence': ['docs/history/development.md:6  -  unclosed code fence'],
    # BILLING is in x-areas, so its history file has an area doc in the schema;
    # the missing doc is reported once, by the schema check.
    'history-area-doc-missing': [
        'docs/history/billing.md:4  R-BILLING-001  Replaced → R-BILLING-002, which does not exist',
        'docs/rulings.schema.json:1  -  area BILLING: docs/billing.md does not exist',
    ],
}


def run_cli(*args):
    return subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


class CheckRulingsTest(unittest.TestCase):
    maxDiff = None

    def test_valid_fixture_zero_errors(self):
        """valid fixture: every field, a replaced pair, globs -> 0 errors"""
        result = check_rulings(fixture('valid'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['docCount'], 2)
        self.assertEqual(len(result['rulings']), 7)

    def test_valid_fixture_json_shape(self):
        """valid fixture: --json shape matches the schema"""
        rulings = check_rulings(fixture('valid'))['rulings']
        by_id = {r['id']: r for r in rulings}

        self.assertEqual(by_id['R-DEV-001'], {
            'id': 'R-DEV-001',
            'kind': 'ruled',
            'date': '2026-01-10',
            'doc': 'docs/development.md',
            'file': 'docs/history/development.md',
            'line': 3,
            'decision': 'run the tests before every push.',
            'why': 'CI minutes are limited.',
            'covers': 'every worker.',
            'paths': ['src/**/*.js', 'src/app.js'],
            'replacedBy': {'id': 'R-DEV-002', 'date': '2026-03-01'},
            'tests': ['tests/dev.test.js', 'scripts/pre-push.sh'],
        })
        self.assertEqual(by_id['R-DEV-002'], {
            'id': 'R-DEV-002',
            'kind': 'ruled',
            'date': '2026-03-01',
            'doc': 'docs/development.md',
            'file': 'docs/development.md',
            'line': 7,
            'decision': 'a pre-push hook runs the tests.',
            'paths': ['scripts/pre-push.sh'],
            'replaces': ['R-DEV-001'],
        })
        self.assertEqual(by_id['R-DEV-003'], {
            'id': 'R-DEV-003',
            'kind': 'parked',
            'date': '2026-04-02',
            'doc': 'docs/development.md',
            'file': 'docs/development.md',
            'line': 10,
            'decision': 'a staging environment, until we have paying users.',
        })
        self.assertEqual(by_id['R-DEV-004']['kind'], 'asked')
        self.assertEqual(by_id['R-DEV-004']['paths'], ['src/?.js'])
        self.assertEqual(by_id['R-BILLING-003']['replaces'], ['R-BILLING-001', 'R-BILLING-002'])
        self.assertEqual(by_id['R-BILLING-001']['replacedBy'], {'id': 'R-BILLING-003', 'date': '2026-06-01'})
        self.assertEqual((by_id['R-BILLING-001']['doc'], by_id['R-BILLING-001']['file']),
                         ('docs/billing.md', 'docs/history/billing.md'))

        # Check every object against the fixture's own schema (the parts we use).
        with open(os.path.join(fixture('valid'), 'docs/rulings.schema.json'), encoding='utf-8') as f:
            schema = json.load(f)
        id_re = re.compile(schema['$defs']['rulingId']['pattern'])
        date_re = re.compile(schema['$defs']['date']['pattern'])
        allowed = list(schema['properties'].keys())
        for r in rulings:
            for k in schema['required']:
                self.assertIn(k, r, '%s lacks %s' % (r['id'], k))
            for k in r:
                self.assertIn(k, allowed, '%s has unknown key %s' % (r['id'], k))
            self.assertRegex(r['id'], id_re)
            self.assertRegex(r['date'], date_re)
            self.assertIn(r['kind'], schema['properties']['kind']['enum'])
            self.assertIn(r['doc'], schema['properties']['doc']['enum'])
            self.assertRegex(r['file'], schema['properties']['file']['pattern'])
            self.assertIn(r['file'], (r['doc'], 'docs/history/' + r['doc'][len('docs/'):]))
            self.assertTrue(isinstance(r['line'], int) and not isinstance(r['line'], bool) and r['line'] >= 1)
            self.assertTrue(len(r['decision']) > 0)
            for k in ('paths', 'replaces', 'tests'):
                if k in r:
                    self.assertTrue(isinstance(r[k], list) and len(r[k]) > 0, '%s.%s' % (r['id'], k))
            for rid in r.get('replaces') or []:
                self.assertRegex(rid, id_re)
            if 'replacedBy' in r:
                self.assertEqual(list(r['replacedBy'].keys()), ['id', 'date'])
                self.assertRegex(r['replacedBy']['id'], id_re)

    def test_fenced_code_ignored(self):
        """rulings inside fenced code blocks are ignored"""
        result = check_rulings(fixture('fenced-code'))
        self.assertEqual(result['errors'], [])
        self.assertEqual([r['id'] for r in result['rulings']], ['R-DEV-001'])

    def test_guide_example_parses(self):
        """the guide's R-SECURITY-001 example parses"""
        result = check_rulings(fixture('guide-example'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['rulings'], [
            {
                'id': 'R-SECURITY-001',
                'kind': 'ruled',
                'date': '2026-01-15',
                'doc': 'docs/security.md',
                'file': 'docs/security.md',
                'line': 3,
                'decision': (
                    "never look at secret values. No worker may see a secret's value: not in a secrets manager, "
                    'command output, environment variables, files or logs.'
                ),
                'covers': 'every worker.',
            },
        ])

    def test_future_date_utc_plus_14(self):
        """future date: "today" is the date at UTC+14"""
        # The fixture's ruling is dated 2026-01-15, which starts at UTC+14 at 2026-01-14T10:00Z.
        def at(now):
            return [format_error(e) for e in check_rulings(fixture('date-boundary'), now=now)['errors']]

        self.assertEqual(at(datetime(2026, 1, 14, 10, 0, 0, 0, tzinfo=timezone.utc)), [])
        self.assertEqual(at(datetime(2026, 1, 14, 9, 59, 59, 999000, tzinfo=timezone.utc)), [
            'docs/development.md:3  R-DEV-001  date 2026-01-15 is in the future',
        ])

    @unittest.skipIf(sys.platform == 'win32', 'symlinks')
    def test_symlink_escape(self):
        """symlinks that point outside the repo are rejected"""
        tmp = tempfile.mkdtemp(prefix='check-rulings-')
        try:
            repo = os.path.join(tmp, 'repo')
            shutil.copytree(fixture('symlink-escape'), repo, symlinks=True)
            with open(os.path.join(tmp, 'outside.js'), 'w'):
                pass
            os.symlink(os.path.join(tmp, 'outside.js'), os.path.join(repo, 'src', 'link.js'))
            os.symlink('ok.js', os.path.join(repo, 'src', 'inside.js'))
            self.assertEqual([format_error(e) for e in check_rulings(repo)['errors']], [
                'docs/development.md:3  R-DEV-001  Paths item "src/link.js" points outside the repo',
                'docs/development.md:3  R-DEV-001  Paths glob "src/**/*.js" matches "src/link.js", which points outside the repo',
            ])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli(self):
        """CLI: exit codes and summary line"""
        def run(*args):
            return subprocess.run(
                [sys.executable, SCRIPT] + list(args),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        valid_report = (
            'docs/development.md:7  R-DEV-002  note: not enforced; add Tests or Enforced: review\n'
            'Enforcement: 0 tested, 1 review-only, 1 not enforced (of 2 in-force rulings)\n'
            '7 rulings in 2 docs (2 history files), 0 errors\n'
        )
        ok = run('--root', fixture('valid'))
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.decode('utf-8'), valid_report)

        bad = run('--root', fixture('missing-path'))
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(
            bad.stdout.decode('utf-8'),
            '\n'.join(FAILURES['missing-path'] + [
                'Enforcement: 0 tested, 0 review-only, 1 not enforced (of 1 in-force rulings)',
                '1 rulings in 2 docs, 2 errors', '']),
        )

        js = run('--root', fixture('valid'), '--json')
        self.assertEqual(js.returncode, 0)
        self.assertEqual(json.loads(js.stdout.decode('utf-8')), check_rulings(fixture('valid'))['rulings'])
        self.assertEqual(js.stderr.decode('utf-8'), valid_report)

    def test_enforced_field(self):
        """Enforced: review (any case) is stored; other values are errors and count as not enforced"""
        result = check_rulings(fixture('enforced'))
        by_id = {r['id']: r for r in result['rulings']}
        self.assertEqual(by_id['R-DEV-001']['enforced'], 'review — judgment call')
        self.assertEqual(by_id['R-DEV-004']['enforced'], 'Review')
        self.assertNotIn('R-DEV-004', [e['id'] for e in result['errors']])
        self.assertNotIn('enforced', by_id['R-DEV-002'])
        self.assertEqual(result['enforcement'], {'tested': 0, 'review': 2, 'unenforced': 2, 'inForce': 4})
        self.assertEqual([n['id'] for n in result['notes']], ['R-DEV-002', 'R-DEV-003'])
        valid = {r['id']: r for r in check_rulings(fixture('valid'))['rulings']}
        self.assertEqual(valid['R-BILLING-003']['enforced'], 'review — judgment call')

    def test_tests_mention_passes(self):
        """Tests files mentioning the ID (hyphens or underscores, any case, or via a glob) pass"""
        ids = [e['id'] for e in check_rulings(fixture('tests-mention'))['errors']]
        for rid in ('R-DEV-001', 'R-DEV-002', 'R-DEV-004', 'R-DEV-007'):
            self.assertNotIn(rid, ids)

    def test_id_mention_regexp(self):
        """ID mentions: any case, - or _, not inside a longer name or number"""
        rx = checker.id_mention_regexp('R-X-004')
        for text in (b'R-X-004', b'r_x_004', b'test_R_X_004_name', b'R-x_004.', b'(R-X-004)'):
            self.assertTrue(rx.search(text), text)
        for text in (b'R-X-0042', b'XR-X-004', b'R-X-04', b'R-XY-004', b'1R-X-004'):
            self.assertFalse(rx.search(text), text)

    def test_mentions_reads_in_chunks(self):
        """a mention across a chunk boundary is found; one cut by a boundary is not faked"""
        tmp = tempfile.mkdtemp(prefix='check-rulings-')
        saved = checker._CHUNK
        checker._CHUNK = 8
        try:
            rx = checker.id_mention_regexp('R-DEV-004')

            def state(data):
                path = os.path.join(tmp, 'f.txt')
                with open(path, 'wb') as f:
                    f.write(data)
                return checker._mentions(path, rx, 9)

            for pad in range(0, 20):
                self.assertEqual(state(b'x' * pad + b' R-DEV-004 tail'), 'yes', pad)
                self.assertEqual(state(b'x' * pad + b' R-DEV-0042'), 'no', pad)
                self.assertEqual(state(b'x' * pad + b'R-DEV-004'), 'no' if pad else 'yes', pad)
            self.assertEqual(state(b'R-DEV-004'), 'yes')
            self.assertEqual(checker._mentions(tmp, rx, 9), 'dir')
        finally:
            checker._CHUNK = saved
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipIf(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                     'file permissions')
    def test_tests_item_unreadable(self):
        """an unreadable Tests file gets its own message"""
        tmp = tempfile.mkdtemp(prefix='check-rulings-')
        try:
            repo = os.path.join(tmp, 'repo')
            shutil.copytree(fixture('tests-mention'), repo)
            target = os.path.join(repo, 'tests', 'hyphen.test.js')
            os.chmod(target, 0)
            try:
                lines = [format_error(e) for e in check_rulings(repo)['errors']]
            finally:
                os.chmod(target, 0o644)
            self.assertIn('docs/development.md:3  R-DEV-001  Tests item "tests/hyphen.test.js" could not be read', lines)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_coverage_with_failing_tests(self):
        """coverage: failing Tests do not count as tested; a duplicate ID counts once"""
        result = check_rulings(fixture('coverage-failing'))
        # R-DEV-001 tested; -002 (Tests fail) not enforced; -003 (one Tests item
        # fails, Enforced: review) review-only; -004 not enforced; the second
        # R-DEV-001 is a duplicate and not counted again.
        self.assertEqual(result['enforcement'], {'tested': 1, 'review': 1, 'unenforced': 2, 'inForce': 4})
        out = run_cli('--root', fixture('coverage-failing'))
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout.decode('utf-8'), (
            'docs/development.md:5  R-DEV-002  Tests item "tests/nope.test.js" does not exist\n'
            'docs/development.md:7  R-DEV-003  Tests item "tests/nope.test.js" does not exist\n'
            'docs/development.md:11  R-DEV-001  duplicate ID; first defined at docs/development.md:3\n'
            'docs/development.md:9  R-DEV-004  note: not enforced; add Tests or Enforced: review\n'
            'Enforcement: 1 tested, 1 review-only, 2 not enforced (of 4 in-force rulings)\n'
            '5 rulings in 2 docs, 3 errors\n'
        ))

    def test_enforcement_coverage(self):
        """coverage: counts and notes for in-force rulings; notes are not errors"""
        result = check_rulings(fixture('coverage'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['enforcement'], {'tested': 2, 'review': 1, 'unenforced': 2, 'inForce': 5})
        self.assertEqual([format_error(n) for n in result['notes']], [
            'docs/development.md:9  R-DEV-004  note: not enforced; add Tests or Enforced: review',
            'docs/development.md:11  R-DEV-006  note: not enforced; add Tests or Enforced: review',
        ])
        out = run_cli('--root', fixture('coverage'))
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.decode('utf-8'), '\n'.join(
            [format_error(n) for n in result['notes']]
            + ['Enforcement: 2 tested, 1 review-only, 2 not enforced (of 5 in-force rulings)',
               '7 rulings in 2 docs (1 history files), 0 errors', '']))
        js = run_cli('--root', fixture('coverage'), '--json')
        self.assertEqual(js.returncode, 0)
        self.assertIn('note: not enforced', js.stderr.decode('utf-8'))
        self.assertNotIn('note:', js.stdout.decode('utf-8'))

    def test_guide_example_note(self):
        """the guide's example has no Tests/Enforced: a note, not an error"""
        result = check_rulings(fixture('guide-example'))
        self.assertEqual(result['errors'], [])
        self.assertEqual([n['id'] for n in result['notes']], ['R-SECURITY-001'])

    def test_rulings_md_skipped(self):
        """docs/RULINGS.md is skipped like docs/README.md"""
        result = check_rulings(fixture('rulings-md'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['docCount'], 2)
        self.assertEqual([r['id'] for r in result['rulings']], ['R-DEV-001'])

    def test_area_paths_valid(self):
        """x-area-paths with existing files and a matching glob -> 0 errors"""
        self.assertEqual(check_rulings(fixture('area-paths'))['errors'], [])

    # --- history files and Source -------------------------------------------

    def test_history_valid(self):
        """history file: the replaced ruling and its marker there, the replacing one in the area doc -> 0 errors"""
        result = check_rulings(fixture('history'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['docCount'], 2)
        self.assertEqual(result['historyCount'], 1)
        out = run_cli('--root', fixture('history'))
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.decode('utf-8'), (
            'Enforcement: 0 tested, 2 review-only, 0 not enforced (of 2 in-force rulings)\n'
            '3 rulings in 2 docs (1 history files), 0 errors\n'
        ))

    def test_history_json_doc_and_file(self):
        """--json: doc is the area doc, file is where the ruling sits, line is in file"""
        by_id = {r['id']: r for r in check_rulings(fixture('history'))['rulings']}
        old, new = by_id['R-BILLING-001'], by_id['R-BILLING-002']
        self.assertEqual((old['doc'], old['file'], old['line']), ('docs/billing.md', 'docs/history/billing.md', 3))
        self.assertEqual((new['doc'], new['file'], new['line']), ('docs/billing.md', 'docs/billing.md', 3))
        self.assertEqual(list(new.keys())[3:6], ['doc', 'file', 'line'])
        self.assertEqual(new['source'], 'docs/statements/billing.md')
        self.assertEqual(list(new.keys())[-1], 'source')
        js = run_cli('--root', fixture('history'), '--json')
        self.assertEqual(json.loads(js.stdout.decode('utf-8')), check_rulings(fixture('history'))['rulings'])

    def test_history_lookup_id(self):
        """--id finds a replaced ruling in a history file and shows its file and line"""
        out = run_cli('--root', fixture('history'), '--id', 'R-BILLING-001')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr.decode('utf-8'), '')
        self.assertEqual(out.stdout.decode('utf-8'), (
            'R-BILLING-001 · Ruled 2026-02-01 · docs/history/billing.md:3\n'
            '  invoices are PDFs.\n'
            '  Enforced: review\n'
            '  Replaced 2026-06-01 → R-BILLING-002\n'
        ))
        js = run_cli('--root', fixture('history'), '--json', '--id', 'R-BILLING-001')
        [r] = json.loads(js.stdout.decode('utf-8'))
        self.assertEqual((r['doc'], r['file'], r['line']), ('docs/billing.md', 'docs/history/billing.md', 3))

    def test_history_lookup_for_and_area_exclude(self):
        """--for and --area leave out rulings in history files"""
        self.assertEqual(self.ids_for('src/billing/invoices.py', root=fixture('history')), ['R-BILLING-002'])
        self.assertEqual([r['id'] for r in lookup_rulings(fixture('history'), area='BILLING')['rulings']],
                         ['R-BILLING-002'])

    def test_lookup_shows_source(self):
        """lookup text output names the Source file on the fields line, after Enforced"""
        out = run_cli('--root', fixture('history'), '--area', 'BILLING')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.decode('utf-8'), (
            'R-BILLING-002 · Ruled 2026-06-01 · docs/billing.md:3\n'
            '  invoices are HTML.\n'
            '  Enforced: review · Source: `docs/statements/billing.md`\n'
            '\n'
            '1 rulings in area BILLING\n'
        ))

    def test_source_lower_case_underscore_passes(self):
        """Source mentioning the ID in lower case with underscores passes and is stored"""
        result = check_rulings(fixture('source'))
        by_id = {r['id']: r for r in result['rulings']}
        self.assertEqual(by_id['R-DEV-001']['source'], 'docs/statements/development.md')
        self.assertNotIn('R-DEV-001', [e['id'] for e in result['errors']])
        # Invalid Source values are not stored; statement files are not docs.
        for rid in ('R-DEV-003', 'R-DEV-004', 'R-DEV-005'):
            self.assertNotIn('source', by_id[rid], rid)
        self.assertEqual(result['docCount'], 2)
        # Source never counts as enforcement.
        self.assertEqual(result['enforcement']['unenforced'], 7)

    def test_history_lookup_in_force_only(self):
        """--for and --area leave out a marked ruling in an area doc and an unmarked one in history; --id finds both"""
        root = fixture('history-misplaced')
        self.assertEqual(self.ids_for('src/a.js', root=root), ['R-DEV-002'])
        result = lookup_rulings(root, area='DEV')
        self.assertEqual([r['id'] for r in result['rulings']], ['R-DEV-002'])
        self.assertEqual(result['problems'], 2)
        for rid, file in (('R-DEV-001', 'docs/development.md'), ('R-DEV-003', 'docs/history/development.md')):
            [r] = lookup_rulings(root, rid=rid)['rulings']
            self.assertEqual(r['file'], file)
        out = run_cli('--root', root, '--for', 'src/a.js')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr.decode('utf-8'),
                         'warning: the rulings docs have 2 problems; run python3 scripts/check_rulings.py\n')

    def test_history_paths_tests_not_checked(self):
        """a replaced ruling whose Paths and Tests no longer exist -> 0 errors, and it is not counted in coverage"""
        result = check_rulings(fixture('history-stale'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['enforcement'], {'tested': 0, 'review': 1, 'unenforced': 0, 'inForce': 1})
        old = {r['id']: r for r in result['rulings']}['R-DEV-001']
        self.assertEqual(old['paths'], ['src/gone.js', 'src/gone/**/*.js'])
        self.assertEqual(old['tests'], ['tests/gone.test.js'])
        self.assertFalse(os.path.exists(os.path.join(fixture('history-stale'), 'src')))

    def test_history_readme_ignored(self):
        """docs/history/README.md is not a history file"""
        root = fixture('history-stale')
        self.assertTrue(os.path.isfile(os.path.join(root, 'docs', 'history', 'README.md')))
        result = check_rulings(root)
        self.assertEqual(result['historyCount'], 1)
        self.assertEqual(sorted(r['file'] for r in result['rulings']),
                         ['docs/development.md', 'docs/history/development.md'])
        self.assertEqual(lookup_rulings(root, area='DEV')['problems'], 0)

    def test_lookup_warns_on_source_shape(self):
        """lookup counts Source shape errors as problems"""
        self.assertEqual(lookup_rulings(fixture('source-shapes'), area='DEV')['problems'], 5)
        out = run_cli('--root', fixture('source-shapes'), '--area', 'DEV')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr.decode('utf-8'),
                         'warning: the rulings docs have 5 problems; run python3 scripts/check_rulings.py\n')
        by_id = {r['id']: r for r in check_rulings(fixture('source-shapes'))['rulings']}
        for rid in ('R-DEV-001', 'R-DEV-002', 'R-DEV-003', 'R-DEV-004', 'R-DEV-005'):
            self.assertNotIn('source', by_id[rid], rid)

    def test_source_symlink(self):
        """Source must resolve to a file in docs/statements/: a symlink out of it fails, one within it passes"""
        tmp = tempfile.mkdtemp(prefix='check-rulings-')
        try:
            repo = os.path.join(tmp, 'repo')
            shutil.copytree(fixture('history'), repo)
            statement = os.path.join(repo, 'docs', 'statements', 'billing.md')
            moved = os.path.join(repo, 'notes.md')
            os.rename(statement, moved)
            try:
                os.symlink(os.path.join('..', '..', 'notes.md'), statement)
            except (OSError, NotImplementedError, AttributeError):
                self.skipTest('symlinks not supported')
            self.assertEqual([format_error(e) for e in check_rulings(repo)['errors']], [
                'docs/billing.md:3  R-BILLING-002  Source "docs/statements/billing.md" must resolve to a file'
                ' in docs/statements/',
            ])
            os.remove(statement)
            os.rename(moved, os.path.join(repo, 'docs', 'statements', 'real.md'))
            os.symlink('real.md', statement)
            self.assertEqual(check_rulings(repo)['errors'], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- lookup -------------------------------------------------------------

    def ids_for(self, *paths, **kw):
        root = kw.pop('root', fixture('area-paths'))
        return [r['id'] for r in lookup_rulings(root, for_paths=list(paths))['rulings']]

    def test_lookup_for_exact_path(self):
        """--for: exact Paths item"""
        self.assertEqual(self.ids_for('scripts/deploy.sh'), ['R-DEV-002'])
        self.assertEqual(self.ids_for('./scripts\\deploy.sh'), ['R-DEV-002'])

    def test_lookup_for_dir_glob_area(self):
        """--for: directory prefix, globs and x-area-paths; replaced excluded, every kind included"""
        # R-BILLING-002 by directory (and area), -003 and -004 (Parked) by area,
        # -005 (Asked) by glob and area, R-DEV-001 by glob. -001 is replaced.
        self.assertEqual(self.ids_for('src/billing/rates.py'),
                         ['R-BILLING-002', 'R-BILLING-003', 'R-BILLING-004', 'R-BILLING-005', 'R-DEV-001'])
        # A trailing slash is dropped: the folder itself matches the `src/billing/`
        # Paths item but not the `src/billing/**` glob, which needs a file under it.
        self.assertEqual(self.ids_for('src/billing/'), ['R-BILLING-002'])
        self.assertEqual(self.ids_for('src/billing/'), self.ids_for('src/billing'))
        self.assertEqual(self.ids_for('src/main.py'), ['R-DEV-001'])

    def test_lookup_for_replaced_excluded(self):
        """--for: a replaced ruling whose Paths match is excluded"""
        # app/invoices.py is in R-BILLING-001 (replaced) and -003 Paths, and in
        # BILLING's x-area-paths (brings in -002, -004 and -005).
        self.assertEqual(self.ids_for('app/invoices.py'),
                         ['R-BILLING-002', 'R-BILLING-003', 'R-BILLING-004', 'R-BILLING-005'])

    def test_lookup_for_absolute_path(self):
        """--for: an absolute path inside root is made relative; outside is a usage error"""
        self.assertEqual(self.ids_for(os.path.join(fixture('area-paths'), 'src', 'main.py')), ['R-DEV-001'])
        with self.assertRaises(UsageError) as cm:
            self.ids_for(os.path.join(fixture('valid'), 'src', 'app.js'))
        self.assertEqual(cm.exception.code, 2)

    def test_lookup_area(self):
        """--area: every non-replaced ruling in the area, of any kind"""
        result = lookup_rulings(fixture('area-paths'), area='BILLING')
        self.assertEqual([r['id'] for r in result['rulings']],
                         ['R-BILLING-002', 'R-BILLING-003', 'R-BILLING-004', 'R-BILLING-005'])
        out = run_cli('--root', fixture('area-paths'), '--area', 'NOPE')
        self.assertEqual(out.returncode, 2)

    def test_lookup_id_replaced(self):
        """--id: shows a replaced ruling with its Replaced line"""
        out = run_cli('--root', fixture('area-paths'), '--id', 'R-BILLING-001')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.decode('utf-8'), (
            'R-BILLING-001 · Ruled 2026-02-01 · docs/history/billing.md:3\n'
            '  invoices are PDFs.\n'
            '  Enforced: review\n'
            '  Replaced 2026-06-01 → R-BILLING-003\n'
        ))
        self.assertEqual(out.stderr.decode('utf-8'), '')
        self.assertEqual(run_cli('--root', fixture('area-paths'), '--id', 'R-BILLING-099').returncode, 1)

    def test_lookup_cli_text_and_json(self):
        """--for text output (grouped per path) and --json"""
        out = run_cli('--root', fixture('area-paths'), '--for', 'scripts/deploy.sh', '--for', 'src/main.py')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.decode('utf-8'), (
            'R-DEV-002 · Ruled 2026-01-11 · docs/development.md:6\n'
            '  deploys go through the script.\n'
            '  Why: it runs the checks. · Covers: every worker.\n'
            '\n'
            '1 rulings apply to scripts/deploy.sh\n'
            '\n'
            'R-DEV-001 · Ruled 2026-01-10 · docs/development.md:3\n'
            '  type-check all Python.\n'
            '  Tests: `tests/dev_spec.py`\n'
            '\n'
            '1 rulings apply to src/main.py\n'
        ))
        js = run_cli('--root', fixture('area-paths'), '--json', '--for', 'src/main.py')
        self.assertEqual(js.returncode, 0)
        self.assertEqual([r['id'] for r in json.loads(js.stdout.decode('utf-8'))], ['R-DEV-001'])

    def test_lookup_combined_usage_error(self):
        """combining --for, --area, --id is a usage error"""
        out = run_cli('--root', fixture('area-paths'), '--for', 'src/main.py', '--area', 'BILLING')
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout.decode('utf-8'), '')
        self.assertEqual(run_cli('--root', fixture('area-paths'), '--id', 'R-DEV-001', '--area', 'DEV').returncode, 2)

    def test_lookup_warns_on_problems(self):
        """lookup prints a warning when the docs have problems, still exits 0"""
        out = run_cli('--root', fixture('malformed-id'), '--area', 'DEV')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr.decode('utf-8'),
                         'warning: the rulings docs have 1 problems; run python3 scripts/check_rulings.py\n')

    def test_lookup_warns_on_cross_ruling_problems(self):
        """lookup warns about a dangling Replaced marker and a duplicate ID"""
        warning = 'warning: the rulings docs have 1 problems; run python3 scripts/check_rulings.py\n'
        for name, args in (('replaced-dangling', ('--id', 'R-DEV-002')), ('duplicate-id', ('--area', 'DEV'))):
            out = run_cli('--root', fixture(name), *args)
            self.assertEqual(out.returncode, 0, name)
            self.assertEqual(out.stderr.decode('utf-8'), warning, name)
            self.assertNotEqual(out.stdout.decode('utf-8'), '', name)

    def test_lookup_no_rulings_found(self):
        """lookup with no schema or no docs/ at the root is an error (exit 2), not a silent "0 rulings apply"."""
        for root in (fixture('missing-schema'), fixture('missing-docs'), os.path.join(fixture('valid'), 'src')):
            out = run_cli('--root', root, '--for', 'src/app.js')
            self.assertEqual(out.returncode, 2, root)
            self.assertEqual(out.stdout.decode('utf-8'), '', root)
            self.assertEqual(out.stderr.decode('utf-8'), (
                'error: no rulings found at %s (missing or unreadable docs/rulings.schema.json, or missing docs/);'
                ' run from the repo root or pass --root\n' % os.path.abspath(root)), root)
        # A schema that is invalid JSON or not an object is the same error, not a traceback.
        for text in ('{not json', 'null'):
            with tempfile.TemporaryDirectory() as tmp:
                os.mkdir(os.path.join(tmp, 'docs'))
                with open(os.path.join(tmp, 'docs', 'rulings.schema.json'), 'w', encoding='utf-8') as f:
                    f.write(text)
                out = run_cli('--root', tmp, '--for', 'src/app.js')
                self.assertEqual(out.returncode, 2, text)
                self.assertEqual(out.stdout.decode('utf-8'), '', text)
                err = out.stderr.decode('utf-8')
                self.assertNotIn('Traceback', err, text)
                self.assertEqual(err, (
                    'error: no rulings found at %s (missing or unreadable docs/rulings.schema.json, or missing docs/);'
                    ' run from the repo root or pass --root\n' % os.path.abspath(tmp)), text)
        # The default root is the current directory.
        out = subprocess.run([sys.executable, os.path.abspath(SCRIPT), '--area', 'DEV'],
                             cwd=fixture('missing-docs'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(out.returncode, 2)
        self.assertIn('error: no rulings found at ', out.stderr.decode('utf-8'))
        ok = subprocess.run([sys.executable, os.path.abspath(SCRIPT), '--area', 'DEV'],
                            cwd=fixture('area-paths'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(ok.returncode, 0)

    def test_lookup_for_paths(self):
        """--for: `..` escaping the root, a missing value, and a `.` item"""
        with self.assertRaises(UsageError) as cm:
            self.ids_for('src/../../valid/src/app.js')
        self.assertEqual(cm.exception.code, 2)
        out = run_cli('--root', fixture('area-paths'), '--for', '../valid/src/app.js')
        self.assertEqual(out.returncode, 2)
        self.assertIn('is outside the repo root', out.stderr.decode('utf-8'))
        out = run_cli('--root', fixture('area-paths'), '--for')
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout.decode('utf-8'), '')
        self.assertTrue(out.stderr.decode('utf-8').startswith('--for needs a value\n'))
        for item in ('.', './'):
            self.assertTrue(checker.item_matches(item, 'any/file.py'), item)
            self.assertTrue(checker.item_matches(item, 'top.py'), item)
        self.assertFalse(checker.item_matches('src', 'srcx/a.py'))
        # Items the full check rejects never match in a lookup, and never crash it.
        for item in ('/etc/hosts', '../valid/docs', 'src/{a,b}/*.py', 'src\\a.py'):
            self.assertFalse(checker.item_matches(item, 'src/a.py'), item)
        self.assertEqual(self.ids_for('src/a.py', root=fixture('area-paths-items')), ['R-BILLING-001'])
        self.assertEqual(self.ids_for('src/a.py', root=fixture('area-paths-nonobject')), [])

    @unittest.skipIf(sys.platform == 'win32', 'symlinks')
    def test_lookup_for_absolute_through_symlink(self):
        """--for: an absolute path in the real form of a symlinked root, and the reverse"""
        tmp = tempfile.mkdtemp(prefix='check-rulings-')
        try:
            real_tmp = os.path.realpath(tmp)
            os.symlink(real_tmp, os.path.join(real_tmp, 'link'))
            shutil.copytree(fixture('area-paths'), os.path.join(real_tmp, 'repo'))
            linked = os.path.join(real_tmp, 'link', 'repo')
            real = os.path.join(real_tmp, 'repo')
            self.assertNotEqual(linked, os.path.realpath(linked))
            for root, base in ((linked, real), (real, linked)):
                self.assertEqual(self.ids_for(os.path.join(base, 'src', 'main.py'), root=root), ['R-DEV-001'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_lookup_json_area_and_id(self):
        """--json with --area and with --id"""
        js = run_cli('--root', fixture('area-paths'), '--json', '--area', 'BILLING')
        self.assertEqual(js.returncode, 0)
        self.assertEqual(json.loads(js.stdout.decode('utf-8')),
                         lookup_rulings(fixture('area-paths'), area='BILLING')['rulings'])
        self.assertEqual([r['kind'] for r in json.loads(js.stdout.decode('utf-8'))],
                         ['ruled', 'ruled', 'parked', 'asked'])
        js = run_cli('--root', fixture('area-paths'), '--json', '--id', 'R-BILLING-001')
        self.assertEqual(js.returncode, 0)
        rulings = json.loads(js.stdout.decode('utf-8'))
        self.assertEqual([r['id'] for r in rulings], ['R-BILLING-001'])
        self.assertEqual(rulings[0]['replacedBy'], {'id': 'R-BILLING-003', 'date': '2026-06-01'})

    def test_lookup_does_not_walk(self):
        """lookup never lists the repo's files, checks Paths/Tests/Source on disk or reads docs/statements/"""
        def boom(*a, **k):
            raise AssertionError('lookup must not walk the repo')

        saved = checker.list_files, checker.check_path_item, checker._mentions
        checker.list_files = checker.check_path_item = checker._mentions = boom
        # A test file or an owner statement must never be opened either.
        real_read_text = checker._read_text

        def read_text(full):
            rel = '/' + os.path.relpath(full, fixture('.')).replace(os.sep, '/').split('/', 1)[-1]
            if not rel.startswith('/docs/') or rel.startswith('/docs/statements/'):
                raise AssertionError('lookup read %s' % full)
            return real_read_text(full)

        checker._read_text = read_text
        try:
            self.assertEqual(self.ids_for('src/billing/sub/tax.py'),
                             ['R-BILLING-002', 'R-BILLING-003', 'R-BILLING-004', 'R-BILLING-005', 'R-DEV-001'])
            # The doc-only checks still run, without the file tree.
            self.assertEqual(lookup_rulings(fixture('replaced-dangling'), area='DEV')['problems'], 1)
            self.assertEqual(lookup_rulings(fixture('tests-mention'), area='DEV')['problems'], 0)
            self.assertEqual(len(lookup_rulings(fixture('area-paths'), area='DEV')['rulings']), 2)
            self.assertEqual(len(lookup_rulings(fixture('area-paths'), rid='R-DEV-001')['rulings']), 1)
            # History files are read; statement files never are.
            history = lookup_rulings(fixture('history'), rid='R-BILLING-001')
            self.assertEqual(history['rulings'][0]['file'], 'docs/history/billing.md')
            self.assertEqual(history['problems'], 0)
            self.assertEqual(lookup_rulings(fixture('history'), area='BILLING')['rulings'][0]['source'],
                             'docs/statements/billing.md')
            self.assertEqual(self.ids_for('src/billing/invoices.py', root=fixture('history')), ['R-BILLING-002'])
            self.assertEqual(len(lookup_rulings(fixture('source'), area='DEV')['rulings']), 7)
        finally:
            checker.list_files, checker.check_path_item, checker._mentions = saved
            checker._read_text = real_read_text


def _make_failure_test(name, expected):
    def test(self):
        self.assertEqual(problems(name), expected)
    test.__doc__ = 'fails: %s' % name
    return test


for _name, _expected in FAILURES.items():
    setattr(CheckRulingsTest, 'test_fails_' + _name.replace('-', '_'), _make_failure_test(_name, _expected))


if __name__ == '__main__':
    unittest.main()
