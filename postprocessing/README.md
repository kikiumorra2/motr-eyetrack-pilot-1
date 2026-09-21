# Analysing the data

## The short version

You need Python 3.9 or newer ([python.org](https://www.python.org/downloads/)) and, the
first time only, an internet connection. No other setup.

1. **Download** the results of your experiment from the magpie server as a CSV file
   (magpie-serverless: *Download results* on the experiment's page; a dump of the classic
   magpie results table works too) and save it in the project folder, e.g. as
   `results/raw/export.csv`.
2. **Open a terminal in the project folder.**
   macOS: right-click the folder in Finder → *Services* → *New Terminal at Folder*
   (or open Terminal and type `cd `, drag the folder into the window, press Enter).
   Windows: open the folder, Shift + right-click → *Open PowerShell window here*.
   VS Code: *Terminal → New Terminal*.
3. **Run one command** (use `python` instead of `python3` on Windows; replace `42` with
   your experiment ID from `src/magpie.config.js`):

   ```bash
   python3 postprocessing/run_pipeline.py --experiment-id 42 --csv results/raw/export.csv
   ```

   The first run creates a private Python environment in `.venv/` and installs the
   required packages (about a minute). Every later run takes seconds.
4. **Your data** is in `output/exp_42/reading_measures_all.csv` — one row per participant
   × word, ready for R, Python or Excel. The command's last step checks that file
   (`check_reading_measures.py`); if it prints `INVARIANTS VIOLATED` or `DIFFERS`, do not
   use the output — something upstream is wrong.

Useful options: `--require-prolific-id` (keep only participants whose ID is a 24-character
Prolific ID), `--min-trials 30` (drop participants who did not finish), `--low-thres` /
`--up-thres` (fixation duration limits in ms; default 160 and 4000), `--char-events`
and `--resample` (below).

Try it before collecting any data:

```bash
python3 scripts/simulate_results.py --experiment-id 0 --n-participants 3
python3 postprocessing/run_pipeline.py --experiment-id 0 --csv results/exp_0/simulated_export.csv
```

`simulate_results.py --format legacy|events|both` (default `events`) chooses the recording
format; the same `--seed` produces the same simulated pointer paths in every format.

## Character-event data (`samplingMode: "events"`)

With the default app setting, each trial arrives as **one** row (`TrialType = "charEvents"`)
holding the character boxes, the millisecond change events and (optionally) the raw pointer
trace in compact text fields (`src/charEvents/FORMAT.md`). Step 1 decodes them
(`postprocessing/motr_char_events.py`):

- `--char-events auto` (default): expand charEvents rows into the classic sample rows — one
  row per character change (`Index`, `Word`, `responseTime`, `mousePositionX/Y`,
  `wordPosition*`, plus `charIndex`) and the `Index = -1` end marker — so steps 2–3 run
  unchanged. If a submission also contains legacy 20 Hz rows (`samplingMode: "both"`), the
  legacy rows are used and the charEvents row is dropped.
- `--char-events expand`: always use the events (drops legacy rows in `both` data);
  `ignore`: drop charEvents rows; `keep`: leave them untouched.
- `--resample 50`: with `expand`, emit one row every 50 ms (the state at each tick) instead of
  one per change. The pipeline output is then identical to what the legacy sampler would have
  produced from the same pointer movement — useful to compare studies across modes.
- In all modes a character-level table is written:
  `results/exp_<ID>/char_events_exp_<ID>_<date>.csv` — one row per event with `t` (ms since
  the trial screen started), `dt`, `kind` (`c` character, `n` no word, `o` outside the text,
  `l` layout change, `h`/`s` tab hidden/shown, `e` done reading, `t` truncated), `word_idx`,
  `char_idx` (0 = leading space, 1… the word's characters, last = trailing space), `char`,
  `global_idx`, `layout_id`, `x`, `y`.

Because character changes are timestamped to the millisecond, durations are no longer
multiples of 50 ms and short excursions onto a neighbouring word are no longer missed. Expect
word-level measures to differ slightly from a 20 Hz study; `--resample 50` gives the
apples-to-apples numbers. `mtStats` in the raw row records per-trial diagnostics (`coal`:
coalesced events available, `mindt`: smallest inter-sample interval, `hmax`: slowest handler
call in µs, `trunc`: event cap hit). To look at a session recorded locally (`mode: "debug"` in
`src/magpie.config.js`, `npm run serve`): the app collects every row in `window.__motrRows`;
in the browser console run `copy(JSON.stringify(window.__motrRows))`, paste into `rows.json`,
then

```bash
python3 postprocessing/plot_char_events.py --rows rows.json --list          # trials in the file
python3 postprocessing/plot_char_events.py --rows rows.json --item 3 --show  # scanpath, dwell heatmap, trace, diagnostics
python3 postprocessing/motr_char_events.py --check rows.json                 # decode + agreement with legacy rows ("both" mode)
```

`plot_char_events.py --csv export.csv` does the same for a server export or a simulated one. The
layout panel is framed on the text and sized from its aspect ratio; `--fit block` frames the whole
recorded text block instead and `--fit all` every position the pointer visited (which shows the
strokes that enter and leave the screen, at the price of much smaller words).

## What the output contains

`output/exp_<ID>/reading_measures_all.csv` — one row per participant × sentence × word:

| column | meaning |
|---|---|
| `submission_id` | participant ID (as entered on the consent screen) |
| `item_id`, `condition_id` | from your materials; `para_nr` is the combined `<item>_<condition>` key |
| `word`, `word_nr` | the word and its 0-based position in the sentence |
| `first_duration` | duration of the first fixation on the word (ms), whether or not it was in first pass |
| `gaze_duration` | duration of the first fixation on the word if it was fixated in first pass, else 0 (first-pass first-fixation duration) |
| `first_pass_duration` | sum of the consecutive fixations on the word from first entering it in first pass until leaving it (eye-tracking gaze duration) |
| `total_duration` | sum of all fixations on the word |
| `right_bounded_rt` | time from first entering the word until first moving past it to the right |
| `go_past_time` | as above but including re-reading of earlier words |
| `FPFix` | 1 if the word was fixated in first pass |
| `FPReg` | 1 if a regression was launched from the word in first pass |
| `RegIn_incl` / `RegIn_excl` | 1 if the word was visited again after a word to its right had been visited (`_excl`: only if the word was also fixated in first pass, `FPFix = 1`) |
| `response_chosen` | the participant's answer to the post-sentence question (NA if none was recorded) |
| `correct_response`, `accuracy` | from the `correct` column of your materials (if given) |
| `trial_num` | order in which the participant read the sentence |
| `ListId`, `device`, `hand` | participant info from the app and survey |
| any extra columns from `materials/*.csv` | e.g. your own condition labels |

Durations are 0 for words that received no fixation. "Fixation" means an *association* in
MoTR terms: a run of consecutive mouse samples on the same word, kept if its duration is
between `--low-thres` and `--up-thres`.

**[READING_MEASURES.md](READING_MEASURES.md) defines every measure exactly** (how samples
become associations, what is excluded, how each column differs from its eye-tracking
counterpart, with a worked example). Read it before analysing the data.

`results/exp_<ID>/participants_exp_<ID>_<date>.csv` — one row per participant: list,
device, hand, free-text feedback, duration, browser zoom, screen size, user agent, number
of completed trials.

## Getting the data off the server

- **CSV export** (`--csv`), either format (detected from the columns):
  - the **magpie-serverless** "download results" file (https://magpie-serverless.vercel.app):
    already flattened, one line per submitted row, with a `submission_id` column that groups
    the rows of one submission;
  - a dump of the classic magpie-backend results table with columns `id`, `experiment_id`,
    `results`, … where `results` holds each submission as a JSON array of rows (plain JSON or
    Postgres' `{"{\"...\"}"}` array syntax are both accepted).
- **Direct database access** (`--db`): set the environment variables `MOTR_DB_NAME`,
  `MOTR_DB_USER`, `MOTR_DB_PASS`, `MOTR_DB_HOST` (and `MOTR_DB_TABLE`, default `results`),
  install `psycopg2-binary`, and run with `--db` instead of `--csv`. Never commit credentials.

## How the pipeline works

```
raw submissions ──▶ 1_fetch_and_flatten.py ──▶ results/exp_<ID>/results_processed_exp_<ID>_<date>.csv  (one row per mouse sample / character change)
                                               results/exp_<ID>/char_events_exp_<ID>_<date>.csv       (one row per character event)
                                               results/exp_<ID>/participants_exp_<ID>_<date>.csv
                                               results/exp_<ID>/items_processed.csv
                ──▶ 2_compute_reading_measures.py (the MoTR pipeline, utils/)
                                               output/exp_<ID>/divided/, corrected_divided/, processed_trial/, associations/
                                               output/exp_<ID>/reading_measures/reader_<participant>_reading_measures.csv
                ──▶ 3_aggregate.py          ──▶ output/exp_<ID>/reading_measures_all.csv
                ──▶ check_reading_measures.py   sanity checks of that file (invariants, and every
                                                measure recomputed independently from the
                                                association files); a failure stops the pipeline
```

`run_pipeline.py` simply runs the four scripts in order; each can also be run on its own
(`--help` lists the options).

**Step 1** parses the JSON of every submission (one per trial, plus one for the survey),
broadcasts the per-participant columns from each submission's first row to all its rows (a
submission without a `SubjectId` cannot be assigned to anyone - it is dropped with a loud
warning; the app puts the id on every submission in `src/submit.js`), drops the survey rows from the sample
file, builds `ItemId = <item_id>_<condition_id>`, and renames `userResponse → response`,
`SubjectId → submission_id`. The sample file has one row per mouse sample with `Index` /
`Word` (word under the cursor; `-1` = no word, or the end-of-reading marker), `responseTime`
(ms since the trial started), `mousePositionX/Y`, `wordPositionTop/Left/Bottom/Right`,
plus one summary row per trial (`TrialType = trial`).

**Step 2** is the published MoTR pipeline (Wilcox, Cui & Ćeplö 2024): split into one file
per participant → tokenise the materials → merge consecutive samples on the same word into
associations (dropping those outside the duration limits, samples on no word, and anything
before the reader first reaches one of the first four words) → compute the reading
measures per word.

**Step 3** concatenates the per-participant files, splits the `<item>_<condition>` key,
joins participant info and item metadata from `materials/`, spreads the trial's response
over all of its words, and computes `accuracy`.

## Changes relative to the original MoTR postprocessing package

`utils/` is the shared `postprocessing_package` (divideCsv, mergeAssociations,
preprocessTrialData, extractLingusticFeatures). Differences:

- `utils/divideCsv.py`: `fillna(method=…, inplace=True)` calls rewritten as plain
  assignments (`.bfill()` / `.ffill()` / `.fillna(value)`) — required by pandas ≥ 3, same result.
- `utils/divideCsv.py`: the `response` back-fill is done within each participant × trial
  (the original back-filled across the whole file, so a trial without an answer inherited
  the next trial's answer); `utils/extractLingusticFeatures.py`: `write_out` keeps every
  trial with at least one association (the original kept only trials with an answer, so
  answerless trials were dropped). Such trials now have `response_chosen = NA`.
- `2_compute_reading_measures.py` replaces `postprocessing.py`: identical four stages and
  calls; new command-line flags with defaults derived from the experiment ID; output under
  `output/exp_<ID>/`.
- `1_fetch_and_flatten.py` replaces the ad-hoc `process_exp_data_step1.py` /
  `db_connect.py` / `clean_data.py` scripts: same transformations, plus a participants table
  (instead of `feedback.csv`), `--require-prolific-id` and `--min-trials` filters, and
  `items_processed.csv` generated from `materials/`.
- `utils/extractLingusticFeatures.py`: new measure `first_pass_duration`
  (`get_first_pass_duration`), the eye-tracking gaze duration; `gaze_duration` is unchanged
  and remains the first-pass first-fixation duration.
- `3_aggregate.py` and `run_pipeline.py` are new.
- On the app side, the template records an end-of-reading marker (`Index = -1`) when
  "Done Reading" is clicked, so the fixation on the **last word** of each sentence is closed
  and counted (the original app never closed it); sampling stops during the question; and
  `Word` is stored without the surrounding spaces the original recorded.

## Visualisation

```bash
python3 postprocessing/plot_trial_mouse_overlay.py --input results/exp_42/results_processed_exp_42_<date>.csv \
    --submission-id <participant> --item-id 3_obj_rc --output output/exp_42/trial.png
```

draws one trial's mouse samples over the recorded word boxes (run inside `.venv`:
`.venv/bin/python` on macOS/Linux, `.venv\Scripts\python` on Windows, or activate it first).
