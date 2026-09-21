"""Reading measures: the worked example of READING_MEASURES.md §6 through the real step-2 code,
the invariants of §4.12, and the reference recomputation from the association files."""
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import check_reading_measures as crm

ROOT = Path(__file__).resolve().parents[2]
PP = ROOT / "postprocessing"
SENTENCE = "The senator that the reporter attacked resigned."

# READING_MEASURES.md §6: (Index, duration in ms) runs of 50 ms samples, in reading order.
SCANPATH = [(5, 200),                       # noise before reading: removed by _clear_noises_before_reading
            (0, 200), (1, 300), (2, 100), (3, 250), (4, 400), (1, 200), (2, 300), (3, 200), (4, 200),
            (5, 300), (-1, 200), (5, 200), (6, 350)]
EXPECTED = pd.DataFrame(
    [[0, 200, 200, 200, 200, 200, 200, 1, 0, 0, 0],
     [1, 300, 300, 300, 500, 300, 300, 1, 0, 1, 1],
     [2, 300, 0, 0, 300, 0, 0, 0, 0, 1, 0],
     [3, 250, 250, 250, 450, 250, 250, 1, 0, 1, 1],
     [4, 400, 400, 400, 600, 600, 1300, 1, 1, 0, 0],
     [5, 300, 300, 500, 500, 500, 500, 1, 0, 0, 0],
     [6, 350, 350, 350, 350, 350, 350, 1, 0, 0, 0]],
    columns=["word_nr", "first_duration", "gaze_duration", "first_pass_duration", "total_duration",
             "right_bounded_rt", "go_past_time", "FPFix", "FPReg", "RegIn_incl", "RegIn_excl"])


def sample_rows(scanpath, subject="p_01", item="7_a", cond="a", t0=1000, step=50):
    words = SENTENCE.split()
    base = {"submission_id": subject, "Experiment": "x", "Condition": cond, "ItemId": item, "mousePositionX": 300, "mousePositionY": 150}
    rows, t = [], t0
    for idx, dur in scanpath:
        for _ in range(dur // step):
            rows.append({**base, "Index": idx, "Word": words[idx] if idx >= 0 else "", "responseTime": t})
            t += step
    rows.append({**base, "Index": -1, "Word": "", "responseTime": t})                       # Done Reading marker
    rows.append({**base, "TrialType": "trial", "response": "Yes", "responseTime": t + 1500})  # summary row
    return rows


@pytest.fixture(scope="module")
def worked_example(tmp_path_factory):
    """Run 2_compute_reading_measures.py on the §6 scan-path; return (measures, associations)."""
    tmp = tmp_path_factory.mktemp("worked")
    flat = tmp / "flat.csv"
    pd.DataFrame(sample_rows(SCANPATH)).to_csv(flat, index=False)
    items = tmp / "items_processed.csv"
    pd.DataFrame([{"item_id": "7_a", "condition_id": "a", "text": SENTENCE}]).to_csv(items, index=False)
    out = tmp / "out"
    subprocess.run([sys.executable, str(PP / "2_compute_reading_measures.py"), "--experiment-id", "0", "--in-file", str(flat),
                    "--trial-file", str(items), "--out-dir", str(out)], check=True, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # the participant id contains underscores: the file name must keep it whole
    measures = pd.read_csv(out / "exp_0" / "reading_measures" / "reader_p_01_reading_measures.csv")
    assoc = pd.read_csv(out / "exp_0" / "associations" / "reader_p_01_clean.csv", dtype={"sbm_id": str, "para_nr": str})
    return measures, assoc


def test_worked_example_matches_the_documentation(worked_example):
    measures, assoc = worked_example
    got = measures.sort_values("word_nr")[EXPECTED.columns].reset_index(drop=True).astype(int)
    pd.testing.assert_frame_equal(got, EXPECTED)
    assert list(measures.sort_values("word_nr")["word"]) == SENTENCE.split()
    assert (measures["response_chosen"] == "Yes").all()                 # spread over skipped words too
    assert (measures["trial_num"] == 0).all()
    assert list(assoc["duration"]) == [200, 300, 250, 400, 200, 300, 200, 200, 300, 200, 350]   # 100 ms and -1 removed, noise popped


def test_worked_example_passes_invariants_and_reference(worked_example):
    measures, assoc = worked_example
    assert crm.invariant_violations(measures) == []
    m = measures.assign(submission_id="p_01")
    assert crm.compare_with_reference(m, assoc).empty


def test_reference_recomputation_equals_expected_table(worked_example):
    _, assoc = worked_example
    ref = crm.reference_measures(assoc).sort_values("word_nr")[EXPECTED.columns].reset_index(drop=True).astype(int)
    pd.testing.assert_frame_equal(ref, EXPECTED)


def _break(df, word, **values):
    d = df.copy()
    for k, v in values.items():
        d.loc[d["word_nr"] == word, k] = v
    return d


def test_invariants_catch_each_kind_of_corruption(worked_example):
    measures, _ = worked_example
    cases = {
        "first_duration <= total_duration": _break(measures, 0, first_duration=250),
        "gaze_duration in {0, first_duration}": _break(measures, 0, gaze_duration=150),
        "RegIn_incl = 1 <=> total_duration > right_bounded_rt": _break(measures, 1, RegIn_incl=0),
        "FPReg = 1 <=> go_past_time > right_bounded_rt": _break(measures, 4, FPReg=0),
        "RegIn_excl = RegIn_incl and FPFix": _break(measures, 2, RegIn_excl=1),
        "FPFix = 1 <=> gaze_duration > 0 <=> first_pass_duration > 0 <=> right_bounded_rt > 0 <=> go_past_time > 0": _break(measures, 5, FPFix=0),
        "first_duration = 0 or low_thres < first_duration < up_thres": _break(measures, 0, first_duration=150, gaze_duration=150, first_pass_duration=150, total_duration=150, right_bounded_rt=150, go_past_time=150),
        "response_chosen is constant within a trial": _break(measures, 3, response_chosen="No"),
        "word_nr is 0..n-1 exactly once within a trial": _break(measures, 3, word_nr=4),
        "binary columns are 0/1": _break(measures, 3, FPFix=2),
    }
    for rule, df in cases.items():
        assert any(r == rule for r, _ in crm.invariant_violations(df)), f"{rule!r} not detected"


def test_reference_comparison_catches_a_wrong_value(worked_example):
    measures, assoc = worked_example
    m = measures.assign(submission_id="p_01")
    diff = crm.compare_with_reference(_break(m, 4, go_past_time=1250), assoc)
    assert len(diff) == 1 and int(diff["word_nr"].iloc[0]) == 4 and int(diff["go_past_time_ref"].iloc[0]) == 1300


def test_cli(worked_example, tmp_path):
    measures, assoc = worked_example
    f = tmp_path / "m.csv"
    measures.assign(submission_id="p_01").to_csv(f, index=False)
    adir = tmp_path / "assoc"
    adir.mkdir()
    assoc.to_csv(adir / "reader_p_01_clean.csv", index=False)
    r = subprocess.run([sys.executable, str(PP / "check_reading_measures.py"), "--file", str(f), "--associations-dir", str(adir)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert r.returncode == 0 and "invariants: OK" in r.stdout and "every measure matches" in r.stdout, r.stdout
    _break(measures.assign(submission_id="p_01"), 0, first_duration=250).to_csv(f, index=False)
    r = subprocess.run([sys.executable, str(PP / "check_reading_measures.py"), "--file", str(f), "--associations-dir", str(adir)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert r.returncode == 1 and "INVARIANTS VIOLATED" in r.stdout and "DIFFERS" in r.stdout
