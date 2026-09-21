// Performance / size checks. Thresholds are deliberately loose for CI; run
// `npm run test:perf` (MOTR_PERF=1) locally for the strict ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { CharEventRecorder } from "../src/charEvents/recorder.js";
import { spanOffsets, buildIndex, hitState } from "../src/charEvents/layout.js";
import { decodeRow } from "../src/charEvents/decoder.js";
import { fakeTable } from "./sample-layout.js";
import { prng } from "./helpers.js";

const STRICT = !!process.env.MOTR_PERF;
const WORDS = "The reporter that attacked the senator admitted the error yesterday afternoon".split(" "); // 12 words, ~80 chars
const TABLE = fakeTable(WORDS, { charW: 10, lineChars: 40 });
const OFF = spanOffsets(WORDS);
const N = 1_000_000;

function samples(seed) {
  const rnd = prng(seed);
  const xs = new Float64Array(N), ys = new Float64Array(N), ts = new Float64Array(N);
  const B = TABLE.block;
  let x = 200, y = 190, t = 1000;
  for (let i = 0; i < N; i++) {
    x += (rnd() - 0.5) * 20; y += (rnd() - 0.5) * 6;
    if (x < B[0] - 20 || x > B[2] + 20) x = (B[0] + B[2]) / 2;
    if (y < B[1] - 20 || y > B[3] + 20) y = B[1] + 30;
    t += rnd() * 2;
    xs[i] = x; ys[i] = y; ts[i] = t;
  }
  return { xs, ys, ts };
}

test("hitState throughput", (t) => {
  const idx = buildIndex(TABLE);
  const { xs, ys } = samples(1);
  let acc = 0;
  const start = performance.now();
  for (let i = 0; i < N; i++) acc += hitState(idx, OFF, xs[i], ys[i]);
  const secs = (performance.now() - start) / 1000;
  const rate = N / secs;
  t.diagnostic(`hitState: ${(rate / 1e6).toFixed(2)} M/s (acc ${acc})`);
  assert.ok(rate >= (STRICT ? 1e6 : 3e5), `hitState ${rate.toFixed(0)}/s`);
});

test("recorder.feed throughput with raw trace", (t) => {
  const { xs, ys, ts } = samples(2);
  const r = new CharEventRecorder({ maxEvents: 1e7, maxTraceSamples: N });
  r.start(1000, WORDS, TABLE);
  const start = performance.now();
  for (let i = 0; i < N; i++) r.feed(xs[i], ys[i], ts[i]);
  r.end(ts[N - 1] + 1);
  const secs = (performance.now() - start) / 1000;
  const rate = N / secs;
  const f = r.fields();
  t.diagnostic(`feed: ${(rate / 1e6).toFixed(2)} M/s, ${r.events.length} events, fields ${(f.mtEvents.length + f.mtTrace.length + f.mtLayout.length + f.mtStats.length) / 1024 | 0} KB`);
  t.diagnostic(`bytes/event ${(f.mtEvents.length / r.events.length).toFixed(2)}, bytes/trace sample ${(f.mtTrace.length / N).toFixed(2)}`);
  assert.ok(rate >= (STRICT ? 5e5 : 2e5), `feed ${rate.toFixed(0)}/s`);
  assert.ok(f.mtTrace.length / N < 3.6);
});

test("size: 10k-event jitter trial and 60 s at 1 kHz", (t) => {
  // worst case for events: the pointer straddles a character boundary and flips every ms
  const r = new CharEventRecorder({ maxEvents: 20000 });
  r.start(0, WORDS, TABLE);
  const x0 = TABLE.words[3].frags[0].xs[2];
  for (let i = 0; i < 10000; i++) r.feed(i % 2 ? x0 - 1.5 : x0 + 0.5, 190, i);   // 1 px probe: stay clear of the edge
  r.end(10000);
  const f = r.fields();
  const total = f.mtEvents.length + f.mtTrace.length + f.mtLayout.length + f.mtStats.length;
  t.diagnostic(`10k jitter events: events ${f.mtEvents.length} B, trace ${f.mtTrace.length} B, layout ${f.mtLayout.length} B, total ${(total / 1024).toFixed(1)} KB`);
  assert.equal(decodeRow(f).events.length, 10001);
  assert.ok(total < 200 * 1024);
  // 60 s of 1 kHz mouse reports along a realistic reading path
  const r2 = new CharEventRecorder({ maxEvents: 20000, maxTraceSamples: 120000 });
  r2.start(0, WORDS, TABLE);
  const rnd = prng(3);
  let x = TABLE.words[0].rect[0], y = 190;
  for (let i = 0; i < 60000; i++) {
    x += 0.02 + (rnd() - 0.5) * 1.5; y += (rnd() - 0.5) * 0.6;
    if (x > TABLE.words[WORDS.length - 1].rect[2]) x = TABLE.words[0].rect[0];
    r2.feed(x, y, i);
  }
  r2.end(60000);
  const f2 = r2.fields();
  const total2 = f2.mtEvents.length + f2.mtTrace.length + f2.mtLayout.length + f2.mtStats.length;
  t.diagnostic(`60 s @ 1 kHz: ${r2.events.length} events ${f2.mtEvents.length} B, trace ${(f2.mtTrace.length / 1024).toFixed(1)} KB, total ${(total2 / 1024).toFixed(1)} KB (legacy 20 Hz ≈ ${(1200 * 330 / 1024).toFixed(0)} KB)`);
  assert.ok(total2 < 400 * 1024);
});
