import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FORMAT_ID, FormatError, assertCharset, parseFormatId, fmtNum, parseNum,
  encodeLayout, decodeLayout, encodeSnapshot, decodeSnapshot,
  encodeEvents, decodeEvents, encodeTrace, decodeTrace, encodeStats, decodeStats,
} from "../src/charEvents/format.js";
import { prng, randInt } from "./helpers.js";

const SNAP = {
  id: 0, T: 0, block: [100, 150, 900, 260],
  words: [
    { rect: [120, 180, 155, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [120, 130, 140, 150, 155] }] },
    { rect: [155, 180, 190, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [155, 165, 175, 185, 190] }] },
    { rect: [190, 180, 230, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [190, 200, 210, 220, 230] }] },
  ],
};
const SNAP_STR =
  "l0@0 B100,150,900,260 W120,180,155,201 F1@180,201:120,130,140,150,155 " +
  "W155,180,190,201 F1@180,201:155,165,175,185,190 W190,180,230,201 F1@180,201:190,200,210,220,230";

test("format id", () => {
  assert.equal(FORMAT_ID, "motr-ce/1");
  assert.deepEqual(parseFormatId("motr-ce/1"), { name: "motr-ce", major: 1 });
  assert.throws(() => parseFormatId("motr-ce/2"), /unsupported motr-ce major version 2/);
  assert.throws(() => parseFormatId("other/1"), /unknown format id/);
  assert.throws(() => parseFormatId(""), FormatError);
});

test("number formatting: integer tenths, no -0, ties round up", () => {
  const cases = [
    [0, "0"], [-0, "0"], [0.04, "0"], [0.05, "0.1"], [0.1, "0.1"], [2.5, "2.5"], [-1.25, "-1.2"],
    [-1.26, "-1.3"], [120, "120"], [1e6, "1000000"], [-0.04, "0"], [-0.05, "0"], [-0.06, "-0.1"],
    [123.456, "123.5"], [999.95, "1000"],
  ];
  for (const [x, s] of cases) assert.equal(fmtNum(x), s, `fmtNum(${x})`);
  assert.throws(() => fmtNum(NaN), FormatError);
  assert.throws(() => fmtNum(Infinity), FormatError);
  // round trip is idempotent
  const rnd = prng(7);
  for (let i = 0; i < 5000; i++) {
    const x = (rnd() - 0.5) * 4000;
    const s = fmtNum(x);
    assert.match(s, /^-?\d+(\.\d)?$/);
    assert.equal(fmtNum(parseNum(s)), s);
    assert.ok(Math.abs(parseNum(s) - x) <= 0.05 + 1e-9);
  }
  assert.throws(() => parseNum("1.25"), FormatError);
  assert.throws(() => parseNum("1e3"), FormatError);
});

test("charset assertion", () => {
  assertCharset("l0@0 B1,2,3,4 F1@1,2:3,4;#-_= motr-ce/1");
  for (const bad of ['a"b', "a\\b", "a|b", "a{b", "a\nb", "é"]) {
    assert.throws(() => assertCharset(bad), /disallowed character/);
  }
  assert.throws(() => assertCharset(null), FormatError);
});

test("layout snapshot round trip and grammar", () => {
  assert.equal(encodeSnapshot(SNAP), SNAP_STR);
  assert.deepEqual(decodeSnapshot(SNAP_STR), SNAP);
  const two = [SNAP, { ...SNAP, id: 1, T: 1234 }];
  const s = encodeLayout(two);
  assert.equal(s.split("#").length, 2);
  assert.deepEqual(decodeLayout(s), two);
  // word without fragments, decimals
  const w = { id: 3, T: 5, block: [0.05, -1.26, 10, 10], words: [{ rect: [1, 2, 3, 4], frags: [] }] };
  assert.deepEqual(decodeLayout(encodeLayout([w])), { ...w, block: [0.1, -1.3, 10, 10] } && [{ ...w, block: [0.1, -1.3, 10, 10] }]);
  assertCharset(s);
});

test("layout malformed input throws", () => {
  assert.throws(() => decodeLayout(""), /empty layout/);
  assert.throws(() => decodeLayout("x0@0 B1,2,3,4"), /bad snapshot header/);
  assert.throws(() => decodeLayout("l0@0"), /without block rect/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3"), /bad block rect/);
  assert.throws(() => decodeLayout("l0@0 W1,2,3,4"), /before block rect/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3,4 F1@1,2:3,4"), /before any word/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3,4 W1,2,3,4 F1@1,2:3"), /needs >= 2/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3,4 W1,2,3,4 F1@1:3,4"), /bad fragment band/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3,4 Q1"), /unexpected layout token/);
  assert.throws(() => decodeLayout("l0@0 B1,2,3,4 B1,2,3,4"), /duplicate block/);
  assert.throws(() => encodeSnapshot({ ...SNAP, words: [{ rect: [1, 2, 3, 4], frags: [{ k0: 0, top: 1, bottom: 2, xs: [1] }] }] }), /needs >= 2/);
});

test("events round trip", () => {
  const evs = [
    { dt: 812, kind: "c", num: 1 }, { dt: 48, kind: "c", num: 2 }, { dt: 0, kind: "n" },
    { dt: 510, kind: "o" }, { dt: 3, kind: "l", num: 1 }, { dt: 0, kind: "c", num: 7 },
    { dt: 1000000, kind: "h" }, { dt: 5, kind: "s" }, { dt: 1, kind: "t" }, { dt: 700, kind: "e" },
  ];
  const s = encodeEvents(evs);
  assert.equal(s, "812c1;48c2;0n;510o;3l1;0c7;1000000h;5s;1t;700e;");
  const dec = decodeEvents(s);
  let T = 0;
  assert.deepEqual(dec, evs.map((e) => ({ dt: e.dt, T: (T += e.dt), kind: e.kind, num: e.num ?? null })));
  assert.deepEqual(decodeEvents(""), []);
  assert.equal(encodeEvents([]), "");
  assertCharset(s);
});

test("events malformed input throws", () => {
  assert.throws(() => decodeEvents("812c1"), /must end with ';'/);
  assert.throws(() => decodeEvents("c1;"), /bad event token/);
  assert.throws(() => decodeEvents("12c;"), /missing its number/);
  assert.throws(() => decodeEvents("12n3;"), /must not carry a number/);
  assert.throws(() => decodeEvents("12q;"), /unknown event kind/);
  assert.throws(() => decodeEvents("-1c1;"), /bad event token/);
  assert.throws(() => decodeEvents("1c1;;"), /bad event token/);
  assert.throws(() => encodeEvents([{ dt: -1, kind: "n" }]), /bad dt/);
  assert.throws(() => encodeEvents([{ dt: 1.5, kind: "n" }]), /bad dt/);
  assert.throws(() => encodeEvents([{ dt: 1, kind: "c" }]), /needs a non-negative integer/);
  assert.throws(() => encodeEvents([{ dt: 1, kind: "z" }]), /unknown event kind/);
});

test("trace round trip (worked example) and scaling", () => {
  const samples = [{ T: 812, X: 121, Y: 190 }, { T: 820, X: 123, Y: 191 }, { T: 828, X: 126, Y: 191 }];
  const s = encodeTrace(samples);
  assert.equal(s, "4yByH8LQECQGA");
  assert.deepEqual(decodeTrace(s), samples.map((p) => ({ T: p.T, x: p.X, y: p.Y })));
  assert.deepEqual(decodeTrace(s, 2), samples.map((p) => ({ T: p.T, x: p.X * 2, y: p.Y * 2 })));
  assert.deepEqual(decodeTrace(""), []);
  assert.equal(encodeTrace([]), "");
  assertCharset(s);
});

test("trace fuzz: bytes per sample and integrity", () => {
  const rnd = prng(99);
  let bytes = 0, n = 0;
  for (let i = 0; i < 300; i++) {
    const len = randInt(rnd, 0, 400);
    const samples = [];
    let T = 0, X = randInt(rnd, 0, 1500), Y = randInt(rnd, 0, 900);
    for (let j = 0; j < len; j++) {
      T += randInt(rnd, 0, 12);
      X += randInt(rnd, -6, 6);
      Y += randInt(rnd, -4, 4);
      samples.push({ T, X, Y });
    }
    const s = encodeTrace(samples);
    bytes += s.length; n += len;
    assert.deepEqual(decodeTrace(s), samples.map((p) => ({ T: p.T, x: p.X, y: p.Y })));
  }
  assert.ok(bytes / n < 3.3, `bytes/sample = ${(bytes / n).toFixed(2)}`);
});

test("trace malformed input throws", () => {
  assert.throws(() => decodeTrace("4"), /bad trace/);
  assert.throws(() => decodeTrace("AB"), /multiple of 3/);
  assert.throws(() => decodeTrace(encodeTrace([{ T: 5, X: 0, Y: 0 }, { T: 2, X: 0, Y: 0 }])), /backwards/);
});

test("stats round trip", () => {
  const st = { v: 1, t0: 1043, tsrc: "event", n: 3, ne: 8, trunc: false, coal: true, px: 1, mindt: 7.8, hmax: 41, ptypes: "mouse.pen" };
  const s = encodeStats(st);
  assert.equal(s, "v=1 t0=1043 tsrc=event n=3 ne=8 trunc=0 coal=1 px=1 mindt=7.8 hmax=41 ptypes=mouse.pen");
  assert.deepEqual(decodeStats(s), { ...st, trunc: 0, coal: 1 });
  assert.deepEqual(decodeStats(""), {});
  assertCharset(s);
  assert.throws(() => encodeStats({ "bad key": 1 }), /bad stats key/);
  assert.throws(() => encodeStats({ k: "has space" }), /bad stats value/);
  assert.throws(() => encodeStats({ k: null }), /bad stats value/);
  assert.throws(() => decodeStats("k"), /bad stats entry/);
  assert.throws(() => decodeStats("k=1;2"), /bad stats value/);
});
