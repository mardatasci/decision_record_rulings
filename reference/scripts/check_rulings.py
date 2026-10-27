#!/usr/bin/env python3
# Reference implementation. Provided as is, without warranty of any kind.
# Review it and use it at your own discretion and risk; the author is not
# responsible for any outcome of using it. MIT license.
#
# Owner rulings checker: reference implementation.
#
# Usage:
#   python3 scripts/check_rulings.py [--root <dir>] [--json]
#   python3 scripts/check_rulings.py [--root <dir>] [--json] --for <path> [--for <path> ...]
#   python3 scripts/check_rulings.py [--root <dir>] [--json] --area <AREA>
#   python3 scripts/check_rulings.py [--root <dir>] [--json] --id <R-AREA-NNN>
#
#   --root <dir>  Repo root (default: current directory). docs/, the schema
#                 docs/rulings.schema.json, and every Paths/Tests
#                 entry are resolved against it. The tests use it to point the
#                 checker at sample repos in tests/fixtures/.
#   --json        Print the extracted rulings as a JSON array matching the
#                 schema on stdout. Problems and the summary go to stderr.
#
# Area docs (docs/<name>.md) hold the rulings in force. A replaced ruling moves,
# with its Replaced marker, to the area's history file docs/history/<name>.md.
# A ruling's Source names the file in docs/owner-words/ that keeps the owner's
# exact words; that file must mention the ruling's ID. History is never
# reworded, so the Paths and Tests of replaced rulings are not checked on disk;
# their Source still is.
#
# Owner quotes: if the schema sets "x-quotes-since": "YYYY-MM-DD", every ruling
# (any kind, in an area doc or a history file) dated on or after that day must
# have its decision, and its Why if it has one, in quotes: the owner's exact
# words, never written or reworded by AI. Rulings dated before it are not
# checked.
#
# Full check (no lookup option): prints, in this order, one line per problem,
# `docs/x.md:LINE  R-ID  message`, then a note line if x-quotes-since is not
# set, then a note line for each in-force ruling with neither Tests nor
# Enforced, then
# `Enforcement: T tested, V review-only, U not enforced (of K in-force rulings)`
# and `N rulings in M docs, E errors` (`N rulings in M docs (H history files),
# E errors` when there are history files). Notes never count as errors. A
# ruling counts as tested only if it has Tests and none of its Tests items has
# an error. Exits 1 if there are errors, else 0.
#
# Lookup (run it from the repo root, or pass --root, before editing a file; it
# reads only the schema, the area docs and the history files, never walks the
# repo, never reads docs/owner-words/ and never checks Paths/Tests/Source on
# disk):
#   --for <path>  Rulings that apply to the file: a Paths item matches it, or
#                 it falls under the x-area-paths of the ruling's area. May
#                 repeat; results are grouped per path. Relative paths are
#                 taken relative to the root.
#   --area <AREA> Every ruling in force in the area.
#   --id <ID>     That ruling, wherever it is, even if it has been replaced
#                 (it is then in a history file, whose path and line are shown).
#   --for and --area print only rulings in force: in an area doc (not a history
#   file) and not replaced. Of any kind: Ruled ones bind; Parked and Asked ones
#   are shown for context.
#   Use one kind of lookup per call. With --json, prints the selected rulings
#   as a JSON array. Exits 0; 1 if --id finds nothing; 2 on a usage error or
#   when no rulings are found at the root (no docs/rulings.schema.json or
#   docs/). If the docs have problems that the docs alone show, a warning with
#   their count goes to stderr and results still print. Those are: rules 1, 2,
#   4 and 5; the placement rule (in force in the area doc, replaced in its
#   history file); owner quotes (x-quotes-since); malformed rulings, fields
#   and Replaced markers, including a Source that is not one backtick-quoted
#   file in docs/owner-words/; unclosed code fences; and the schema (its own shape, a doc without an area, an area
#   without a doc, a history file without an area doc).
#
# Zero dependencies: Python 3.8+ standard library only.

from __future__ import annotations

import errno
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

SCHEMA_PATH = 'docs/rulings.schema.json'
FIELDS = ['Why', 'Covers', 'Paths', 'Replaces', 'Tests', 'Enforced', 'Source']
RESERVED_DOCS = ('README.md', 'RULINGS.md')  # in docs/ and docs/history/, never rulings files
HISTORY_DIR = 'docs/history'  # docs/history/<name>.md: replaced rulings of docs/<name>.md
SOURCE_RE = re.compile(r'^docs/owner-words/[^/]+\.md\Z')  # a Source item
QUOTES_SINCE_NOTE = 'note: x-quotes-since is not set; owner quotes are not checked'
OPEN_QUOTES = ('"', '\u201c')  # " and left double quotation mark
CLOSE_QUOTES = ('"', '\u201d')  # " and right double quotation mark
KIND_WORDS = {'ruled': 'Ruled', 'parked': 'Parked', 'asked': 'Asked'}
KINDS = {'Ruled': 'ruled', 'Parked': 'parked', 'Asked': 'asked'}
SKIP_DIRS = {'.git', 'node_modules'}

# Regexes keep the semantics of the original ECMAScript ones: \d, \b and /i are
# ASCII-only, "\s" is ECMAScript white space, "." stops at any line terminator,
# and "$" only matches at the very end (\Z).
_A = re.ASCII
WSC = (
    '\t\n\x0b\x0c\r \xa0        '
    '        　﻿'
)
WS = '[' + WSC + ']'
NWS = '[^' + WSC + ']'
DOT = '[^\n\r  ]'

ID_RE = re.compile(r'^R-[A-Z][A-Z0-9_]*-[0-9]{3}\Z', _A)
DATE_RE = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z', _A)

# A line that starts a new block: list item, heading, or a bold span that is a
# ruling lead-in (or lookalike) or a Replaced marker.
LIST_RE = re.compile(r'^' + WS + r'*(?:[-*+]|\d+[.)])' + WS + r'+', _A)
HEADING_RE = re.compile(r'^' + WS + r'{0,3}#{1,6}(' + WS + r'|\Z)', _A)
FENCE_RE = re.compile(r'^' + WS + r'{0,3}(`{3,}|~{3,})', _A)
# Bold span at the start of a line, optionally after a list marker.
LEAD_RE = re.compile(
    r'^(' + WS + r'*(?:(?:[-*+]|\d+[.)])' + WS + r'+)?)\*\*([^*]+?)\*\*(' + DOT + r'*)\Z', _A
)
# Field separator inside a ruling: optional "·", then **Field:**
FIELD_SPLIT_RE = re.compile(r'(?:·' + WS + r'*)?\*\*(' + '|'.join(FIELDS) + r'):\*\*', _A)

R_PREFIX_RE = re.compile(r'^R-', _A)
BY_OWNER_RE = re.compile(r'\bby owner\b', _A | re.IGNORECASE)
REPLACED_SPAN_RE = re.compile(r'^Replaced\b', _A)
INLINE_CODE_RE = re.compile(r'`[^`]*`', _A)
BOLD_RE = re.compile(r'\*\*([^*]+?)\*\*(:?)', _A)
LOOKALIKE_ID_RE = re.compile(r'^R-[^' + WSC + r'·:]*', _A)
REPLACED_MARKER_RE = re.compile(
    r'^Replaced ([0-9]{4}-[0-9]{2}-[0-9]{2}) → (' + NWS + r'+):\Z', _A
)
LEAD_IN_RE = re.compile(
    r'^(' + NWS + r'+) · (' + NWS + r'+) by owner (' + NWS + r'+)\Z', _A
)
HEAD_ID_RE = re.compile(r'^(R-' + NWS + r'*)', _A)
TRAILING_COLON_RE = re.compile(r':\Z', _A)
TRAILING_DOT_SEP_RE = re.compile(WS + r'*·' + WS + r'*\Z', _A)
LABEL_COLON_RE = re.compile(r'^[A-Za-z]+:\Z', _A)
LABEL_RE = re.compile(r'^[A-Za-z]+\Z', _A)
AND_RE = re.compile(r'\band\b', _A)
REPLACES_SPLIT_RE = re.compile(r'[' + WSC + r',;]+', _A)
TRAILING_DOT_RE = re.compile(r'\.\Z', _A)
LEFTOVER_RE = re.compile(r'[,;.' + WSC + r']', _A)
DRIVE_RE = re.compile(r'^[A-Za-z]:', _A)
GLOB_CHARS_RE = re.compile(r'[*?]', _A)
GLOB_UNSUPPORTED_RE = re.compile(r'[{}[\]]', _A)
AREA_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]*\Z', _A)
AREA_DOC_RE = re.compile(r'^docs/[^/]+\.md\Z', _A)
PATTERN_RE = re.compile(r'^\^R-\(([A-Z0-9_|]+)\)-\[0-9\]\{3\}\$\Z', _A)
ID_AREA_RE = re.compile(r'^R-(' + DOT + r'+)-[0-9]{3}\Z', _A)
ENFORCED_RE = re.compile(r'^review\b', _A | re.IGNORECASE)
LINE_SPLIT_RE = re.compile(r'\r?\n')
SURROGATE_RE = re.compile('[\ud800-\udfff]')

# ---------------------------------------------------------------------------
# Helpers that reproduce JavaScript semantics the checker relies on.


class _Undefined(object):
    """JavaScript `undefined` (a missing property)."""

    def __repr__(self):
        return 'undefined'


UNDEFINED = _Undefined()


class _JsFunction(object):
    """A JavaScript function value (from a lookup that hits Object.prototype)."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '[Function: %s]' % self.name


# Own properties of Object.prototype: KINDS[x] is truthy for these in JS.
_OBJECT_PROTO_FUNCS = {
    'constructor', '__defineGetter__', '__defineSetter__', 'hasOwnProperty',
    '__lookupGetter__', '__lookupSetter__', 'isPrototypeOf',
    'propertyIsEnumerable', 'toString', 'valueOf', 'toLocaleString',
}


def _kind_of(word):
    """KINDS[word] as JavaScript evaluates it on a plain object literal."""
    if word in KINDS:
        return KINDS[word]
    if word in _OBJECT_PROTO_FUNCS:
        return _JsFunction(word)
    if word == '__proto__':
        return {}  # Object.prototype, which serializes as {}
    return None


def js_trim(s):
    return s.strip(WSC)


def _utf16_units(s):
    """The string as a sequence of UTF-16 code units (one char per unit)."""
    if all(ord(c) < 0x10000 for c in s):
        return s
    out = []
    for c in s:
        o = ord(c)
        if o >= 0x10000:
            o -= 0x10000
            out.append(chr(0xD800 + (o >> 10)))
            out.append(chr(0xDC00 + (o & 0x3FF)))
        else:
            out.append(c)
    return ''.join(out)


def _utf16_key(s):
    """Sort key giving JavaScript's default (UTF-16 code unit) string order."""
    return s.encode('utf-16-be', 'surrogatepass')


def _is_array_index(k):
    if k == '0':
        return True
    if not k or k[0] not in '123456789' or any(c not in '0123456789' for c in k):
        return False
    return int(k) <= 2 ** 32 - 2


def _js_object(pairs):
    """Builds a dict with JavaScript's own-property key order."""
    d = {}
    for k, v in pairs:
        d[k] = v
    idx = sorted((k for k in d if _is_array_index(k)), key=int)
    if not idx:
        return d
    out = {}
    for k in idx:
        out[k] = d[k]
    for k in d:
        if k not in out:
            out[k] = d[k]
    return out


def _reject_constant(name):
    raise ValueError('Unexpected token %s in JSON' % name)


def json_parse(text):
    """JSON.parse: numbers are doubles, keys in JavaScript order, no NaN/Infinity."""
    return json.loads(
        text,
        object_pairs_hook=_js_object,
        parse_int=float,
        parse_constant=_reject_constant,
    )


def _js_number(x):
    if x != x:
        return 'NaN'
    if x in (float('inf'), float('-inf')):
        return 'Infinity' if x > 0 else '-Infinity'
    if x == 0:
        return '0'
    if x < 0:
        return '-' + _js_number(-x)
    t = Decimal(repr(float(x))).as_tuple()
    all_digits = ''.join(str(d) for d in t.digits)
    digits = all_digits.rstrip('0')
    n = len(digits) + t.exponent + (len(all_digits) - len(digits))
    k = len(digits)
    if k <= n <= 21:
        return digits + '0' * (n - k)
    if 0 < n <= 21:
        return digits[:n] + '.' + digits[n:]
    if -6 < n <= 0:
        return '0.' + '0' * (-n) + digits
    e = n - 1
    sign = '+' if e >= 0 else '-'
    if k == 1:
        return digits + 'e' + sign + str(abs(e))
    return digits[0] + '.' + digits[1:] + 'e' + sign + str(abs(e))


def js_to_string(v):
    """String(v) / template-literal conversion."""
    if v is UNDEFINED:
        return 'undefined'
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return _js_number(float(v))
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return js_join(v, ',')
    return '[object Object]'


def js_join(items, sep):
    """Array.prototype.join: null and undefined become ''."""
    return sep.join('' if (x is None or x is UNDEFINED) else js_to_string(x) for x in items)


def _js_quote(s):
    out = ['"']
    for c in s:
        o = ord(c)
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\b':
            out.append('\\b')
        elif c == '\f':
            out.append('\\f')
        elif c == '\n':
            out.append('\\n')
        elif c == '\r':
            out.append('\\r')
        elif c == '\t':
            out.append('\\t')
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append('\\u%04x' % o)
        else:
            out.append(c)
    out.append('"')
    return ''.join(out)


def js_stringify(v, indent=0, _level=0):
    """JSON.stringify(v, null, indent). Returns UNDEFINED for unserializable values."""
    if v is UNDEFINED or isinstance(v, _JsFunction):
        return UNDEFINED
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f or f in (float('inf'), float('-inf')):
            return 'null'
        return _js_number(f)
    if isinstance(v, str):
        return _js_quote(v)
    pad = ' ' * (indent * (_level + 1))
    end = ' ' * (indent * _level)
    if isinstance(v, list):
        if not v:
            return '[]'
        parts = []
        for x in v:
            s = js_stringify(x, indent, _level + 1)
            parts.append('null' if s is UNDEFINED else s)
        if indent:
            return '[\n' + pad + (',\n' + pad).join(parts) + '\n' + end + ']'
        return '[' + ','.join(parts) + ']'
    parts = []
    for k, x in v.items():
        s = js_stringify(x, indent, _level + 1)
        if s is UNDEFINED:
            continue
        parts.append(_js_quote(k) + (': ' if indent else ':') + s)
    if not parts:
        return '{}'
    if indent:
        return '{\n' + pad + (',\n' + pad).join(parts) + '\n' + end + '}'
    return '{' + ','.join(parts) + '}'


def _same_value_key(v):
    """Key implementing SameValueZero (Array.prototype.includes, Set)."""
    if isinstance(v, str):
        return ('s', v)
    if v is True or v is False:
        return ('b', v)
    if isinstance(v, (int, float)):
        return ('n', float(v))
    if v is None:
        return ('null',)
    if v is UNDEFINED:
        return ('undefined',)
    return ('o', id(v))


def _js_includes(items, v):
    k = _same_value_key(v)
    return any(_same_value_key(x) == k for x in items)


def _js_get(obj, key):
    """obj?.[key] for a JSON value (none of the keys used exist on prototypes)."""
    if isinstance(obj, dict):
        return obj.get(key, UNDEFINED)
    return UNDEFINED


# Node's fs error texts (libuv), for "schema is not valid JSON: <message>".
_UV_MESSAGES = {
    'EACCES': 'permission denied',
    'EPERM': 'operation not permitted',
    'ENOTDIR': 'not a directory',
    'EISDIR': 'illegal operation on a directory',
    'ELOOP': 'too many symbolic links encountered',
    'ENAMETOOLONG': 'name too long',
    'EMFILE': 'too many open files',
    'ENFILE': 'file table overflow',
    'EIO': 'i/o error',
    'EBUSY': 'resource busy or locked',
    'ENXIO': 'no such device or address',
    'ENODEV': 'no such device',
    'ETIMEDOUT': 'connection timed out',
    'EAGAIN': 'resource temporarily unavailable',
}


def _node_fs_message(e, full):
    code = errno.errorcode.get(e.errno, 'UNKNOWN') if e.errno else 'UNKNOWN'
    desc = _UV_MESSAGES.get(code) or (os.strerror(e.errno).lower() if e.errno else 'unknown error')
    if code == 'EISDIR':
        return '%s: %s, read' % (code, desc)
    return "%s: %s, open '%s'" % (code, desc, full)


def _read_text(full):
    """fs.readFileSync(full, 'utf8'): invalid UTF-8 becomes U+FFFD, no newline translation."""
    with open(full, 'rb') as f:
        return f.read().decode('utf-8', 'replace')


def _scandir_sorted(d):
    """fs.readdirSync(d, {withFileTypes: true}): names sorted bytewise, as libuv does."""
    with os.scandir(os.fsencode(d)) as it:
        ents = sorted(it, key=lambda e: e.name)
    return [(e.name.decode('utf-8', 'replace'), e) for e in ents]


# --- Node path semantics (posix); Windows falls back to os.path. ------------

def _normalize_string(p, allow_above_root):
    res = ''
    last_segment_length = 0
    last_slash = -1
    dots = 0
    code = ''
    i = 0
    n = len(p)
    while i <= n:
        if i < n:
            code = p[i]
        elif code == '/':
            break
        else:
            code = '/'
        if code == '/':
            if last_slash == i - 1 or dots == 1:
                pass
            elif dots == 2:
                if (len(res) < 2 or last_segment_length != 2
                        or res[-1] != '.' or res[-2] != '.'):
                    if len(res) > 2:
                        last_slash_index = res.rfind('/')
                        if last_slash_index == -1:
                            res = ''
                            last_segment_length = 0
                        else:
                            res = res[:last_slash_index]
                            last_segment_length = len(res) - 1 - res.rfind('/')
                        last_slash = i
                        dots = 0
                        i += 1
                        continue
                    elif len(res) != 0:
                        res = ''
                        last_segment_length = 0
                        last_slash = i
                        dots = 0
                        i += 1
                        continue
                if allow_above_root:
                    res += '/..' if len(res) > 0 else '..'
                    last_segment_length = 2
            else:
                if len(res) > 0:
                    res += '/' + p[last_slash + 1:i]
                else:
                    res = p[last_slash + 1:i]
                last_segment_length = i - last_slash - 1
            last_slash = i
            dots = 0
        elif code == '.' and dots != -1:
            dots += 1
        else:
            dots = -1
        i += 1
    return res


def posix_normalize(p):
    """path.posix.normalize."""
    if p == '':
        return '.'
    is_abs = p[0] == '/'
    trailing = p[-1] == '/'
    p = _normalize_string(p, not is_abs)
    if p == '':
        if is_abs:
            return '/'
        return './' if trailing else '.'
    if trailing:
        p += '/'
    return '/' + p if is_abs else p


def _resolve(*segments):
    """path.resolve."""
    if os.name == 'nt':
        return os.path.abspath(os.path.join(*segments))
    resolved = ''
    absolute = False
    for seg in list(reversed(segments)) + [os.getcwd()]:
        if absolute:
            break
        if not seg:
            continue
        resolved = seg + '/' + resolved
        absolute = seg[0] == '/'
    resolved = _normalize_string(resolved, not absolute)
    if absolute:
        return '/' + resolved
    return resolved if resolved else '.'


def _is_absolute(p):
    if os.name == 'nt':
        return os.path.isabs(p) or p.startswith(('/', '\\'))
    return p.startswith('/')


def _is_outside(frm, to):
    """True if path.relative(frm, to) leaves frm."""
    if os.name == 'nt':
        try:
            rel = os.path.relpath(to, frm)
        except ValueError:
            return True
        return rel == '..' or rel.startswith('..' + os.sep) or os.path.isabs(rel)
    frm = _resolve(frm)
    to = _resolve(to)
    if to == frm:
        return False
    prefix = frm if frm.endswith('/') else frm + '/'
    return not to.startswith(prefix)


def _realpath(p):
    """fs.realpathSync: raises OSError if the path (or a link in it) is missing."""
    os.stat(p)
    return os.path.realpath(p)


# ---------------------------------------------------------------------------


def latest_today(now=None):
    """
    The latest calendar date anywhere on Earth (UTC+14) as YYYY-MM-DD, so a
    ruling dated "today" by an owner in any time zone is never in the future.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    t = now.astimezone(timezone.utc) + timedelta(hours=14)
    return '%04d-%02d-%02d' % (t.year, t.month, t.day)


def is_ruling_candidate(span, after):
    """
    True if a bold span at the start of a line is a ruling lead-in or lookalike.
    `after` is the text right after the closing **, for `**Ruled by owner …**:`.
    """
    if span.endswith(':') and (R_PREFIX_RE.search(span) or BY_OWNER_RE.search(span)):
        return True
    return bool(after.startswith(':') and not R_PREFIX_RE.search(span) and BY_OWNER_RE.search(span))


def _days_in_month(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return 30 if m in (4, 6, 9, 11) else 31


def date_problem(date, today):
    """Returns an error message for a bad date, or None if it is fine."""
    if not DATE_RE.search(date):
        return 'date "%s" is not YYYY-MM-DD' % date
    y, m, d = (int(x) for x in date.split('-'))
    # Date.UTC maps years 0-99 to 1900-1999, so those never round-trip.
    if y < 100 or not 1 <= m <= 12 or not 1 <= d <= _days_in_month(y, m):
        return 'date %s is not a real calendar date' % date
    if date > today:
        return 'date %s is in the future' % date
    return None


def is_quoted(text):
    """
    True if the text is in quotes: after trimming, it starts with " or \u201c
    and ends with " or \u201d, optionally followed by one ".", with at least one
    non-whitespace character between the quotes. Inner quotes are allowed.
    """
    t = js_trim(text)
    if t.endswith('.'):
        t = t[:-1]
    return len(t) >= 3 and t[0] in OPEN_QUOTES and t[-1] in CLOSE_QUOTES and js_trim(t[1:-1]) != ''


def glob_to_regexp(glob):
    """Converts a glob with *, ** and ? into a regex over posix relative paths (UTF-16 units)."""
    glob = _utf16_units(glob)
    out = []
    i = 0
    n = len(glob)
    while i < n:
        c = glob[i]
        if c == '*':
            if i + 1 < n and glob[i + 1] == '*':
                # "**/" matches zero or more whole segments; a trailing "**" matches anything.
                if i + 2 < n and glob[i + 2] == '/':
                    out.append('(?:[^/]+/)*')
                    i += 2
                else:
                    out.append(DOT + '*')
                    i += 1
            else:
                out.append('[^/]*')
        elif c == '?':
            out.append('[^/]')
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile('^' + ''.join(out) + r'\Z')


def is_glob(p):
    return bool(GLOB_CHARS_RE.search(p))


def list_files(root):
    """Lists every file under root as posix relative paths (skips .git, node_modules)."""
    out = []

    def walk(d, rel):
        for name, ent in _scandir_sorted(d):
            if name in SKIP_DIRS:
                continue
            r = rel + '/' + name if rel else name
            if ent.is_dir(follow_symlinks=False):
                walk(os.path.join(d, name), r)
            else:
                out.append(r)

    walk(root, '')
    return out


def backtick_items(value):
    """Splits a Paths/Tests value into backtick-quoted items."""
    items = []

    def repl(mo):
        items.append(js_trim(mo.group(1)))
        return ' '

    rest = re.sub(r'`([^`]*)`', repl, value)
    leftover = LEFTOVER_RE.sub('', AND_RE.sub(' ', rest))
    return items, leftover


def describe_diff(missing, extra):
    parts = []
    if missing:
        parts.append('is missing %s' % js_join(missing, ', '))
    if extra:
        parts.append('has extra %s' % js_join(extra, ', '))
    return ' and '.join(parts)


def read_schema(root, errors, today):
    """Reads the schema and checks its three area lists agree."""

    def err(message):
        errors.append({'file': SCHEMA_PATH, 'line': 1, 'id': '-', 'message': message})

    full = os.path.join(root, SCHEMA_PATH)
    try:
        text = _read_text(full)
    except OSError as e:
        err('schema file not found' if e.errno == errno.ENOENT
            else 'schema is not valid JSON: %s' % _node_fs_message(e, full))
        return None
    try:
        schema = json_parse(text)
    except (ValueError, RecursionError) as e:
        err('schema is not valid JSON: %s' % e)
        return None
    if schema is None:
        raise TypeError("Cannot read properties of null (reading 'x-areas')")
    areas = _js_get(schema, 'x-areas')
    if not isinstance(areas, dict):
        err('schema has no "x-areas" object')
        return None
    area_names = list(areas.keys())
    area_docs = list(areas.values())

    for area, doc in areas.items():
        if not AREA_NAME_RE.search(area):
            err('x-areas: area "%s" must be upper-case letters, digits or _' % area)
        if not isinstance(doc, str) or not AREA_DOC_RE.search(doc) or doc in ['docs/' + n for n in RESERVED_DOCS]:
            err('x-areas: area %s must map to a docs/<name>.md file, got %s' % (area, js_to_string(js_stringify(doc))))
    seen_docs = set()
    for doc in area_docs:
        k = _same_value_key(doc)
        if k in seen_docs:
            err('x-areas: %s is listed for more than one area' % js_to_string(doc))
        seen_docs.add(k)

    pattern = _js_get(_js_get(_js_get(schema, '$defs'), 'rulingId'), 'pattern')
    pm = PATTERN_RE.search(pattern) if isinstance(pattern, str) else None
    if not pm:
        err('$defs.rulingId.pattern must look like ^R-(A|B)-[0-9]{3}$, got %s' % js_to_string(js_stringify(pattern)))
    else:
        pat_areas = pm.group(1).split('|')
        missing = [a for a in area_names if a not in pat_areas]
        extra = [a for a in pat_areas if a not in area_names]
        if missing or extra:
            err('area lists disagree: $defs.rulingId.pattern %s compared with x-areas' % describe_diff(missing, extra))

    doc_enum = _js_get(_js_get(_js_get(schema, 'properties'), 'doc'), 'enum')
    if not isinstance(doc_enum, list):
        err('schema has no properties.doc.enum list')
    else:
        missing = [d for d in area_docs if not _js_includes(doc_enum, d)]
        extra = [d for d in doc_enum if not _js_includes(area_docs, d)]
        if missing or extra:
            err('area lists disagree: properties.doc.enum %s compared with x-areas' % describe_diff(missing, extra))

    # Optional x-area-paths: {AREA: [path or glob, ...]}. Items are checked
    # against the file tree in check_rulings, not here.
    area_paths = {}
    raw = _js_get(schema, 'x-area-paths')
    if raw is not UNDEFINED:
        if not isinstance(raw, dict):
            err('x-area-paths must be an object mapping areas to lists of paths')
        else:
            for area, items in raw.items():
                if area not in areas:
                    err('x-area-paths: area %s is not in x-areas' % area)
                elif (not isinstance(items, list) or not items
                        or any(not isinstance(x, str) or not x for x in items)):
                    err('x-area-paths: area %s must map to a non-empty list of non-empty strings' % area)
                else:
                    area_paths[area] = items

    # Optional x-quotes-since: "YYYY-MM-DD", a real date, not in the future.
    # From that day on, decisions and Why must be the owner's words in quotes.
    quotes_since = None
    raw = _js_get(schema, 'x-quotes-since')
    if raw is not UNDEFINED:
        if not isinstance(raw, str):
            err('x-quotes-since must be a YYYY-MM-DD date string, got %s' % js_to_string(js_stringify(raw)))
        else:
            dp = date_problem(raw, today)
            if dp:
                err('x-quotes-since: %s' % dp)
            else:
                quotes_since = raw
    return {'areas': areas, 'areaPaths': area_paths, 'quotesSince': quotes_since,
            'quotesSinceSet': raw is not UNDEFINED}


def parse_doc(file, text, errors, today, doc=None):
    """
    Parses one area doc or history file into rulings and Replaced markers.
    `file` is where the text comes from; `doc` is its area doc (default: the
    file itself). Malformed lookalikes are reported as errors.
    """
    if doc is None:
        doc = file
    lines = LINE_SPLIT_RE.split(text)
    rulings = []
    markers = []

    def err(line, rid, message):
        errors.append({'file': file, 'line': line, 'id': rid, 'message': message})

    # Mark lines inside fenced code blocks.
    in_code = [False] * len(lines)
    fence = None
    fence_line = -1
    for i, ln in enumerate(lines):
        m = FENCE_RE.search(ln)
        if fence:
            in_code[i] = True
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and js_trim(ln) == m.group(1):
                fence = None
        elif m:
            in_code[i] = True
            fence = m.group(1)
            fence_line = i
    if fence:
        err(fence_line + 1, '-', 'unclosed code fence')

    def is_boundary(i):
        if i >= len(lines) or in_code[i]:
            return True
        ln = lines[i]
        if js_trim(ln) == '' or LIST_RE.search(ln) or HEADING_RE.search(ln):
            return True
        lead = LEAD_RE.search(ln)
        if not lead:
            return False
        span = js_trim(lead.group(2))
        return bool(REPLACED_SPAN_RE.search(span)) or is_ruling_candidate(span, lead.group(3))

    # Collects the block starting at line i: returns (joined_text, last_line_index).
    def block(i, first):
        parts = [first]
        j = i + 1
        while not is_boundary(j):
            parts.append(js_trim(lines[j]))
            j += 1
        return js_trim(' '.join(parts)), j - 1

    # Lookalikes in a piece of text: bold "R-..." that isn't a valid ID, or a
    # bold "... by owner ..." lead-in that doesn't start a line.
    def scan_lookalikes(text, line_no):
        no_inline = INLINE_CODE_RE.sub('', text)
        for bm in BOLD_RE.finditer(no_inline):
            s = js_trim(bm.group(1))
            if R_PREFIX_RE.search(s):
                idm = LOOKALIKE_ID_RE.search(s).group(0)
                if not ID_RE.search(idm):
                    err(line_no, idm, 'malformed ruling ID "%s"; expected R-AREA-NNN' % idm)
                elif BY_OWNER_RE.search(s):
                    err(line_no, idm, 'malformed ruling lead-in; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:** at the start of a line')
            elif BY_OWNER_RE.search(s) and (s.endswith(':') or bm.group(2) == ':'):
                err(line_no, '-', 'ruling lead-in "**%s**%s" has no ID or does not start the line' % (s, bm.group(2)))

    # Scans the continuation lines i+1..end of a block.
    def scan_continuation(i, end):
        for j in range(i + 1, end + 1):
            scan_lookalikes(lines[j], j + 1)

    prev_ruling_end = -2  # index of the last line of the previous ruling (or its marker)
    prev_ruling = None
    prev_malformed_end = -2  # index of the last line of the previous malformed ruling

    i = 0
    while i < len(lines):
        if in_code[i]:
            i += 1
            continue
        line_no = i + 1
        raw = lines[i]
        lead = LEAD_RE.search(raw)
        span = js_trim(lead.group(2)) if lead else None

        if lead and REPLACED_SPAN_RE.search(span):
            note, end = block(i, js_trim(lead.group(3)))
            scan_lookalikes(lead.group(3), line_no)
            scan_continuation(i, end)
            m = REPLACED_MARKER_RE.search(span)
            kept = False
            if not m:
                err(line_no, '-', 'malformed Replaced marker "**%s**"; expected **Replaced YYYY-MM-DD → R-AREA-NNN:**' % span)
            elif prev_malformed_end == i - 1:
                err(line_no, '-', 'Replaced marker follows a malformed ruling; fix the ruling above it')
            elif prev_ruling_end != i - 1 or not prev_ruling:
                err(line_no, '-', 'Replaced marker must be on the line right after the ruling it replaces')
            else:
                date, by = m.group(1), m.group(2)
                dp = date_problem(date, today)
                if dp:
                    err(line_no, prev_ruling['id'], 'Replaced marker %s' % dp)
                if not ID_RE.search(by):
                    err(line_no, prev_ruling['id'], 'Replaced marker points to malformed ID "%s"' % by)
                if 'replacedBy' in prev_ruling:
                    err(line_no, prev_ruling['id'], 'ruling has more than one Replaced marker')
                else:
                    prev_ruling['replacedBy'] = {'id': by, 'date': date}
                    markers.append({'ruling': prev_ruling, 'line': line_no, 'by': by})
                if not note:
                    err(line_no, prev_ruling['id'], 'Replaced marker has no note')
                # A second marker right after this one is reported as a duplicate.
                prev_ruling_end = end
                kept = True
            if not kept:
                prev_ruling = None
            prev_malformed_end = -2
            i = end + 1
            continue

        if lead and is_ruling_candidate(span, lead.group(3)):
            colon_outside = not span.endswith(':')
            head = span if colon_outside else js_trim(span[:-1])
            rest = lead.group(3)[1:] if colon_outside else lead.group(3)
            m = None if colon_outside else LEAD_IN_RE.search(head)
            problems = []
            rid = '-'
            kind = None
            if not m:
                idm = HEAD_ID_RE.search(head)
                if idm:
                    rid = idm.group(1)
                if not idm:
                    problems.append('ruling lead-in has no ID; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**')
                elif not ID_RE.search(TRAILING_COLON_RE.sub('', idm.group(1), count=1)):
                    rid = TRAILING_COLON_RE.sub('', idm.group(1), count=1)
                    problems.append('malformed ruling ID "%s"; expected R-AREA-NNN' % rid)
                else:
                    problems.append('malformed ruling lead-in "**%s**"; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**' % span)
            else:
                rid = m.group(1)
                kind = _kind_of(m.group(2))
                if not ID_RE.search(m.group(1)):
                    problems.append('malformed ruling ID "%s"; expected R-AREA-NNN' % m.group(1))
                if kind is None:
                    problems.append('unknown kind "%s by owner"; expected Ruled, Parked or Asked' % m.group(2))
                if not DATE_RE.search(m.group(3)):
                    problems.append('date "%s" is not YYYY-MM-DD' % m.group(3))
            body, end = block(i, js_trim(rest))
            for p in problems:
                err(line_no, rid, p)
            # Every body line except the lead-in itself is scanned for lookalikes.
            scan_lookalikes(rest, line_no)
            scan_continuation(i, end)
            if problems:
                prev_ruling = None
                prev_ruling_end = -2
                prev_malformed_end = end
                i = end + 1
                continue
            ruling = {'id': rid, 'kind': kind, 'date': m.group(3), 'doc': doc, 'file': file, 'line': line_no}
            parse_fields(ruling, body, err)
            rulings.append(ruling)
            prev_ruling = ruling
            prev_ruling_end = end
            prev_malformed_end = -2
            i = end + 1
            continue

        scan_lookalikes(raw, line_no)
        prev_ruling = None
        prev_malformed_end = -2
        i += 1
    return rulings, markers


def _dedupe(items):
    out = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_fields(ruling, body, err):
    """Splits a ruling body into decision and fields."""
    parts = FIELD_SPLIT_RE.split(body)
    decision = js_trim(TRAILING_DOT_SEP_RE.sub('', parts[0], count=1))

    def at(msg):
        err(ruling['line'], ruling['id'], msg)

    if not decision:
        at('ruling has no decision text')
    # A bold span that looks like a field label (**Word:** or **Word**:) must be
    # exactly one of the known fields, e.g. not **Paths**:, **paths:** or **Path:**.
    for lm in BOLD_RE.finditer(INLINE_CODE_RE.sub('', body)):
        whole, inner, colon = lm.group(0), lm.group(1), lm.group(2)
        looks_like_label = bool(LABEL_COLON_RE.search(inner)) or (bool(LABEL_RE.search(inner)) and colon == ':')
        if looks_like_label and (colon or inner[:-1] not in FIELDS):
            at('unknown field "%s"' % whole)
    ruling['decision'] = decision
    seen = set()
    for k in range(1, len(parts), 2):
        name = parts[k]
        value = js_trim(TRAILING_DOT_SEP_RE.sub('', parts[k + 1], count=1))
        if name in seen:
            at('%s appears more than once' % name)
            continue
        seen.add(name)
        if not value:
            at('%s is empty' % name)
            continue
        if name in ('Why', 'Covers'):
            ruling[name.lower()] = value
        elif name == 'Enforced':
            if not ENFORCED_RE.search(value):
                at('Enforced must start with "review"; link a test with Tests instead')
            else:
                ruling['enforced'] = value
        elif name == 'Replaces':
            ids = [TRAILING_DOT_RE.sub('', s, count=1)
                   for s in REPLACES_SPLIT_RE.split(AND_RE.sub(' ', value.replace('`', ' ')))]
            ids = [s for s in ids if s]
            for x in ids:
                if not ID_RE.search(x):
                    at('Replaces has malformed ID "%s"' % x)
            good = [x for x in ids if ID_RE.search(x)]
            if len(set(good)) != len(good):
                at('Replaces lists an ID more than once')
            if good:
                ruling['replaces'] = _dedupe(good)
        elif name == 'Source':
            # One file in docs/owner-words/; it is checked on disk in the full check.
            items, leftover = backtick_items(value)
            non_empty = [x for x in items if x]
            if leftover or not items:
                at('Source must be backtick-quoted, e.g. `docs/owner-words/billing.md`')
            elif len(non_empty) != len(items):
                at('Source has an empty item')
            elif len(non_empty) > 1:
                at('Source must be one file')
            elif is_glob(non_empty[0]):
                at('Source must be a file, not a glob')
            elif not SOURCE_RE.search(non_empty[0]):
                at('Source must be a file in docs/owner-words/')
            else:
                ruling['source'] = non_empty[0]
        else:
            items, leftover = backtick_items(value)
            if leftover:
                at('%s items must be backtick-quoted, e.g. `src/x.js`' % name)
            non_empty = [x for x in items if x]
            if len(non_empty) != len(items):
                at('%s has an empty item' % name)
            if name == 'Paths' and len(set(non_empty)) != len(non_empty):
                at('Paths lists an item more than once')
            if non_empty:
                ruling[name.lower()] = _dedupe(non_empty) if name == 'Paths' else non_empty


def check_path_item(root, real_root, item, field, get_files, at, label=None):
    """
    Checks one Paths/Tests item against the file tree. Returns the full paths it
    names (the item itself, or a glob's matches) if it passed, else None.
    """
    if label is None:
        label = 'Paths' if field == 'paths' else 'Tests'
    if _is_absolute(item) or DRIVE_RE.search(item):
        at('%s item "%s" points outside the repo' % (label, item))
        return None
    if '\\' in item:
        at('%s item "%s" must use / separators' % (label, item))
        return None

    # Follows symlinks: an item inside the repo may still point outside it.
    def real_outside(full):
        try:
            return _is_outside(real_root, _realpath(full))
        except (OSError, ValueError):
            return False  # broken symlink or unreadable: reported elsewhere, if at all

    resolved = _resolve(root, item)
    if _is_outside(root, resolved):
        at('%s item "%s" points outside the repo' % (label, item))
        return None
    # Tests must be test files; docs/ (where the rulings live) never counts.
    in_docs_msg = 'Tests item "%s" points into docs/; list a test file' % item
    if field == 'tests' and not is_glob(item) and _in_docs(re.sub(r'^\./', '', item, count=1)):
        at(in_docs_msg)
        return None
    if is_glob(item):
        if GLOB_UNSUPPORTED_RE.search(item):
            at('%s glob "%s" uses unsupported glob syntax ({} and [] are not supported)' % (label, item))
            return None
        rx = glob_to_regexp(posix_normalize(re.sub(r'^\./', '', item, count=1)))
        matches = [f for f in get_files() if rx.search(_utf16_units(f))]
        if not matches:
            at('%s glob "%s" matches no files' % (label, item))
            return None
        if field == 'tests':
            matches = [f for f in matches if not _in_docs(f)]
            if not matches:
                at(in_docs_msg)
                return None
        ok = True
        for f in matches:
            if real_outside(os.path.join(root, f)):
                at('%s glob "%s" matches "%s", which points outside the repo' % (label, item, f))
                ok = False
        return [os.path.join(root, f) for f in matches] if ok else None
    elif not os.path.exists(resolved):
        at('%s item "%s" does not exist' % (label, item))
    elif real_outside(resolved):
        at('%s item "%s" points outside the repo' % (label, item))
    else:
        return [resolved]
    return None


def _in_docs(rel):
    """True if a root-relative posix path is docs/ or inside it."""
    p = posix_normalize(rel) if rel else '.'
    return p == 'docs' or p.startswith('docs/')


def id_mention_regexp(rid):
    """
    A bytes regex for mentions of `rid` in a test file: any case, - or _ as
    separators, not inside a longer name or number (R-X-004 is not in R-X-0042).
    """
    m = re.match(r'^R-(.+)-([0-9]{3})\Z', rid)
    return re.compile(
        (r'(?<![A-Za-z0-9])R[-_]' + re.escape(m.group(1)) + r'[-_]' + m.group(2) + r'(?![0-9])').encode('utf-8'),
        re.IGNORECASE | re.ASCII,
    )


_CHUNK = 1 << 16


def _mentions(full, rx, length):
    """
    Whether the file at `full` mentions a ruling: 'yes', 'no', 'dir' (a
    directory) or 'unreadable'. Reads in chunks; `length` is the length of a
    match, and the last length + 1 bytes are kept between chunks.
    """
    if os.path.isdir(full):
        return 'dir'
    keep = length + 1
    try:
        with open(full, 'rb') as f:
            buf = b''
            at_start = True
            while True:
                chunk = f.read(_CHUNK)
                eof = not chunk
                buf += chunk
                for m in rx.finditer(buf):
                    # A match at the very start lacks the byte before it, and one
                    # at the very end the byte after it, unless that is the file's
                    # start or end. Kept bytes bring such matches back next time.
                    if (m.start() > 0 or at_start) and (m.end() < len(buf) or eof):
                        return 'yes'
                if eof:
                    return 'no'
                if len(buf) > keep:
                    buf = buf[-keep:]
                    at_start = False
    except OSError:
        return 'unreadable'


def read_docs(root, today, errors):
    """
    Reads the schema and parses every area doc and every history file
    (docs/history/*.md); touches nothing else (never docs/owner-words/).
    Returns (schema, doc_files, history_files, rulings, markers); problems go
    to `errors`.
    """
    rulings = []
    markers = []

    schema = read_schema(root, errors, today)
    areas = schema['areas'] if schema else {}
    docs_with_area = {d for d in areas.values() if isinstance(d, str)}

    docs_dir = os.path.join(root, 'docs')
    doc_files = []
    try:
        doc_files = sorted(
            ('docs/' + name for name, e in _scandir_sorted(docs_dir)
             if e.is_file(follow_symlinks=False) and name.endswith('.md') and name not in RESERVED_DOCS),
            key=_utf16_key,
        )
    except OSError:
        errors.append({'file': 'docs/', 'line': None, 'id': '-', 'message': 'docs/ folder not found'})

    # History files are optional: docs/history/ exists once a ruling is replaced.
    # README.md and RULINGS.md are never history files, as in docs/.
    history_files = []
    try:
        history_files = sorted(
            (HISTORY_DIR + '/' + name for name, e in _scandir_sorted(os.path.join(root, HISTORY_DIR))
             if e.is_file(follow_symlinks=False) and name.endswith('.md') and name not in RESERVED_DOCS),
            key=_utf16_key,
        )
    except OSError:
        pass

    # The schema must not go stale: every doc has an area, every area a doc,
    # and every history file an area doc.
    if schema:
        for doc in doc_files:
            if doc not in docs_with_area:
                errors.append({'file': doc, 'line': 1, 'id': '-', 'message': '%s has no area in x-areas' % doc})
        for area, doc in areas.items():
            if isinstance(doc, str) and doc not in doc_files:
                errors.append({'file': SCHEMA_PATH, 'line': 1, 'id': '-', 'message': 'area %s: %s does not exist' % (area, doc)})
        for hist in history_files:
            doc = history_doc(hist)
            if doc not in docs_with_area:
                errors.append({'file': hist, 'line': 1, 'id': '-',
                               'message': '%s has no area doc %s in x-areas' % (hist, doc)})

    for doc in doc_files:
        parsed_rulings, parsed_markers = parse_doc(doc, _read_text(os.path.join(root, doc)), errors, today)
        rulings.extend(parsed_rulings)
        markers.extend(parsed_markers)
    for hist in history_files:
        parsed_rulings, parsed_markers = parse_doc(hist, _read_text(os.path.join(root, hist)), errors, today,
                                                   doc=history_doc(hist))
        rulings.extend(parsed_rulings)
        markers.extend(parsed_markers)
    return schema, doc_files, history_files, rulings, markers


def history_doc(hist):
    """The area doc of a history file: docs/history/<name>.md -> docs/<name>.md."""
    return 'docs/' + hist[len(HISTORY_DIR) + 1:]


def history_file(doc):
    """The history file of an area doc: docs/<name>.md -> docs/history/<name>.md."""
    return HISTORY_DIR + '/' + doc[len('docs/'):]


def check_doc_rules(schema, rulings, markers, today, errors):
    """
    The checks the docs alone settle, with no file tree: rule 1 (unique IDs),
    rule 2 (Replaces and Replaced markers link both ways), rule 4 (dates),
    rule 5 (known area, right doc), where a ruling sits (in force in the
    area doc, replaced in its history file) and owner quotes (x-quotes-since).
    Used by the full check and by lookups. Errors point to the file a ruling
    sits in.
    """
    areas = schema['areas'] if schema else {}
    quotes_since = schema['quotesSince'] if schema else None
    by_id = {}
    for r in rulings:
        def at(message, r=r):
            errors.append({'file': r['file'], 'line': r['line'], 'id': r['id'], 'message': message})

        # Rule 1: unique ID, across area docs and history files.
        first = by_id.get(r['id'])
        if first:
            at('duplicate ID; first defined at %s:%s' % (first['file'], first['line']))
        else:
            by_id[r['id']] = r

        # Rule 4: real date, not in the future.
        dp = date_problem(r['date'], today)
        if dp:
            at(dp)

        # Rule 5: known area, in its area doc or that doc's history file.
        area = ID_AREA_RE.search(r['id']).group(1)
        placed = True
        if schema and area not in areas:
            at("area %s is not in the schema's x-areas" % area)
            placed = False
        elif schema and not (isinstance(areas[area], str) and areas[area] == r['doc']):
            want = areas[area]
            if isinstance(want, str) and AREA_DOC_RE.search(want):
                at('area %s belongs in %s or %s, not %s' % (area, want, history_file(want), r['file']))
            else:
                at('area %s belongs in %s, not %s' % (area, js_to_string(want), r['file']))
            placed = False

        # In force in the area doc; replaced in its history file. Checked only
        # when the area is right, so the advice never contradicts rule 5.
        if placed:
            in_history = r['file'] != r['doc']
            if 'replacedBy' in r and not in_history:
                at('replaced ruling must move to %s' % history_file(r['doc']))
            elif 'replacedBy' not in r and in_history:
                at('ruling in history has no Replaced marker; rulings in force belong in %s' % r['doc'])

        # Owner quotes: from x-quotes-since on, the decision and Why are the
        # owner's exact words in quotes. An empty decision is reported already.
        if quotes_since and r['date'] >= quotes_since:
            if r['decision'] and not is_quoted(r['decision']):
                at("decision must be the owner's exact words in quotes (required for rulings dated from %s)"
                   % quotes_since)
            if 'why' in r and not is_quoted(r['why']):
                at("Why must be the owner's exact words in quotes")

    # Rule 2: Replaces and Replaced markers link both ways.
    for r in rulings:
        for old in r.get('replaces') or []:
            target = by_id.get(old)

            def at(message, r=r):
                errors.append({'file': r['file'], 'line': r['line'], 'id': r['id'], 'message': message})

            if old == r['id']:
                at('ruling replaces itself')
            elif not target:
                at('Replaces %s, which does not exist' % old)
            elif 'replacedBy' not in target or target['replacedBy']['id'] != r['id']:
                at('Replaces %s, but %s has no "Replaced → %s" marker' % (old, old, r['id']))
    for mk in markers:
        ruling, line, by = mk['ruling'], mk['line'], mk['by']
        target = by_id.get(by)
        if not ID_RE.search(by):
            continue  # already reported
        if not target:
            errors.append({'file': ruling['file'], 'line': line, 'id': ruling['id'],
                           'message': 'Replaced → %s, which does not exist' % by})
        elif ruling['id'] not in (target.get('replaces') or []):
            errors.append({'file': ruling['file'], 'line': line, 'id': ruling['id'],
                           'message': 'Replaced → %s, but %s does not list %s in Replaces' % (by, by, ruling['id'])})


def check_rulings(root=None, now=None):
    """
    Checks the rulings in the repo at `root` (default: current directory).
    `now` (an aware datetime) replaces the current time (for tests).
    Returns {'rulings': [...], 'errors': [{file, line, id, message}], 'docCount': int,
    'historyCount': int, 'schemaNotes': [{file, line, id, message}] (the
    x-quotes-since note), 'notes': [{file, line, id, message}],
    'enforcement': {tested, review, unenforced, inForce}}.
    """
    root = _resolve(os.getcwd() if root is None else os.fspath(root))
    today = latest_today(now)
    errors = []
    schema, doc_files, history_files, rulings, markers = read_docs(root, today, errors)

    files_cache = []

    def get_files():
        if not files_cache:
            files_cache.append(list_files(root))
        return files_cache[0]

    real_root = root
    try:
        real_root = _realpath(root)
    except (OSError, ValueError):
        pass  # root does not exist; the docs/ and schema errors already say so.

    # x-area-paths items follow the same rules as Paths items.
    for area, items in (schema['areaPaths'] if schema else {}).items():
        def at_schema(message):
            errors.append({'file': SCHEMA_PATH, 'line': 1, 'id': '-', 'message': message})

        for item in items:
            check_path_item(root, real_root, item, 'paths', get_files, at_schema, label='x-area-paths %s' % area)

    check_doc_rules(schema, rulings, markers, today, errors)

    # Rule 3: Paths and Tests exist, inside the repo. Each Tests file (or at
    # least one file a Tests glob matches, outside docs/) must mention the
    # ruling's ID: any case, with - or _ separators (test names cannot contain
    # hyphens). A ruling counts as tested only if none of its Tests items fail.
    # Replaced rulings are skipped: history is never reworded, so it must not
    # fail when the code it named moves. Their Source is still checked.
    real_owner_words = os.path.join(real_root, 'docs', 'owner-words')
    failed_tests = set()
    for r in rulings:
        def at(message, r=r):
            errors.append({'file': r['file'], 'line': r['line'], 'id': r['id'], 'message': message})

        for field in (() if 'replacedBy' in r else ('paths', 'tests')):
            for item in r.get(field) or []:
                n_before = len(errors)
                found = check_path_item(root, real_root, item, field, get_files, at)
                if field == 'tests' and found is not None:
                    rx = id_mention_regexp(r['id'])
                    states = [_mentions(f, rx, len(r['id'])) for f in found]
                    if 'yes' in states:
                        pass
                    elif not is_glob(item) and states[0] == 'dir':
                        at('Tests item "%s" is a directory; list test files' % item)
                    elif 'unreadable' in states:
                        at('Tests item "%s" could not be read' % item)
                    else:
                        alt = r['id'].replace('-', '_')
                        at('Tests item "%s" does not mention %s (any case, - or _ separators, e.g. %s)'
                           % (item, r['id'], alt))
                if field == 'tests' and len(errors) > n_before:
                    failed_tests.add(id(r))

        # Source: the owner's words, in a file in docs/owner-words/ that
        # mentions the ruling's ID like a Tests file does. Never affects coverage.
        if 'source' in r:
            item = r['source']
            found = check_path_item(root, real_root, item, 'source', get_files, at, label='Source')
            if found is not None and not _strictly_inside(real_owner_words, found[0]):
                at('Source "%s" must resolve to a file in docs/owner-words/' % item)
            elif found is not None:
                state = _mentions(found[0], id_mention_regexp(r['id']), len(r['id']))
                if state == 'dir':
                    at('Source "%s" is a directory; list a file in docs/owner-words/' % item)
                elif state == 'unreadable':
                    at('Source "%s" could not be read' % item)
                elif state == 'no':
                    at('Source "%s" does not mention %s' % (item, r['id']))

    errors.sort(key=lambda e: (_utf16_key(e['file']), e['line'] if e['line'] is not None else 0))

    # Enforcement coverage of in-force rulings (Ruled, not replaced). Never an
    # error. Each ID counts once, even if it is (wrongly) defined twice.
    notes = []
    counts = {'tested': 0, 'review': 0, 'unenforced': 0, 'inForce': 0}
    counted = set()
    for r in rulings:
        if not is_in_force(r) or r['id'] in counted:
            continue
        counted.add(r['id'])
        counts['inForce'] += 1
        if 'tests' in r and id(r) not in failed_tests:
            counts['tested'] += 1
        elif 'enforced' in r:
            counts['review'] += 1
        else:
            counts['unenforced'] += 1
            if 'tests' in r:
                continue  # its failing Tests items are already reported as errors
            notes.append({'file': r['file'], 'line': r['line'], 'id': r['id'],
                          'message': 'note: not enforced; add Tests or Enforced: review'})
    # Not an error: without x-quotes-since, owner quotes are not checked.
    schema_notes = []
    if schema and not schema['quotesSinceSet']:
        schema_notes.append({'file': SCHEMA_PATH, 'line': None, 'id': '-', 'message': QUOTES_SINCE_NOTE})
    return {'rulings': [to_schema_shape(r) for r in rulings], 'errors': errors, 'docCount': len(doc_files),
            'historyCount': len(history_files), 'schemaNotes': schema_notes, 'notes': notes,
            'enforcement': counts}


def _strictly_inside(real_dir, full):
    """True if the real path of `full` is inside `real_dir` (not `real_dir` itself)."""
    try:
        real = _realpath(full)
    except (OSError, ValueError):
        return False
    return real != _resolve(real_dir) and not _is_outside(real_dir, real)


def is_in_force(r):
    """A Ruled ruling with no Replaced marker."""
    return r.get('kind') == 'ruled' and 'replacedBy' not in r


def to_schema_shape(r):
    """Orders keys as in the schema and drops absent optional fields."""
    out = {'id': r['id']}
    if not isinstance(r['kind'], _JsFunction):  # JSON.stringify drops functions
        out['kind'] = r['kind']
    out.update({'date': r['date'], 'doc': r['doc'], 'file': r['file'], 'line': r['line'], 'decision': r['decision']})
    for k in ('why', 'covers', 'paths', 'replaces', 'replacedBy', 'tests', 'enforced', 'source'):
        if k in r:
            out[k] = r[k]
    return out


class UsageError(Exception):
    """A lookup that cannot run; `code` is the exit status (2 usage, 1 not found)."""

    def __init__(self, message, code=2):
        Exception.__init__(self, message)
        self.code = code


def normalize_lookup_path(root, p):
    """A --for path as a posix path relative to root, or UsageError if outside it."""
    p = p.replace('\\', '/')
    if _is_absolute(p) or DRIVE_RE.search(p):
        if _is_outside(root, p):
            try:
                real_root, real_p = os.path.realpath(root), os.path.realpath(p)
            except (OSError, ValueError):
                real_root = real_p = None
            if real_root is None or _is_outside(real_root, real_p):
                raise UsageError('--for path "%s" is outside the repo root %s' % (p, root))
            root, p = real_root, real_p
        try:
            p = os.path.relpath(_resolve(p), _resolve(root)).replace(os.sep, '/')
        except ValueError:  # Windows: another drive
            raise UsageError('--for path "%s" is outside the repo root %s' % (p, root))
    while p.startswith('./'):
        p = p[2:]
    p = posix_normalize(p) if p else '.'
    if p == '..' or p.startswith('../'):
        raise UsageError('--for path "%s" is outside the repo root %s' % (p, root))
    if len(p) > 1 and p.endswith('/'):
        p = p.rstrip('/')
    return p


def item_matches(item, path, _cache={}):
    """True if a Paths/x-area-paths item covers the root-relative posix path."""
    if '\\' in item or _is_absolute(item):
        return False
    it = re.sub(r'^\./', '', item, count=1)
    if is_glob(item):
        if GLOB_UNSUPPORTED_RE.search(item):
            return False
        rx = _cache.get(it)
        if rx is None:
            rx = _cache[it] = glob_to_regexp(posix_normalize(it))
        return bool(rx.search(_utf16_units(path)))
    it = posix_normalize(it).rstrip('/')
    if it in ('', '.'):
        return True  # `.` or `./`: the whole repo
    return path == it or path.startswith(it + '/')


def _area_of(r):
    return ID_AREA_RE.search(r['id']).group(1)


def _has_rulings(root):
    """True if root has a docs/ folder and a readable schema that parses to a JSON object."""
    if not os.path.isdir(os.path.join(root, 'docs')):
        return False
    try:
        schema = json_parse(_read_text(os.path.join(root, SCHEMA_PATH)))
    except (OSError, ValueError, RecursionError):
        return False
    return isinstance(schema, dict)


def lookup_rulings(root=None, for_paths=None, area=None, rid=None, now=None):
    """
    Finds rulings without walking the repo: reads the schema, the area docs
    and the history files only.
    Pass exactly one of for_paths (a list), area or rid. --for and --area pick
    rulings in force (in an area doc and not replaced), of any kind (Parked
    and Asked too); --id finds any ruling, including those in history files. Never reads
    docs/owner-words/. Returns {'groups': [(label, [rulings])], 'rulings': [...],
    'problems': int}, rulings in schema shape ordered by area doc, then file
    (the area doc before its history file), then line. Raises UsageError.
    """
    root = _resolve(os.getcwd() if root is None else os.fspath(root))
    if not _has_rulings(root):
        raise UsageError('error: no rulings found at %s (missing or unreadable %s, or missing docs/); run from the repo root or pass --root'
                         % (root, SCHEMA_PATH))
    errors = []
    today = latest_today(now)
    schema, _docs, _history, rulings, markers = read_docs(root, today, errors)
    check_doc_rules(schema, rulings, markers, today, errors)
    areas = schema['areas'] if schema else {}
    area_paths = schema['areaPaths'] if schema else {}
    rulings = sorted(rulings, key=_lookup_order)
    groups = []

    if for_paths:
        for raw in for_paths:
            path = normalize_lookup_path(root, raw)
            hit_areas = {a for a, items in area_paths.items() if any(item_matches(x, path) for x in items)}
            picked = [
                r for r in rulings
                if _in_force_place(r) and (
                    _area_of(r) in hit_areas
                    or any(item_matches(x, path) for x in r.get('paths') or []))
            ]
            groups.append((path, picked))
    elif area is not None:
        if area not in areas:
            raise UsageError('unknown area "%s"; areas in x-areas: %s' % (area, js_join(list(areas.keys()), ', ') or '(none)'))
        groups.append((area, [r for r in rulings if _area_of(r) == area and _in_force_place(r)]))
    elif rid is not None:
        picked = [r for r in rulings if r['id'] == rid]
        if not picked:
            raise UsageError('no ruling %s in docs/' % rid, code=1)
        groups.append((rid, picked))
    else:
        raise UsageError('no lookup given')

    union = []
    seen = set()
    for _label, picked in groups:
        for r in picked:
            if id(r) not in seen:
                seen.add(id(r))
                union.append(r)
    union.sort(key=_lookup_order)
    return {
        'groups': [(label, [to_schema_shape(r) for r in picked]) for label, picked in groups],
        'rulings': [to_schema_shape(r) for r in union],
        'problems': len(errors),
    }


def _in_force_place(r):
    """In its area doc (not a history file) and not replaced: what --for and --area show."""
    return r['file'] == r['doc'] and 'replacedBy' not in r


def _lookup_order(r):
    """Area doc, then file (the area doc sorts before its history file), then line."""
    return (_utf16_key(r['doc']), r['file'] != r['doc'], r['line'])


def format_ruling(r):
    """A compact text block for one ruling (lookup output)."""
    kind = KIND_WORDS.get(r.get('kind'), js_to_string(r.get('kind', UNDEFINED)))
    lines = ['%s · %s %s · %s:%s' % (r['id'], kind, r['date'], r['file'], r['line']), '  ' + r['decision']]
    extra = []
    if 'why' in r:
        extra.append('Why: ' + r['why'])
    if 'covers' in r:
        extra.append('Covers: ' + r['covers'])
    if 'tests' in r:
        extra.append('Tests: ' + ', '.join('`%s`' % t for t in r['tests']))
    if 'enforced' in r:
        extra.append('Enforced: ' + r['enforced'])
    if 'source' in r:
        extra.append('Source: `%s`' % r['source'])
    if extra:
        lines.append('  ' + ' · '.join(extra))
    if 'replacedBy' in r:
        lines.append('  Replaced %s → %s' % (r['replacedBy']['date'], r['replacedBy']['id']))
    return '\n'.join(lines)


def format_lookup(result, mode):
    """Text output of a lookup; `mode` is 'for', 'area' or 'id'."""
    out = []
    for label, picked in result['groups']:
        blocks = [format_ruling(r) for r in picked]
        if mode == 'for':
            blocks.append('%d rulings apply to %s' % (len(picked), label))
        elif mode == 'area':
            blocks.append('%d rulings in area %s' % (len(picked), label))
        out.append('\n\n'.join(blocks))
    return '\n\n'.join(out) + '\n' if out else ''


def format_error(e):
    loc = e['file'] if e['line'] is None else '%s:%s' % (e['file'], e['line'])
    return '%s  %s  %s' % (loc, e['id'], e['message'])


def summary(result):
    history = result.get('historyCount', 0)
    docs = '%d docs (%d history files)' % (result['docCount'], history) if history else '%d docs' % result['docCount']
    return '%d rulings in %s, %d errors' % (len(result['rulings']), docs, len(result['errors']))


def enforcement_line(result):
    c = result['enforcement']
    return 'Enforcement: %d tested, %d review-only, %d not enforced (of %d in-force rulings)' % (
        c['tested'], c['review'], c['unenforced'], c['inForce'])


def _write(stream, text):
    """Writes UTF-8 like Node: lone surrogates become U+FFFD, no newline translation."""
    data = SURROGATE_RE.sub('�', text).encode('utf-8')
    buf = getattr(stream, 'buffer', None)
    if buf is not None:
        stream.flush()
        buf.write(data)
        buf.flush()
    else:
        stream.write(data.decode('utf-8'))


USAGE = ('usage: python3 scripts/check_rulings.py [--root <dir>] [--json]'
         ' [--for <path> ... | --area <AREA> | --id <R-AREA-NNN>]\n')


def main(argv):
    root = os.getcwd()
    as_json = False
    for_paths = []
    area = None
    rid = None
    i = 0
    while i < len(argv):
        if argv[i] == '--json':
            as_json = True
        elif argv[i] == '--root' and i + 1 < len(argv):
            i += 1
            root = argv[i]
        elif argv[i] == '--for' and i + 1 < len(argv):
            i += 1
            for_paths.append(argv[i])
        elif argv[i] in ('--area', '--id') and i + 1 < len(argv):
            if (area if argv[i] == '--area' else rid) is not None:
                _write(sys.stderr, '%s given more than once\n%s' % (argv[i], USAGE))
                return 2
            if argv[i] == '--area':
                area = argv[i + 1]
            else:
                rid = argv[i + 1]
            i += 1
        elif argv[i] in ('--root', '--for', '--area', '--id'):
            _write(sys.stderr, '%s needs a value\n%s' % (argv[i], USAGE))
            return 2
        else:
            _write(sys.stderr, 'unknown argument: %s\n%s' % (argv[i], USAGE))
            return 2
        i += 1

    modes = [m for m, on in (('for', for_paths), ('area', area is not None), ('id', rid is not None)) if on]
    if len(modes) > 1:
        _write(sys.stderr, 'use only one of --for, --area, --id per call\n' + USAGE)
        return 2
    if modes:
        try:
            result = lookup_rulings(root, for_paths=for_paths or None, area=area, rid=rid)
        except UsageError as e:
            _write(sys.stderr, '%s\n' % e)
            return e.code
        if result['problems']:
            _write(sys.stderr, 'warning: the rulings docs have %d problems; run python3 scripts/check_rulings.py\n'
                   % result['problems'])
        if as_json:
            _write(sys.stdout, js_stringify(result['rulings'], 2) + '\n')
        else:
            _write(sys.stdout, format_lookup(result, modes[0]))
        return 0

    result = check_rulings(root)
    report = '\n'.join(
        [format_error(e) for e in result['errors']]
        + [format_error(n) for n in result['schemaNotes']]
        + [format_error(n) for n in result['notes']]
        + [enforcement_line(result), summary(result)]
    ) + '\n'
    if as_json:
        _write(sys.stdout, js_stringify(result['rulings'], 2) + '\n')
        _write(sys.stderr, report)
    else:
        _write(sys.stdout, report)
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
