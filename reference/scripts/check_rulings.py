#!/usr/bin/env python3
# Reference implementation. Provided as is, without warranty of any kind.
# Review it and use it at your own discretion and risk; the author is not
# responsible for any outcome of using it. MIT license.
#
# Owner rulings checker: reference implementation.
#
# Usage:
#   python3 scripts/check_rulings.py [--root <dir>] [--json]
#
#   --root <dir>  Repo root (default: current directory). docs/, the schema
#                 docs/rulings.schema.json, package.json, and every Paths/Tests
#                 entry are resolved against it. The tests use it to point the
#                 checker at sample repos in tests/fixtures/.
#   --json        Print the extracted rulings as a JSON array matching the
#                 schema on stdout. Problems and the summary go to stderr.
#
# Prints one line per problem, `docs/x.md:LINE  R-ID  message`, then
# `N rulings in M docs, E errors`. Exits 1 if there are errors, else 0.
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
FIELDS = ['Why', 'Covers', 'Paths', 'Replaces', 'Tests']
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
NPM_RE = re.compile(r'^npm\b', _A)
NPM_RUN_RE = re.compile(r'^npm run (' + NWS + r'+)\Z', _A)
DRIVE_RE = re.compile(r'^[A-Za-z]:', _A)
GLOB_CHARS_RE = re.compile(r'[*?]', _A)
GLOB_UNSUPPORTED_RE = re.compile(r'[{}[\]]', _A)
AREA_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_]*\Z', _A)
AREA_DOC_RE = re.compile(r'^docs/[^/]+\.md\Z', _A)
PATTERN_RE = re.compile(r'^\^R-\(([A-Z0-9_|]+)\)-\[0-9\]\{3\}\$\Z', _A)
ID_AREA_RE = re.compile(r'^R-(' + DOT + r'+)-[0-9]{3}\Z', _A)
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


def _js_truthy(v):
    if v is None or v is UNDEFINED or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v == v and v != 0
    if isinstance(v, str):
        return v != ''
    return True


def _js_has_own(obj, key):
    """Object.prototype.hasOwnProperty.call(obj, key) for a JSON value."""
    if isinstance(obj, dict):
        return key in obj
    if isinstance(obj, (list, str)):
        if key == 'length':
            return True
        n = len(obj) if isinstance(obj, list) else len(_utf16_units(obj))
        return _is_array_index(key) and int(key) < n
    return False


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


def read_schema(root, errors):
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
        if not isinstance(doc, str) or not AREA_DOC_RE.search(doc) or doc == 'docs/README.md':
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
    return {'areas': areas}


def parse_doc(doc, text, errors, today):
    """
    Parses one doc into rulings and Replaced markers. Malformed lookalikes are
    reported as errors.
    """
    lines = LINE_SPLIT_RE.split(text)
    rulings = []
    markers = []

    def err(line, rid, message):
        errors.append({'file': doc, 'line': line, 'id': rid, 'message': message})

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
            ruling = {'id': rid, 'kind': kind, 'date': m.group(3), 'doc': doc, 'line': line_no}
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


def check_path_item(root, real_root, item, field, get_files, scripts, at):
    """Checks one Paths/Tests item against the file tree."""
    if field == 'tests' and NPM_RE.search(item):
        m = NPM_RUN_RE.search(item)
        if not m:
            at('Tests item "%s" must be a file or "npm run <script>"' % item)
        elif scripts is None:
            at('Tests uses "%s" but package.json is missing or unreadable' % item)
        elif not _js_has_own(scripts, m.group(1)):
            at('Tests uses "%s" but package.json has no "%s" script' % (item, m.group(1)))
        return
    label = 'Paths' if field == 'paths' else 'Tests'
    if _is_absolute(item) or DRIVE_RE.search(item):
        at('%s item "%s" points outside the repo' % (label, item))
        return
    if '\\' in item:
        at('%s item "%s" must use / separators' % (label, item))
        return

    # Follows symlinks: an item inside the repo may still point outside it.
    def real_outside(full):
        try:
            return _is_outside(real_root, _realpath(full))
        except (OSError, ValueError):
            return False  # broken symlink or unreadable: reported elsewhere, if at all

    resolved = _resolve(root, item)
    if _is_outside(root, resolved):
        at('%s item "%s" points outside the repo' % (label, item))
        return
    if is_glob(item):
        if GLOB_UNSUPPORTED_RE.search(item):
            at('%s glob "%s" uses unsupported glob syntax ({} and [] are not supported)' % (label, item))
            return
        rx = glob_to_regexp(posix_normalize(re.sub(r'^\./', '', item, count=1)))
        matches = [f for f in get_files() if rx.search(_utf16_units(f))]
        if not matches:
            at('%s glob "%s" matches no files' % (label, item))
        for f in matches:
            if real_outside(os.path.join(root, f)):
                at('%s glob "%s" matches "%s", which points outside the repo' % (label, item, f))
    elif not os.path.exists(resolved):
        at('%s item "%s" does not exist' % (label, item))
    elif real_outside(resolved):
        at('%s item "%s" points outside the repo' % (label, item))


def check_rulings(root=None, now=None):
    """
    Checks the rulings in the repo at `root` (default: current directory).
    `now` (an aware datetime) replaces the current time (for tests).
    Returns {'rulings': [...], 'errors': [{file, line, id, message}], 'docCount': int}.
    """
    root = _resolve(os.getcwd() if root is None else os.fspath(root))
    today = latest_today(now)
    errors = []
    rulings = []
    markers = []

    schema = read_schema(root, errors)
    areas = schema['areas'] if schema else {}
    docs_with_area = {d for d in areas.values() if isinstance(d, str)}

    docs_dir = os.path.join(root, 'docs')
    doc_files = []
    try:
        doc_files = sorted(
            ('docs/' + name for name, e in _scandir_sorted(docs_dir)
             if e.is_file(follow_symlinks=False) and name.endswith('.md') and name != 'README.md'),
            key=_utf16_key,
        )
    except OSError:
        errors.append({'file': 'docs/', 'line': None, 'id': '-', 'message': 'docs/ folder not found'})

    # The schema must not go stale: every doc has an area, every area a doc.
    if schema:
        for doc in doc_files:
            if doc not in docs_with_area:
                errors.append({'file': doc, 'line': 1, 'id': '-', 'message': '%s has no area in x-areas' % doc})
        for area, doc in areas.items():
            if isinstance(doc, str) and doc not in doc_files:
                errors.append({'file': SCHEMA_PATH, 'line': 1, 'id': '-', 'message': 'area %s: %s does not exist' % (area, doc)})

    for doc in doc_files:
        parsed_rulings, parsed_markers = parse_doc(doc, _read_text(os.path.join(root, doc)), errors, today)
        rulings.extend(parsed_rulings)
        markers.extend(parsed_markers)

    # package.json scripts, read once.
    try:
        pkg = json_parse(_read_text(os.path.join(root, 'package.json')))
        if pkg is None:
            raise TypeError('null package.json')
        scripts = _js_get(pkg, 'scripts')
        if not _js_truthy(scripts):
            scripts = {}
    except Exception:
        scripts = None
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

    by_id = {}
    for r in rulings:
        def at(message, r=r):
            errors.append({'file': r['doc'], 'line': r['line'], 'id': r['id'], 'message': message})

        # Rule 1: unique ID.
        first = by_id.get(r['id'])
        if first:
            at('duplicate ID; first defined at %s:%s' % (first['doc'], first['line']))
        else:
            by_id[r['id']] = r

        # Rule 4: real date, not in the future.
        dp = date_problem(r['date'], today)
        if dp:
            at(dp)

        # Rule 5: known area, right doc.
        area = ID_AREA_RE.search(r['id']).group(1)
        if schema and area not in areas:
            at("area %s is not in the schema's x-areas" % area)
        elif schema and not (isinstance(areas[area], str) and areas[area] == r['doc']):
            at('area %s belongs in %s, not %s' % (area, js_to_string(areas[area]), r['doc']))

        # Rule 3: Paths and Tests exist, inside the repo.
        for field in ('paths', 'tests'):
            for item in r.get(field) or []:
                check_path_item(root, real_root, item, field, get_files, scripts, at)

    # Rule 2: Replaces and Replaced markers link both ways.
    for r in rulings:
        for old in r.get('replaces') or []:
            target = by_id.get(old)

            def at(message, r=r):
                errors.append({'file': r['doc'], 'line': r['line'], 'id': r['id'], 'message': message})

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
            errors.append({'file': ruling['doc'], 'line': line, 'id': ruling['id'],
                           'message': 'Replaced → %s, which does not exist' % by})
        elif ruling['id'] not in (target.get('replaces') or []):
            errors.append({'file': ruling['doc'], 'line': line, 'id': ruling['id'],
                           'message': 'Replaced → %s, but %s does not list %s in Replaces' % (by, by, ruling['id'])})

    errors.sort(key=lambda e: (_utf16_key(e['file']), e['line'] if e['line'] is not None else 0))
    return {'rulings': [to_schema_shape(r) for r in rulings], 'errors': errors, 'docCount': len(doc_files)}


def to_schema_shape(r):
    """Orders keys as in the schema and drops absent optional fields."""
    out = {'id': r['id']}
    if not isinstance(r['kind'], _JsFunction):  # JSON.stringify drops functions
        out['kind'] = r['kind']
    out.update({'date': r['date'], 'doc': r['doc'], 'line': r['line'], 'decision': r['decision']})
    for k in ('why', 'covers', 'paths', 'replaces', 'replacedBy', 'tests'):
        if k in r:
            out[k] = r[k]
    return out


def format_error(e):
    loc = e['file'] if e['line'] is None else '%s:%s' % (e['file'], e['line'])
    return '%s  %s  %s' % (loc, e['id'], e['message'])


def summary(result):
    return '%d rulings in %d docs, %d errors' % (len(result['rulings']), result['docCount'], len(result['errors']))


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


def main(argv):
    root = os.getcwd()
    as_json = False
    i = 0
    while i < len(argv):
        if argv[i] == '--json':
            as_json = True
        elif argv[i] == '--root' and i + 1 < len(argv):
            i += 1
            root = argv[i]
        else:
            _write(sys.stderr, 'unknown argument: %s\nusage: python3 scripts/check_rulings.py [--root <dir>] [--json]\n' % argv[i])
            return 2
        i += 1
    result = check_rulings(root)
    report = '\n'.join([format_error(e) for e in result['errors']] + [summary(result)]) + '\n'
    if as_json:
        _write(sys.stdout, js_stringify(result['rulings'], 2) + '\n')
        _write(sys.stderr, report)
    else:
        _write(sys.stdout, report)
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
