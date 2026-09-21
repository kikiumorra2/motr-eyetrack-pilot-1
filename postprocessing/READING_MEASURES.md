# MoTR reading measures — exact definitions

This document explains how every column of `output/exp_<ID>/reading_measures_all.csv` is
computed, starting from the raw mouse samples the app records. It is written for readers
who know eye-tracking reading measures (fixations, first pass, gaze duration, go-past time,
regressions) and want to know precisely where the MoTR versions agree with and differ from
those.

Everything below is derived from the code that actually runs: the recording code in
`src/components/MotrTrial.vue` and the pipeline in `postprocessing/`
(`1_fetch_and_flatten.py`, `2_compute_reading_measures.py` with `utils/mergeAssociations.py`
and `utils/extractLingusticFeatures.py`, `3_aggregate.py`). The worked example in §6 is the
real output of the pipeline run on a hand-built scan-path.

**Contents**

1. [Quick reference](#1-quick-reference)
2. [Raw data: mouse samples](#2-raw-data-mouse-samples)
3. [From samples to "fixations": associations](#3-from-samples-to-fixations-associations)
4. [Word-level reading measures](#4-word-level-reading-measures)
5. [Trial-level columns](#5-trial-level-columns)
6. [Worked example](#6-worked-example)
7. [Checklist: what is excluded, and what is not](#7-checklist-what-is-excluded-and-what-is-not)
8. [Relation to eye-tracking measures](#8-relation-to-eye-tracking-measures)
9. [Computing other measures from the association files](#9-computing-other-measures-from-the-association-files)

---

## 1. Quick reference

One row per participant × trial × word. Durations are in milliseconds. An **association** is
MoTR's counterpart of a fixation: a run of consecutive mouse samples on the same word (§3).

| column | definition | closest eye-tracking measure |
|---|---|---|
| `first_duration` | duration of the first association on the word, *whenever* it occurred | first fixation duration, but **not** restricted to first pass |
| `gaze_duration` | duration of the first association on the word, if it occurred before any word to the right had been visited; else 0 | first-pass **first fixation** duration (not gaze duration — §4.3) |
| `first_pass_duration` | sum of the consecutive associations on the word starting at its first-pass entry, up to the first association on any other word; 0 if skipped in first pass | gaze duration / first-pass reading time |
| `total_duration` | sum of all associations on the word | total reading time |
| `right_bounded_rt` | sum of all associations on the word before any word to its right had been visited | right-bounded reading time |
| `go_past_time` | sum of all associations from the first-pass entry into the word until the first association on a word to its right | go-past / regression-path duration |
| `FPFix` | 1 if the word was visited before any word to its right | 1 − first-pass skipping |
| `FPReg` | 1 if an association on the word, before any word to its right was visited, was directly followed by an association on a word to its left | first-pass regression out |
| `RegIn_incl` | 1 if the word was visited after a word to its right had been visited | regression in (any later visit) |
| `RegIn_excl` | `RegIn_incl`, restricted to words with `FPFix = 1` | regression in, excluding words skipped in first pass |
| `response_chosen`, `correct_response`, `accuracy`, `trial_num` | trial-level (§5) | — |

A value of 0 in any duration or binary column means "no association survived for this
word"; the output does not distinguish a skipped word from an unmeasured one (§4.12).

---

## 2. Raw data: mouse samples

### 2.1 One sample every 50 ms (`samplingMode: "interval"`) — or one row per character change (`"events"`)

In the legacy mode, while a sentence is on screen and the pointer is inside the text block
(the padded box that contains the sentence, `.readingText`), the app records a row every
`sampleIntervalMs` (50 ms, `src/config.js`). The timer fires whether or not the pointer
moves, so a stationary pointer keeps producing samples.

In the default **character-event mode** the app instead records, with millisecond
timestamps, every change of the *character* under the pointer (from every hardware pointer
sample, see `src/charEvents/FORMAT.md`), and step 1 of the pipeline expands that record into
rows of exactly the shape below — one row per character change, `Index` being the word the
character belongs to (the gap after a word counts as that word, as with the legacy hit test),
plus the same `Index = −1` marker at "Done Reading". Everything from §2.2 on applies
unchanged; the only differences are noted where they matter. Each sample row has:

| field | meaning |
|---|---|
| `Index` | the word under the pointer: its 0-based position in the sentence, or **−1** when the pointer is inside the text block but on no word (padding, the band between lines) |
| `Word` | the word's text |
| `mousePositionX/Y` | pointer position (`clientX/Y`, CSS pixels) |
| `wordPositionTop/Left/Bottom/Right` | bounding box of the word under the pointer (CSS pixels) |
| `responseTime` | milliseconds since the trial screen started (added by magpie as `Date.now() − screen start`). **All timing in the pipeline is derived from this field.** |

Nothing is recorded while the pointer is outside the text block (over the buttons, the
trial counter, the page margins). The `Index` stored in a sample is the one set by the most
recent `mousemove` event before the timer fired.

### 2.2 Which word is "under the pointer"

- Words are `text.split(/\s+/)`: whitespace-delimited tokens, punctuation attached
  (`resigned.` is one word). The pipeline splits the materials the same way
  (`utils/preprocessTrialData.py`), so `Index` in the samples equals `word_nr` in the output.
- Each word is rendered as a `<span>` that contains the word *with a space on either side*,
  so the gap between two words belongs to a word, not to "no word": along a line there are
  no dead zones.
- Vertically, the hit area is the span's glyph box (18 px font, roughly 20 px tall) inside a
  40 px line, so there is a band of roughly 20 px between lines that is "no word" — except
  that a pointer up to 3 px *below* a word's box still counts as that word (the app re-tests
  the point 3 px above the pointer).
- The test is `document.elementFromPoint` at the **pointer hotspot**. The sharp window the
  participant sees is a 102 × 38 px oval drawn centred 12 px to the right of and 6 px above
  the hotspot; word assignment does not use the window.
- **No offline re-assignment.** There is no analogue of drift correction or line assignment:
  the word recorded at sampling time is final, and the pipeline never uses the coordinates
  to decide which word was read. (`FileDivider.correct_motr_data` in `utils/divideCsv.py` is a
  legacy coordinate fix for the original MoTR app; it runs only if negative x coordinates
  occur, which this app never produces, and it does not touch `Index` in any case.)

### 2.3 Trial markers

- Clicking **Done Reading** records a marker row with `Index = −1` and stops sampling. The
  question, if any, is shown without sampling.
- Clicking **Next** records one trial-summary row (`TrialType = "trial"`) carrying the answer
  (`userResponse`), `readingTime`, `TrialId`, list, zoom level, etc. Its `responseTime` is the
  time of the click.

### 2.4 Step 1: flattening (`1_fetch_and_flatten.py`)

Produces one CSV with one row per sample plus one summary row per trial, in the order
recorded (sorted by participant, experiment start time and submission order with a stable
sort, so within a trial the recorded order is preserved). Survey rows are dropped.
Participant-level filters only: `--require-prolific-id`, and `--min-trials N`, which counts
summary rows, i.e. completed trials *including practice*. No trial- or sample-level
exclusion happens in this step.

---

## 3. From samples to "fixations": associations

Code: `utils/divideCsv.py` (preparation) and `utils/mergeAssociations.py` (everything else).

### 3.1 Preparation (`FileDivider`)

The flat file is split into one file per participant. Before the split, `response` is
**back-filled within each participant × trial** (every sample row receives the answer from
its trial's summary row; a trial without an answer keeps NA),
`ItemId`/`Condition`/`Experiment` are forward-filled, a missing `Index` (the summary rows)
becomes −100, and missing coordinates become 425/285. None of this changes the `Index` of a
sample.

### 3.2 Merging samples into associations (`associationMerger.merge_associations`)

An **association** is a maximal run of consecutive rows, within one trial, that have the
same `Index`. The code walks through a participant's rows in order; when row *i+1* has the
same `ItemId` and the same `Index` as row *i* it joins the current run; when the `Index`
changes, the run is closed and written as one association with:

| field | value |
|---|---|
| `start_t` | `responseTime` of the run's first sample |
| `end_t` | `responseTime` of the **first sample of the next run** (the first sample with a different `Index`) |
| `duration` | `end_t − start_t` |
| `x_mean`, `y_mean` | mean pointer position over the run's samples (diagnostic only — not used by any measure) |

Consequences worth internalising:

- A duration runs until the *next* word is detected, so it includes the movement to that
  word (up to one sampling interval). A single-sample visit has a duration of ≈ 50 ms, not
  0. Durations are multiples of the (jittery) sampling interval. *Character-event mode:*
  the next word is detected the moment the pointer crosses into it, so durations are exact
  to the millisecond (not multiples of 50 ms), and a brief pass over a neighbouring word
  that 20 Hz sampling would have missed now splits the association. `--resample 50` in
  step 1 reproduces the legacy behaviour exactly for comparisons.
- No samples are recorded while the pointer is off the text block, but a run is only broken
  by a sample with a *different* `Index`. Time spent away from the text is therefore
  absorbed into the association that was active when the pointer left: leave from word 3 and
  come back onto word 3 → one association on word 3 that includes the away time; come back
  onto word 5 → the association on word 3 ends only when word 5 is sampled and still
  includes the away time. (If that makes it longer than `--up-thres`, it is removed, §3.4.)
  Timer throttling in a background tab is absorbed the same way.
- Inside the text block, passing through "no word" (`Index −1`, e.g. the band between
  lines) *does* break a run: a visit to a word interrupted by such a trip becomes two
  associations on that word with a −1 association between them (the −1 is removed in §3.4,
  making the two associations on the word **consecutive** — this matters in §4).
- The run on a trial's last row (the summary row) is discarded; it is never an association.
  The association on the last word actually read is closed by the Done Reading marker row.
  (The original MoTR app had no marker, so that association was lost; this template records
  it.)

### 3.3 Noise before reading (`_clear_noises_before_reading`)

Per trial, associations are removed from the beginning of the trial until the first
association on word **0, 1, 2 or 3** (`start_sent = (0, 1, 2, 3)`). Everything the pointer did
before reaching one of the first four words — landing in the middle of the sentence when
the screen appears, wandering over the text — is dropped, *including visits to later words*,
which are therefore not "first visits" any more. This step runs before the duration
thresholds, so a sub-threshold pass over word 0 counts as the start of reading (and is then
itself removed by §3.4).

### 3.4 Duration thresholds and "no word" (`write_out_denoise_merged_associations`)

Only associations with

    low_thres < duration < up_thres      (strict; defaults 160 ms and 4000 ms)
    Index ≠ −1

are kept, and written to `output/exp_<ID>/associations/reader_<participant>_clean.csv`.
(`--low-thres` and `--up-thres` on `run_pipeline.py` / `2_compute_reading_measures.py`; the
`> low_thres` test is repeated in `FeatureExtractor`, with the same result.)

Removed associations vanish entirely: they are not merged into their neighbours, not
capped, and their time is not credited to any word or measure.

- **Below 160 ms.** Mostly the words the pointer sweeps across on its way somewhere else
  (the analogue of a saccade passing over words), but also genuinely brief visits. The word
  counts as *not visited* at that moment. Two effects matter downstream: (a) a word whose
  only visits were brief has every measure = 0, i.e. looks skipped; (b) once a brief
  association is gone, the associations on either side of it become *adjacent*, which
  matters for `FPReg` (a regression whose landing association was brief is invisible) and
  makes consecutive associations on the same word possible.
- **Above 4000 ms.** Long stays: pauses, distraction, the pointer parked on a word while the
  participant thinks, or away-time absorbed as described in §3.2. Removing such an
  association can turn a genuinely read word into a "skipped" one and removes that time from
  `total_duration`, `go_past_time`, etc. If long stays are plausible in your task (long
  sentences, the last word before Done Reading), check the duration distribution in the
  association files and consider raising `--up-thres`.
- **`Index −1`.** Time on no word is never counted anywhere.

From here on every measure is computed on the **surviving associations of each trial, in
time order**. "Next", "previous", "immediately followed" and "consecutive" below always refer
to neighbours in this filtered sequence.

---

## 4. Word-level reading measures

Code: `utils/extractLingusticFeatures.py` (`FeatureExtractor`). Each measure is computed
per (trial, word) within one participant's file, over the chronological sequence of that
trial's surviving associations. Associations from other trials never enter, and nothing is
averaged across trials or participants.

### 4.1 Three events that define everything

For one participant and one trial, let *a₁ … aₙ* be the surviving associations in time
order, with `word(aₖ)` the word index and `dur(aₖ)` the duration. Fix a word *w*.

- **First visit** of *w*: the earliest *aₖ* with `word(aₖ) = w`.
- ***w* is passed**: the earliest *aₖ* with `word(aₖ) > w` — the first time the pointer is on
  *any* word to the right of *w*, not necessarily *w+1* and not necessarily arriving from
  *w*. If this never happens, *w* is passed "at the end of the trial". Associations before
  this point are **before *w* is passed**.
- **First-pass entry** of *w*: the first visit of *w*, provided it occurs before *w* is
  passed. A word either has a first-pass entry or it was *skipped in first pass* in the
  pipeline's sense.

Note what is *not* an event: moving **left** of *w* does not end "before *w* is passed". A
reader who goes *w* → *w−2* → *w* → *w+1* is still before *w* is passed on the return to
*w*. The eye-tracking notion "first pass ends when the word is left in either direction" is
used only by `first_pass_duration` (§4.4) — and, degenerately, by `gaze_duration`, which
counts a single association.

### 4.2 `first_duration`

`dur(first visit of w)`; 0 if *w* has no surviving association.

Code: `groupby(para_nr, cond_id, word_nr)["duration"].first()`.

This is the first association *ever* on *w*, in or out of first pass. If the reader skipped
*w* and only reached it on a regression, `first_duration` is the duration of that regressive
visit. Eye-tracking first fixation duration is normally restricted to first pass — that is
`gaze_duration` here.

### 4.3 `gaze_duration`

`dur(first-pass entry of w)`; 0 if *w* has no first-pass entry.

Code: an association on *w* is counted iff **every** earlier association of the trial is on
a word strictly to the left of *w*. Only the first visit can satisfy this (any later visit
is preceded by an association on *w* itself), and only if nothing to the right had been
visited before it.

So `gaze_duration` is either `first_duration` (when `FPFix = 1`) or 0, and it is the
duration of a **single association**. If the first-pass visit to *w* consists of two
consecutive associations (a trip through "no word" or a sub-threshold pass over another
word in between, §3.2/3.4), only the first is counted; a return to *w* after a leftward
excursion is not counted either. Despite the name, this is the analogue of eye-tracking
**first-pass first fixation duration**, not of gaze duration (the sum of first-pass
fixations); `first_pass_duration` (§4.4) is the latter.

### 4.4 `first_pass_duration`

Sum of `dur` over the consecutive associations on *w* that start at the first-pass entry of
*w*, ending just before the first association on any other word; 0 if *w* has no first-pass
entry.

Code: from the first-pass entry, add durations forward while the next association is still
on *w*; stop at the first association on a different word, to the left or to the right.

This is eye-tracking **gaze duration / first-pass reading time**: the whole first-pass
visit, including directly following associations on the same word (which exist when a
"no word" or sub-threshold association between them was removed, §3.2/3.4), but not
returns to *w* after the pointer has been on another word. It equals `gaze_duration`
whenever the first-pass visit is a single association, which is the common case.
`gaze_duration ≤ first_pass_duration ≤ right_bounded_rt`.

### 4.5 `total_duration`

Sum of `dur` over all associations on *w*; 0 if none. Total reading time.

### 4.6 `right_bounded_rt`

Sum of `dur` over all associations on *w* that occur before *w* is passed; 0 if none (which
is exactly `FPFix = 0`).

Code: an association on *w* is counted iff every earlier association is on a word ≤ *w*.

Includes the first-pass entry, any immediately following associations on *w*, **and** any
returns to *w* after leftward excursions, as long as no word to the right has been visited
yet. This is the standard right-bounded reading time.
`gaze_duration ≤ first_pass_duration ≤ right_bounded_rt ≤ total_duration`.

### 4.7 `go_past_time`

Sum of `dur` over every association from the first-pass entry of *w* (inclusive) up to the
point where *w* is passed (exclusive): the first-pass entry plus every following association
on words ≤ *w* until the pointer first reaches a word to the right of *w*. 0 if *w* has no
first-pass entry.

Code: from the first-pass entry, add durations forward until the first association with
`word > w`, then stop.

This is go-past / regression-path duration. `go_past_time − right_bounded_rt` is the time
spent on words *left* of *w* during regressions launched before *w* was passed. If *w* is
never passed (the last word, or the reader stops), `go_past_time` includes everything up to
Done Reading.

### 4.8 `FPFix`

1 if *w* has a first-pass entry, else 0.

Code: some association on *w* has every earlier association on a word ≤ *w*.

Equivalent to `gaze_duration > 0`, `right_bounded_rt > 0` and `go_past_time > 0`.
`1 − FPFix` is first-pass skipping — but `FPFix` is also 0 when the word was visited only
too briefly (< `low_thres`) or too long (> `up_thres`), §3.4.

### 4.9 `FPReg`

1 if some association on *w* that occurs before *w* is passed is **immediately followed** by
an association on a word < *w*; else 0.

Code: for each association on *w* satisfying the `FPFix` condition, look at the next
association; if its word is < *w*, set 1; otherwise stop looking (a next association on *w*
itself simply gets its own turn).

This is first-pass regression out, with two nuances relative to the usual eye-tracking
definition: the launching association may be *any* association on *w* before *w* is
passed, including a return to *w* after an earlier leftward excursion; and a regression
whose first landing association did not survive the thresholds is invisible (the next
surviving association may be *w* again, or a word to the right).

### 4.10 `RegIn_incl`

1 if some association on *w* occurs **after *w* has been passed** — i.e. after the reader had
already visited a word to the right of *w*; else 0.

Code: some association on *w* is preceded, anywhere earlier in the trial, by an association
on a word > *w*.

This is "regression in" in the broad sense — *any* later visit — not "a leftward movement
landed on this word": after regressing to *w−3*, re-reading *w−2*, *w−1* and *w* forwards sets
`RegIn_incl = 1` for all of them. It also fires for words skipped in first pass and reached
only by a regression (`FPFix = 0`).

### 4.11 `RegIn_excl`

`RegIn_incl AND FPFix`: 1 only if the word was visited after being passed *and* had a
first-pass entry. Words that were skipped in first pass and then visited during a
regression have `RegIn_incl = 1, RegIn_excl = 0`.

### 4.12 Zeros, and identities you can rely on

Every duration and binary column is 0 for a word with no surviving association. For
duration analyses, treat 0 as missing: keep rows with `FPFix = 1` for `gaze_duration`,
`first_pass_duration`,
`right_bounded_rt` and `go_past_time`, and rows with `total_duration > 0` for
`total_duration` and `first_duration`. Within a row:

- `first_duration > 0 ⇔ total_duration > 0 ⇔` the word has at least one surviving association
- `FPFix = 1 ⇔ gaze_duration > 0 ⇔ first_pass_duration > 0 ⇔ right_bounded_rt > 0 ⇔ go_past_time > 0`
- `gaze_duration ∈ {0, first_duration}`
- `gaze_duration ≤ first_pass_duration ≤ right_bounded_rt ≤ go_past_time`, and `right_bounded_rt ≤ total_duration`
- `FPFix = 1 ⇒ gaze_duration = first_duration`
- `RegIn_incl = 1 ⇔ total_duration > right_bounded_rt` (the associations on a word are
  exactly those before any word to its right was visited — `right_bounded_rt` — plus the
  regressive ones; so `FPFix = 0 and total_duration > 0 ⇒ RegIn_incl = 1`)
- `RegIn_excl = RegIn_incl and FPFix`
- `FPReg = 1 ⇔ go_past_time > right_bounded_rt` (hence `FPReg = 1 ⇒ FPFix = 1`)
- `first_duration = 0` or `low_thres < first_duration < up_thres`; `first_pass_duration ≤ total_duration`
- **Not** an identity: `total_duration > first_duration ⇒ RegIn_incl = 1`. A second
  association on a word also arises without any word to the right having been visited —
  after a regression to the *left* and back, or after a removed `−1` / sub-threshold
  excursion (*attacked* in §6: `total 500 > first 300`, `RegIn_incl = 0`).

`check_reading_measures.py` (step 4 of `run_pipeline.py`) verifies all of these on every row,
plus per-trial consistency (`response_chosen`, `trial_num`, `word_nr = 0…n−1`), and recomputes
every measure independently from the association files; the §6 example is pinned by
`tests/test_reading_measures.py`.

---

## 5. Trial-level columns

- **`response_chosen`** — the answer on the trial's summary row, copied to every word of the
  trial. Mechanics: back-filled onto the sample rows within the trial (§3.1), carried on
  each association, attached to the visited words, then spread over all words of the trial
  — skipped words (`FPFix = 0`) included — already in step 2
  (`FeatureExtractor.check_comprehension_answer`), so the per-participant
  `reader_*_reading_measures.csv` files and `reading_measures_all.csv` agree; step 3 repeats
  the spread as a safety net. A trial without an answer (an item without a question, or the
  question disabled) is kept with `response_chosen = NA`; step 3 prints a warning with the
  number of such trials. (The original MoTR package back-filled across trial boundaries and
  dropped answerless trials; this template does not.)
- **`correct_response`** — the `correct` column of `materials/*.csv` (NA if absent).
- **`accuracy`** — 1 if `response_chosen` equals `correct_response` as strings (exact,
  case-sensitive match), 0 otherwise; NA when either is missing.
- **`trial_num`** — 0-based rank of the trial among this participant's trials that have at
  least one surviving association, in the order they were read. Practice trials come first
  and count.
- **`item_id`, `condition_id`** — split from the `<item>_<condition>` key at its first
  underscore. `word`, `word_nr` come from the materials, not from the samples.
- **`ListId`, `device`, `hand`** — from the participants table. Any extra column in
  `materials/*.csv` is merged on (`item_id`, `condition_id`). Practice and filler trials are
  included in the output and not marked; add a column to those CSVs if you need to tell
  them apart.

**Which rows exist:** every word of every trial for which the participant has at least one
surviving association. Unvisited words are present with zeros; trials that were not shown
to the participant (other lists) are absent.

---

## 6. Worked example

The sentence *The senator that the reporter attacked resigned.* (words 0–6) was read with the
following scan-path (produced as 50 ms samples and run through the actual pipeline with the
default thresholds). Before the first row, the pointer sat 200 ms on *attacked* (word 5)
when the screen appeared; that association was removed as noise before reading (§3.3).

| # | word | duration | note |
|---|---|---|---|
| 1 | 0 The | 200 | reading starts (first association on words 0–3) |
| 2 | 1 senator | 300 | |
| – | 2 that | 100 | **removed**: < 160 ms |
| 3 | 3 the | 250 | |
| 4 | 4 reporter | 400 | next surviving association is on word 1 → regression launched here |
| 5 | 1 senator | 200 | |
| 6 | 2 that | 300 | first *surviving* visit to *that* |
| 7 | 3 the | 200 | |
| 8 | 4 reporter | 200 | |
| 9 | 5 attacked | 300 | |
| – | (no word) | 200 | **removed**: `Index −1` (pointer in the band between lines) |
| 10 | 5 attacked | 200 | consecutive with #9 once the −1 is gone |
| 11 | 6 resigned. | 350 | closed by the Done Reading marker |

Output rows for this trial (`reading_measures_all.csv`):

| word_nr | word | first_duration | gaze_duration | first_pass_duration | total_duration | right_bounded_rt | go_past_time | FPFix | FPReg | RegIn_incl | RegIn_excl |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | The | 200 | 200 | 200 | 200 | 200 | 200 | 1 | 0 | 0 | 0 |
| 1 | senator | 300 | 300 | 300 | 500 | 300 | 300 | 1 | 0 | 1 | 1 |
| 2 | that | 300 | 0 | 0 | 300 | 0 | 0 | 0 | 0 | 1 | 0 |
| 3 | the | 250 | 250 | 250 | 450 | 250 | 250 | 1 | 0 | 1 | 1 |
| 4 | reporter | 400 | 400 | 400 | 600 | 600 | 1300 | 1 | 1 | 0 | 0 |
| 5 | attacked | 300 | 300 | 500 | 500 | 500 | 500 | 1 | 0 | 0 | 0 |
| 6 | resigned. | 350 | 350 | 350 | 350 | 350 | 350 | 1 | 0 | 0 | 0 |

How to read it:

- **that (2)** — its only surviving visit (#6) came after words 3 and 4, so it has no
  first-pass entry: `gaze_duration`, `right_bounded_rt`, `go_past_time` and `FPFix` are 0,
  yet `first_duration = 300` (the regressive visit) and `total_duration = 300`.
  `RegIn_incl = 1` (visited after being passed) but `RegIn_excl = 0` (no first-pass entry).
  Its genuine first-pass visit of 100 ms is invisible.
- **senator (1)** and **the (3)** — read in first pass, passed, then visited again (#5, #7):
  `RegIn_incl = RegIn_excl = 1`, `total_duration > right_bounded_rt`.
- **reporter (4)** — passed at #9. Before that it received #4 (400) and #8 (200):
  `right_bounded_rt = 600`, but `gaze_duration = first_pass_duration = 400` (the first-pass
  visit is a single association: #4 is followed by an association on another word).
  `go_past_time = 400 + 200 + 300 + 200 + 200 = 1300` (#4 through #8). `FPReg = 1` because #4
  is immediately followed by an association on word 1. `RegIn = 0`: never visited after #9.
- **attacked (5)** — #9 and #10 are consecutive associations on the same word (the −1 between
  them was removed): `gaze_duration = 300` (#9 only) while `first_pass_duration = 500`
  (#9 + #10, the whole first-pass visit) and `right_bounded_rt = 500`.
  `FPReg = 0` (after #9 comes #10 on the same word, then #11 to the right).
- **resigned. (6)** — never passed, so `go_past_time` runs to the end of reading.

The same run also included two trials without an answer: they were kept with
`response_chosen = NA` and `accuracy = NA`, and did not affect the other trials.

---

## 7. Checklist: what is excluded, and what is not

| level | what is dropped | where | control |
|---|---|---|---|
| participant | IDs that are not 24-character Prolific IDs (optional) | step 1 | `--require-prolific-id` |
| participant | fewer than N completed trials (practice counts) | step 1 | `--min-trials N` |
| trial | trials with no surviving association | step 2 | — |
| association | everything before the first association on words 0–3 of the trial | step 2, §3.3 | `start_sent` in `mergeAssociations.py` |
| association | `duration ≤ low_thres` (160 ms) | step 2, §3.4 | `--low-thres` |
| association | `duration ≥ up_thres` (4000 ms) | step 2, §3.4 | `--up-thres` |
| association | `Index = −1` (no word) | step 2, §3.4 | — |
| association | the run on a trial's last row (summary row) | step 2, §3.2 | — |
| sample | none recorded while the pointer is off the text block; the time is absorbed into the current association | app | — |
| word | nothing — every word of every kept trial has a row | | |

Not applied anywhere: trimming or winsorising of the measures, merging of short associations
into neighbours, per-participant standardisation, accuracy-based trial exclusion, dropping
of trials without an answer (kept with `response_chosen = NA`), and any use of the pointer
coordinates. The output is the raw per-word measure for every kept
trial; all further cleaning is up to the analyst.

Parameters that change the numbers: `--low-thres`, `--up-thres` (above), `samplingMode`
in `src/config.js` (millisecond character events vs. the 50 ms timer; `sampleIntervalMs`
is the resolution of every duration in the legacy mode) and, for character-event data,
`--char-events` / `--resample` in step 1.

---

## 8. Relation to eye-tracking measures

**Associations vs. fixations.** An association is not a fixation with a different sensor;
keep these differences in mind:

- Its duration is measured from the first sample on the word to the first sample on the
  *next* word, so it includes the "saccade" to the next word (up to 50 ms), and it is
  quantised to the sampling interval.
- There is no minimum-duration merging: short associations are deleted, never merged into
  neighbours; long ones are deleted, never capped.
- Time with the pointer off the text is absorbed into the current association; time on
  "no word" inside the text is discarded.
- Word assignment happens at recording time from the pointer hotspot; there is no drift
  correction, and the sharp window is offset from the hotspot (§2.2).
- The sharp window is about 100 px wide (one to two words at 18 px), so an association
  records where the window was, not where the eyes were within it.

**Column by column.**

| eye-tracking measure | MoTR column | agreement / differences |
|---|---|---|
| first fixation duration (first pass) | `gaze_duration` | same idea: the first association on the word, if it occurred before any word to the right. Zero when skipped. |
| first fixation duration (unconditional) | `first_duration` | the first association whenever it occurred, including regressive first visits |
| gaze duration / first-pass reading time | `first_pass_duration` | same definition: consecutive associations on the word from the first-pass entry up to the first association on any other word |
| right-bounded reading time | `right_bounded_rt` | same definition |
| go-past / regression-path duration | `go_past_time` | same definition; runs to the end of reading if the word is never passed |
| total reading time | `total_duration` | same definition |
| first-pass skipping | `1 − FPFix` | also 1 when every visit was shorter than `low_thres` or longer than `up_thres` |
| first-pass regression out | `FPReg` | launched from any association on the word before it was passed (including returns to it), and only if the landing association survived the thresholds |
| regression in | `RegIn_incl` | "visited after being passed", including forward re-reading after a regression that landed further left; fires for first-pass-skipped words too |
| regression in, first-pass-fixated words only | `RegIn_excl` | `RegIn_incl` with `FPFix = 1` |
| second-pass time, refixation count, landing position, … | *(none)* | computable from the association files, §9 |

---

## 9. Computing other measures from the association files

`output/exp_<ID>/associations/reader_<participant>_clean.csv` holds the surviving
associations (after §3.3–3.4) of one participant, in time order, with columns
`sbm_id, expr_id, cond_id, para_nr, word_nr, word, duration, start_t, end_t, x_mean, y_mean,
response`. Only this filtered file is written; to inspect the unfiltered associations call
`associationMerger.write_out_all_merged_associations()` yourself, or lower/raise the
thresholds. Some measures the pipeline does not output:

- **Number of associations on a word** (fixation-count analogue): count its rows in the trial.
- **Second-pass / re-reading time**: `total_duration − right_bounded_rt`.
- **Regression-in in the narrow sense** (arriving from the right): a row on *w* whose
  immediately preceding row has `word_nr > w`.

For plots of the raw trajectory over the word boxes use
`postprocessing/plot_trial_mouse_overlay.py` on the step-1 sample file.
