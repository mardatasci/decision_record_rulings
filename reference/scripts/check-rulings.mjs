#!/usr/bin/env node
// Reference implementation. Provided as is, without warranty of any kind.
// Review it and use it at your own discretion and risk; the author is not
// responsible for any outcome of using it. MIT license.
//
// Owner rulings checker: reference implementation.
//
// Usage:
//   node scripts/check-rulings.mjs [--root <dir>] [--json]
//
//   --root <dir>  Repo root (default: current directory). docs/, the schema
//                 docs/rulings.schema.json, package.json, and every Paths/Tests
//                 entry are resolved against it. The tests use it to point the
//                 checker at sample repos in tests/fixtures/.
//   --json        Print the extracted rulings as a JSON array matching the
//                 schema on stdout. Problems and the summary go to stderr.
//
// Prints one line per problem, `docs/x.md:LINE  R-ID  message`, then
// `N rulings in M docs, E errors`. Exits 1 if there are errors, else 0.
//
// Zero dependencies: Node built-ins only (Node 20+).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCHEMA_PATH = 'docs/rulings.schema.json';
const FIELDS = ['Why', 'Covers', 'Paths', 'Replaces', 'Tests'];
const KINDS = { Ruled: 'ruled', Parked: 'parked', Asked: 'asked' };
const ID_RE = /^R-[A-Z][A-Z0-9_]*-[0-9]{3}$/;
const DATE_RE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const SKIP_DIRS = new Set(['.git', 'node_modules']);

// A line that starts a new block: list item, heading, or a bold span that is a
// ruling lead-in (or lookalike) or a Replaced marker.
const LIST_RE = /^\s*(?:[-*+]|\d+[.)])\s+/;
const HEADING_RE = /^\s{0,3}#{1,6}(\s|$)/;
const FENCE_RE = /^\s{0,3}(`{3,}|~{3,})/;
// Bold span at the start of a line, optionally after a list marker.
const LEAD_RE = /^(\s*(?:(?:[-*+]|\d+[.)])\s+)?)\*\*([^*]+?)\*\*(.*)$/;
// Field separator inside a ruling: optional "·", then **Field:**
const FIELD_SPLIT_RE = new RegExp(`(?:·\\s*)?\\*\\*(${FIELDS.join('|')}):\\*\\*`, 'g');

/**
 * The latest calendar date anywhere on Earth (UTC+14) as YYYY-MM-DD, so a
 * ruling dated "today" by an owner in any time zone is never in the future.
 */
function latestToday(now = new Date()) {
  return new Date(now.getTime() + 14 * 3600 * 1000).toISOString().slice(0, 10);
}

/**
 * True if a bold span at the start of a line is a ruling lead-in or lookalike.
 * `after` is the text right after the closing **, for `**Ruled by owner …**:`.
 */
function isRulingCandidate(span, after) {
  if (span.endsWith(':') && (/^R-/.test(span) || /\bby owner\b/i.test(span))) return true;
  return after.startsWith(':') && !/^R-/.test(span) && /\bby owner\b/i.test(span);
}

/** Returns an error message for a bad date, or null if it is fine. */
function dateProblem(date, today) {
  if (!DATE_RE.test(date)) return `date "${date}" is not YYYY-MM-DD`;
  const [y, m, d] = date.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) {
    return `date ${date} is not a real calendar date`;
  }
  if (date > today) return `date ${date} is in the future`;
  return null;
}

function escapeRe(s) {
  return s.replace(/[.+^${}()|[\]\\]/g, '\\$&');
}

/** Converts a glob with *, ** and ? into a RegExp over posix relative paths. */
function globToRegExp(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*') {
      if (glob[i + 1] === '*') {
        // "**/" matches zero or more whole segments; a trailing "**" matches anything.
        if (glob[i + 2] === '/') {
          re += '(?:[^/]+/)*';
          i += 2;
        } else {
          re += '.*';
          i += 1;
        }
      } else {
        re += '[^/]*';
      }
    } else if (c === '?') {
      re += '[^/]';
    } else {
      re += escapeRe(c);
    }
  }
  return new RegExp(`^${re}$`);
}

function isGlob(p) {
  return /[*?]/.test(p);
}

/** Lists every file under root as posix relative paths (skips .git, node_modules). */
function listFiles(root) {
  const out = [];
  const walk = (dir, rel) => {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(ent.name)) continue;
      const r = rel ? `${rel}/${ent.name}` : ent.name;
      if (ent.isDirectory()) walk(path.join(dir, ent.name), r);
      else out.push(r);
    }
  };
  walk(root, '');
  return out;
}

/** Splits a Paths/Tests value into backtick-quoted items. */
function backtickItems(value) {
  const items = [];
  const rest = value.replace(/`([^`]*)`/g, (_, item) => {
    items.push(item.trim());
    return ' ';
  });
  const leftover = rest.replace(/\band\b/g, ' ').replace(/[,;.\s]/g, '');
  return { items, leftover };
}

/** Reads the schema and checks its three area lists agree. */
function readSchema(root, errors) {
  const err = (message) => errors.push({ file: SCHEMA_PATH, line: 1, id: '-', message });
  const full = path.join(root, SCHEMA_PATH);
  let schema;
  try {
    schema = JSON.parse(fs.readFileSync(full, 'utf8'));
  } catch (e) {
    err(e.code === 'ENOENT' ? 'schema file not found' : `schema is not valid JSON: ${e.message}`);
    return null;
  }
  const areas = schema['x-areas'];
  if (!areas || typeof areas !== 'object' || Array.isArray(areas)) {
    err('schema has no "x-areas" object');
    return null;
  }
  const areaNames = Object.keys(areas);
  const areaDocs = Object.values(areas);

  for (const [area, doc] of Object.entries(areas)) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(area)) err(`x-areas: area "${area}" must be upper-case letters, digits or _`);
    if (typeof doc !== 'string' || !/^docs\/[^/]+\.md$/.test(doc) || doc === 'docs/README.md') {
      err(`x-areas: area ${area} must map to a docs/<name>.md file, got ${JSON.stringify(doc)}`);
    }
  }
  const seenDocs = new Set();
  for (const doc of areaDocs) {
    if (seenDocs.has(doc)) err(`x-areas: ${doc} is listed for more than one area`);
    seenDocs.add(doc);
  }

  const pattern = schema.$defs?.rulingId?.pattern;
  const pm = typeof pattern === 'string' && pattern.match(/^\^R-\(([A-Z0-9_|]+)\)-\[0-9\]\{3\}\$$/);
  if (!pm) {
    err(`$defs.rulingId.pattern must look like ^R-(A|B)-[0-9]{3}$, got ${JSON.stringify(pattern)}`);
  } else {
    const patAreas = pm[1].split('|');
    const missing = areaNames.filter((a) => !patAreas.includes(a));
    const extra = patAreas.filter((a) => !areaNames.includes(a));
    if (missing.length || extra.length) {
      err(`area lists disagree: $defs.rulingId.pattern ${describeDiff(missing, extra)} compared with x-areas`);
    }
  }

  const docEnum = schema.properties?.doc?.enum;
  if (!Array.isArray(docEnum)) {
    err('schema has no properties.doc.enum list');
  } else {
    const missing = areaDocs.filter((d) => !docEnum.includes(d));
    const extra = docEnum.filter((d) => !areaDocs.includes(d));
    if (missing.length || extra.length) {
      err(`area lists disagree: properties.doc.enum ${describeDiff(missing, extra)} compared with x-areas`);
    }
  }
  return { areas };
}

function describeDiff(missing, extra) {
  const parts = [];
  if (missing.length) parts.push(`is missing ${missing.join(', ')}`);
  if (extra.length) parts.push(`has extra ${extra.join(', ')}`);
  return parts.join(' and ');
}

/**
 * Parses one doc into rulings and Replaced markers. Malformed lookalikes are
 * reported as errors.
 */
function parseDoc(doc, text, errors, today) {
  const lines = text.split(/\r?\n/);
  const rulings = [];
  const markers = [];
  const err = (line, id, message) => errors.push({ file: doc, line, id, message });

  // Mark lines inside fenced code blocks.
  const inCode = new Array(lines.length).fill(false);
  let fence = null;
  let fenceLine = -1;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(FENCE_RE);
    if (fence) {
      inCode[i] = true;
      if (m && m[1][0] === fence[0] && m[1].length >= fence.length && lines[i].trim() === m[1]) fence = null;
    } else if (m) {
      inCode[i] = true;
      fence = m[1];
      fenceLine = i;
    }
  }
  if (fence) err(fenceLine + 1, '-', 'unclosed code fence');

  const isBoundary = (i) => {
    if (i >= lines.length || inCode[i]) return true;
    const l = lines[i];
    if (l.trim() === '' || LIST_RE.test(l) || HEADING_RE.test(l)) return true;
    const lead = l.match(LEAD_RE);
    if (!lead) return false;
    const span = lead[2].trim();
    return /^Replaced\b/.test(span) || isRulingCandidate(span, lead[3]);
  };

  // Collects the block starting at line i: returns [joinedText, lastLineIndex].
  const block = (i, first) => {
    const parts = [first];
    let j = i + 1;
    while (!isBoundary(j)) {
      parts.push(lines[j].trim());
      j++;
    }
    return [parts.join(' ').trim(), j - 1];
  };

  // Lookalikes in a piece of text: bold "R-..." that isn't a valid ID, or a
  // bold "... by owner ..." lead-in that doesn't start a line.
  const scanLookalikes = (text, lineNo) => {
    const noInline = text.replace(/`[^`]*`/g, '');
    for (const bm of noInline.matchAll(/\*\*([^*]+?)\*\*(:?)/g)) {
      const s = bm[1].trim();
      if (/^R-/.test(s)) {
        const idm = s.match(/^R-[^\s·:]*/)[0];
        if (!ID_RE.test(idm)) err(lineNo, idm, `malformed ruling ID "${idm}"; expected R-AREA-NNN`);
        else if (/\bby owner\b/i.test(s)) {
          err(lineNo, idm, 'malformed ruling lead-in; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:** at the start of a line');
        }
      } else if (/\bby owner\b/i.test(s) && (s.endsWith(':') || bm[2] === ':')) {
        err(lineNo, '-', `ruling lead-in "**${s}**${bm[2]}" has no ID or does not start the line`);
      }
    }
  };
  // Scans the continuation lines i+1..end of a block.
  const scanContinuation = (i, end) => {
    for (let j = i + 1; j <= end; j++) scanLookalikes(lines[j], j + 1);
  };

  let prevRulingEnd = -2; // index of the last line of the previous ruling (or its marker)
  let prevRuling = null;
  let prevMalformedEnd = -2; // index of the last line of the previous malformed ruling

  for (let i = 0; i < lines.length; i++) {
    if (inCode[i]) continue;
    const lineNo = i + 1;
    const raw = lines[i];
    const lead = raw.match(LEAD_RE);
    const span = lead ? lead[2].trim() : null;

    if (lead && /^Replaced\b/.test(span)) {
      const [note, end] = block(i, lead[3].trim());
      scanLookalikes(lead[3], lineNo);
      scanContinuation(i, end);
      const m = span.match(/^Replaced ([0-9]{4}-[0-9]{2}-[0-9]{2}) → (\S+):$/);
      let kept = false;
      if (!m) {
        err(lineNo, '-', `malformed Replaced marker "**${span}**"; expected **Replaced YYYY-MM-DD → R-AREA-NNN:**`);
      } else if (prevMalformedEnd === i - 1) {
        err(lineNo, '-', 'Replaced marker follows a malformed ruling; fix the ruling above it');
      } else if (prevRulingEnd !== i - 1 || !prevRuling) {
        err(lineNo, '-', 'Replaced marker must be on the line right after the ruling it replaces');
      } else {
        const [, date, by] = m;
        const dp = dateProblem(date, today);
        if (dp) err(lineNo, prevRuling.id, `Replaced marker ${dp}`);
        if (!ID_RE.test(by)) err(lineNo, prevRuling.id, `Replaced marker points to malformed ID "${by}"`);
        if (prevRuling.replacedBy) {
          err(lineNo, prevRuling.id, 'ruling has more than one Replaced marker');
        } else {
          prevRuling.replacedBy = { id: by, date };
          markers.push({ ruling: prevRuling, line: lineNo, by });
        }
        if (!note) err(lineNo, prevRuling.id, 'Replaced marker has no note');
        // A second marker right after this one is reported as a duplicate.
        prevRulingEnd = end;
        kept = true;
      }
      if (!kept) prevRuling = null;
      prevMalformedEnd = -2;
      i = end;
      continue;
    }

    if (lead && isRulingCandidate(span, lead[3])) {
      const colonOutside = !span.endsWith(':');
      const head = colonOutside ? span : span.slice(0, -1).trim();
      const rest = colonOutside ? lead[3].slice(1) : lead[3];
      const m = colonOutside ? null : head.match(/^(\S+) · (\S+) by owner (\S+)$/);
      const problems = [];
      let id = '-';
      if (!m) {
        const idm = head.match(/^(R-\S*)/);
        if (idm) id = idm[1];
        if (!idm) problems.push('ruling lead-in has no ID; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**');
        else if (!ID_RE.test(idm[1].replace(/:$/, ''))) {
          id = idm[1].replace(/:$/, '');
          problems.push(`malformed ruling ID "${id}"; expected R-AREA-NNN`);
        } else problems.push(`malformed ruling lead-in "**${span}**"; expected **R-AREA-NNN · Ruled by owner YYYY-MM-DD:**`);
      } else {
        id = m[1];
        if (!ID_RE.test(m[1])) problems.push(`malformed ruling ID "${m[1]}"; expected R-AREA-NNN`);
        if (!KINDS[m[2]]) problems.push(`unknown kind "${m[2]} by owner"; expected Ruled, Parked or Asked`);
        if (!DATE_RE.test(m[3])) problems.push(`date "${m[3]}" is not YYYY-MM-DD`);
      }
      const [body, end] = block(i, rest.trim());
      for (const p of problems) err(lineNo, id, p);
      // Every body line except the lead-in itself is scanned for lookalikes.
      scanLookalikes(rest, lineNo);
      scanContinuation(i, end);
      if (problems.length) {
        prevRuling = null;
        prevRulingEnd = -2;
        prevMalformedEnd = end;
        i = end;
        continue;
      }
      const ruling = { id, kind: KINDS[m[2]], date: m[3], doc, line: lineNo };
      parseFields(ruling, body, err);
      rulings.push(ruling);
      prevRuling = ruling;
      prevRulingEnd = end;
      prevMalformedEnd = -2;
      i = end;
      continue;
    }

    scanLookalikes(raw, lineNo);
    prevRuling = null;
    prevMalformedEnd = -2;
  }
  return { rulings, markers };
}

/** Splits a ruling body into decision and fields. */
function parseFields(ruling, body, err) {
  const parts = body.split(FIELD_SPLIT_RE);
  const decision = parts[0].replace(/\s*·\s*$/, '').trim();
  const at = (msg) => err(ruling.line, ruling.id, msg);
  if (!decision) at('ruling has no decision text');
  // A bold span that looks like a field label (**Word:** or **Word**:) must be
  // exactly one of the known fields, e.g. not **Paths**:, **paths:** or **Path:**.
  for (const lm of body.replace(/`[^`]*`/g, '').matchAll(/\*\*([^*]+?)\*\*(:?)/g)) {
    const [whole, inner, colon] = lm;
    const looksLikeLabel = /^[A-Za-z]+:$/.test(inner) || (/^[A-Za-z]+$/.test(inner) && colon === ':');
    if (looksLikeLabel && (colon || !FIELDS.includes(inner.slice(0, -1)))) at(`unknown field "${whole}"`);
  }
  ruling.decision = decision;
  const seen = new Set();
  for (let k = 1; k < parts.length; k += 2) {
    const name = parts[k];
    const value = parts[k + 1].replace(/\s*·\s*$/, '').trim();
    if (seen.has(name)) {
      at(`${name} appears more than once`);
      continue;
    }
    seen.add(name);
    if (!value) {
      at(`${name} is empty`);
      continue;
    }
    if (name === 'Why' || name === 'Covers') {
      ruling[name.toLowerCase()] = value;
    } else if (name === 'Replaces') {
      const ids = value.replace(/`/g, ' ').replace(/\band\b/g, ' ').split(/[\s,;]+/).map((s) => s.replace(/\.$/, '')).filter(Boolean);
      for (const x of ids) if (!ID_RE.test(x)) at(`Replaces has malformed ID "${x}"`);
      const good = ids.filter((x) => ID_RE.test(x));
      if (new Set(good).size !== good.length) at('Replaces lists an ID more than once');
      if (good.length) ruling.replaces = [...new Set(good)];
    } else {
      const { items, leftover } = backtickItems(value);
      if (leftover) at(`${name} items must be backtick-quoted, e.g. \`src/x.js\``);
      const nonEmpty = items.filter(Boolean);
      if (nonEmpty.length !== items.length) at(`${name} has an empty item`);
      if (name === 'Paths' && new Set(nonEmpty).size !== nonEmpty.length) at('Paths lists an item more than once');
      if (nonEmpty.length) ruling[name.toLowerCase()] = name === 'Paths' ? [...new Set(nonEmpty)] : nonEmpty;
    }
  }
}

/** Checks one Paths/Tests item against the file tree. */
function checkPathItem(root, realRoot, item, field, getFiles, scripts, at) {
  if (field === 'tests' && /^npm\b/.test(item)) {
    const m = item.match(/^npm run (\S+)$/);
    if (!m) {
      at(`Tests item "${item}" must be a file or "npm run <script>"`);
    } else if (scripts === null) {
      at(`Tests uses "${item}" but package.json is missing or unreadable`);
    } else if (!Object.prototype.hasOwnProperty.call(scripts, m[1])) {
      at(`Tests uses "${item}" but package.json has no "${m[1]}" script`);
    }
    return;
  }
  const label = field === 'paths' ? 'Paths' : 'Tests';
  if (path.isAbsolute(item) || /^[A-Za-z]:/.test(item)) {
    at(`${label} item "${item}" points outside the repo`);
    return;
  }
  if (item.includes('\\')) {
    at(`${label} item "${item}" must use / separators`);
    return;
  }
  const isOutside = (from, to) => {
    const rel = path.relative(from, to);
    return rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel);
  };
  // Follows symlinks: an item inside the repo may still point outside it.
  const realOutside = (full) => {
    try {
      return isOutside(realRoot, fs.realpathSync(full));
    } catch {
      return false; // broken symlink or unreadable: reported elsewhere, if at all
    }
  };
  const resolved = path.resolve(root, item);
  if (isOutside(root, resolved)) {
    at(`${label} item "${item}" points outside the repo`);
    return;
  }
  if (isGlob(item)) {
    if (/[{}[\]]/.test(item)) {
      at(`${label} glob "${item}" uses unsupported glob syntax ({} and [] are not supported)`);
      return;
    }
    const re = globToRegExp(path.posix.normalize(item.replace(/^\.\//, '')));
    const matches = getFiles().filter((f) => re.test(f));
    if (!matches.length) at(`${label} glob "${item}" matches no files`);
    for (const f of matches) {
      if (realOutside(path.join(root, f))) at(`${label} glob "${item}" matches "${f}", which points outside the repo`);
    }
  } else if (!fs.existsSync(resolved)) {
    at(`${label} item "${item}" does not exist`);
  } else if (realOutside(resolved)) {
    at(`${label} item "${item}" points outside the repo`);
  }
}

/**
 * Checks the rulings in the repo at `root`.
 * @param {string} [root] Repo root (default: current directory).
 * @param {{ now?: Date }} [options] `now` replaces the current time (for tests).
 * @returns {{ rulings: object[], errors: {file:string,line:number|null,id:string,message:string}[], docCount: number }}
 */
export function checkRulings(root = process.cwd(), { now = new Date() } = {}) {
  root = path.resolve(root);
  const today = latestToday(now);
  const errors = [];
  const rulings = [];
  const markers = [];

  const schema = readSchema(root, errors);
  const areas = schema ? schema.areas : {};
  const areaByDoc = new Map(Object.entries(areas).map(([a, d]) => [d, a]));

  const docsDir = path.join(root, 'docs');
  let docFiles = [];
  try {
    docFiles = fs
      .readdirSync(docsDir, { withFileTypes: true })
      .filter((e) => e.isFile() && e.name.endsWith('.md') && e.name !== 'README.md')
      .map((e) => `docs/${e.name}`)
      .sort();
  } catch {
    errors.push({ file: 'docs/', line: null, id: '-', message: 'docs/ folder not found' });
  }

  // The schema must not go stale: every doc has an area, every area a doc.
  if (schema) {
    for (const doc of docFiles) {
      if (!areaByDoc.has(doc)) errors.push({ file: doc, line: 1, id: '-', message: `${doc} has no area in x-areas` });
    }
    for (const [area, doc] of Object.entries(areas)) {
      if (typeof doc === 'string' && !docFiles.includes(doc)) {
        errors.push({ file: SCHEMA_PATH, line: 1, id: '-', message: `area ${area}: ${doc} does not exist` });
      }
    }
  }

  for (const doc of docFiles) {
    const parsed = parseDoc(doc, fs.readFileSync(path.join(root, doc), 'utf8'), errors, today);
    rulings.push(...parsed.rulings);
    markers.push(...parsed.markers);
  }

  // package.json scripts, read once.
  let scripts = null;
  try {
    scripts = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).scripts || {};
  } catch {
    scripts = null;
  }
  let files = null;
  const getFiles = () => (files ??= listFiles(root));
  let realRoot = root;
  try {
    realRoot = fs.realpathSync(root);
  } catch {
    // root does not exist; the docs/ and schema errors already say so.
  }

  const byId = new Map();
  for (const r of rulings) {
    const at = (message) => errors.push({ file: r.doc, line: r.line, id: r.id, message });

    // Rule 1: unique ID.
    const first = byId.get(r.id);
    if (first) at(`duplicate ID; first defined at ${first.doc}:${first.line}`);
    else byId.set(r.id, r);

    // Rule 4: real date, not in the future.
    const dp = dateProblem(r.date, today);
    if (dp) at(dp);

    // Rule 5: known area, right doc.
    const area = r.id.match(/^R-(.+)-[0-9]{3}$/)[1];
    if (schema && !Object.prototype.hasOwnProperty.call(areas, area)) {
      at(`area ${area} is not in the schema's x-areas`);
    } else if (schema && areas[area] !== r.doc) {
      at(`area ${area} belongs in ${areas[area]}, not ${r.doc}`);
    }

    // Rule 3: Paths and Tests exist, inside the repo.
    for (const field of ['paths', 'tests']) {
      for (const item of r[field] || []) checkPathItem(root, realRoot, item, field, getFiles, scripts, at);
    }
  }

  // Rule 2: Replaces and Replaced markers link both ways.
  for (const r of rulings) {
    for (const old of r.replaces || []) {
      const target = byId.get(old);
      const at = (message) => errors.push({ file: r.doc, line: r.line, id: r.id, message });
      if (old === r.id) at('ruling replaces itself');
      else if (!target) at(`Replaces ${old}, which does not exist`);
      else if (!target.replacedBy || target.replacedBy.id !== r.id) {
        at(`Replaces ${old}, but ${old} has no "Replaced → ${r.id}" marker`);
      }
    }
  }
  for (const { ruling, line, by } of markers) {
    const target = byId.get(by);
    const at = (message) => errors.push({ file: ruling.doc, line, id: ruling.id, message });
    if (!ID_RE.test(by)) continue; // already reported
    if (!target) at(`Replaced → ${by}, which does not exist`);
    else if (!(target.replaces || []).includes(ruling.id)) {
      at(`Replaced → ${by}, but ${by} does not list ${ruling.id} in Replaces`);
    }
  }

  errors.sort((a, b) => (a.file < b.file ? -1 : a.file > b.file ? 1 : (a.line ?? 0) - (b.line ?? 0)));
  return { rulings: rulings.map(toSchemaShape), errors, docCount: docFiles.length };
}

/** Orders keys as in the schema and drops absent optional fields. */
function toSchemaShape(r) {
  const out = { id: r.id, kind: r.kind, date: r.date, doc: r.doc, line: r.line, decision: r.decision };
  for (const k of ['why', 'covers', 'paths', 'replaces', 'replacedBy', 'tests']) {
    if (r[k] !== undefined) out[k] = r[k];
  }
  return out;
}

export function formatError(e) {
  return `${e.line == null ? e.file : `${e.file}:${e.line}`}  ${e.id}  ${e.message}`;
}

export function summary({ rulings, errors, docCount }) {
  return `${rulings.length} rulings in ${docCount} docs, ${errors.length} errors`;
}

function main(argv) {
  let root = process.cwd();
  let json = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--json') json = true;
    else if (argv[i] === '--root' && argv[i + 1] !== undefined) root = argv[++i];
    else {
      process.stderr.write(`unknown argument: ${argv[i]}\nusage: node scripts/check-rulings.mjs [--root <dir>] [--json]\n`);
      return 2;
    }
  }
  const result = checkRulings(root);
  const report = [...result.errors.map(formatError), summary(result)].join('\n') + '\n';
  if (json) {
    process.stdout.write(JSON.stringify(result.rulings, null, 2) + '\n');
    process.stderr.write(report);
  } else {
    process.stdout.write(report);
  }
  return result.errors.length > 0 ? 1 : 0;
}

function isEntryPoint() {
  try {
    return Boolean(process.argv[1]) && fs.realpathSync(process.argv[1]) === fs.realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (isEntryPoint()) {
  process.exitCode = main(process.argv.slice(2));
}
