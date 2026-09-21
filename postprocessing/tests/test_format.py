import random

import pytest

import motr_char_events as ce


SNAP = {
    "id": 0, "T": 0, "block": [100, 150, 900, 260],
    "words": [
        {"rect": [120, 180, 155, 201], "frags": [{"k0": 1, "top": 180, "bottom": 201, "xs": [120, 130, 140, 150, 155]}]},
        {"rect": [155, 180, 190, 201], "frags": [{"k0": 1, "top": 180, "bottom": 201, "xs": [155, 165, 175, 185, 190]}]},
        {"rect": [190, 180, 230, 201], "frags": [{"k0": 1, "top": 180, "bottom": 201, "xs": [190, 200, 210, 220, 230]}]},
    ],
}
SNAP_STR = (
    "l0@0 B100,150,900,260 W120,180,155,201 F1@180,201:120,130,140,150,155 "
    "W155,180,190,201 F1@180,201:155,165,175,185,190 W190,180,230,201 F1@180,201:190,200,210,220,230"
)


def test_format_id():
    assert ce.FORMAT_ID == "motr-ce/1"
    assert ce.parse_format_id("motr-ce/1") == ("motr-ce", 1)
    with pytest.raises(ce.CharEventsError, match="unsupported motr-ce major version 2"):
        ce.parse_format_id("motr-ce/2")
    with pytest.raises(ce.CharEventsError, match="unknown format id"):
        ce.parse_format_id("other/1")


@pytest.mark.parametrize("x,s", [
    (0, "0"), (-0.0, "0"), (0.04, "0"), (0.05, "0.1"), (0.1, "0.1"), (2.5, "2.5"), (-1.25, "-1.2"), (-1.26, "-1.3"),
    (120, "120"), (1e6, "1000000"), (-0.04, "0"), (-0.05, "0"), (-0.06, "-0.1"), (123.456, "123.5"), (999.95, "1000"),
])
def test_fmt_num(x, s):
    assert ce.fmt_num(x) == s


def test_fmt_num_roundtrip_and_errors():
    rnd = random.Random(7)
    for _ in range(5000):
        x = (rnd.random() - 0.5) * 4000
        s = ce.fmt_num(x)
        assert ce.fmt_num(ce.parse_num(s)) == s
        assert abs(ce.parse_num(s) - x) <= 0.05 + 1e-9
    with pytest.raises(ce.CharEventsError):
        ce.fmt_num(float("nan"))
    with pytest.raises(ce.CharEventsError):
        ce.parse_num("1.25")


def test_charset():
    ce.assert_charset("l0@0 B1,2,3,4 F1@1,2:3,4;#-_= motr-ce/1")
    for bad in ['a"b', "a\\b", "a|b", "a{b", "a\nb", "é"]:
        with pytest.raises(ce.CharEventsError, match="disallowed"):
            ce.assert_charset(bad)


def test_layout_roundtrip():
    assert ce.encode_snapshot(SNAP) == SNAP_STR
    assert ce.decode_snapshot(SNAP_STR) == SNAP
    two = [SNAP, {**SNAP, "id": 1, "T": 1234}]
    assert ce.decode_layout(ce.encode_layout(two)) == two


@pytest.mark.parametrize("s,msg", [
    ("", "empty layout"), ("x0@0 B1,2,3,4", "bad snapshot header"), ("l0@0", "without block rect"),
    ("l0@0 B1,2,3", "bad block rect"), ("l0@0 W1,2,3,4", "before block rect"),
    ("l0@0 B1,2,3,4 F1@1,2:3,4", "before any word"), ("l0@0 B1,2,3,4 W1,2,3,4 F1@1,2:3", ">= 2"),
    ("l0@0 B1,2,3,4 W1,2,3,4 F1@1:3,4", "bad fragment band"), ("l0@0 B1,2,3,4 Q1", "unexpected layout token"),
    ("l0@0 B1,2,3,4 B1,2,3,4", "duplicate block"),
])
def test_layout_errors(s, msg):
    with pytest.raises(ce.CharEventsError, match=msg):
        ce.decode_layout(s)


def test_events_roundtrip():
    evs = [
        {"dt": 812, "kind": "c", "num": 1}, {"dt": 48, "kind": "c", "num": 2}, {"dt": 0, "kind": "n"},
        {"dt": 510, "kind": "o"}, {"dt": 3, "kind": "l", "num": 1}, {"dt": 0, "kind": "c", "num": 7},
        {"dt": 1000000, "kind": "h"}, {"dt": 5, "kind": "s"}, {"dt": 1, "kind": "t"}, {"dt": 700, "kind": "e"},
    ]
    s = ce.encode_events(evs)
    assert s == "812c1;48c2;0n;510o;3l1;0c7;1000000h;5s;1t;700e;"
    dec = ce.decode_events(s)
    T = 0
    for e, d in zip(evs, dec):
        T += e["dt"]
        assert d == {"dt": e["dt"], "T": T, "kind": e["kind"], "num": e.get("num")}
    assert ce.decode_events("") == [] and ce.encode_events([]) == ""


@pytest.mark.parametrize("s,msg", [
    ("812c1", "must end with"), ("c1;", "bad event token"), ("12c;", "missing its number"),
    ("12n3;", "must not carry"), ("12q;", "unknown event kind"), ("-1c1;", "bad event token"), ("1c1;;", "bad event token"),
])
def test_events_errors(s, msg):
    with pytest.raises(ce.CharEventsError, match=msg):
        ce.decode_events(s)


def test_trace_roundtrip():
    samples = [(812, 121, 190), (820, 123, 191), (828, 126, 191)]
    s = ce.encode_trace(samples)
    assert s == "4yByH8LQECQGA"
    assert ce.decode_trace(s) == [{"T": T, "x": X, "y": Y} for T, X, Y in samples]
    assert ce.decode_trace(s, 2) == [{"T": T, "x": X * 2, "y": Y * 2} for T, X, Y in samples]
    assert ce.decode_trace("") == []
    with pytest.raises(ce.CharEventsError, match="bad trace"):
        ce.decode_trace("4")
    with pytest.raises(ce.CharEventsError, match="multiple of 3"):
        ce.decode_trace("AB")
    with pytest.raises(ce.CharEventsError, match="backwards"):
        ce.decode_trace(ce.encode_trace([(5, 0, 0), (2, 0, 0)]))


def test_stats_roundtrip():
    st = {"v": 1, "t0": 1043, "tsrc": "event", "n": 3, "ne": 8, "trunc": False, "coal": True, "px": 1, "mindt": 7.8, "hmax": 41, "ptypes": "mouse.pen"}
    s = ce.encode_stats(st)
    assert s == "v=1 t0=1043 tsrc=event n=3 ne=8 trunc=0 coal=1 px=1 mindt=7.8 hmax=41 ptypes=mouse.pen"
    assert ce.decode_stats(s) == {**st, "trunc": 0, "coal": 1}
    assert ce.decode_stats("") == {}
    with pytest.raises(ce.CharEventsError):
        ce.encode_stats({"bad key": 1})
    with pytest.raises(ce.CharEventsError):
        ce.decode_stats("k")
