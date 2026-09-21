// Decoder for motr-ce/1 trial rows (pure, no DOM). Mirrors postprocessing/motr_char_events.py.
//
//   decodeRow(fields)                 → { snapshots, events, trace, stats }
//   expandToLegacyRows(fields, words) → one legacy-shaped sample row per c/n event + end marker
//   charTable(fields, words)          → one record per event with word/char detail
//   resample(fields, words, ms, ph)   → legacy-style fixed-interval rows (validation only)
//
// Legacy row shape (MotrTrial.vue recordSample / finishReading):
//   responseTime, Index, mousePositionX, mousePositionY, [Word, wordPositionTop/Left/Bottom/Right]

import { parseFormatId, decodeLayout, decodeEvents, decodeTrace, decodeStats, FormatError } from "./format.js";
import { OUT, NONE, spanOffsets, wordOfGlobal, charAt, charBox } from "./layout.js";

/** Words exactly as the reading screen splits them (MotrTrial.vue `words`). */
export function wordsOf(text) {
  return String(text).split(/\s+/);
}

export function decodeRow(fields) {
  parseFormatId(fields.mtFormat);
  const stats = decodeStats(fields.mtStats == null ? "" : fields.mtStats);
  const snapshots = decodeLayout(fields.mtLayout == null ? "" : fields.mtLayout);
  const events = decodeEvents(fields.mtEvents == null ? "" : fields.mtEvents);
  const px = stats.px > 0 ? stats.px : 1;
  const trace = decodeTrace(fields.mtTrace == null ? "" : fields.mtTrace, px);
  snapshots.forEach((s, i) => {
    if (s.id !== i) throw new FormatError(`snapshot ids must be 0..n-1 in order (got ${s.id} at ${i})`);
  });
  return { snapshots, events, trace, stats };
}

/** Walks events in order, tracking the active snapshot and the latest trace sample. */
function* walk(decoded, words) {
  const { snapshots, events, trace } = decoded;
  const offsets = spanOffsets(words);
  const nw = words.length;
  let snap = snapshots[0];
  let ti = -1;                      // index of the last trace sample with T <= event T
  let lastXY = null;                // last known pointer position (trace or synthesized)
  for (const ev of events) {
    while (ti + 1 < trace.length && trace[ti + 1].T <= ev.T) ti++;
    if (ti >= 0) lastXY = { x: trace[ti].x, y: trace[ti].y };
    let info = null;
    if (ev.kind === "l") {
      snap = snapshots[ev.num];
      if (!snap) throw new FormatError(`event refers to unknown snapshot ${ev.num}`);
    } else if (ev.kind === "c") {
      const { i, k } = wordOfGlobal(offsets, ev.num);
      if (i >= nw || i >= snap.words.length) throw new FormatError(`character ${ev.num} is outside the ${nw} words`);
      const box = charBox(snap, offsets, ev.num);
      if (!lastXY || ti < 0) {
        // no trace: synthesize the position from the character box (or the word rect)
        const r = box || snap.words[i].rect;
        lastXY = { x: (r[0] + r[2]) / 2, y: (r[1] + r[3]) / 2 };
      }
      info = { i, k, box, char: charAt(words[i], k) };
    }
    yield { ev, snap, info, xy: lastXY };
  }
}

function legacyRow(base, t0, T, Index, xy) {
  return {
    ...base,
    responseTime: t0 + T,
    Index,
    mousePositionX: xy ? xy.x : null,
    mousePositionY: xy ? xy.y : null,
  };
}

/**
 * Expand a charEvents row into legacy sample rows (+ the Index=-1 end marker).
 * `base` is spread into every row (Experiment, Condition, ItemId).
 */
export function expandToLegacyRows(fields, words, base = {}) {
  const decoded = decodeRow(fields);
  const t0 = decoded.stats.t0 == null ? 0 : decoded.stats.t0;
  const rows = [];
  for (const { ev, snap, info, xy } of walk(decoded, words)) {
    if (ev.kind === "c") {
      const rect = snap.words[info.i].rect;
      rows.push({
        ...legacyRow(base, t0, ev.T, info.i, xy),
        Word: words[info.i],
        wordPositionTop: rect[1],
        wordPositionLeft: rect[0],
        wordPositionBottom: rect[3],
        wordPositionRight: rect[2],
        charIndex: info.k,
      });
    } else if (ev.kind === "n" || ev.kind === "e") {
      rows.push(legacyRow(base, t0, ev.T, -1, xy));
    }
  }
  return rows;
}

/** One record per event, with character detail (for char-level analyses). */
export function charTable(fields, words, base = {}) {
  const decoded = decodeRow(fields);
  const t0 = decoded.stats.t0 == null ? 0 : decoded.stats.t0;
  const out = [];
  for (const { ev, snap, info, xy } of walk(decoded, words)) {
    out.push({
      ...base,
      t: t0 + ev.T,
      T: ev.T,
      dt: ev.dt,
      kind: ev.kind,
      num: ev.num,
      wordIdx: info ? info.i : null,
      charIdx: info ? info.k : null,
      char: info ? info.char : null,
      globalIdx: ev.kind === "c" ? ev.num : null,
      layoutId: snap.id,
      x: xy ? xy.x : null,
      y: xy ? xy.y : null,
    });
  }
  return out;
}

/**
 * Legacy-style fixed-interval rows: at every tick T = phase + k*intervalMs up to the end
 * event, the state of the latest c/n/o event at or before the tick is recorded (nothing
 * while OUT, exactly like the 50 ms timer), using the latest trace position; then the
 * Index=-1 end marker. For apples-to-apples comparison with the 20 Hz pipeline.
 */
export function resample(fields, words, intervalMs, phase = 0, base = {}) {
  if (!(intervalMs > 0)) throw new RangeError("intervalMs must be > 0");
  const decoded = decodeRow(fields);
  const t0 = decoded.stats.t0 == null ? 0 : decoded.stats.t0;
  const steps = [...walk(decoded, words)];
  const end = steps.find((s) => s.ev.kind === "e");
  const Tend = end ? end.ev.T : (steps.length ? steps[steps.length - 1].ev.T : 0);
  const rows = [];
  let state = OUT, snap = decoded.snapshots[0], info = null;
  let si = 0, ti = -1;
  const trace = decoded.trace;
  for (let T = phase; T <= Tend; T += intervalMs) {
    while (si < steps.length && steps[si].ev.T <= T) {
      const s = steps[si++];
      if (s.ev.kind === "c") { state = s.ev.num; info = s.info; snap = s.snap; }
      else if (s.ev.kind === "n") { state = NONE; snap = s.snap; }
      else if (s.ev.kind === "o") { state = OUT; snap = s.snap; }
      else if (s.ev.kind === "l") { snap = s.snap; }
    }
    while (ti + 1 < trace.length && trace[ti + 1].T <= T) ti++;
    const xy = ti >= 0 ? { x: trace[ti].x, y: trace[ti].y } : (si > 0 ? steps[si - 1].xy : null);
    if (state === OUT) continue;
    if (state === NONE) { rows.push(legacyRow(base, t0, T, -1, xy)); continue; }
    const rect = snap.words[info.i].rect;
    rows.push({
      ...legacyRow(base, t0, T, info.i, xy),
      Word: words[info.i],
      wordPositionTop: rect[1], wordPositionLeft: rect[0], wordPositionBottom: rect[3], wordPositionRight: rect[2],
    });
  }
  if (end) rows.push(legacyRow(base, t0, Tend, -1, end.xy));
  return rows;
}
