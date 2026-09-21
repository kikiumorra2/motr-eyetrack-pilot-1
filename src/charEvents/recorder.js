// CharEventRecorder — the state machine behind samplingMode "events" (pure, no DOM).
//
// Feed it every pointer sample (x, y, t) and it records
//   * a state-change event whenever the character under the pointer changes
//     (see layout.js hitState: OUT / NONE / global character index),
//   * optionally every sample in a delta-coded raw trace,
//   * layout snapshots, visibility changes and the end marker,
// and serialises everything into the motr-ce/1 fields (format.js / FORMAT.md).
//
// All times are absolute floats on one clock (performance.now() in the browser);
// t0 is passed to start(). The implicit initial pointer state is OUT.

import { FORMAT_ID, encodeLayout, encodeEvents, encodeTrace, encodeStats, assertCharset } from "./format.js";
import { OUT, NONE, buildIndex, spanOffsets, hitState, tablesEqual } from "./layout.js";

export const DEFAULTS = {
  maxEvents: 20000,
  maxTraceSamples: 120000,
  recordRawTrace: true,
  tracePrecisionPx: 1,
};

export class CharEventRecorder {
  constructor(options = {}) {
    const o = { ...DEFAULTS, ...options };
    this.maxEvents = o.maxEvents;
    this.maxTraceSamples = o.maxTraceSamples;
    this.recordRawTrace = !!o.recordRawTrace;
    this.px = o.tracePrecisionPx > 0 ? o.tracePrecisionPx : 1;
    this.started = false;
    this.ended = false;
  }

  /**
   * @param t0        recorder start time (same clock as later `t`s)
   * @param words     the trial's words (whitespace tokens)
   * @param table     layout table measured at t0 (layout.js shape)
   * @param opts.t0Response  t0 on magpie's responseTime clock (ms since screen start)
   * @param opts.tsrc        "event" or "perf" (where sample times come from)
   */
  start(t0, words, table, { t0Response = 0, tsrc = "event" } = {}) {
    if (this.started) throw new Error("recorder already started");
    this.started = true;
    this.t0 = t0;
    this.t0Response = t0Response;
    this.tsrc = tsrc;
    this.words = words;
    this.offsets = spanOffsets(words);
    this.lastRaw = t0;      // last (clamped) raw time seen
    this.lastFeedRaw = null; // clamped time of the last feed() (for mindt)
    this.lastT = 0;         // T of the last recorded event
    this.state = OUT;
    this.lastPoint = null;
    this.hidden = null;
    this.snapshots = [];
    this.events = [];       // {dt, kind, num}
    this.traceT = []; this.traceX = []; this.traceY = [];
    this.truncated = false;
    this.dropped = 0;
    this.traceDropped = 0;
    this.nSamples = 0;
    this.batches = 0;
    this.maxBatch = 0;
    this.coalesced = false;
    this.minDt = Infinity;
    this.hmax = 0;
    this.ptypes = new Set();
    this.relayoutChecks = 0;
    this._addSnapshot(0, table);
  }

  // --- time -----------------------------------------------------------------

  /** Clamp to the monotonic clock and return integer ms since t0. */
  _T(t) {
    if (!(t >= this.lastRaw)) t = this.lastRaw;   // also catches NaN
    this.lastRaw = t;
    return Math.floor(t - this.t0 + 0.5);
  }

  // --- events ---------------------------------------------------------------

  _emit(T, kind, num = null) {
    if (this.ended) return;
    if (kind !== "e") {
      if (this.truncated) { this.dropped++; return; }
      if (this.events.length >= this.maxEvents) {
        this.truncated = true;
        this.events.push({ dt: T - this.lastT, kind: "t", num: null });
        this.lastT = T;
        this.dropped++;
        return;
      }
    }
    this.events.push({ dt: T - this.lastT, kind, num });
    this.lastT = T;
  }

  _setState(T, state) {
    if (state === this.state) return;
    this.state = state;
    if (state === OUT) this._emit(T, "o");
    else if (state === NONE) this._emit(T, "n");
    else this._emit(T, "c", state);
  }

  _addSnapshot(T, table) {
    const id = this.snapshots.length;
    this.snapshots.push({ id, T, table });
    this.table = table;
    this.index = buildIndex(table);
    return id;
  }

  // --- public API -----------------------------------------------------------

  /** One pointer sample. Returns the resulting state (OUT / NONE / g), or null after end(). */
  feed(x, y, t, pointerType) {
    if (!this.started || this.ended) return null;
    const T = this._T(t);
    if (this.lastFeedRaw !== null) {
      const d = this.lastRaw - this.lastFeedRaw;
      if (d > 0 && d < this.minDt) this.minDt = d;
    }
    this.lastFeedRaw = this.lastRaw;
    this.nSamples++;
    if (pointerType) this.ptypes.add(pointerType);
    if (this.recordRawTrace) {
      if (this.traceT.length < this.maxTraceSamples) {
        this.traceT.push(T);
        this.traceX.push(Math.floor(x / this.px + 0.5));
        this.traceY.push(Math.floor(y / this.px + 0.5));
      } else {
        this.traceDropped++;
      }
    }
    const state = hitState(this.index, this.offsets, x, y);
    this.lastPoint = { x, y };
    this._setState(T, state);
    return state;
  }

  /** The pointer left the text block (pointerleave) without a sample inside it. */
  leave(t) {
    if (!this.started || this.ended) return;
    this._setState(this._T(t), OUT);
  }

  /** Re-measured layout. Adds a snapshot (and re-evaluates the state) only if it changed. */
  relayout(t, table) {
    if (!this.started || this.ended) return false;
    this.relayoutChecks++;
    if (tablesEqual(this.table, table)) return false;
    const T = this._T(t);
    const id = this._addSnapshot(T, table);
    this._emit(T, "l", id);
    if (this.lastPoint) this._setState(T, hitState(this.index, this.offsets, this.lastPoint.x, this.lastPoint.y));
    return true;
  }

  /** visibilitychange: hidden=true → 'h', false → 's' (consecutive duplicates ignored). */
  visibility(t, hidden) {
    if (!this.started || this.ended) return;
    hidden = !!hidden;
    if (this.hidden === hidden) return;
    this.hidden = hidden;
    this._emit(this._T(t), hidden ? "h" : "s");
  }

  /** Per pointermove-handler bookkeeping (from dom.js). */
  noteBatch(nSamples, coalescedAvailable, handlerMicros) {
    this.batches++;
    if (nSamples > this.maxBatch) this.maxBatch = nSamples;
    if (coalescedAvailable) this.coalesced = true;
    if (handlerMicros > this.hmax) this.hmax = handlerMicros;
  }

  /** "Done Reading": records the end marker and freezes the recorder. */
  end(t) {
    if (!this.started || this.ended) return;
    this._emit(this._T(t), "e");
    this.ended = true;
  }

  // --- output ---------------------------------------------------------------

  /** Events with cumulative T (for tests / self-checks). */
  eventList() {
    let T = 0;
    return this.events.map((e) => ({ dt: e.dt, T: (T += e.dt), kind: e.kind, num: e.num }));
  }

  traceSamples() {
    const out = new Array(this.traceT.length);
    for (let i = 0; i < out.length; i++) out[i] = { T: this.traceT[i], X: this.traceX[i], Y: this.traceY[i] };
    return out;
  }

  stats() {
    return {
      v: 1,
      t0: Math.floor(this.t0Response + 0.5),
      tsrc: this.tsrc,
      n: this.nSamples,
      ne: this.events.length,
      nl: this.snapshots.length,
      nw: this.words.length,
      trunc: this.truncated ? 1 : 0,
      drop: this.dropped,
      tdrop: this.traceDropped,
      batches: this.batches,
      coal: this.coalesced ? 1 : 0,
      maxb: this.maxBatch,
      px: this.recordRawTrace ? this.px : 0,
      mindt: this.minDt === Infinity ? 0 : Math.floor(this.minDt * 10 + 0.5) / 10,
      hmax: Math.floor(this.hmax + 0.5),
      ptypes: this.ptypes.size ? [...this.ptypes].sort().join(".") : "none",
    };
  }

  /** The motr-ce/1 fields to store on the trial row. */
  fields() {
    const fields = {
      mtFormat: FORMAT_ID,
      mtLayout: encodeLayout(this.snapshots.map((s) => ({ id: s.id, T: s.T, block: s.table.block, words: s.table.words }))),
      mtEvents: encodeEvents(this.events),
      mtTrace: this.recordRawTrace ? encodeTrace(this.traceSamples()) : "",
      mtStats: encodeStats(this.stats()),
    };
    for (const [k, v] of Object.entries(fields)) assertCharset(v, k);
    return fields;
  }
}
