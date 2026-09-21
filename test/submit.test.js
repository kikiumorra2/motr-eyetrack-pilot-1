// src/submit.js: every submission must carry the experiment-level data (SubjectId, ...) on its
// first row. magpie's getAllData() merges it into the first row of ALL data only, so without
// this every per-trial submission after the first (and the survey row) would be anonymous and
// 1_fetch_and_flatten.py would drop it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { withExpData, submitRows } from "../src/submit.js";

const EXP = { experiment_start_time: 1700000000000, SubjectId: "abc123", ListId: 2, Experiment: "motr_template" };

test("withExpData fills missing experiment-level fields on the first row only and never overwrites", () => {
  const rows = [
    { Experiment: "motr_template", ItemId: "3", Index: 0, SubjectId: null, ListId: "", experiment_start_time: null },
    { Experiment: "motr_template", ItemId: "3", Index: 1, SubjectId: null },
    { Experiment: "motr_template", ItemId: "3", TrialType: "trial", ListId: 2 },
  ];
  const out = withExpData(rows, EXP);
  assert.deepEqual(out[0], { ...rows[0], SubjectId: "abc123", ListId: 2, experiment_start_time: 1700000000000 });
  assert.deepEqual(out.slice(1), rows.slice(1));            // later rows untouched
  assert.equal(rows[0].SubjectId, null);                     // input not mutated
  const kept = withExpData([{ SubjectId: "keep", ListId: 7, Experiment: "x" }], EXP)[0];
  assert.deepEqual(kept, { SubjectId: "keep", ListId: 7, Experiment: "x", experiment_start_time: 1700000000000 });
  assert.equal(withExpData([{ SubjectId: "NA" }], EXP)[0].SubjectId, "abc123");   // "NA" (older exports, simulator) counts as missing too
  assert.deepEqual(withExpData([], EXP), []);
  assert.deepEqual(withExpData([{ a: 1 }], undefined), [{ a: 1 }]);
});

test("submitRows (debug mode): every submission - later trials and the survey row - gets SubjectId", async () => {
  globalThis.window = {};
  const logs = [];
  const origLog = console.log;
  console.log = (...a) => logs.push(String(a[0]));
  try {
    const magpie = { debug: true, expData: EXP };
    // what MotrTrial.submitTrial() / App.finish() hand over: magpie tagged only the first row of the first trial
    const trial1 = [{ ItemId: "1", Index: 0, SubjectId: "abc123", experiment_start_time: 1700000000000, experiment_end_time: 1700000005000, experiment_duration: 5000 }, { ItemId: "1", TrialType: "trial" }];
    const trial2 = [{ ItemId: "2", Index: 0, SubjectId: null, experiment_start_time: null, experiment_end_time: null }, { ItemId: "2", TrialType: "trial", ListId: 2 }];
    const survey = [{ TrialType: "survey", device: "Computer Mouse", SubjectId: null }];
    await submitRows(magpie, trial1, "trial 1");
    await submitRows(magpie, trial2, "trial 2");
    await submitRows(magpie, survey, "final");
    const stored = globalThis.window.__motrRows;
    assert.equal(stored.length, 5);
    assert.equal(stored[0].SubjectId, "abc123");
    assert.equal(stored[0].experiment_end_time, 1700000005000);  // magpie's own values are kept
    assert.equal(stored[2].SubjectId, "abc123");                  // second trial, first row
    assert.equal(stored[2].experiment_start_time, 1700000000000);
    assert.ok(stored[2].experiment_end_time >= 1700000000000 && stored[2].experiment_duration > 0);
    assert.equal(stored[3].SubjectId, undefined);                 // only the first row of a submission
    assert.equal(stored[4].SubjectId, "abc123");                  // survey row
    assert.equal(stored[4].device, "Computer Mouse");
    assert.equal(logs.filter((l) => l.includes("debug mode")).length, 3);
  } finally {
    console.log = origLog;
    delete globalThis.window;
  }
});
