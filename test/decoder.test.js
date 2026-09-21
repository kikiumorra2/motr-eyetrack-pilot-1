import { test } from "node:test";
import assert from "node:assert/strict";
import { CharEventRecorder } from "../src/charEvents/recorder.js";
import { decodeRow, expandToLegacyRows, charTable, resample, wordsOf } from "../src/charEvents/decoder.js";
import { OUT, NONE, spanOffsets, globalIndex, wordOfGlobal, buildIndex, hitState } from "../src/charEvents/layout.js";
import { FormatError } from "../src/charEvents/format.js";
import { WORDS, TABLE, shiftedTable, fakeTable } from "./sample-layout.js";
import { prng, randInt, checkFixture } from "./helpers.js";

const OFF = spanOffsets(WORDS);
const g = (i, k) => globalIndex(OFF, i, k);
const BASE = { Experiment: "motr_template", Condition: "a", ItemId: "1" };

/** Replays an op list on a fresh recorder (the same op list is stored in fixtures). */
export function replay(words, table, ops, opts = {}, t0 = 1000, t0Response = 1043.4) {
  const r = new CharEventRecorder(opts);
  r.start(t0, words, table, { t0Response, tsrc: "event" });
  for (const op of ops) {
    switch (op[0]) {
      case "feed": r.feed(op[1], op[2], op[3], op[4]); break;
      case "leave": r.leave(op[1]); break;
      case "relayout": r.relayout(op[1], op[2]); break;
      case "visibility": r.visibility(op[1], op[2]); break;
      case "noteBatch": r.noteBatch(op[1], op[2], op[3]); break;
      case "end": r.end(op[1]); break;
      default: throw new Error(op[0]);
    }
  }
  return r;
}

test("wordsOf splits like the reading screen", () => {
  assert.deepEqual(wordsOf("The cat  sat."), ["The", "cat", "sat."]);
  assert.deepEqual(wordsOf("a\tb\nc"), ["a", "b", "c"]);
});

test("hand-scripted trial expands to the expected legacy rows", () => {
  const ops = [
    ["feed", 50, 50, 1005, "mouse"],      // outside → nothing
    ["feed", 125, 190, 1010.4, "mouse"],  // "T" of The
    ["feed", 135, 190, 1020, "mouse"],    // "h"
    ["feed", 155, 190, 1030, "mouse"],    // trailing space of The → still Index 0
    ["feed", 165, 190, 1040, "mouse"],    // "c" of cat
    ["feed", 165, 219, 1050, "mouse"],    // gap → n
    ["leave", 1060],                       // o
    ["feed", 125, 230, 1070, "mouse"],    // "w" of wrapped (line 2)
    ["end", 1080.2],
  ];
  const r = replay(WORDS, TABLE, ops);
  const f = r.fields();
  const rows = expandToLegacyRows(f, WORDS, BASE);
  const t0 = 1043;
  assert.deepEqual(rows.map((x) => [x.responseTime - t0, x.Index, x.Word ?? null, x.mousePositionX, x.mousePositionY, x.charIndex ?? null]), [
    [10, 0, "The", 125, 190, 1],
    [20, 0, "The", 135, 190, 2],
    [30, 0, "The", 155, 190, 4],
    [40, 1, "cat", 165, 190, 1],
    [50, -1, null, 165, 219, null],
    [70, 3, "wrapped", 125, 230, 1],
    [80, -1, null, 125, 230, null],
  ]);
  const c = rows[0];
  assert.deepEqual(Object.keys(c), ["Experiment", "Condition", "ItemId", "responseTime", "Index", "mousePositionX", "mousePositionY", "Word", "wordPositionTop", "wordPositionLeft", "wordPositionBottom", "wordPositionRight", "charIndex"]);
  assert.deepEqual([c.wordPositionLeft, c.wordPositionTop, c.wordPositionRight, c.wordPositionBottom], TABLE.words[0].rect);
  assert.deepEqual(Object.keys(rows[4]), ["Experiment", "Condition", "ItemId", "responseTime", "Index", "mousePositionX", "mousePositionY"]);
  // char table
  const ct = charTable(f, WORDS);
  assert.deepEqual(ct.map((x) => [x.T, x.kind, x.wordIdx, x.charIdx, x.char, x.layoutId]), [
    [10, "c", 0, 1, "T", 0], [20, "c", 0, 2, "h", 0], [30, "c", 0, 4, " ", 0], [40, "c", 1, 1, "c", 0],
    [50, "n", null, null, null, 0], [60, "o", null, null, null, 0], [70, "c", 3, 1, "w", 0], [80, "e", null, null, null, 0],
  ]);
});

test("no trace: positions are synthesized from character boxes", () => {
  const ops = [["feed", 125, 190, 1010], ["feed", 165, 219, 1020], ["end", 1030]];
  const rows = expandToLegacyRows(replay(WORDS, TABLE, ops, { recordRawTrace: false }).fields(), WORDS);
  assert.deepEqual(rows.map((x) => [x.Index, x.mousePositionX, x.mousePositionY]), [
    [0, 125, 190.5],      // centre of the "T" box [120,180,130,201]
    [-1, 125, 190.5],     // n: last synthesized point
    [-1, 125, 190.5],     // e
  ]);
});

test("relayout switches the boxes used for later rows", () => {
  const ops = [["feed", 125, 190, 1010], ["relayout", 1020, shiftedTable(TABLE, 0, 40)], ["feed", 125, 230, 1030], ["end", 1040]];
  const f = replay(WORDS, TABLE, ops).fields();
  const rows = expandToLegacyRows(f, WORDS);
  assert.deepEqual(rows.map((x) => [x.responseTime - 1043, x.Index, x.wordPositionTop ?? null]), [
    [10, 0, 180], [20, -1, null], [30, 0, 220], [40, -1, null],
  ]);
  assert.deepEqual(charTable(f, WORDS).map((x) => [x.kind, x.layoutId]), [["c", 0], ["l", 1], ["n", 1], ["c", 1], ["e", 1]]);
});

test("decoder rejects broken payloads", () => {
  const f = replay(WORDS, TABLE, [["feed", 125, 190, 1010], ["end", 1020]]).fields();
  assert.throws(() => decodeRow({ ...f, mtFormat: "motr-ce/2" }), /unsupported/);
  assert.throws(() => decodeRow({ ...f, mtFormat: "" }), FormatError);
  assert.throws(() => expandToLegacyRows({ ...f, mtEvents: "5l7;" }, WORDS), /unknown snapshot/);
  assert.throws(() => expandToLegacyRows({ ...f, mtEvents: "5c999;" }, WORDS), RangeError);
  assert.throws(() => expandToLegacyRows({ ...f, mtEvents: "5c40;" }, [...WORDS, "extra"]), /outside the/); // word 7 has no layout
  assert.throws(() => decodeRow({ ...f, mtLayout: f.mtLayout + "#" + f.mtLayout }), /ids must be/);
  assert.throws(() => resample(f, WORDS, 0), RangeError);
});

/** Random pointer path over a table; returns ops at ~`rateHz` with float jitter. */
function randomOps(rnd, table, { seconds = 5, rateHz = 1000, t0 = 1000, relayouts = 0 } = {}) {
  const B = table.block;
  const ops = [];
  let t = t0, x = (B[0] + B[2]) / 2, y = B[1] + 30;
  const n = Math.floor(seconds * rateHz);
  const relayoutAt = new Set(Array.from({ length: relayouts }, () => randInt(rnd, 1, n - 1)));
  for (let i = 0; i < n; i++) {
    t += (1000 / rateHz) * (0.5 + rnd());
    x += (rnd() - 0.5) * 24; y += (rnd() - 0.5) * 10;
    if (rnd() < 0.005) { x = B[0] - 30 + rnd() * (B[2] - B[0] + 60); y = B[1] - 30 + rnd() * (B[3] - B[1] + 60); }
    if (rnd() < 0.002) ops.push(["leave", t]);
    if (relayoutAt.has(i)) ops.push(["relayout", t, shiftedTable(table, 0, randInt(rnd, -60, 60))]);
    ops.push(["feed", Math.round(x * 100) / 100, Math.round(y * 100) / 100, Math.round(t * 1000) / 1000, "mouse"]);
  }
  ops.push(["end", t + 5]);
  return ops;
}

test("property: decode(encode(x)) reproduces the recorder's events, snapshots and trace (200 runs)", () => {
  const rnd = prng(2025);
  const texts = ["The cat sat.", "The reporter that attacked the senator admitted the error.", "Über naïve façades — “quotes” & co.", "a", "one two three four five six seven eight nine ten eleven twelve"];
  for (let run = 0; run < 200; run++) {
    const words = wordsOf(texts[run % texts.length]);
    const table = fakeTable(words, { charW: 6 + randInt(rnd, 0, 8), lineChars: 12 + randInt(rnd, 0, 40) });
    const ops = randomOps(rnd, table, { seconds: 0.5 + rnd(), rateHz: [60, 125, 1000][run % 3], relayouts: run % 7 === 0 ? 2 : 0 });
    const opts = { recordRawTrace: run % 5 !== 4, tracePrecisionPx: run % 11 === 10 ? 2 : 1, maxEvents: run % 13 === 12 ? 20 : 20000 };
    const r = replay(words, table, ops, opts);
    const d = decodeRow(r.fields());
    assert.deepEqual(d.events, r.eventList());
    assert.deepEqual(d.snapshots.map((s) => [s.id, s.T]), r.snapshots.map((s) => [s.id, s.T]));
    assert.deepEqual(d.trace, opts.recordRawTrace ? r.traceSamples().map((s) => ({ T: s.T, x: s.X * opts.tracePrecisionPx, y: s.Y * opts.tracePrecisionPx })) : []);
    assert.equal(d.stats.ne, r.events.length);
    const rows = expandToLegacyRows(r.fields(), words, BASE);
    assert.equal(rows.length, d.events.filter((e) => e.kind === "c" || e.kind === "n" || e.kind === "e").length);
    for (const row of rows) {
      assert.ok(Number.isInteger(row.responseTime));
      assert.ok(Number.isInteger(row.Index) && row.Index >= -1 && row.Index < words.length);
      assert.ok(Number.isFinite(row.mousePositionX) && Number.isFinite(row.mousePositionY));
      if (row.Index >= 0) assert.equal(row.Word, words[row.Index]);
    }
  }
});

/**
 * Reference 20 Hz sampler, as MotrTrial.vue does it: currentIndex is updated by every
 * pointer sample (null while outside the text), a timer at phase + k*ms records the
 * current index and the last pointer position, "Done Reading" records an Index=-1 marker.
 */
function referenceSampler(words, table, ops, ms, phase, t0) {
  const offsets = spanOffsets(words);
  let index = buildIndex(table);
  const samples = [];   // {T, state, x, y}
  let lastT = t0;
  const T = (t) => { if (!(t >= lastT)) t = lastT; lastT = t; return Math.floor(t - t0 + 0.5); };
  let last = null;
  let Tend = null;
  for (const op of ops) {
    if (op[0] === "feed") {
      const x = Math.floor(op[1] + 0.5), y = Math.floor(op[2] + 0.5);
      const st = hitState(index, offsets, op[1], op[2]);
      last = { x, y, rx: op[1], ry: op[2] };
      samples.push({ T: T(op[3]), state: st, x, y });
    } else if (op[0] === "leave") {
      samples.push({ T: T(op[1]), state: OUT, x: last?.x, y: last?.y });
    } else if (op[0] === "relayout") {
      index = buildIndex(op[2]);
      if (last) samples.push({ T: T(op[1]), state: hitState(index, offsets, last.rx, last.ry), x: last.x, y: last.y });
    } else if (op[0] === "end") {
      Tend = T(op[1]);
    }
  }
  const rows = [];
  let si = 0, cur = null;
  for (let tick = phase; tick <= Tend; tick += ms) {
    while (si < samples.length && samples[si].T <= tick) cur = samples[si++];
    if (!cur || cur.state === OUT) continue;
    const Index = cur.state === NONE ? -1 : wordOfGlobal(offsets, cur.state).i;
    rows.push([tick, Index, cur.x, cur.y]);
  }
  const lastSample = samples[samples.length - 1];   // finishReading records the last mouse position
  rows.push([Tend, -1, lastSample?.x, lastSample?.y]);
  return rows;
}

test("legacy equivalence: resample(...) equals the reference 20 Hz sampler for every phase", () => {
  const rnd = prng(777);
  for (let run = 0; run < 6; run++) {
    const words = wordsOf(["The cat sat.", "The reporter that attacked the senator admitted the error."][run % 2]);
    const table = fakeTable(words, { charW: 9, lineChars: 30 });
    const ops = randomOps(rnd, table, { seconds: 3, rateHz: 1000, relayouts: run >= 4 ? 1 : 0 });
    const r = replay(words, table, ops);
    const f = r.fields();
    for (let phase = 0; phase < 50; phase += run < 2 ? 1 : 7) {
      const got = resample(f, words, 50, phase).map((x) => [x.responseTime - 1043, x.Index, x.mousePositionX, x.mousePositionY]);
      const want = referenceSampler(words, table, ops, 50, phase, 1000);
      assert.deepEqual(got, want, `run ${run} phase ${phase}`);
    }
  }
});

test("relayout mid-trial keeps the reference equivalence (state re-evaluated at the new layout)", () => {
  const ops = [["feed", 125, 190, 1010], ["relayout", 1020, shiftedTable(TABLE, 0, 40)], ["feed", 125, 230, 1030], ["end", 1100]];
  const f = replay(WORDS, TABLE, ops).fields();
  for (const phase of [0, 5, 10, 15, 20, 25, 30, 35]) {
    const got = resample(f, WORDS, 10, phase).map((x) => [x.responseTime - 1043, x.Index]);
    const want = referenceSampler(WORDS, TABLE, ops, 10, phase, 1000).map((x) => [x[0], x[1]]);
    assert.deepEqual(got, want, `phase ${phase}`);
  }
});

test("cross-language fixtures (JS encode → Python decode)", () => {
  const rnd = prng(31337);
  const scenarios = [];
  const cases = [
    { text: "The cat sat.", seconds: 0.4, rateHz: 125, opts: {} },
    { text: "The reporter that attacked the senator admitted the error.", seconds: 1.2, rateHz: 1000, opts: {}, relayouts: 1 },
    { text: "Über naïve façades — “quotes” & co.", seconds: 0.5, rateHz: 60, opts: { recordRawTrace: false } },
    { text: "one two three four five six seven eight nine ten eleven twelve", seconds: 0.8, rateHz: 250, opts: { maxEvents: 25, tracePrecisionPx: 2 } },
  ];
  for (const c of cases) {
    const words = wordsOf(c.text);
    const table = fakeTable(words, { charW: 8, lineChars: 24 });
    const ops = randomOps(rnd, table, { seconds: c.seconds, rateHz: c.rateHz, relayouts: c.relayouts || 0 });
    const tv = ops[2][0] === "feed" ? ops[2][3] : ops[2][1];
    ops.splice(3, 0, ["visibility", tv, true], ["visibility", tv + 1, false]);
    ops.splice(1, 0, ["noteBatch", 4, true, 37.6]);
    const r = replay(words, table, ops, c.opts);
    const fields = r.fields();
    scenarios.push({
      text: c.text, words, table, t0: 1000, t0Response: 1043.4, options: { ...c.opts }, ops,
      fields,
      eventList: r.eventList(),
      legacyRows: expandToLegacyRows(fields, words, BASE),
      charTable: charTable(fields, words),
      resample50: resample(fields, words, 50, 0, BASE),
      resample50phase17: resample(fields, words, 50, 17, BASE),
    });
  }
  checkFixture("js_roundtrip.json", { base: BASE, scenarios }, assert);
});
