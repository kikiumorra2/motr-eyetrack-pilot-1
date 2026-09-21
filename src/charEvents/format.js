// Text codecs for the `motr-ce/1` trial payload (see FORMAT.md).
//
// A trial is stored as ONE magpie row with four string fields:
//   mtLayout  layout snapshots (block rect, word rects, per-character x boundaries)
//   mtEvents  state-change events: "<dt><kind>[<num>];" ...
//   mtTrace   VLQ-coded raw pointer samples (optional)
//   mtStats   "key=value key=value ..."
// plus mtFormat = FORMAT_ID. Everything here is pure (no DOM) and mirrored 1:1 by
// postprocessing/motr_char_events.py.

import { encodeInts, decodeInts } from "./vlq.js";

export const FORMAT_NAME = "motr-ce";
export const FORMAT_MAJOR = 1;
export const FORMAT_ID = `${FORMAT_NAME}/${FORMAT_MAJOR}`;

/** Characters allowed in every mt* field: JSON/CSV/Postgres-export safe. */
export const CHARSET_RE = /^[0-9A-Za-z .,:;@#_=/-]*$/;

/** Event kinds. `c` and `l` carry a number; the others do not. */
export const KINDS_WITH_NUM = new Set(["c", "l"]);
export const KINDS_WITHOUT_NUM = new Set(["n", "o", "h", "s", "e", "t"]);

export class FormatError extends Error {
  constructor(message) {
    super(message);
    this.name = "FormatError";
  }
}

export function assertCharset(s, what = "field") {
  if (typeof s !== "string") throw new FormatError(`${what} is not a string`);
  if (!CHARSET_RE.test(s)) {
    const bad = s.match(/[^0-9A-Za-z .,:;@#_=/-]/);
    throw new FormatError(`${what} contains disallowed character ${JSON.stringify(bad[0])}`);
  }
  return s;
}

/** Parse "motr-ce/1" → {name, major}; throws on unknown format / major version. */
export function parseFormatId(s) {
  const m = /^([a-z-]+)\/(\d+)$/.exec(String(s));
  if (!m || m[1] !== FORMAT_NAME) throw new FormatError(`unknown format id ${JSON.stringify(s)}`);
  const major = Number(m[2]);
  if (major !== FORMAT_MAJOR) {
    throw new FormatError(`unsupported ${FORMAT_NAME} major version ${major} (this decoder handles ${FORMAT_MAJOR})`);
  }
  return { name: m[1], major };
}

// ---------------------------------------------------------------------------
// Numbers: at most one decimal, computed as integer tenths so JS and Python agree.

export function fmtNum(x) {
  if (!Number.isFinite(x)) throw new FormatError(`non-finite number ${x}`);
  let t = Math.floor(x * 10 + 0.5);
  if (t === 0) return "0";
  const neg = t < 0;
  if (neg) t = -t;
  const ip = Math.floor(t / 10);
  const fp = t % 10;
  return (neg ? "-" : "") + String(ip) + (fp ? "." + fp : "");
}

const NUM_RE = /^-?\d+(\.\d)?$/;

export function parseNum(s, what = "number") {
  if (!NUM_RE.test(s)) throw new FormatError(`bad ${what} ${JSON.stringify(s)}`);
  return Number(s);
}

const INT_RE = /^\d+$/;

function parseInt_(s, what) {
  if (!INT_RE.test(s)) throw new FormatError(`bad ${what} ${JSON.stringify(s)}`);
  return Number(s);
}

function fmtRect(r) {
  if (!Array.isArray(r) || r.length !== 4) throw new FormatError("rect must be [l,t,r,b]");
  return r.map(fmtNum).join(",");
}

function parseRect(s, what) {
  const parts = s.split(",");
  if (parts.length !== 4) throw new FormatError(`bad ${what} ${JSON.stringify(s)}`);
  return parts.map((p) => parseNum(p, what));
}

// ---------------------------------------------------------------------------
// Layout snapshots.
//   snapshot = 'l' id '@' T ' B' l,t,r,b ( ' W' l,t,r,b ( ' F' k0 '@' top ',' bottom ':' x0 (',' x)+ )* )*
//   snapshots are joined by '#'.
// Snapshot object: { id, T, block:[l,t,r,b], words:[ { rect:[l,t,r,b], frags:[ {k0, top, bottom, xs:[...]} ] } ] }

export function encodeSnapshot(snap) {
  const parts = [`l${snap.id}@${snap.T}`, "B" + fmtRect(snap.block)];
  for (const w of snap.words) {
    parts.push("W" + fmtRect(w.rect));
    for (const f of w.frags || []) {
      if (!Array.isArray(f.xs) || f.xs.length < 2) throw new FormatError("fragment needs >= 2 x boundaries");
      parts.push(`F${f.k0}@${fmtNum(f.top)},${fmtNum(f.bottom)}:${f.xs.map(fmtNum).join(",")}`);
    }
  }
  return parts.join(" ");
}

export function decodeSnapshot(s) {
  const toks = s.split(" ");
  const head = /^l(\d+)@(\d+)$/.exec(toks[0] || "");
  if (!head) throw new FormatError(`bad snapshot header ${JSON.stringify(toks[0])}`);
  const snap = { id: Number(head[1]), T: Number(head[2]), block: null, words: [] };
  let word = null;
  for (let i = 1; i < toks.length; i++) {
    const tok = toks[i];
    const tag = tok[0];
    const body = tok.slice(1);
    if (tag === "B") {
      if (snap.block) throw new FormatError("duplicate block rect");
      snap.block = parseRect(body, "block rect");
    } else if (tag === "W") {
      if (!snap.block) throw new FormatError("word rect before block rect");
      word = { rect: parseRect(body, "word rect"), frags: [] };
      snap.words.push(word);
    } else if (tag === "F") {
      if (!word) throw new FormatError("fragment before any word");
      const m = /^(\d+)@([^:]+):(.+)$/.exec(body);
      if (!m) throw new FormatError(`bad fragment ${JSON.stringify(tok)}`);
      const band = m[2].split(",");
      if (band.length !== 2) throw new FormatError(`bad fragment band ${JSON.stringify(tok)}`);
      const xs = m[3].split(",").map((p) => parseNum(p, "fragment x"));
      if (xs.length < 2) throw new FormatError(`fragment needs >= 2 x boundaries ${JSON.stringify(tok)}`);
      word.frags.push({
        k0: Number(m[1]),
        top: parseNum(band[0], "fragment top"),
        bottom: parseNum(band[1], "fragment bottom"),
        xs,
      });
    } else {
      throw new FormatError(`unexpected layout token ${JSON.stringify(tok)}`);
    }
  }
  if (!snap.block) throw new FormatError("snapshot without block rect");
  return snap;
}

export function encodeLayout(snapshots) {
  return snapshots.map(encodeSnapshot).join("#");
}

export function decodeLayout(s) {
  if (s === "") throw new FormatError("empty layout");
  return s.split("#").map(decodeSnapshot);
}

// ---------------------------------------------------------------------------
// Events: ( dt kind [num] ';' )*

export function encodeEvents(events) {
  let out = "";
  for (const ev of events) {
    if (!Number.isInteger(ev.dt) || ev.dt < 0) throw new FormatError(`bad dt ${ev.dt}`);
    if (KINDS_WITH_NUM.has(ev.kind)) {
      if (!Number.isInteger(ev.num) || ev.num < 0) throw new FormatError(`kind ${ev.kind} needs a non-negative integer`);
      out += `${ev.dt}${ev.kind}${ev.num};`;
    } else if (KINDS_WITHOUT_NUM.has(ev.kind)) {
      out += `${ev.dt}${ev.kind};`;
    } else {
      throw new FormatError(`unknown event kind ${JSON.stringify(ev.kind)}`);
    }
  }
  return out;
}

const EVENT_RE = /^(\d+)([a-z])(\d*)$/;

/** → [{dt, T, kind, num}] where T is the cumulative time since t0. */
export function decodeEvents(s) {
  if (s === "") return [];
  if (!s.endsWith(";")) throw new FormatError("events string must end with ';'");
  const out = [];
  let T = 0;
  const toks = s.slice(0, -1).split(";");
  for (const tok of toks) {
    const m = EVENT_RE.exec(tok);
    if (!m) throw new FormatError(`bad event token ${JSON.stringify(tok)}`);
    const dt = Number(m[1]);
    const kind = m[2];
    T += dt;
    if (KINDS_WITH_NUM.has(kind)) {
      if (m[3] === "") throw new FormatError(`event ${kind} is missing its number: ${JSON.stringify(tok)}`);
      out.push({ dt, T, kind, num: Number(m[3]) });
    } else if (KINDS_WITHOUT_NUM.has(kind)) {
      if (m[3] !== "") throw new FormatError(`event ${kind} must not carry a number: ${JSON.stringify(tok)}`);
      out.push({ dt, T, kind, num: null });
    } else {
      throw new FormatError(`unknown event kind ${JSON.stringify(kind)}`);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Raw trace: samples [{T, X, Y}] (integers; X/Y already in units of `px`) as VLQ deltas.

export function encodeTrace(samples) {
  const ints = new Array(samples.length * 3);
  let pT = 0, pX = 0, pY = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    ints[3 * i] = s.T - pT;
    ints[3 * i + 1] = s.X - pX;
    ints[3 * i + 2] = s.Y - pY;
    pT = s.T; pX = s.X; pY = s.Y;
  }
  return encodeInts(ints);
}

/** → [{T, x, y}] with x/y scaled back by `px`. Empty string → []. */
export function decodeTrace(s, px = 1) {
  if (s === "") return [];
  let ints;
  try {
    ints = decodeInts(s);
  } catch (e) {
    throw new FormatError(`bad trace: ${e.message}`);
  }
  if (ints.length % 3 !== 0) throw new FormatError(`trace length ${ints.length} is not a multiple of 3`);
  const out = new Array(ints.length / 3);
  let T = 0, X = 0, Y = 0;
  for (let i = 0; i < out.length; i++) {
    T += ints[3 * i];
    X += ints[3 * i + 1];
    Y += ints[3 * i + 2];
    if (ints[3 * i] < 0) throw new FormatError(`trace time goes backwards at sample ${i}`);
    out[i] = { T, x: X * px, y: Y * px };
  }
  return out;
}

// ---------------------------------------------------------------------------
// Stats: "key=value key=value"; values are numbers (<= 1 decimal) or [A-Za-z.]+ words.

const STAT_KEY_RE = /^[a-z][a-z0-9]*$/;
const STAT_WORD_RE = /^[A-Za-z][A-Za-z0-9.]*$/;

export function encodeStats(stats) {
  const parts = [];
  for (const [k, v] of Object.entries(stats)) {
    if (!STAT_KEY_RE.test(k)) throw new FormatError(`bad stats key ${JSON.stringify(k)}`);
    let sv;
    if (typeof v === "number") sv = fmtNum(v);
    else if (typeof v === "boolean") sv = v ? "1" : "0";
    else if (typeof v === "string" && STAT_WORD_RE.test(v)) sv = v;
    else throw new FormatError(`bad stats value for ${k}: ${JSON.stringify(v)}`);
    parts.push(`${k}=${sv}`);
  }
  return parts.join(" ");
}

export function decodeStats(s) {
  const out = {};
  if (s === "") return out;
  for (const part of s.split(" ")) {
    const eq = part.indexOf("=");
    if (eq <= 0) throw new FormatError(`bad stats entry ${JSON.stringify(part)}`);
    const k = part.slice(0, eq);
    const v = part.slice(eq + 1);
    if (!STAT_KEY_RE.test(k)) throw new FormatError(`bad stats key ${JSON.stringify(k)}`);
    if (NUM_RE.test(v)) out[k] = Number(v);
    else if (STAT_WORD_RE.test(v)) out[k] = v;
    else throw new FormatError(`bad stats value ${JSON.stringify(part)}`);
  }
  return out;
}
