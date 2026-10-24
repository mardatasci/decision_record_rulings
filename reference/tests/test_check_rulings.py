# Tests for scripts/check_rulings.py. They run only against the sample
# repos in tests/fixtures/, never against real docs.
#
# Run from reference/: python3 -m unittest discover -s tests
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

from check_rulings import check_rulings, format_error  # noqa: E402


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
        'docs/development.md:4  R-DEV-001  Replaced → R-DEV-002, but R-DEV-002 does not list R-DEV-001 in Replaces',
    ],
    'missing-path': [
        'docs/development.md:3  R-DEV-001  Paths item "src/nope.js" does not exist',
        'docs/development.md:3  R-DEV-001  Tests item "tests/nope.test.js" does not exist',
    ],
    'glob-no-match': ['docs/development.md:3  R-DEV-001  Paths glob "src/**/*.ts" matches no files'],
    'path-outside-root': ['docs/development.md:3  R-DEV-001  Paths item "../valid/package.json" points outside the repo'],
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
    'replaced-duplicate': ['docs/development.md:5  R-DEV-001  ruling has more than one Replaced marker'],
    'replaced-future-date': ['docs/development.md:4  R-DEV-001  Replaced marker date 2999-01-01 is in the future'],
    'self-replace': ['docs/development.md:3  R-DEV-001  ruling replaces itself'],
    'empty-field': ['docs/development.md:3  R-DEV-001  Why is empty'],
    'unquoted-item': ['docs/development.md:3  R-DEV-001  Paths items must be backtick-quoted, e.g. `src/x.js`'],
    # Tests items are files only; an npm command is just a path that does not exist.
    'npm-run-item': ['docs/development.md:3  R-DEV-001  Tests item "npm run lint" does not exist'],
    'absolute-path': ['docs/development.md:3  R-DEV-001  Paths item "/etc/hosts" points outside the repo'],
    'glob-dotdot': ['docs/development.md:3  R-DEV-001  Paths item "src/../../*.js" points outside the repo'],
    'missing-schema': ['docs/rulings.schema.json:1  -  schema file not found'],
}


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
            'line': 7,
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
            'line': 11,
            'decision': 'a pre-push hook runs the tests.',
            'paths': ['scripts/pre-push.sh'],
            'replaces': ['R-DEV-001'],
        })
        self.assertEqual(by_id['R-DEV-003'], {
            'id': 'R-DEV-003',
            'kind': 'parked',
            'date': '2026-04-02',
            'doc': 'docs/development.md',
            'line': 14,
            'decision': 'a staging environment, until we have paying users.',
        })
        self.assertEqual(by_id['R-DEV-004']['kind'], 'asked')
        self.assertEqual(by_id['R-DEV-004']['paths'], ['src/?.js'])
        self.assertEqual(by_id['R-BILLING-003']['replaces'], ['R-BILLING-001', 'R-BILLING-002'])
        self.assertEqual(by_id['R-BILLING-001']['replacedBy'], {'id': 'R-BILLING-003', 'date': '2026-06-01'})

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

        ok = run('--root', fixture('valid'))
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.decode('utf-8'), '7 rulings in 2 docs, 0 errors\n')

        bad = run('--root', fixture('missing-path'))
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(
            bad.stdout.decode('utf-8'),
            '\n'.join(FAILURES['missing-path'] + ['1 rulings in 2 docs, 2 errors', '']),
        )

        js = run('--root', fixture('valid'), '--json')
        self.assertEqual(js.returncode, 0)
        self.assertEqual(json.loads(js.stdout.decode('utf-8')), check_rulings(fixture('valid'))['rulings'])
        self.assertEqual(js.stderr.decode('utf-8'), '7 rulings in 2 docs, 0 errors\n')


def _make_failure_test(name, expected):
    def test(self):
        self.assertEqual(problems(name), expected)
    test.__doc__ = 'fails: %s' % name
    return test


for _name, _expected in FAILURES.items():
    setattr(CheckRulingsTest, 'test_fails_' + _name.replace('-', '_'), _make_failure_test(_name, _expected))


if __name__ == '__main__':
    unittest.main()
