"""Cross-language checks: the Python decoder against JS-produced fixtures, the Python
Recorder re-encoding the JS scenarios byte-for-byte, and a Python-produced fixture for the
JS side (test/pyfixtures.test.js)."""
import random

import pytest

import motr_char_events as ce
from tests.util import check_fixture

JS_TO_PY_CHAR_COLS = {"wordIdx": "word_idx", "charIdx": "char_idx", "globalIdx": "global_idx", "layoutId": "layout_id"}
OPTS = {"recordRawTrace": "record_raw_trace", "tracePrecisionPx": "trace_precision_px", "maxEvents": "max_events", "maxTraceSamples": "max_trace_samples"}


def replay(sc):
    r = ce.Recorder(**{OPTS[k]: v for k, v in sc["options"].items()})
    r.start(sc["t0"], sc["words"], sc["table"], t0_response=sc["t0Response"], tsrc="event")
    for op in sc["ops"]:
        kind = op[0]
        if kind == "feed":
            r.feed(op[1], op[2], op[3], op[4] if len(op) > 4 else None)
        elif kind == "leave":
            r.leave(op[1])
        elif kind == "relayout":
            r.relayout(op[1], op[2])
        elif kind == "visibility":
            r.visibility(op[1], op[2])
        elif kind == "noteBatch":
            r.note_batch(op[1], op[2], op[3])
        elif kind == "end":
            r.end(op[1])
        else:
            raise AssertionError(kind)
    return r


def py_char_rows_to_js(rows):
    inv = {v: k for k, v in JS_TO_PY_CHAR_COLS.items()}
    return [{inv.get(k, k): v for k, v in r.items()} for r in rows]


def test_js_fixture_decodes(js_roundtrip):
    base = js_roundtrip["base"]
    assert len(js_roundtrip["scenarios"]) >= 4
    for sc in js_roundtrip["scenarios"]:
        fields, words = sc["fields"], sc["words"]
        assert ce.words_of(sc["text"]) == words
        assert ce.fake_table(words, char_w=8, line_chars=24) == sc["table"]
        d = ce.decode_row(fields)
        assert d["events"] == sc["eventList"]
        assert ce.expand_to_legacy_rows(fields, words, base) == sc["legacyRows"]
        assert py_char_rows_to_js(ce.char_table(fields, words)) == sc["charTable"]
        assert ce.resample(fields, words, 50, 0, base) == sc["resample50"]
        assert ce.resample(fields, words, 50, 17, base) == sc["resample50phase17"]


def test_python_recorder_matches_js_bytes(js_roundtrip):
    for sc in js_roundtrip["scenarios"]:
        r = replay(sc)
        assert r.event_list() == sc["eventList"]
        got = r.fields()
        for k in ce.MT_FIELDS:
            assert got[k] == sc["fields"][k], f"{sc['text']!r}: {k} differs"


def test_expanded_rows_satisfy_pipeline_needs(js_roundtrip):
    required = ["Index", "responseTime", "mousePositionX", "mousePositionY"]
    for sc in js_roundtrip["scenarios"]:
        rows = ce.expand_to_legacy_rows(sc["fields"], sc["words"], js_roundtrip["base"])
        assert rows and rows[-1]["Index"] == -1               # end marker closes the last word
        prev = -1
        for row in rows:
            for c in required:
                assert row[c] is not None
            int(float(row["responseTime"])); int(float(row["mousePositionX"])); int(float(row["mousePositionY"]))
            assert int(row["Index"]) >= -1
            assert row["responseTime"] >= prev
            prev = row["responseTime"]
            if row["Index"] >= 0:
                assert row["Word"] == sc["words"][row["Index"]]
                assert row["wordPositionLeft"] <= row["wordPositionRight"]


def test_decoder_errors(js_roundtrip):
    f = js_roundtrip["scenarios"][0]["fields"]
    words = js_roundtrip["scenarios"][0]["words"]
    with pytest.raises(ce.CharEventsError, match="unsupported"):
        ce.decode_row({**f, "mtFormat": "motr-ce/2"})
    with pytest.raises(ce.CharEventsError, match="unknown snapshot"):
        ce.expand_to_legacy_rows({**f, "mtEvents": "5l7;"}, words)
    with pytest.raises(ce.CharEventsError, match="out of range"):
        ce.expand_to_legacy_rows({**f, "mtEvents": "5c999;"}, words)
    with pytest.raises(ce.CharEventsError, match="ids must be"):
        ce.decode_row({**f, "mtLayout": f["mtLayout"] + "#" + f["mtLayout"]})
    with pytest.raises(ValueError):
        ce.resample(f, words, 0)


def random_ops(rnd, table, seconds, rate_hz, t0=1000.0, relayouts=0):
    B = table["block"]
    ops = []
    t, x, y = t0, (B[0] + B[2]) / 2, B[1] + 30
    n = int(seconds * rate_hz)
    relayout_at = {rnd.randint(1, n - 1) for _ in range(relayouts)}
    for i in range(n):
        t += (1000 / rate_hz) * (0.5 + rnd.random())
        x += (rnd.random() - 0.5) * 24
        y += (rnd.random() - 0.5) * 10
        if rnd.random() < 0.005:
            x = B[0] - 30 + rnd.random() * (B[2] - B[0] + 60)
            y = B[1] - 30 + rnd.random() * (B[3] - B[1] + 60)
        if rnd.random() < 0.002:
            ops.append(["leave", t])
        if i in relayout_at:
            dy = rnd.randint(-60, 60)
            shifted = {"block": [table["block"][0], table["block"][1] + dy, table["block"][2], table["block"][3] + dy],
                       "words": [{"rect": [w["rect"][0], w["rect"][1] + dy, w["rect"][2], w["rect"][3] + dy],
                                  "frags": [{"k0": f["k0"], "top": f["top"] + dy, "bottom": f["bottom"] + dy, "xs": list(f["xs"])} for f in w["frags"]]}
                                 for w in table["words"]]}
            ops.append(["relayout", t, shifted])
        ops.append(["feed", round(x, 2), round(y, 2), round(t, 3), "mouse"])
    ops.append(["end", t + 5])
    return ops


def test_python_fixture_for_js():
    """Python-encoded scenarios + Python-decoded expectations, verified by test/pyfixtures.test.js."""
    rnd = random.Random(4242)
    base = {"Experiment": "motr_template", "Condition": "b", "ItemId": "2"}
    cases = [
        ("The cat sat.", 0.4, 125, {}, 0),
        ("Der Reporter, der den Senator angriff, gab den Fehler zu.", 1.0, 1000, {}, 1),
        ("tiny", 0.3, 60, {"recordRawTrace": False, "maxEvents": 10}, 0),
    ]
    scenarios = []
    for text, seconds, rate, opts, relayouts in cases:
        words = ce.words_of(text)
        table = ce.fake_table(words, char_w=9, line_chars=20)
        ops = random_ops(rnd, table, seconds, rate, relayouts=relayouts)
        ops.insert(1, ["noteBatch", 3, True, 12.25])
        ops.insert(4, ["visibility", ops[3][3] if ops[3][0] == "feed" else ops[3][1], True])
        sc = {"text": text, "words": words, "table": table, "t0": 1000.0, "t0Response": 500.6, "options": opts, "ops": ops}
        r = replay(sc)
        fields = r.fields()
        sc.update({
            "fields": fields,
            "eventList": r.event_list(),
            "legacyRows": ce.expand_to_legacy_rows(fields, words, base),
            "charTable": py_char_rows_to_js(ce.char_table(fields, words)),
            "resample50": ce.resample(fields, words, 50, 0, base),
        })
        scenarios.append(sc)
    check_fixture("py_roundtrip.json", {"base": base, "scenarios": scenarios})
