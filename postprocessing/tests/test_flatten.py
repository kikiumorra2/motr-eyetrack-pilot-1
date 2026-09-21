"""expand_submission and 1_fetch_and_flatten.flatten_all on synthetic submissions."""
import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import motr_char_events as ce

spec = importlib.util.spec_from_file_location("fetch_and_flatten", Path(__file__).resolve().parents[1] / "1_fetch_and_flatten.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)

TEXT = "The reporter that attacked the senator admitted the error."
WORDS = ce.words_of(TEXT)
BASE = {"Experiment": "motr_template", "Condition": "obj_rc", "ItemId": "3"}


def char_events_row(seed=1, **opts):
    rnd = random.Random(seed)
    table = ce.fake_table(WORDS, char_w=10, line_chars=40)
    r = ce.Recorder(**opts)
    r.start(1000.0, WORDS, table, t0_response=800)
    B = table["block"]
    t, x, y = 1000.0, B[0] + 30, B[1] + 30
    for _ in range(300):
        t += 8 * (0.5 + rnd.random())
        x += rnd.random() * 6 - 1
        y += rnd.random() * 2 - 1
        if x > B[2]:
            x, y = B[0] + 25, y + 40
        r.feed(x, y, t, "mouse")
    r.end(t + 10)
    row = {**BASE, "TrialType": "charEvents", "TrialText": TEXT, "responseTime": 3400, **r.fields()}
    return row


def legacy_rows(n=5):
    rows = [{**BASE, "Index": i % 3, "Word": WORDS[i % 3], "responseTime": 500 + 50 * i,
             "mousePositionX": 100 + i, "mousePositionY": 200} for i in range(n)]
    rows.append({**BASE, "Index": -1, "responseTime": 500 + 50 * n, "mousePositionX": 100, "mousePositionY": 200})
    return rows


SUMMARY = {**BASE, "TrialId": 0, "TrialType": "trial", "TrialText": TEXT, "userResponse": "Yes", "readingTime": 3000, "responseTime": 3500}
SURVEY = {"Experiment": "motr_template", "TrialType": "survey", "device": "Computer Mouse", "responseTime": 9000}


def test_row_classification():
    assert ce.is_char_events_row(char_events_row())
    assert not ce.is_char_events_row(SUMMARY)
    assert ce.is_legacy_sample_row(legacy_rows()[0])
    assert ce.is_legacy_sample_row(legacy_rows()[-1])          # Index=-1 marker
    assert not ce.is_legacy_sample_row(SUMMARY)
    assert not ce.is_legacy_sample_row(SURVEY)
    assert not ce.is_legacy_sample_row({**BASE, "Index": "NA", "TrialType": "NA"})
    assert not ce.is_legacy_sample_row({**BASE, "Index": "", "TrialType": ""})


@pytest.mark.parametrize("mode", ce.MODES)
def test_identity_on_legacy_only_submissions(mode):
    rows = legacy_rows() + [SUMMARY, SURVEY]
    out, char_rows, warns = ce.expand_submission(rows, mode)
    assert out == rows and char_rows == [] and warns == []


def test_expand_replaces_compact_row():
    compact = char_events_row()
    rows = [compact, SUMMARY, SURVEY]
    out, char_rows, warns = ce.expand_submission(rows, "expand")
    assert warns == []
    assert not any(ce.is_char_events_row(r) for r in out)
    samples = [r for r in out if ce.is_legacy_sample_row(r)]
    assert len(samples) > 10 and samples[-1]["Index"] == -1
    assert out[-2] == SUMMARY and out[-1] == SURVEY
    assert out.index(SUMMARY) == len(samples)                   # expanded rows precede the summary row
    for r in samples:
        assert r["Experiment"] == "motr_template" and r["ItemId"] == "3" and r["Condition"] == "obj_rc"
        assert "mtEvents" not in r and "TrialType" not in r and "TrialText" not in r
        assert r["responseTime"] >= 800
    assert len(char_rows) == len(ce.decode_row(compact)["events"])
    assert {r["kind"] for r in char_rows} >= {"c", "e"}
    assert all(r["ItemId"] == "3" for r in char_rows)


def test_auto_prefers_legacy_when_both_present():
    compact = char_events_row()
    rows = legacy_rows() + [compact, SUMMARY]
    out, char_rows, _ = ce.expand_submission(rows, "auto")
    assert out == legacy_rows() + [SUMMARY]                     # compact row dropped, legacy kept
    assert len(char_rows) > 0                                   # char rows still collected
    out2, _, _ = ce.expand_submission(rows, "expand")
    assert not any(r in legacy_rows() for r in out2)            # explicit expand: legacy samples dropped
    assert any(ce.is_legacy_sample_row(r) for r in out2)
    out3, _, _ = ce.expand_submission(rows, "ignore")
    assert out3 == legacy_rows() + [SUMMARY]
    out4, _, _ = ce.expand_submission(rows, "keep")
    assert out4 == rows


def test_auto_expands_when_only_compact():
    rows = [char_events_row(), SUMMARY]
    out, _, _ = ce.expand_submission(rows, "auto")
    assert any(ce.is_legacy_sample_row(r) for r in out) and not any(ce.is_char_events_row(r) for r in out)


def test_resample_option():
    rows = [char_events_row(), SUMMARY]
    out, _, _ = ce.expand_submission(rows, "expand", resample_ms=50)
    samples = [r for r in out if ce.is_legacy_sample_row(r)]
    ts = [r["responseTime"] for r in samples[:-1]]
    assert all((t - 800) % 50 == 0 for t in ts)


def test_truncation_and_decode_errors_warn():
    rows = [char_events_row(max_events=5), SUMMARY]
    out, _, warns = ce.expand_submission(rows, "expand")
    assert any("truncated" in w for w in warns)
    bad = {**char_events_row(), "mtEvents": "garbage"}
    out, char_rows, warns = ce.expand_submission([bad, SUMMARY], "expand")
    assert out == [SUMMARY] and char_rows == [] and any("cannot decode" in w for w in warns)
    out, _, _ = ce.expand_submission([bad, SUMMARY], "keep")
    assert out == [bad, SUMMARY]                                # keep never drops


def test_flatten_all_on_fake_export():
    compact = char_events_row()
    sub1 = [{**compact, "SubjectId": "s1", "ListId": 1, "experiment_start_time": 1700000000000}, SUMMARY]
    sub2 = [{**legacy_rows()[0], "SubjectId": "s2", "ListId": 2, "experiment_start_time": 1700000001000}] + legacy_rows()[1:] + [SUMMARY]
    survey = [{**SURVEY, "SubjectId": "s1", "experiment_start_time": 1700000000000}]
    records = [{"id": 1, "results": json.dumps(sub1)}, {"id": 2, "results": json.dumps(sub2)}, {"id": 3, "results": json.dumps(survey)}]
    df, char_df, warns = ff.flatten_all(records, "auto")
    assert warns == []
    assert "mtEvents" not in df.columns
    s1 = df[df["SubjectId"] == "s1"]
    assert (s1["ListId"] == 1).all()                            # participant columns broadcast to expanded rows
    trial_rows = s1[s1["ItemId"].notna()]
    assert trial_rows["TrialType"].iloc[-1] == "trial"          # summary row last
    assert (trial_rows["TrialType"].iloc[:-1].isna()).all()     # expanded rows before it
    assert int(trial_rows["Index"].iloc[-2]) == -1              # end marker closes the trial
    assert (df[df["SubjectId"] == "s2"]["Index"].dropna().astype(int).tolist() == [0, 1, 2, 0, 1, -1])
    assert (df["TrialType"] == "survey").sum() == 1
    for col in ff.REQUIRED_COLS:
        assert col in df.columns
    assert len(char_df) > 0 and set(char_df["SubjectId"]) == {"s1"}
    assert list(char_df["submission_row_id"].unique()) == [1]
    # legacy-only behaves as before
    df2 = ff.flatten([{"id": 2, "results": json.dumps(sub2)}])
    assert len(df2) == len(sub2)


def test_participant_fields_carry_over_from_dropped_rows():
    # events mode: the charEvents row is the first row of the submission and carries SubjectId
    compact = {**char_events_row(), "SubjectId": "s1", "ListId": 1}
    out, _, _ = ce.expand_submission([compact, SUMMARY], "ignore")
    assert out == [{**SUMMARY, "SubjectId": "s1", "ListId": 1}]
    out, _, _ = ce.expand_submission([compact, SUMMARY], "expand")
    assert out[0]["SubjectId"] == "s1" and out[0]["ListId"] == 1 and "Index" in out[0]
    assert out[-1] == SUMMARY
    # both mode: the first row is a legacy sample; expand drops it but keeps SubjectId
    first = {**legacy_rows()[0], "SubjectId": "s7", "ListId": 2}
    rows = [first] + legacy_rows()[1:] + [char_events_row(), SUMMARY]
    out, _, _ = ce.expand_submission(rows, "expand")
    assert out[0]["SubjectId"] == "s7" and out[0]["ListId"] == 2
    assert out[0]["Word"] != first["Word"] or out[0]["responseTime"] != first["responseTime"]  # not the legacy row
    assert "Index" in out[0]
    # a broken compact first row: dropped, fields still carried
    bad = {**compact, "mtEvents": "garbage"}
    out, _, warns = ce.expand_submission([bad, SUMMARY], "auto")
    assert out == [{**SUMMARY, "SubjectId": "s1", "ListId": 1}] and warns
    # existing values on the next row are never overwritten
    out, _, _ = ce.expand_submission([compact, {**SUMMARY, "ListId": 9}], "ignore")
    assert out[0]["ListId"] == 9


def test_submissions_without_subjectid_are_reported():
    # magpie alone tags only the first row of ALL data, i.e. only a participant's first per-trial
    # submission carries SubjectId (src/submit.js adds it to every one). Such submissions cannot be
    # assigned to a participant: step 1 must say so loudly instead of silently dropping them.
    first = [{**legacy_rows()[0], "SubjectId": "s1", "ListId": 1, "experiment_start_time": 1}] + legacy_rows()[1:] + [SUMMARY]
    orphan = [{**r, "ItemId": "4", "SubjectId": None, "experiment_start_time": None} for r in legacy_rows() + [SUMMARY]]
    records = [{"id": 1, "results": json.dumps(first)}, {"id": 2, "results": json.dumps(orphan)}]
    df, _, warns = ff.flatten_all(records, "auto")
    assert len(warns) == 1 and "submission 2" in warns[0] and "no SubjectId" in warns[0] and "DROPPED" in warns[0]
    assert df["SubjectId"].isna().sum() == len(orphan)
    assert set(df.loc[df["SubjectId"] == "s1", "ItemId"]) == {"3"}
    # with the id on the first row (what src/submit.js guarantees) the submission is assigned to its participant
    fixed = [{**orphan[0], "SubjectId": "s1"}] + orphan[1:]
    df, _, warns = ff.flatten_all([records[0], {"id": 2, "results": json.dumps(fixed)}], "auto")
    assert warns == [] and df["SubjectId"].isna().sum() == 0 and set(df["ItemId"]) == {"3", "4"}


def test_read_csv_export_both_formats(tmp_path):
    """The classic magpie-backend table dump and the flattened magpie-serverless download must
    yield the same submissions and the same flat table."""
    import csv
    compact = {**char_events_row(), "SubjectId": "s1", "ListId": 1, "experiment_start_time": 1}
    subs = [[compact, SUMMARY], [{**legacy_rows()[0], "SubjectId": "s1", "ListId": 1, "experiment_start_time": 1}] + legacy_rows()[1:] + [{**SUMMARY, "ItemId": "4"}],
            [{**SURVEY, "SubjectId": "s1", "experiment_start_time": 1}]]
    classic = tmp_path / "classic.csv"
    with open(classic, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "inserted_at", "updated_at", "experiment_id", "results"])
        for i, s in enumerate(subs, 1):
            w.writerow([i, "x", "x", "0", json.dumps(s)])
        w.writerow([99, "x", "x", "1", json.dumps(subs[0])])                     # another experiment: filtered out
    cols = ["submission_id"] + sorted({k for s in subs for r in s for k in r})
    flat = tmp_path / "serverless.csv"
    with open(flat, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i, s in enumerate(subs, 1):
            for r in s:
                w.writerow({"submission_id": 1000 + i, **{k: ("" if v is None else v) for k, v in r.items()}})
    rec_c = ff.read_csv_export(classic, "0")
    rec_f = ff.read_csv_export(flat, "0")
    assert [len(ce.expand_submission(ff.parse_results_cell(r["results"]))[0]) for r in rec_c] == \
           [len(ce.expand_submission(ff.parse_results_cell(r["results"]))[0]) for r in rec_f]
    assert [r["id"] for r in rec_c] == ["1", "2", "3"] and [r["id"] for r in rec_f] == ["1001", "1002", "1003"]
    df_c, char_c, warns_c = ff.flatten_all(rec_c, "auto")
    df_f, char_f, warns_f = ff.flatten_all(rec_f, "auto")
    assert warns_c == warns_f == []
    assert len(df_c) == len(df_f) and len(char_c) == len(char_f) > 0
    # the classic path carries JSON numbers, the flattened one strings; both end up the same CSV
    def canon(df):
        out = df[["ItemId", "Index", "responseTime", "Word", "TrialType", "SubjectId"]].reset_index(drop=True).copy()
        for c in ("Index", "responseTime"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
        for c in ("ItemId", "Word", "TrialType", "SubjectId"):
            out[c] = out[c].astype("string")
        return out
    pd.testing.assert_frame_equal(canon(df_c), canon(df_f))
    assert df_f["submission_row_id"].dtype.kind in "iuf"                        # numeric sort key
    assert (df_f["SubjectId"] == "s1").all()


def test_flatten_ignore_and_keep():
    compact = {**char_events_row(), "SubjectId": "s1", "experiment_start_time": 1}
    records = [{"id": 1, "results": json.dumps([compact, SUMMARY])}]
    df, char_df, _ = ff.flatten_all(records, "ignore")
    assert len(df) == 1 and df["TrialType"].iloc[0] == "trial" and len(char_df) > 0
    df, _, _ = ff.flatten_all(records, "keep")
    assert len(df) == 2 and "mtEvents" in df.columns
