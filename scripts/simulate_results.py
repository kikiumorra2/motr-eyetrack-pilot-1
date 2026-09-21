#!/usr/bin/env python3
"""
Generate fake MoTR data in the format the magpie server exports, so the postprocessing
pipeline can be tested before any real data is collected.

Each participant reads practice items, then one list plus the fillers. Per trial, one
submission (one row of the export) is produced - exactly like the app with
`submitEachTrial: true` - followed by one submission with the survey answers.

A continuous pointer path (125 Hz) is simulated for every trial and recorded in the
requested format (`--format`):
  legacy  one row every --sample-ms (the 20 Hz `samplingMode: "interval"` rows)
  events  one charEvents row per trial (`samplingMode: "events"`, src/charEvents/FORMAT.md)
  both    both, from the same path (`samplingMode: "both"`)
The same --seed gives the same path in every format, so the pipeline outputs of
`--format legacy` and `--format events` + `--char-events expand --resample 50` are identical.

Usage:
  python scripts/simulate_results.py --experiment-id 0 --n-participants 3
  python postprocessing/1_fetch_and_flatten.py --experiment-id 0 --csv results/exp_0/simulated_export.csv
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "postprocessing"))
import motr_char_events as ce  # noqa: E402

LINE_HEIGHT, CHAR_WIDTH, LEFT, TOP, LINE_CHARS = 40, 10, 120, 180, 60
GLYPH_HEIGHT = 21          # glyph band inside the 40 px line (18 px font)
PATH_STEP_MS = 8           # 125 Hz pointer
T_START = 500              # recording starts 500 ms after the screen appears
FORMATS = ("legacy", "events", "both")


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fake_snapshot(words):
    """Character layout of the trial text (same geometry as the JS test helper fakeTable)."""
    return ce.fake_table(words, char_w=CHAR_WIDTH, line_chars=LINE_CHARS, line_h=LINE_HEIGHT,
                         glyph_h=GLYPH_HEIGHT, left=LEFT, top=TOP)


def visit_order(rng, n_words):
    """Left-to-right reading with occasional regressions (jump back 1-3 words and re-read)."""
    path = list(range(n_words))
    for i in range(2, n_words):
        if rng.random() < 0.15:
            back = rng.randint(1, min(3, i))
            path[i:i] = list(range(i - back, i))
    return path


def simulate_path(rng, words, snapshot):
    """Pointer samples [(t, x, y)] at PATH_STEP_MS: travel to each visited word, then dwell."""
    samples = []
    B = snapshot["block"]
    t, x, y = float(T_START), B[0] + 5.0, B[1] + 5.0      # start inside the block, on no word
    for idx in visit_order(rng, len(words)):
        frag = snapshot["words"][idx]["frags"][0]
        tx = rng.uniform(frag["xs"][0], frag["xs"][len(words[idx])] - 0.01)   # on a letter
        ty = rng.uniform(frag["top"] + 3, frag["bottom"] - 3)
        travel = rng.uniform(60, 160)
        steps = max(1, int(travel / PATH_STEP_MS))
        for k in range(1, steps + 1):
            t += PATH_STEP_MS
            samples.append((t, x + (tx - x) * k / steps, y + (ty - y) * k / steps))
        x, y = tx, ty
        dwell = int(rng.lognormvariate(5.6, 0.4))        # ~270 ms median
        for _ in range(max(1, dwell // PATH_STEP_MS)):
            t += PATH_STEP_MS
            samples.append((t, x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)))
    return samples


def legacy_rows(samples, snapshot, words, base, sample_ms):
    """The 20 Hz sampler: every sample_ms record the word under the latest pointer sample."""
    offsets = ce.span_offsets(words)
    index = ce.HitIndex(snapshot)
    rows, si, cur = [], 0, None
    t_end = samples[-1][0]
    t = T_START
    while t <= t_end:
        while si < len(samples) and samples[si][0] <= t:
            cur = samples[si]
            si += 1
        if cur is not None:
            state = ce.hit_state(index, offsets, cur[1], cur[2])
            if state != ce.OUT:
                idx = -1 if state == ce.NONE else ce.word_of_global(offsets, state)[0]
                row = {**base, "Index": idx, "responseTime": t, "mousePositionX": cur[1], "mousePositionY": cur[2]}
                if idx >= 0:
                    left, top, right, bottom = snapshot["words"][idx]["rect"]
                    row.update({"Word": words[idx], "wordPositionTop": top, "wordPositionLeft": left,
                                "wordPositionBottom": bottom, "wordPositionRight": right})
                rows.append(row)
        t += sample_ms
    rows.append({**base, "Index": -1, "responseTime": t_end, "mousePositionX": samples[-1][1], "mousePositionY": samples[-1][2]})
    return rows


def events_row(samples, snapshot, words, base, text):
    """The character-event recorder (mirror of the browser encoder) fed with the same path."""
    rec = ce.Recorder()
    rec.start(float(T_START), words, snapshot, t0_response=T_START)
    for t, x, y in samples:
        rec.feed(x, y, t, "mouse")
    rec.note_batch(len(samples), True, 40)
    rec.end(samples[-1][0])
    return {**base, "TrialType": "charEvents", "TrialText": text, "responseTime": samples[-1][0], **rec.fields()}


def simulate_trial(rng, trial, trial_idx, exp_data, sample_ms, options, fmt):
    words = ce.words_of(trial["text"])
    snapshot = fake_snapshot(words)
    base = {"Experiment": exp_data["Experiment"], "Condition": trial["condition_id"], "ItemId": trial["item_id"]}
    samples = simulate_path(rng, words, snapshot)
    t_end = samples[-1][0]
    rows = []
    if fmt in ("legacy", "both"):
        rows += legacy_rows(samples, snapshot, words, base, sample_ms)
    if fmt in ("events", "both"):
        rows.append(events_row(samples, snapshot, words, base, trial["text"]))
    opts = trial["options"].split("|") if trial.get("options") else options
    response = trial["correct"] if trial.get("correct") and rng.random() < 0.9 else rng.choice(opts)
    rows.append({**base, "TrialId": trial_idx, "TrialType": "trial", "Phase": "practice" if trial["condition_id"] == "practice" else "main",
                 "TrialText": trial["text"], "userResponse": response, "correctResponse": trial.get("correct") or "",
                 "readingTime": t_end - T_START, "ListId": exp_data["ListId"], "responseTime": t_end + 1500,
                 "zoomPercent": 100, "devicePixelRatio": 2, "windowInnerWidth": 1440, "windowInnerHeight": 900})
    return rows


EXP_DATA_MODES = ("first-row", "first-submission", "every-row")


def finalize(rows, exp_data, mode="first-row", first_submission=False):
    """
    Mimic magpie + the app: columns a row lacks become "" (magpie's addEmptyColumns); the experiment-level data (SubjectId,
    ListId, experiment_start_time, ...) is written according to `mode`:
      first-row         on the first row of every submission, null on the others - what the app
                        submits (src/submit.js); default
      first-submission  only on the first row of the participant's FIRST submission - what magpie
                        alone would do with per-trial submissions (later trials cannot be assigned
                        to a participant; step 1 warns and drops them)
      every-row         on every row
    A row's own value of a key (Experiment, ListId on summary rows) is never overwritten.
    """
    cols = set(exp_data)
    for r in rows:
        cols |= set(r)
    out = []
    for i, r in enumerate(rows):
        row = {**{c: "" for c in cols}, **r}
        carry = mode == "every-row" or (i == 0 and (mode == "first-row" or first_submission))
        for k, v in exp_data.items():
            if k not in r:
                row[k] = v if carry else None
        out.append(row)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", default="0")
    parser.add_argument("--n-participants", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None, help="default: results/exp_<ID>/simulated_export.csv")
    parser.add_argument("--format", choices=FORMATS, default="events", help="recording format (default: events)")
    parser.add_argument("--sample-ms", type=int, default=50, help="legacy sampling interval (default 50)")
    parser.add_argument("--exp-data", choices=EXP_DATA_MODES, default="first-row",
                        help="where the experiment-level data (SubjectId, ...) is written (see finalize; default first-row)")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    materials = ROOT / "materials"
    lists = sorted(materials.glob("lists/list_*.csv"))
    fillers, practice = read(materials / "fillers.csv"), read(materials / "practice.csv")
    options = ["I noticed an error", "Not sure", "Sentence was OK"]

    out = args.out or ROOT / "results" / f"exp_{args.experiment_id}" / "simulated_export.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    submissions, row_id = [], 1
    for p in range(args.n_participants):
        list_path = lists[p % len(lists)]
        list_id = int(list_path.stem.split("_")[1])
        subject = f"{rng.getrandbits(96):024x}"  # Prolific-style 24-hex ID
        start = 1_700_000_000_000 + p * 3_600_000
        exp_data = {"SubjectId": subject, "ListId": list_id, "Experiment": "motr_template",
                    "experiment_start_time": start, "experiment_end_time": start + 900_000, "experiment_duration": 900_000}
        main_trials = fillers[:2] + rng.sample(read(list_path) + fillers[2:], len(read(list_path)) + len(fillers) - 2)
        for i, trial in enumerate(practice + main_trials):
            rows = finalize(simulate_trial(rng, trial, i, exp_data, args.sample_ms, options, args.format), exp_data,
                            args.exp_data, first_submission=(i == 0))
            submissions.append((row_id, rows)); row_id += 1
        survey = finalize([{"Experiment": "motr_template", "TrialType": "survey", "responseTime": 20000,
                            "device": rng.choice(["Computer Mouse", "Computer Trackpad"]), "hand": "Right", "feedback": "simulated",
                            "zoomPercent": 100, "devicePixelRatio": 2, "screenWidth": 1440, "screenHeight": 900,
                            "windowInnerWidth": 1440, "windowInnerHeight": 900, "userAgent": "simulated"}], exp_data, args.exp_data)
        submissions.append((row_id, survey)); row_id += 1

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "inserted_at", "updated_at", "experiment_id", "results", "variant", "chain", "generation", "is_intermediate", "player"])
        for rid, rows in submissions:
            w.writerow([rid, "2026-01-01 12:00:00", "2026-01-01 12:00:00", args.experiment_id, json.dumps(rows), "", "", "", "false", ""])
    print(f"wrote {out}: {args.n_participants} participants, {len(submissions)} submissions, format {args.format}")


if __name__ == "__main__":
    main()
