// Python-produced fixture (postprocessing/tests/test_decoder.py): the JS recorder must
// re-encode the same ops byte-for-byte and the JS decoder must reproduce Python's rows.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { decodeRow, expandToLegacyRows, charTable, resample } from "../src/charEvents/decoder.js";
import { replay } from "./decoder.test.js";
import { FIXTURE_DIR } from "./helpers.js";

const file = path.join(FIXTURE_DIR, "py_roundtrip.json");

test("Python fixture: JS re-encodes byte-for-byte and decodes to the same rows", () => {
  assert.ok(fs.existsSync(file), "missing test/fixtures/py_roundtrip.json; run MOTR_WRITE_FIXTURES=1 npm run test:py");
  const fx = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.ok(fx.scenarios.length >= 3);
  for (const sc of fx.scenarios) {
    const r = replay(sc.words, sc.table, sc.ops, sc.options, sc.t0, sc.t0Response);
    assert.deepEqual(r.fields(), sc.fields, sc.text);
    assert.deepEqual(r.eventList(), sc.eventList);
    assert.deepEqual(decodeRow(sc.fields).events, sc.eventList);
    assert.deepEqual(expandToLegacyRows(sc.fields, sc.words, fx.base), sc.legacyRows);
    assert.deepEqual(charTable(sc.fields, sc.words), sc.charTable);
    assert.deepEqual(resample(sc.fields, sc.words, 50, 0, fx.base), sc.resample50);
  }
});
