import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeInts, decodeInts, zigzag, unzigzag, ALPHABET } from "../src/charEvents/vlq.js";
import { prng, randInt } from "./helpers.js";

test("alphabet has 64 distinct safe characters", () => {
  assert.equal(ALPHABET.length, 64);
  assert.equal(new Set(ALPHABET).size, 64);
  assert.match(ALPHABET, /^[A-Za-z0-9_-]+$/);
});

test("zigzag mapping", () => {
  const pairs = [[0, 0], [-1, 1], [1, 2], [-2, 3], [2, 4], [-16, 31], [16, 32]];
  for (const [v, z] of pairs) {
    assert.equal(zigzag(v), z);
    assert.equal(unzigzag(z), v);
  }
});

test("fixed vectors", () => {
  assert.equal(encodeInts([0]), "A");
  assert.equal(encodeInts([-1]), "B");
  assert.equal(encodeInts([1]), "C");
  assert.equal(encodeInts([15]), "e"); // zigzag 30
  assert.equal(encodeInts([16]), "gB"); // zigzag 32 → chunk 0 (+cont) then 1
  assert.equal(encodeInts([-16]), "f"); // zigzag 31
  assert.equal(encodeInts([812, 121, 190]), "4yByH8L"); // worked example from FORMAT.md
  assert.equal(encodeInts([]), "");
  assert.deepEqual(decodeInts("4yByH8L"), [812, 121, 190]);
  assert.equal(encodeInts([50]), "kD"); // zigzag 100 = 3*32 + 4 → chunks 4+32, 3
});

test("round trip of extreme values", () => {
  const vals = [0, 1, -1, 31, 32, -32, 2 ** 31, -(2 ** 31), 2 ** 40, -(2 ** 40), 2 ** 52 - 1, -(2 ** 52)];
  assert.deepEqual(decodeInts(encodeInts(vals)), vals);
  // zigzag doubles the magnitude, so |v| must stay below 2^52
  assert.throws(() => encodeInts([Number.MAX_SAFE_INTEGER]), /too large/);
  assert.throws(() => encodeInts([Number.MIN_SAFE_INTEGER]), /too large/);
});

test("seeded fuzz round trip (10k arrays)", () => {
  const rnd = prng(42);
  for (let i = 0; i < 10000; i++) {
    const n = randInt(rnd, 0, 12);
    const arr = [];
    for (let j = 0; j < n; j++) {
      const mag = randInt(rnd, 0, 3);
      const lim = [16, 1000, 1e6, 2 ** 40][mag];
      arr.push(randInt(rnd, -lim, lim));
    }
    const s = encodeInts(arr);
    assert.match(s, /^[A-Za-z0-9_-]*$/);
    assert.deepEqual(decodeInts(s), arr);
  }
});

test("invalid input throws", () => {
  assert.throws(() => decodeInts("A!B"), /invalid VLQ character/);
  assert.throws(() => decodeInts("4"), /dangling continuation/); // '4' = 56 has the continuation bit
  assert.throws(() => decodeInts("gBg"), /dangling continuation/);
  assert.throws(() => encodeInts([1.5]), RangeError);
  assert.throws(() => encodeInts([NaN]), RangeError);
});
