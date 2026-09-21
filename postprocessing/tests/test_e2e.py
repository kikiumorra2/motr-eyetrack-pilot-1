"""End-to-end: simulate exports in both formats from the same pointer paths, run steps
1→4 on each (in a temp dir), and compare the final reading measures.

  legacy  ==  events + `--char-events expand --resample 50`   (byte-identical)
  legacy  ~=  events (raw millisecond events)                  (within 50 ms quantization)
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PP = ROOT / "postprocessing"
PY = sys.executable
KEY = ["submission_id", "item_id", "condition_id", "word_nr"]
DURATIONS = ["first_duration", "total_duration", "gaze_duration", "first_pass_duration", "right_bounded_rt", "go_past_time"]
BINARY = ["FPFix", "FPReg", "RegIn_excl", "RegIn_incl"]


def run(*args):
    r = subprocess.run(
        [PY] + [str(a) for a in args],
        check=False,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if r.returncode != 0:
        raise AssertionError(
            f"Command failed:\n{' '.join(str(a) for a in args)}\n\n"
            f"{r.stdout}"
        )

    return r.stdout


def pipeline(tmp, name, export, *step1_args):
    res, out = tmp / f"res_{name}", tmp / f"out_{name}"
    run(PP / "1_fetch_and_flatten.py", "--experiment-id", "0", "--csv", export, "--out-dir", res, *step1_args)
    in_file = next(res.glob("results_processed_exp_0_*.csv"))
    run(PP / "2_compute_reading_measures.py", "--experiment-id", "0", "--in-file", in_file,
        "--trial-file", res / "items_processed.csv", "--out-dir", out)
    run(PP / "3_aggregate.py", "--experiment-id", "0", "--out-dir", out,
        "--participants", next(res.glob("participants_exp_0_*.csv")))
    # step 4: invariants + reference recomputation must pass on every variant
    run(PP / "check_reading_measures.py", "--experiment-id", "0", "--out-dir", out)
    return pd.read_csv(out / "exp_0" / "reading_measures_all.csv")


@pytest.mark.slow
def test_every_submission_is_assigned_to_its_participant(tmp_path):
    """Per-trial submissions: the app writes the experiment-level data on the first row of EVERY
    submission (src/submit.js). With magpie's own behaviour (first row of all data only, i.e. the
    participant's first submission) every later trial would be anonymous: step 1 must keep all
    trials in the first case and warn loudly in the second."""
    import json
    for mode, expect_all in (("first-row", True), ("first-submission", False)):
        export = tmp_path / f"{mode}.csv"
        run(ROOT / "scripts" / "simulate_results.py", "--experiment-id", "0", "--n-participants", "2", "--seed", "5",
            "--exp-data", mode, "--out", export)
        subs = [json.loads(r) for r in pd.read_csv(export)["results"]]
        n_trials_written = sum(1 for s in subs for r in s if r.get("TrialType") == "trial")
        subjects = {r["SubjectId"] for s in subs for r in s if r.get("SubjectId") not in (None, "NA")}
        assert len(subjects) == 2 and n_trials_written > 4
        res = tmp_path / f"res_{mode}"
        log = run(PP / "1_fetch_and_flatten.py", "--experiment-id", "0", "--csv", export, "--out-dir", res)
        participants = pd.read_csv(next(res.glob("participants_exp_0_*.csv")))
        flat = pd.read_csv(next(res.glob("results_processed_exp_0_*.csv")), low_memory=False)
        assert len(participants) == 2
        if expect_all:
            assert participants["n_trials"].sum() == n_trials_written           # nothing dropped
            assert (flat["TrialType"] == "trial").sum() == n_trials_written
            assert participants["device"].notna().all()                          # survey row assigned too
            assert "no SubjectId" not in log and "WARNING" not in log
        else:
            assert (participants["n_trials"] == 1).all()                         # only the first trial survives
            assert log.count("warning: submission") == len(subs) - 2 and "WARNING" in log and "were dropped" in log


@pytest.mark.slow
def test_pipeline_equivalence(tmp_path):
    exports = {}
    for fmt in ("legacy", "events", "both"):
        exports[fmt] = tmp_path / f"{fmt}.csv"
        run(ROOT / "scripts" / "simulate_results.py", "--experiment-id", "0", "--n-participants", "2",
            "--seed", "11", "--format", fmt, "--out", exports[fmt])
    assert exports["events"].stat().st_size * 5 < exports["legacy"].stat().st_size  # far smaller

    legacy = pipeline(tmp_path, "legacy", exports["legacy"])
    resampled = pipeline(tmp_path, "resampled", exports["events"], "--char-events", "expand", "--resample", "50")
    raw = pipeline(tmp_path, "raw", exports["events"], "--char-events", "expand")
    both_auto = pipeline(tmp_path, "both_auto", exports["both"])                     # auto → legacy rows
    both_expand = pipeline(tmp_path, "both_expand", exports["both"], "--char-events", "expand")

    assert len(legacy) > 100 and set(KEY + DURATIONS + BINARY) <= set(legacy.columns)
    # per-participant step-2 files: the answer is trial-level, so it is on every word of an
    # answered trial - skipped words (FPFix = 0) included - before step 3 ever runs
    per = pd.concat([pd.read_csv(p) for p in (tmp_path / "out_legacy" / "exp_0" / "reading_measures").glob("reader_*_reading_measures.csv")])
    answered = per.groupby(["cond_id", "para_nr"])["response_chosen"].transform(lambda s: s.notna().any())
    assert answered.any() and (per.loc[answered, "FPFix"] == 0).any()
    assert per.loc[answered, "response_chosen"].notna().all()
    # 1) resampling the events at the legacy interval reproduces the legacy pipeline exactly
    pd.testing.assert_frame_equal(legacy, resampled)
    pd.testing.assert_frame_equal(legacy, both_auto)
    pd.testing.assert_frame_equal(raw, both_expand)

    # 2) raw millisecond events: same words, durations within the 50 ms quantization noise
    m = legacy.merge(raw, on=KEY, suffixes=("_l", "_r"))
    assert len(m) == len(legacy) == len(raw)
    for c in DURATIONS:
        a, b = m[c + "_l"].fillna(0), m[c + "_r"].fillna(0)
        r = np.corrcoef(a, b)[0, 1]
        assert r > 0.9, f"{c}: r={r:.3f}"
        assert np.abs(a - b).mean() < 60, f"{c}: mean |diff| {np.abs(a - b).mean():.1f} ms"
    for c in BINARY:
        same = (m[c + "_l"].fillna(-1) == m[c + "_r"].fillna(-1)).mean()
        assert same > 0.9, f"{c}: identical for {same:.1%} of words"

    # 3) the character table is produced and consistent
    char = pd.read_csv(next((tmp_path / "res_raw").glob("char_events_exp_0_*.csv")))
    assert {"submission_id", "ItemId", "t", "kind", "word_idx", "char_idx", "char", "layout_id"} <= set(char.columns)
    n_trials = char.groupby(["submission_id", "ItemId"]).ngroups
    assert n_trials >= 20 and (char["kind"] == "e").sum() == n_trials                 # one end event per trial
    assert (char.loc[char["kind"] == "c", "char_idx"] >= 1).all()
