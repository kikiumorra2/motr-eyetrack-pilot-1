# Changelog

## 2.0.0 — 2026-08-28

### Character-level recording (new default)

- `samplingMode: "events"` (`src/config.js`): every pointer sample the hardware delivers
  (`pointermove` + `getCoalescedEvents()`) is hit-tested against measured character boxes,
  and only *changes* of the character under the cursor are stored, with millisecond
  timestamps, as **one compact row per trial** (`TrialType = "charEvents"`, format
  `motr-ce/1`, spec in `src/charEvents/FORMAT.md`; ~5–10 KB per trial instead of
  ~60–100 KB). The raw pointer trace is kept as well, delta-coded.
- `samplingMode: "interval"` keeps the original 50 ms sampler unchanged; `"both"` records
  both, for validation.
- Step 1 of the pipeline expands charEvents rows into the classic per-sample rows, so steps
  2–3 are unchanged. `--resample 50` reproduces the 20 Hz pipeline output exactly for the
  same movement; a character-level table (`char_events_exp_<ID>_<date>.csv`) is written
  alongside. `plot_char_events.py` draws a trial (scanpath, character boxes, raw trace).
- The JS and Python codecs are pinned to each other by `test/fixtures/`; tests in `test/`
  (node:test, including a headless-Chrome check against `document.elementFromPoint`) and
  `postprocessing/tests/` (pytest, including an end-to-end run over simulated data).

### Fixes

- Per-trial submissions after a participant's first — and the survey row — carried no
  `SubjectId` (magpie only tags the first row of *all* recorded data), and the pipeline
  silently dropped them. `src/submit.js` now puts the experiment-level data on every
  submission; step 1 warns loudly when a submission cannot be assigned to a participant.
  Data collected with 1.0.0 and `submitEachTrial: true` has only each participant's first
  trial assignable.
- Step 1 reads the magpie-serverless *Download results* CSV (flattened, `submission_id`
  column) as well as the classic results-table dump; treats magpie's `""` filler as
  missing (it blocked the participant-column broadcast and lost `zoomPercent`,
  `devicePixelRatio` and the window size in the participants table); stores integral
  participant columns as integers; reports the participant's last `experiment_end_time`.
- `response_chosen` is spread over every word of a trial, skipped words included, already
  in the per-participant `reader_*_reading_measures.csv` files.
- Participant IDs containing underscores were truncated in the per-participant file names
  (`reader_<id>_…`), which then mislabelled `submission_id` in `reading_measures_all.csv`.

### Checks and documentation

- `check_reading_measures.py`, step 4 of `run_pipeline.py`: verifies the identities the
  measure definitions guarantee on every row and recomputes all ten measures independently
  from the association files; a failure stops the pipeline.
- `postprocessing/READING_MEASURES.md`: exact definitions of every column, the identities
  between them, and a worked example that is pinned by a test.
- README: which `samplingMode` to choose, and how to verify an experiment end-to-end.
- Validated on a human session against magpie-serverless: the recorder sees coalesced
  batches and sub-ms timestamps; legacy 50 ms rows and character events agree except for
  ticks within a frame of a pointer sample and sub-pixel box-edge cases (`FORMAT.md`).

## 1.0.0 — 2026-08-27

Initial template: the magpie-based MoTR app with the 50 ms sampler, materials and list
tooling, GitHub Pages deployment, and the MoTR postprocessing pipeline
(Wilcox, Cui & Ćeplö, 2024).
