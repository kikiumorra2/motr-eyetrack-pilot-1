# MoTR experiment template

A blank, ready-to-clone project for **Mouse Tracking for Reading (MoTR)** experiments
(Wilcox, Cui & Ćeplö, 2024). MoTR approximates eye-tracking in the browser: the text is
blurred and a small sharp window follows the mouse, so where the mouse goes is where the
participant reads. The app records which *character* is under the cursor with millisecond
timestamps (from every hardware mouse report, stored as compact change events — or, in the
legacy mode, the word under the cursor every 50 ms), and the postprocessing pipeline turns
those records into fixation-like "associations" and standard reading measures (first-pass,
gaze, go-past, …).

The app is built on [magpie](https://magpie-experiments.org/) (Vue 2), using the
[`magpie-base-MoTR`](https://github.com/cuierd/magpie-base-MoTR) fork.

## Repository layout

```
src/
  config.js                 ← experiment settings (name, lists, practice, question, zoom check …)
  magpie.config.js          ← server settings (experiment ID, server URL, mode, completion URL)
  App.vue                   ← screen flow: consent → browser check → instructions → practice → trials → survey → code
  components/MotrTrial.vue  ← the MoTR reading interface (one trial); records the data
  components/BrowserCheck.vue ← asks for 100% browser zoom before the study
  materials.js              ← loads the CSVs below and builds the trial sequence
  submit.js                 ← the one place that sends data to the server
  browser.js                ← zoom / screen measurements
  main.js                   ← boots Vue + magpie
  charEvents/               ← character-event recorder (default samplingMode "events"):
    FORMAT.md               ←   the motr-ce/1 format spec
    measure.js, layout.js   ←   character boxes from the DOM; hit test (mirrors elementFromPoint)
    recorder.js, dom.js     ←   state machine; pointer / resize / visibility wiring
    format.js, vlq.js, decoder.js ← codecs and the decoder (mirrored in postprocessing/motr_char_events.py)
materials/
  items.csv                 ← all critical items × conditions (source of truth)
  lists/list_NN.csv         ← one list per participant group (generated)
  fillers.csv, practice.csv
  README.md                 ← column spec
scripts/
  make_lists.py             ← Latin-square lists from items.csv
  simulate_results.py       ← fake data to test the pipeline
  update_magpie.sh          ← reinstall the magpie fork
  vue-cli.js                ← wrapper that makes Vue CLI 4 run on modern Node
postprocessing/
  run_pipeline.py           ← ONE command: raw export → reading_measures_all.csv (installs Python deps itself)
  1_fetch_and_flatten.py    ← raw submissions → flat sample CSV
  2_compute_reading_measures.py ← MoTR pipeline → per-participant reading measures
  3_aggregate.py            ← one analysis-ready CSV
  check_reading_measures.py ← step 4: sanity checks of that CSV (invariants + independent recomputation)
  motr_char_events.py       ← Python decoder / encoder of the motr-ce/1 format (used by step 1)
  plot_char_events.py       ← scanpath / dwell / trace figure for one trial
  READING_MEASURES.md       ← exact definition of every reading measure (read before analysing)
  plot_trial_mouse_overlay.py, utils/, tests/, README.md
results/                    ← downloaded / flattened data   (git-ignored)
output/                     ← pipeline output               (git-ignored)
.github/workflows/          ← build & deploy to GitHub Pages on push
```

## Quick start

```bash
git clone <this repo> my-experiment && cd my-experiment
npm install                 # Node 16 recommended (.nvmrc); 18–22 work via scripts/vue-cli.js
npm run serve               # http://localhost:8080  (mode: "debug" → nothing is sent anywhere)
```

Open the browser console to see the trial sequence and, in debug mode, the rows that
would be submitted.

## Setting up a new experiment

1. **Materials** – edit `materials/items.csv`, `fillers.csv`, `practice.csv` (schema in
   `materials/README.md`), then `python scripts/make_lists.py`. Rebuild after any change.
2. **Settings** – `src/config.js`: experiment name, practice/filler counts, the post-sentence
   question (per-item questions go in the CSV), zoom check, completion code. Then
   `src/magpie.config.js`: the server that receives the data (`serverUrl`), the experiment
   ID you created there, and `mode` (see *Where the data goes*).
3. **Text** – consent form and instructions in `src/App.vue` (look for `[INSTITUTION]`,
   `[DURATION]`, `[IRB / ETHICS COMMITTEE]`).
4. **Test** – `npm run serve`, run through the experiment, check the console output. Try
   `?LIST_ID=2` to force a list.
5. **Deploy** – push to GitHub (`main` or `master`); the workflow builds and publishes to the `gh-pages`
   branch (enable Pages → branch `gh-pages` in the repo settings). The study URL is
   `https://<user>.github.io/<repo>/?LIST_ID=1`. Alternatively `npm run build` and host
   `dist/` anywhere (`npm start` serves it with Express).
6. **Recruit** – with `mode: "prolific"`, add `&PROLIFIC_PID={{%PROLIFIC_PID%}}` to the study
   URL; the ID is pre-filled on the consent screen and participants are redirected to
   `completionUrl` at the end. One Prolific study per list, or `defaultList: "random"`.
7. **Analyse** – download the results from the server and run one command
   (see `postprocessing/README.md` for the step-by-step version):

   ```bash
   python3 postprocessing/run_pipeline.py --experiment-id 42 --csv results/raw/export.csv
   ```

## Where the data goes

Every trial's rows are sent as soon as the trial ends (`submitEachTrial` in `config.js`),
and the survey row at the very end, by `src/submit.js`:

```
POST {serverUrl}/api/submit_experiment/{experimentId}      body: JSON array of rows
```

`serverUrl` and `experimentId` live in `src/magpie.config.js`, so any magpie backend
(magpie-serverless, a self-hosted magpie server) is a one-line change. To send the data
somewhere else entirely, replace the body of `submitRows()` in `src/submit.js` — that is
the only place data leaves the browser. In `debug` mode nothing is sent; the rows are
printed to the browser console.

## Browser check

MoTR's window and word boxes are defined in CSS pixels, so browser zoom changes their
physical size. After consent, a check screen asks participants to set the zoom to 100 %
(Ctrl/⌘ + 0) and only continues once it is (estimated from
`window.outerWidth / window.innerWidth`, which tracks zoom in desktop Chrome, Firefox and
Edge; a "continue anyway" link appears after 30 s in case the estimate is wrong on some
setup). The zoom level, device pixel ratio and window size are recorded with every trial
(`zoomPercent`, `devicePixelRatio`, `windowInnerWidth/Height`) and screen size / user agent
in the survey row, so you can also filter afterwards. Settings: `browserCheck` in
`src/config.js`.

## How the interface works

`MotrTrial.vue` renders the sentence twice, exactly overlaid: a blurred black copy and a
sharp white copy split into one `<span>` per word. A white oval with
`mix-blend-mode: difference` follows the cursor, inverting the white text to black and
cancelling the blur under it – the moving "window". Because the spans receive the mouse
events, `document.elementFromPoint` tells us which word is under the cursor.

What gets recorded depends on `samplingMode` in `src/config.js`:

- **`"events"` (default)** — the character-event recorder (`src/charEvents/`). When a trial
  starts, the box of every character is measured once (with DOM `Range`s over the existing
  word spans, so nothing about the rendering changes). Every pointer sample the hardware
  delivers (`pointermove` + `getCoalescedEvents()`, typically 125–1000 Hz) is hit-tested
  against those boxes with the same rule the legacy sampler uses (`(x, y)`, then
  `(x, y − 3)`, else "no word"), and only *changes* of the character under the cursor are
  kept, with their millisecond timestamps. Optionally every raw sample is kept too, delta-coded
  (~3 bytes each). The layout is re-measured on resize/scroll/zoom/font load. "Done Reading"
  closes the recording and stores **one row per trial** (`TrialType = "charEvents"`, fields
  `mtFormat/mtLayout/mtEvents/mtTrace/mtStats`; format spec: `src/charEvents/FORMAT.md`).
  A typical trial is ~5–10 KB instead of ~60–100 KB.
- **`"interval"`** — the original sampler: every `sampleIntervalMs` while the cursor is over
  the text, a row is recorded with `Index`/`Word`, the word's bounding box, and the mouse
  position; magpie adds `responseTime`. "Done Reading" records an end-of-reading marker
  (`Index = -1`) so the last word's fixation can be closed.
- **`"both"`** — both at once, for validation studies.

Which one? `"events"` unless you have a reason: it is the default, records everything the
hardware reports, and yields the same reading measures as the 50 ms sampler on the same
movement — to the millisecond rather than to the tick (`postprocessing/READING_MEASURES.md`
§3.2 and §4.12 list the differences). Use `"interval"` to reproduce a published 20 Hz MoTR
study exactly (or pass `--resample 50` to the pipeline, which turns the events into the same
50 ms rows). `"both"` roughly doubles each trial's payload and is meant for validation; the
pipeline then uses the legacy rows unless you pass `--char-events expand`.

`postprocessing/1_fetch_and_flatten.py` expands charEvents rows back into the classic
per-sample rows (one row per character change, plus the marker), so the rest of the pipeline
is identical for all modes; it also writes a character-level table.

In every mode, after "Done Reading" the question is shown. "Next" records a trial-summary
row and, with `submitEachTrial`, immediately sends that trial's rows to the server (per-trial
submission means a dropout still leaves usable data). See the comment block at the top of
`MotrTrial.vue` for the full column list.

Layout details that the data depends on: `font-size: 18px; line-height: 40px;` and
`padding: 2% 11%` on both text layers. Keep the two layers identical if you restyle.

## Data format

Each submission is one JSON array of rows. Its **first row** carries the experiment-level data
(`SubjectId`, `ListId`, `Experiment`, `experiment_start_time`, …): magpie itself only puts that
on the first row of *all* recorded data, so `src/submit.js` adds it to every per-trial submission
and to the survey row (step 1 spreads it over the submission's other rows). Rows hold either sample columns,
the per-trial `charEvents` fields (`samplingMode: "events"`; see `src/charEvents/FORMAT.md`)
or summary columns; magpie fills absent columns with `""`. `1_fetch_and_flatten.py` reads
both export formats — the magpie-serverless *Download results* CSV (already flattened, one
line per row, grouped by `submission_id`) and the classic results-table dump (`id`,
`experiment_id`, `results` with one JSON array per submission) — and produces the flat CSV
documented in `postprocessing/README.md`.

## Verifying an experiment end-to-end

Before recruiting, run the whole path once yourself — ten minutes, and it catches the
configuration mistakes no unit test can:

1. `npm run serve` with `mode: "debug"`, complete a few trials, then in the browser console
   run `copy(JSON.stringify(window.__motrRows))` and paste the result into `rows.json`.
   `python3 postprocessing/motr_char_events.py --check rows.json` decodes every trial and,
   with `samplingMode: "both"`, reports how often the 50 ms rows agree with the character
   events (expect ≥ 95 %; the disagreements are the end-marker row, timer ticks a few ms
   after a pointer sample, and — on hardware that reports fractional pointer positions —
   moments when the pointer rests within 1 px of a box edge, see `src/charEvents/FORMAT.md`). `python3 postprocessing/plot_char_events.py --rows
   rows.json --item <item>` draws the scanpath, the character boxes and the raw trace.
2. Point `src/magpie.config.js` at your server and experiment ID with `mode: "directLink"`,
   complete one full session (enter a 24-character hex ID on the consent screen so
   `--require-prolific-id` accepts it), download the results and run
   `python3 postprocessing/run_pipeline.py --experiment-id <ID> --csv <download> --require-prolific-id`.
   In `results/exp_<ID>/participants_*.csv` expect one row for you with `n_trials` equal to
   the number of trials you completed and `device`/`hand` from the survey; the pipeline's
   last step (`check_reading_measures.py`) verifies the reading measures themselves and fails
   loudly if anything is inconsistent.
3. Exclude that test participant from the real analysis.

## Tests

```bash
npm test                     # JS unit tests (node:test, Node >= 22): codecs, hit test,
                             #   recorder, decoder, legacy equivalence, cross-language fixtures,
                             #   submission rows, and a headless-Chrome check when Chrome is installed
npm run test:perf            # strict throughput / payload-size thresholds
python -m pip install -r postprocessing/requirements-dev.txt
python -m pytest postprocessing          # Python decoder + pipeline tests, including the
                                         #   end-to-end run over simulated data (-m "not slow" skips it)
```

The JS and Python implementations of the `motr-ce/1` format are pinned to each other by
`test/fixtures/*.json`: scenarios encoded on one side must decode — and re-encode
byte-for-byte — on the other. Regenerate with `npm run fixtures` /
`MOTR_WRITE_FIXTURES=1 python -m pytest postprocessing` after changing the format.
`.github/workflows/test.yml` runs everything on push.

## Requirements

- Node 16 (see `.nvmrc`); newer versions work because `scripts/vue-cli.js` adds
  `--openssl-legacy-provider`. npm ≥ 7 (installs magpie's peer dependencies).
- Python ≥ 3.9 for postprocessing; `run_pipeline.py` installs `pandas`/`numpy`/`matplotlib`
  into a private `.venv/` by itself.

## References

Wilcox, E. G., Cui, D., & Ćeplö, S. (2024). Mouse Tracking for Reading (MoTR): A new
naturalistic incremental processing measurement tool. *Journal of Memory and Language*.
