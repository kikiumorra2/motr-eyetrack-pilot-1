import { test } from "node:test";
import assert from "node:assert/strict";
import { CharEventRecorder } from "../src/charEvents/recorder.js";
import { OUT, NONE, spanOffsets, globalIndex } from "../src/charEvents/layout.js";
import { decodeEvents, decodeLayout, decodeTrace, decodeStats, assertCharset, FORMAT_ID } from "../src/charEvents/format.js";
import { WORDS, TABLE, shiftedTable } from "./sample-layout.js";
import { prng, randInt } from "./helpers.js";

const OFF = spanOffsets(WORDS);
const g = (i, k) => globalIndex(OFF, i, k);
const kinds = (r) => r.eventList().map((e) => e.kind + (e.num === null ? "" : e.num)).join(" ");

function rec(opts = {}, t0 = 1000) {
  const r = new CharEventRecorder(opts);
  r.start(t0, WORDS, TABLE, { t0Response: 1043.4, tsrc: "event" });
  return r;
}

test("initial state is OUT; only changes emit events", () => {
  const r = rec();
  assert.equal(r.feed(50, 50, 1001), OUT);        // outside: nothing recorded
  assert.equal(r.events.length, 0);
  assert.equal(r.feed(125, 190, 1010.2), g(0, 1)); // "T"
  assert.equal(r.feed(126, 191, 1018), g(0, 1));   // same char: no event
  assert.equal(r.feed(127, 192, 1026), g(0, 1));
  assert.equal(r.feed(135, 190, 1034), g(0, 2));   // "h"
  assert.equal(r.feed(125, 219, 1042), NONE);      // gap between lines
  assert.equal(r.feed(50, 50, 1050), OUT);
  r.end(1100);
  assert.equal(kinds(r), `c${g(0, 1)} c${g(0, 2)} n o e`);
  assert.deepEqual(r.eventList().map((e) => e.T), [10, 34, 42, 50, 100]);
  assert.equal(r.nSamples, 7);
});

test("sum of dts equals floor(t_last - t0 + 0.5) with no drift (1e5 random floats)", () => {
  const rnd = prng(1);
  const r = rec({ maxEvents: 1e6, recordRawTrace: false });
  let t = 1000;
  for (let i = 0; i < 100000; i++) {
    t += rnd() * 3;                                    // 0..3 ms steps, float
    const x = 110 + rnd() * 180, y = 175 + rnd() * 30; // mostly on line 1 chars / gaps
    r.feed(x, y, t);
  }
  r.end(t);
  const evs = r.eventList();
  assert.ok(evs.length > 1000, `expected many events, got ${evs.length}`);
  assert.equal(evs[evs.length - 1].T, Math.floor(t - 1000 + 0.5));
  assert.equal(evs.reduce((s, e) => s + e.dt, 0), Math.floor(t - 1000 + 0.5));
  for (const e of evs) assert.ok(e.dt >= 0);
});

test("dt = 0 for changes within the same millisecond", () => {
  const r = rec();
  r.feed(125, 190, 1000.1);
  r.feed(135, 190, 1000.3);
  r.feed(145, 190, 1000.4);
  assert.deepEqual(r.eventList().map((e) => [e.dt, e.T]), [[0, 0], [0, 0], [0, 0]]);
});

test("non-monotone and pre-t0 timestamps clamp", () => {
  const r = rec();
  r.feed(125, 190, 900);        // before t0 → treated as t0
  assert.equal(r.eventList()[0].T, 0);
  r.feed(135, 190, 1050);
  r.feed(145, 190, 1040);       // backwards → clamped to 1050
  r.feed(155, 190, NaN);        // NaN → clamped
  assert.deepEqual(r.eventList().map((e) => e.T), [0, 50, 50, 50]);
  r.end(1060);
  assert.equal(r.eventList().at(-1).T, 60);
});

test("huge gaps are just large dts", () => {
  const r = rec();
  r.feed(125, 190, 1000);
  r.feed(135, 190, 1000 + 3.6e6 + 0.4);
  assert.deepEqual(r.eventList().map((e) => e.dt), [0, 3600000]);
});

test("maxEvents → 't', later changes dropped, 'e' still recorded", () => {
  const r = rec({ maxEvents: 5 });
  const xs = [125, 135, 145];
  for (let i = 0; i < 20; i++) r.feed(xs[i % 3], 190, 1000 + i);
  r.end(1100);
  const k = kinds(r).split(" ");
  assert.equal(k.length, 7);                       // 5 events + t + e
  assert.equal(k[5], "t");
  assert.equal(k[6], "e");
  assert.equal(r.stats().trunc, 1);
  assert.equal(r.stats().drop, 15);                // 20 changes - 5 recorded
  assert.equal(r.stats().ne, 7);
  assert.equal(r.eventList().at(-1).T, 100);
});

test("maxTraceSamples → tdrop; events unaffected", () => {
  const r = rec({ maxTraceSamples: 3 });
  for (let i = 0; i < 6; i++) r.feed(125 + i * 10, 190, 1000 + i);
  assert.equal(r.traceSamples().length, 3);
  assert.equal(r.stats().tdrop, 3);
  assert.equal(r.events.length, 6);
});

test("relayout: identical → nothing; changed → snapshot + 'l' + re-evaluated state", () => {
  const r = rec();
  r.feed(125, 190, 1000);                              // on "T"
  assert.equal(r.relayout(1010, JSON.parse(JSON.stringify(TABLE))), false);
  assert.equal(r.snapshots.length, 1);
  assert.equal(r.relayoutChecks, 1);
  // scroll by 40px: the last point (125,190) now falls in the gap above line 1 → NONE
  assert.equal(r.relayout(1020, shiftedTable(TABLE, 0, 40)), true);
  assert.equal(r.snapshots.length, 2);
  assert.equal(kinds(r), `c${g(0, 1)} l1 n`);
  assert.deepEqual(r.eventList().map((e) => e.T), [0, 20, 20]);
  // a sample now: (125, 230) is "T" again on the shifted layout
  assert.equal(r.feed(125, 230, 1030), g(0, 1));
  // another relayout that does not change the hit → only the 'l' token
  assert.equal(r.relayout(1040, shiftedTable(TABLE, 0, 41)), true);
  assert.equal(kinds(r), `c${g(0, 1)} l1 n c${g(0, 1)} l2`);
  const f = r.fields();
  const snaps = decodeLayout(f.mtLayout);
  assert.deepEqual(snaps.map((s) => [s.id, s.T]), [[0, 0], [1, 20], [2, 40]]);
  assert.equal(snaps[1].block[1], 190);
});

test("relayout before any sample records only the 'l' token", () => {
  const r = rec();
  assert.equal(r.relayout(1005, shiftedTable(TABLE, 1, 0)), true);
  assert.equal(kinds(r), "l1");
});

test("visibility tokens (duplicates ignored)", () => {
  const r = rec();
  r.visibility(1001, true);
  r.visibility(1002, true);
  r.visibility(1003, false);
  r.visibility(1004, false);
  r.feed(125, 190, 1005);
  r.visibility(1006, true);
  assert.equal(kinds(r), `h s c${g(0, 1)} h`);
});

test("leave() records OUT once", () => {
  const r = rec();
  r.feed(125, 190, 1000);
  r.leave(1010);
  r.leave(1011);
  assert.equal(kinds(r), `c${g(0, 1)} o`);
  r.feed(125, 190, 1020);
  assert.equal(kinds(r), `c${g(0, 1)} o c${g(0, 1)}`);
});

test("nothing is recorded after end()", () => {
  const r = rec();
  r.feed(125, 190, 1000);
  r.end(1010);
  assert.equal(r.feed(135, 190, 1020), null);
  r.leave(1021);
  r.visibility(1022, true);
  assert.equal(r.relayout(1023, shiftedTable(TABLE, 5, 5)), false);
  r.end(1030);
  assert.equal(kinds(r), `c${g(0, 1)} e`);
  assert.equal(r.nSamples, 1);
});

test("trace disabled → empty mtTrace, px=0", () => {
  const r = rec({ recordRawTrace: false });
  r.feed(125, 190, 1000);
  r.end(1010);
  const f = r.fields();
  assert.equal(f.mtTrace, "");
  assert.equal(decodeStats(f.mtStats).px, 0);
});

test("trace precision rounds coordinates", () => {
  const r = rec({ tracePrecisionPx: 2 });
  r.feed(125.4, 190.9, 1000.2);
  r.feed(126.6, 189.1, 1001.7);
  assert.deepEqual(r.traceSamples(), [{ T: 0, X: 63, Y: 95 }, { T: 2, X: 63, Y: 95 }]);
  assert.deepEqual(decodeTrace(r.fields().mtTrace, 2), [{ T: 0, x: 126, y: 190 }, { T: 2, x: 126, y: 190 }]);
});

test("fields() round-trip and stats", () => {
  const r = rec();
  r.noteBatch(4, true, 37.6);
  r.feed(125, 190, 1000.4, "mouse");
  r.feed(135, 190, 1008.2, "mouse");
  r.noteBatch(2, true, 12);
  r.feed(50, 50, 1016.1, "pen");
  r.end(1020);
  const f = r.fields();
  assert.equal(f.mtFormat, FORMAT_ID);
  for (const v of Object.values(f)) assertCharset(v);
  assert.deepEqual(decodeEvents(f.mtEvents), r.eventList());
  assert.deepEqual(decodeTrace(f.mtTrace), r.traceSamples().map((s) => ({ T: s.T, x: s.X, y: s.Y })));
  assert.deepEqual(decodeLayout(f.mtLayout)[0], { id: 0, T: 0, block: TABLE.block, words: TABLE.words });
  const st = decodeStats(f.mtStats);
  assert.deepEqual(st, {
    v: 1, t0: 1043, tsrc: "event", n: 3, ne: 4, nl: 1, nw: WORDS.length, trunc: 0, drop: 0, tdrop: 0,
    batches: 2, coal: 1, maxb: 4, px: 1, mindt: 7.8, hmax: 38, ptypes: "mouse.pen",
  });
});

test("start() twice throws; feed before start is ignored", () => {
  const r = new CharEventRecorder();
  assert.equal(r.feed(1, 1, 1), null);
  r.start(0, WORDS, TABLE);
  assert.throws(() => r.start(0, WORDS, TABLE), /already started/);
  assert.equal(r.stats().ptypes, "none");
  assert.equal(r.stats().mindt, 0);
});

test("random walk: recorded states equal a straightforward re-simulation", () => {
  const rnd = prng(5);
  const r = rec({ maxEvents: 1e6 });
  let t = 1000, x = 130, y = 190, prev = OUT;
  const expected = [];
  for (let i = 0; i < 20000; i++) {
    t += rnd() * 10;
    x += (rnd() - 0.5) * 30; y += (rnd() - 0.5) * 12;
    if (rnd() < 0.01) { x = 90 + rnd() * 420; y = 140 + rnd() * 170; }
    const s = r.feed(x, y, t);
    if (s !== prev) { expected.push(s); prev = s; }
  }
  const got = r.eventList().map((e) => (e.kind === "c" ? e.num : e.kind === "n" ? NONE : OUT));
  assert.deepEqual(got, expected);
  assert.ok(expected.length > 500);
});
