// Shared test utilities (seeded PRNG so property tests are reproducible).

/** mulberry32: small, fast, deterministic PRNG returning floats in [0, 1). */
export function prng(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randInt(rnd, lo, hi) {
  return lo + Math.floor(rnd() * (hi - lo + 1));
}

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const FIXTURE_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

/**
 * Compare `data` with the committed fixture `test/fixtures/<name>`; with
 * MOTR_WRITE_FIXTURES=1 (npm run fixtures) the fixture is (re)written instead.
 */
export function checkFixture(name, data, assert) {
  const file = path.join(FIXTURE_DIR, name);
  const text = JSON.stringify(data, null, 1) + "\n";
  if (process.env.MOTR_WRITE_FIXTURES) {
    fs.mkdirSync(FIXTURE_DIR, { recursive: true });
    fs.writeFileSync(file, text);
    return;
  }
  assert.ok(fs.existsSync(file), `missing fixture ${name}; run \`npm run fixtures\``);
  assert.deepEqual(JSON.parse(fs.readFileSync(file, "utf8")), data, `fixture ${name} is stale; run \`npm run fixtures\` and commit it`);
}

export function readFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURE_DIR, name), "utf8"));
}
