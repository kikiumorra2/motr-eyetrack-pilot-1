"""plot_char_events.py renders a trial from a CSV export and from a rows JSON."""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("plot_char_events", ROOT / "postprocessing" / "plot_char_events.py")
pce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pce)


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    out = tmp_path_factory.mktemp("plot") / "both.csv"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "simulate_results.py"), "--experiment-id", "0",
                    "--n-participants", "1", "--seed", "3", "--format", "both", "--out", str(out)],
                   check=True, cwd=ROOT, stdout=subprocess.PIPE)
    return out


def test_plot_from_csv(export, tmp_path):
    out = tmp_path / "trial.png"
    assert pce.main(["--csv", str(export), "--trial", "2", "--out", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 20_000


def test_plot_from_rows_json_and_selection(export, tmp_path):
    csv.field_size_limit(sys.maxsize)
    with open(export, newline="") as fh:
        recs = list(csv.DictReader(fh))
    rows = json.loads(recs[1]["results"])
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps(rows))
    item = next(r["ItemId"] for r in rows if r.get("TrialType") == "charEvents")
    out = tmp_path / "rows.png"
    assert pce.main(["--rows", str(rows_path), "--item", item, "--out", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 20_000
    # legacy rows of the same trial are found for the overlay
    row, legacy = pce.select_trial(pce.load_rows(rows_path, None), item=item)
    assert row["ItemId"] == item and len(legacy) > 5
    with pytest.raises(SystemExit):
        pce.select_trial(pce.load_rows(rows_path, None), item="no-such-item")


def test_single_row_without_trace(tmp_path):
    import motr_char_events as ce
    words = ce.words_of("The cat sat.")
    r = ce.Recorder(record_raw_trace=False)
    r.start(0.0, words, ce.fake_table(words), t0_response=100)
    for i, x in enumerate(range(118, 190, 3)):
        r.feed(x, 190, i * 9.0, "mouse")
    r.end(300)
    row = {"Experiment": "t", "Condition": "c", "ItemId": "1", "TrialType": "charEvents", "TrialText": "The cat sat.", **r.fields()}
    rows_path = tmp_path / "one.json"
    rows_path.write_text(json.dumps(row))          # a single row object, not an array
    out = tmp_path / "one.png"
    assert pce.main(["--rows", str(rows_path), "--out", str(out)]) == 0
    assert out.exists()
