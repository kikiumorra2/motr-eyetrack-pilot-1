"""
motr-ce/1 character-event payloads: decoder (and a mirror encoder) for the
Mouse-Tracking-for-Reading template.

In ``samplingMode: "events"`` the browser stores one row per trial with the string fields
``mtFormat, mtLayout, mtEvents, mtTrace, mtStats`` (see src/charEvents/FORMAT.md) instead
of one row per 50 ms sample. This module

* parses those fields (``decode_row``),
* expands them into the legacy per-sample rows the rest of the pipeline reads
  (``expand_to_legacy_rows``; optionally ``resample`` to a fixed interval),
* produces a character-level table (``char_table``),
* rewrites a whole submission (``expand_submission``) for 1_fetch_and_flatten.py,
* and contains a ``Recorder`` that mirrors the browser encoder byte-for-byte, used by
  scripts/simulate_results.py and by the cross-language tests.

Everything mirrors src/charEvents/{vlq,format,layout,recorder,decoder}.js one-to-one;
keep the two in sync (test/fixtures/*.json pins them together).

CLI (debug helper):  python motr_char_events.py --check rows.json
    rows.json = the JSON array of rows of one trial/experiment as printed by the
    browser in debug mode; compares the charEvents row against any legacy rows.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

FORMAT_NAME = "motr-ce"
FORMAT_MAJOR = 1
FORMAT_ID = f"{FORMAT_NAME}/{FORMAT_MAJOR}"

CHARSET_RE = re.compile(r"^[0-9A-Za-z .,:;@#_=/-]*$")
KINDS_WITH_NUM = {"c", "l"}
KINDS_WITHOUT_NUM = {"n", "o", "h", "s", "e", "t"}

OUT = -2
NONE = -1
LOOK_ABOVE_PX = 3

MT_FIELDS = ("mtFormat", "mtLayout", "mtEvents", "mtTrace", "mtStats")
# Row-specific fields that must never be copied from a dropped row onto another row.
_ROW_FIELDS = set(MT_FIELDS) | {
    "TrialType", "TrialText", "responseTime", "Index", "Word", "charIndex",
    "mousePositionX", "mousePositionY",
    "wordPositionTop", "wordPositionLeft", "wordPositionBottom", "wordPositionRight",
}


class CharEventsError(ValueError):
    """Malformed or unsupported motr-ce payload."""


# ---------------------------------------------------------------------------
# VLQ (vlq.js)

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_CODE = {c: i for i, c in enumerate(ALPHABET)}


def zigzag(v: int) -> int:
    return v * 2 if v >= 0 else -v * 2 - 1


def unzigzag(z: int) -> int:
    return z // 2 if z % 2 == 0 else -(z + 1) // 2


def vlq_encode(ints: Iterable[int]) -> str:
    out = []
    for v in ints:
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError(f"not an integer: {v!r}")
        if not (-(2 ** 52) <= v <= 2 ** 52 - 1):  # zigzag(v) must stay a JS safe integer
            raise ValueError(f"magnitude too large for VLQ: {v}")
        z = zigzag(v)
        while True:
            chunk = z % 32
            z //= 32
            if z > 0:
                chunk += 32
            out.append(ALPHABET[chunk])
            if z == 0:
                break
    return "".join(out)


def vlq_decode(s: str) -> list[int]:
    out: list[int] = []
    value = 0
    mult = 1
    is_open = False
    for i, ch in enumerate(s):
        chunk = _CODE.get(ch)
        if chunk is None:
            raise CharEventsError(f"invalid VLQ character {ch!r} at {i}")
        value += (chunk & 31) * mult
        if chunk & 32:
            mult *= 32
            is_open = True
        else:
            out.append(unzigzag(value))
            value = 0
            mult = 1
            is_open = False
    if is_open:
        raise CharEventsError("truncated VLQ string (dangling continuation)")
    return out


# ---------------------------------------------------------------------------
# Numbers and charset (format.js)

def fmt_num(x: float) -> str:
    if not math.isfinite(x):
        raise CharEventsError(f"non-finite number {x}")
    t = math.floor(x * 10 + 0.5)
    if t == 0:
        return "0"
    neg = t < 0
    if neg:
        t = -t
    ip, fp = divmod(t, 10)
    return ("-" if neg else "") + str(ip) + (f".{fp}" if fp else "")


_NUM_RE = re.compile(r"^-?\d+(\.\d)?$")
_INT_RE = re.compile(r"^\d+$")


def parse_num(s: str, what: str = "number") -> float:
    if not _NUM_RE.match(s):
        raise CharEventsError(f"bad {what} {s!r}")
    return int(s) if "." not in s else float(s)


def assert_charset(s: Any, what: str = "field") -> str:
    if not isinstance(s, str):
        raise CharEventsError(f"{what} is not a string")
    if not CHARSET_RE.match(s):
        bad = re.search(r"[^0-9A-Za-z .,:;@#_=/-]", s).group(0)
        raise CharEventsError(f"{what} contains disallowed character {bad!r}")
    return s


def parse_format_id(s: Any) -> tuple[str, int]:
    m = re.match(r"^([a-z-]+)/(\d+)$", str(s))
    if not m or m.group(1) != FORMAT_NAME:
        raise CharEventsError(f"unknown format id {s!r}")
    major = int(m.group(2))
    if major != FORMAT_MAJOR:
        raise CharEventsError(
            f"unsupported {FORMAT_NAME} major version {major} (this decoder handles {FORMAT_MAJOR})"
        )
    return m.group(1), major


def _fmt_rect(r) -> str:
    if len(r) != 4:
        raise CharEventsError("rect must be [l,t,r,b]")
    return ",".join(fmt_num(v) for v in r)


def _parse_rect(s: str, what: str) -> list[float]:
    parts = s.split(",")
    if len(parts) != 4:
        raise CharEventsError(f"bad {what} {s!r}")
    return [parse_num(p, what) for p in parts]


# ---------------------------------------------------------------------------
# Layout snapshots (format.js)
#   snapshot = {"id", "T", "block": [l,t,r,b], "words": [{"rect": [...], "frags": [{"k0","top","bottom","xs"}]}]}

def encode_snapshot(snap: dict) -> str:
    parts = [f"l{snap['id']}@{snap['T']}", "B" + _fmt_rect(snap["block"])]
    for w in snap["words"]:
        parts.append("W" + _fmt_rect(w["rect"]))
        for f in w.get("frags", []):
            if len(f["xs"]) < 2:
                raise CharEventsError("fragment needs >= 2 x boundaries")
            parts.append(
                f"F{f['k0']}@{fmt_num(f['top'])},{fmt_num(f['bottom'])}:" + ",".join(fmt_num(x) for x in f["xs"])
            )
    return " ".join(parts)


def decode_snapshot(s: str) -> dict:
    toks = s.split(" ")
    head = re.match(r"^l(\d+)@(\d+)$", toks[0] if toks else "")
    if not head:
        raise CharEventsError(f"bad snapshot header {toks[0]!r}")
    snap: dict = {"id": int(head.group(1)), "T": int(head.group(2)), "block": None, "words": []}
    word = None
    for tok in toks[1:]:
        tag, body = tok[:1], tok[1:]
        if tag == "B":
            if snap["block"] is not None:
                raise CharEventsError("duplicate block rect")
            snap["block"] = _parse_rect(body, "block rect")
        elif tag == "W":
            if snap["block"] is None:
                raise CharEventsError("word rect before block rect")
            word = {"rect": _parse_rect(body, "word rect"), "frags": []}
            snap["words"].append(word)
        elif tag == "F":
            if word is None:
                raise CharEventsError("fragment before any word")
            m = re.match(r"^(\d+)@([^:]+):(.+)$", body)
            if not m:
                raise CharEventsError(f"bad fragment {tok!r}")
            band = m.group(2).split(",")
            if len(band) != 2:
                raise CharEventsError(f"bad fragment band {tok!r}")
            xs = [parse_num(p, "fragment x") for p in m.group(3).split(",")]
            if len(xs) < 2:
                raise CharEventsError(f"fragment needs >= 2 x boundaries {tok!r}")
            word["frags"].append(
                {"k0": int(m.group(1)), "top": parse_num(band[0], "fragment top"),
                 "bottom": parse_num(band[1], "fragment bottom"), "xs": xs}
            )
        else:
            raise CharEventsError(f"unexpected layout token {tok!r}")
    if snap["block"] is None:
        raise CharEventsError("snapshot without block rect")
    return snap


def encode_layout(snapshots: list[dict]) -> str:
    return "#".join(encode_snapshot(s) for s in snapshots)


def decode_layout(s: str) -> list[dict]:
    if s == "":
        raise CharEventsError("empty layout")
    return [decode_snapshot(part) for part in s.split("#")]


# ---------------------------------------------------------------------------
# Events (format.js): ( dt kind [num] ';' )*

def encode_events(events: list[dict]) -> str:
    out = []
    for ev in events:
        dt, kind, num = ev["dt"], ev["kind"], ev.get("num")
        if not isinstance(dt, int) or dt < 0:
            raise CharEventsError(f"bad dt {dt!r}")
        if kind in KINDS_WITH_NUM:
            if not isinstance(num, int) or num < 0:
                raise CharEventsError(f"kind {kind} needs a non-negative integer")
            out.append(f"{dt}{kind}{num};")
        elif kind in KINDS_WITHOUT_NUM:
            out.append(f"{dt}{kind};")
        else:
            raise CharEventsError(f"unknown event kind {kind!r}")
    return "".join(out)


_EVENT_RE = re.compile(r"^(\d+)([a-z])(\d*)$")


def decode_events(s: str) -> list[dict]:
    """→ [{"dt", "T", "kind", "num"}] with T cumulative since t0."""
    if s == "":
        return []
    if not s.endswith(";"):
        raise CharEventsError("events string must end with ';'")
    out = []
    T = 0
    for tok in s[:-1].split(";"):
        m = _EVENT_RE.match(tok)
        if not m:
            raise CharEventsError(f"bad event token {tok!r}")
        dt, kind, num = int(m.group(1)), m.group(2), m.group(3)
        T += dt
        if kind in KINDS_WITH_NUM:
            if num == "":
                raise CharEventsError(f"event {kind} is missing its number: {tok!r}")
            out.append({"dt": dt, "T": T, "kind": kind, "num": int(num)})
        elif kind in KINDS_WITHOUT_NUM:
            if num != "":
                raise CharEventsError(f"event {kind} must not carry a number: {tok!r}")
            out.append({"dt": dt, "T": T, "kind": kind, "num": None})
        else:
            raise CharEventsError(f"unknown event kind {kind!r}")
    return out


# ---------------------------------------------------------------------------
# Raw trace (format.js)

def encode_trace(samples: Iterable[tuple[int, int, int]]) -> str:
    ints = []
    pT = pX = pY = 0
    for T, X, Y in samples:
        ints.extend((T - pT, X - pX, Y - pY))
        pT, pX, pY = T, X, Y
    return vlq_encode(ints)


def decode_trace(s: str, px: float = 1) -> list[dict]:
    """→ [{"T", "x", "y"}], x/y scaled back by px."""
    if s == "":
        return []
    try:
        ints = vlq_decode(s)
    except CharEventsError as e:
        raise CharEventsError(f"bad trace: {e}") from None
    if len(ints) % 3:
        raise CharEventsError(f"trace length {len(ints)} is not a multiple of 3")
    out = []
    T = X = Y = 0
    for i in range(0, len(ints), 3):
        if ints[i] < 0:
            raise CharEventsError(f"trace time goes backwards at sample {i // 3}")
        T += ints[i]
        X += ints[i + 1]
        Y += ints[i + 2]
        out.append({"T": T, "x": X * px, "y": Y * px})
    return out


# ---------------------------------------------------------------------------
# Stats (format.js)

_STAT_KEY_RE = re.compile(r"^[a-z][a-z0-9]*$")
_STAT_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.]*$")


def encode_stats(stats: dict) -> str:
    parts = []
    for k, v in stats.items():
        if not _STAT_KEY_RE.match(k):
            raise CharEventsError(f"bad stats key {k!r}")
        if isinstance(v, bool):
            sv = "1" if v else "0"
        elif isinstance(v, (int, float)):
            sv = fmt_num(v)
        elif isinstance(v, str) and _STAT_WORD_RE.match(v):
            sv = v
        else:
            raise CharEventsError(f"bad stats value for {k}: {v!r}")
        parts.append(f"{k}={sv}")
    return " ".join(parts)


def decode_stats(s: str) -> dict:
    out: dict = {}
    if s == "":
        return out
    for part in s.split(" "):
        eq = part.find("=")
        if eq <= 0:
            raise CharEventsError(f"bad stats entry {part!r}")
        k, v = part[:eq], part[eq + 1:]
        if not _STAT_KEY_RE.match(k):
            raise CharEventsError(f"bad stats key {k!r}")
        if _NUM_RE.match(v):
            out[k] = parse_num(v)
        elif _STAT_WORD_RE.match(v):
            out[k] = v
        else:
            raise CharEventsError(f"bad stats value {part!r}")
    return out


# ---------------------------------------------------------------------------
# Layout / hit test (layout.js)

def words_of(text: str) -> list[str]:
    """Split exactly like the reading screen: JS text.split(/\\s+/)."""
    return re.split(r"\s+", str(text))


def word_length(word: str) -> int:
    return len(word)  # code points, like Array.from(word).length


def span_offsets(words: list[str]) -> list[int]:
    offsets = []
    off = 0
    for w in words:
        offsets.append(off)
        off += word_length(w) + 2
    offsets.append(off)
    return offsets


def global_index(offsets: list[int], i: int, k: int) -> int:
    return offsets[i] + k


def word_of_global(offsets: list[int], g: int) -> tuple[int, int]:
    n = len(offsets) - 1
    if not isinstance(g, int) or g < 0 or g >= offsets[n]:
        raise CharEventsError(f"global index {g} out of range")
    i = bisect.bisect_right(offsets, g, 0, n) - 1
    return i, g - offsets[i]


def char_at(word: str, k: int) -> str:
    if k == 0 or k == len(word) + 1:
        return " "
    return word[k - 1]


def char_box(table: dict, offsets: list[int], g: int):
    i, k = word_of_global(offsets, g)
    if i >= len(table["words"]):
        return None
    for f in table["words"][i]["frags"]:
        j = k - f["k0"]
        if 0 <= j < len(f["xs"]) - 1:
            return [f["xs"][j], f["top"], f["xs"][j + 1], f["bottom"]]
    return None


@dataclass
class _Frag:
    i: int
    k0: int
    xs: list[float]
    left: float
    right: float


@dataclass
class _Band:
    top: float
    bottom: float
    frags: list[_Frag] = field(default_factory=list)
    lefts: list[float] = field(default_factory=list)


class HitIndex:
    """Search index over a layout table (buildIndex in layout.js)."""

    def __init__(self, table: dict):
        self.block = table["block"]
        bands: dict[tuple, _Band] = {}
        for i, w in enumerate(table["words"]):
            for f in w["frags"]:
                if len(f["xs"]) < 2:
                    continue
                key = (f["top"], f["bottom"])
                b = bands.get(key)
                if b is None:
                    b = bands[key] = _Band(f["top"], f["bottom"])
                b.frags.append(_Frag(i, f["k0"], f["xs"], f["xs"][0], f["xs"][-1]))
        self.bands = sorted(bands.values(), key=lambda b: (b.top, b.bottom))
        for b in self.bands:
            b.frags.sort(key=lambda fr: (fr.left, fr.i, fr.k0))
            b.lefts = [fr.left for fr in b.frags]

    def hit_char_ik(self, x: float, y: float):
        """1x1 px probe rule (see layout.js): box hit iff x+1 > l and x < r and y+1 > t and
        y < b; the right-most hit wins."""
        x1, y1 = x + 1, y + 1
        for band in self.bands:
            if y1 <= band.top:
                break
            if y >= band.bottom:
                continue
            fi = bisect.bisect_left(band.lefts, x1) - 1      # right-most fragment with left < x+1
            while fi >= 0:
                f = band.frags[fi]
                if x < f.right:
                    j = bisect.bisect_left(f.xs, x1) - 1     # right-most boundary < x+1
                    if j == len(f.xs) - 1:
                        j -= 1
                    if j >= 0:
                        return f.i, f.k0 + j
                if fi > 0 and band.lefts[fi - 1] < band.lefts[fi]:
                    break
                fi -= 1
        return None


def hit_state(index: HitIndex, offsets: list[int], x: float, y: float) -> int:
    B = index.block
    if not (x + 1 > B[0] and x < B[2] and y + 1 > B[1] and y < B[3]):
        return OUT
    ik = index.hit_char_ik(x, y)
    if ik is None:
        ik = index.hit_char_ik(x, y - LOOK_ABOVE_PX)
    if ik is None:
        return NONE
    return offsets[ik[0]] + ik[1]


def tables_equal(a: dict, b: dict, eps: float = 0.05) -> bool:
    def close(p, q):
        return abs(p - q) <= eps

    def rect_eq(p, q):
        return len(p) == 4 and len(q) == 4 and all(close(v, q[i]) for i, v in enumerate(p))

    if not rect_eq(a["block"], b["block"]) or len(a["words"]) != len(b["words"]):
        return False
    for wa, wb in zip(a["words"], b["words"]):
        if not rect_eq(wa["rect"], wb["rect"]) or len(wa["frags"]) != len(wb["frags"]):
            return False
        for fa, fb in zip(wa["frags"], wb["frags"]):
            if fa["k0"] != fb["k0"] or not close(fa["top"], fb["top"]) or not close(fa["bottom"], fb["bottom"]):
                return False
            if len(fa["xs"]) != len(fb["xs"]) or any(not close(p, q) for p, q in zip(fa["xs"], fb["xs"])):
                return False
    return True


# ---------------------------------------------------------------------------
# Recorder (recorder.js) — mirror of the browser encoder

class Recorder:
    def __init__(self, max_events=20000, max_trace_samples=120000, record_raw_trace=True, trace_precision_px=1):
        self.max_events = max_events
        self.max_trace_samples = max_trace_samples
        self.record_raw_trace = bool(record_raw_trace)
        self.px = trace_precision_px if trace_precision_px > 0 else 1
        self.started = False
        self.ended = False

    def start(self, t0: float, words: list[str], table: dict, t0_response: float = 0, tsrc: str = "event"):
        if self.started:
            raise RuntimeError("recorder already started")
        self.started = True
        self.t0 = t0
        self.t0_response = t0_response
        self.tsrc = tsrc
        self.words = words
        self.offsets = span_offsets(words)
        self.last_raw = t0
        self.last_feed_raw = None
        self.last_T = 0
        self.state = OUT
        self.last_point = None
        self.hidden = None
        self.snapshots: list[dict] = []
        self.events: list[dict] = []
        self.trace: list[tuple[int, int, int]] = []
        self.truncated = False
        self.dropped = 0
        self.trace_dropped = 0
        self.n_samples = 0
        self.batches = 0
        self.max_batch = 0
        self.coalesced = False
        self.min_dt = math.inf
        self.hmax = 0.0
        self.ptypes: set[str] = set()
        self.relayout_checks = 0
        self._add_snapshot(0, table)

    def _T(self, t: float) -> int:
        if not (t >= self.last_raw):  # also catches NaN
            t = self.last_raw
        self.last_raw = t
        return math.floor(t - self.t0 + 0.5)

    def _emit(self, T: int, kind: str, num=None):
        if self.ended:
            return
        if kind != "e":
            if self.truncated:
                self.dropped += 1
                return
            if len(self.events) >= self.max_events:
                self.truncated = True
                self.events.append({"dt": T - self.last_T, "kind": "t", "num": None})
                self.last_T = T
                self.dropped += 1
                return
        self.events.append({"dt": T - self.last_T, "kind": kind, "num": num})
        self.last_T = T

    def _set_state(self, T: int, state: int):
        if state == self.state:
            return
        self.state = state
        if state == OUT:
            self._emit(T, "o")
        elif state == NONE:
            self._emit(T, "n")
        else:
            self._emit(T, "c", state)

    def _add_snapshot(self, T: int, table: dict) -> int:
        sid = len(self.snapshots)
        self.snapshots.append({"id": sid, "T": T, "table": table})
        self.table = table
        self.index = HitIndex(table)
        return sid

    def feed(self, x: float, y: float, t: float, pointer_type: str | None = None):
        if not self.started or self.ended:
            return None
        T = self._T(t)
        if self.last_feed_raw is not None:
            d = self.last_raw - self.last_feed_raw
            if 0 < d < self.min_dt:
                self.min_dt = d
        self.last_feed_raw = self.last_raw
        self.n_samples += 1
        if pointer_type:
            self.ptypes.add(pointer_type)
        if self.record_raw_trace:
            if len(self.trace) < self.max_trace_samples:
                self.trace.append((T, math.floor(x / self.px + 0.5), math.floor(y / self.px + 0.5)))
            else:
                self.trace_dropped += 1
        state = hit_state(self.index, self.offsets, x, y)
        self.last_point = (x, y)
        self._set_state(T, state)
        return state

    def leave(self, t: float):
        if not self.started or self.ended:
            return
        self._set_state(self._T(t), OUT)

    def relayout(self, t: float, table: dict) -> bool:
        if not self.started or self.ended:
            return False
        self.relayout_checks += 1
        if tables_equal(self.table, table):
            return False
        T = self._T(t)
        sid = self._add_snapshot(T, table)
        self._emit(T, "l", sid)
        if self.last_point is not None:
            self._set_state(T, hit_state(self.index, self.offsets, *self.last_point))
        return True

    def visibility(self, t: float, hidden: bool):
        if not self.started or self.ended:
            return
        hidden = bool(hidden)
        if self.hidden == hidden:
            return
        self.hidden = hidden
        self._emit(self._T(t), "h" if hidden else "s")

    def note_batch(self, n_samples: int, coalesced_available: bool, handler_micros: float):
        self.batches += 1
        self.max_batch = max(self.max_batch, n_samples)
        if coalesced_available:
            self.coalesced = True
        self.hmax = max(self.hmax, handler_micros)

    def end(self, t: float):
        if not self.started or self.ended:
            return
        self._emit(self._T(t), "e")
        self.ended = True

    def event_list(self) -> list[dict]:
        out, T = [], 0
        for e in self.events:
            T += e["dt"]
            out.append({"dt": e["dt"], "T": T, "kind": e["kind"], "num": e["num"]})
        return out

    def stats(self) -> dict:
        return {
            "v": 1,
            "t0": math.floor(self.t0_response + 0.5),
            "tsrc": self.tsrc,
            "n": self.n_samples,
            "ne": len(self.events),
            "nl": len(self.snapshots),
            "nw": len(self.words),
            "trunc": 1 if self.truncated else 0,
            "drop": self.dropped,
            "tdrop": self.trace_dropped,
            "batches": self.batches,
            "coal": 1 if self.coalesced else 0,
            "maxb": self.max_batch,
            "px": self.px if self.record_raw_trace else 0,
            "mindt": 0 if self.min_dt == math.inf else math.floor(self.min_dt * 10 + 0.5) / 10,
            "hmax": math.floor(self.hmax + 0.5),
            "ptypes": ".".join(sorted(self.ptypes)) if self.ptypes else "none",
        }

    def fields(self) -> dict:
        fields = {
            "mtFormat": FORMAT_ID,
            "mtLayout": encode_layout(
                [{"id": s["id"], "T": s["T"], "block": s["table"]["block"], "words": s["table"]["words"]} for s in self.snapshots]
            ),
            "mtEvents": encode_events(self.events),
            "mtTrace": encode_trace(self.trace) if self.record_raw_trace else "",
            "mtStats": encode_stats(self.stats()),
        }
        for k, v in fields.items():
            assert_charset(v, k)
        return fields


# ---------------------------------------------------------------------------
# Decoding (decoder.js)

def decode_row(fields: dict) -> dict:
    parse_format_id(fields.get("mtFormat"))
    stats = decode_stats(fields.get("mtStats") or "")
    snapshots = decode_layout(fields.get("mtLayout") or "")
    events = decode_events(fields.get("mtEvents") or "")
    px = stats.get("px", 0)
    trace = decode_trace(fields.get("mtTrace") or "", px if px and px > 0 else 1)
    for i, s in enumerate(snapshots):
        if s["id"] != i:
            raise CharEventsError(f"snapshot ids must be 0..n-1 in order (got {s['id']} at {i})")
    return {"snapshots": snapshots, "events": events, "trace": trace, "stats": stats}


def _walk(decoded: dict, words: list[str]):
    snapshots, events, trace = decoded["snapshots"], decoded["events"], decoded["trace"]
    offsets = span_offsets(words)
    nw = len(words)
    snap = snapshots[0]
    ti = -1
    last_xy = None
    for ev in events:
        while ti + 1 < len(trace) and trace[ti + 1]["T"] <= ev["T"]:
            ti += 1
        if ti >= 0:
            last_xy = (trace[ti]["x"], trace[ti]["y"])
        info = None
        if ev["kind"] == "l":
            if ev["num"] >= len(snapshots):
                raise CharEventsError(f"event refers to unknown snapshot {ev['num']}")
            snap = snapshots[ev["num"]]
        elif ev["kind"] == "c":
            i, k = word_of_global(offsets, ev["num"])
            if i >= nw or i >= len(snap["words"]):
                raise CharEventsError(f"character {ev['num']} is outside the {nw} words")
            box = char_box(snap, offsets, ev["num"])
            if last_xy is None or ti < 0:
                r = box or snap["words"][i]["rect"]
                last_xy = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
            info = {"i": i, "k": k, "box": box, "char": char_at(words[i], k)}
        yield ev, snap, info, last_xy


def _legacy_row(base: dict, t0: int, T: int, index: int, xy) -> dict:
    row = dict(base)
    row.update({
        "responseTime": t0 + T,
        "Index": index,
        "mousePositionX": xy[0] if xy else None,
        "mousePositionY": xy[1] if xy else None,
    })
    return row


def _t0(decoded: dict) -> int:
    t0 = decoded["stats"].get("t0", 0)
    return int(t0)


def expand_to_legacy_rows(fields: dict, words: list[str], base: dict | None = None) -> list[dict]:
    """One legacy sample row per c/n event plus the Index=-1 end marker."""
    base = base or {}
    decoded = decode_row(fields)
    t0 = _t0(decoded)
    rows = []
    for ev, snap, info, xy in _walk(decoded, words):
        if ev["kind"] == "c":
            rect = snap["words"][info["i"]]["rect"]
            row = _legacy_row(base, t0, ev["T"], info["i"], xy)
            row.update({
                "Word": words[info["i"]],
                "wordPositionTop": rect[1], "wordPositionLeft": rect[0],
                "wordPositionBottom": rect[3], "wordPositionRight": rect[2],
                "charIndex": info["k"],
            })
            rows.append(row)
        elif ev["kind"] in ("n", "e"):
            rows.append(_legacy_row(base, t0, ev["T"], -1, xy))
    return rows


def char_table(fields: dict, words: list[str], base: dict | None = None) -> list[dict]:
    """One record per event with character detail."""
    base = base or {}
    decoded = decode_row(fields)
    t0 = _t0(decoded)
    out = []
    for ev, snap, info, xy in _walk(decoded, words):
        row = dict(base)
        row.update({
            "t": t0 + ev["T"], "T": ev["T"], "dt": ev["dt"], "kind": ev["kind"], "num": ev["num"],
            "word_idx": info["i"] if info else None,
            "char_idx": info["k"] if info else None,
            "char": info["char"] if info else None,
            "global_idx": ev["num"] if ev["kind"] == "c" else None,
            "layout_id": snap["id"],
            "x": xy[0] if xy else None,
            "y": xy[1] if xy else None,
        })
        out.append(row)
    return out


def resample(fields: dict, words: list[str], interval_ms: float, phase: float = 0, base: dict | None = None) -> list[dict]:
    """Legacy-style fixed-interval rows (see decoder.js resample)."""
    if not interval_ms > 0:
        raise ValueError("interval_ms must be > 0")
    base = base or {}
    decoded = decode_row(fields)
    t0 = _t0(decoded)
    steps = list(_walk(decoded, words))
    end = next((s for s in steps if s[0]["kind"] == "e"), None)
    T_end = end[0]["T"] if end else (steps[-1][0]["T"] if steps else 0)
    rows = []
    state, snap, info = OUT, decoded["snapshots"][0], None
    si, ti = 0, -1
    trace = decoded["trace"]
    T = phase
    while T <= T_end:
        while si < len(steps) and steps[si][0]["T"] <= T:
            ev, s_snap, s_info, _ = steps[si]
            si += 1
            if ev["kind"] == "c":
                state, info, snap = ev["num"], s_info, s_snap
            elif ev["kind"] == "n":
                state, snap = NONE, s_snap
            elif ev["kind"] == "o":
                state, snap = OUT, s_snap
            elif ev["kind"] == "l":
                snap = s_snap
        while ti + 1 < len(trace) and trace[ti + 1]["T"] <= T:
            ti += 1
        xy = (trace[ti]["x"], trace[ti]["y"]) if ti >= 0 else (steps[si - 1][3] if si > 0 else None)
        if state == OUT:
            T += interval_ms
            continue
        if state == NONE:
            rows.append(_legacy_row(base, t0, T, -1, xy))
            T += interval_ms
            continue
        rect = snap["words"][info["i"]]["rect"]
        row = _legacy_row(base, t0, T, info["i"], xy)
        row.update({
            "Word": words[info["i"]],
            "wordPositionTop": rect[1], "wordPositionLeft": rect[0],
            "wordPositionBottom": rect[3], "wordPositionRight": rect[2],
        })
        rows.append(row)
        T += interval_ms
    if end:
        rows.append(_legacy_row(base, t0, T_end, -1, end[3]))
    return rows


# ---------------------------------------------------------------------------
# Submission-level helpers for 1_fetch_and_flatten.py

MODES = ("auto", "expand", "ignore", "keep")


def _present(v) -> bool:
    return v is not None and v != "" and v != "NA" and not (isinstance(v, float) and math.isnan(v))


def is_char_events_row(row: dict) -> bool:
    return str(row.get("mtFormat") or "").startswith(FORMAT_NAME + "/") or row.get("TrialType") == "charEvents"


def is_legacy_sample_row(row: dict) -> bool:
    """A 20 Hz sample row (or the Index=-1 marker): has Index, is not a summary/survey row."""
    return _present(row.get("Index")) and not _present(row.get("TrialType")) and not is_char_events_row(row)


def expand_submission(rows: list[dict], mode: str = "auto", resample_ms: float | None = None):
    """
    Rewrite one submission's rows for the legacy pipeline.

    mode:  expand – replace charEvents rows by decoded sample rows, drop legacy sample rows
           ignore – drop charEvents rows, keep everything else
           keep   – leave rows untouched
           auto   – `ignore` if the submission also has legacy sample rows ("both" mode),
                    else `expand`
    resample_ms: with `expand`, emit fixed-interval rows instead of one row per event.

    Returns (rows_out, char_rows, warnings). char_rows (one per event, all modes) carry the
    trial's Experiment/Condition/ItemId plus TrialText-independent detail.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    compact = [r for r in rows if is_char_events_row(r)]
    has_legacy = any(is_legacy_sample_row(r) for r in rows)
    if mode == "auto":
        mode = "ignore" if has_legacy else "expand"
    drop_legacy = mode == "expand" and bool(compact)   # "both"-mode data: use the events
    char_rows: list[dict] = []
    warnings: list[str] = []
    out: list[dict] = []
    # The participant-level data (SubjectId, ListId, ...) sits on the FIRST row of a submission
    # only (magpie's flattenData / src/submit.js); when that row is dropped its fields carry
    # over to the next row.
    carry: dict = {}

    def emit(r: dict):
        if carry:
            for k, v in carry.items():
                if not _present(r.get(k)):
                    r[k] = v
            carry.clear()
        out.append(r)

    def drop(r: dict):
        for k, v in r.items():
            if k not in _ROW_FIELDS and _present(v) and k not in carry:
                carry[k] = v

    for row in rows:
        if not is_char_events_row(row):
            if drop_legacy and is_legacy_sample_row(row):
                drop(row)
                continue
            emit(dict(row))
            continue
        base = {k: row.get(k) for k in ("Experiment", "Condition", "ItemId")}
        label = f"trial {base['ItemId']}/{base['Condition']}"
        try:
            words = words_of(row.get("TrialText") or "")
            fields = {k: row.get(k) or "" for k in MT_FIELDS}
            decoded = decode_row(fields)
            if decoded["stats"].get("trunc"):
                warnings.append(f"{label}: events truncated (maxEvents reached, {decoded['stats'].get('drop', 0)} dropped)")
            char_rows.extend(char_table(fields, words, base))
            if mode == "keep":
                emit(dict(row))
            elif mode == "expand":
                passthrough = {k: v for k, v in row.items() if k not in _ROW_FIELDS}
                expanded = (resample(fields, words, resample_ms, 0, base) if resample_ms
                            else expand_to_legacy_rows(fields, words, base))
                if not expanded:
                    drop(row)
                for e in expanded:
                    merged = dict(passthrough)
                    merged.update(e)
                    emit(merged)
            else:  # ignore
                drop(row)
        except CharEventsError as e:
            warnings.append(f"{label}: cannot decode charEvents row ({e}); dropped")
            if mode == "keep":
                emit(dict(row))
            else:
                drop(row)
    return out, char_rows, warnings


# ---------------------------------------------------------------------------
# CLI: sanity check of browser output (debug mode)

def _check(rows: list[dict]) -> int:
    trials: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (str(r.get("ItemId")), str(r.get("Condition")))
        trials.setdefault(key, []).append(r)
    status = 0
    for key, trows in trials.items():
        compact = [r for r in trows if is_char_events_row(r)]
        legacy = [r for r in trows if is_legacy_sample_row(r)]
        if not compact:
            continue
        for row in compact:
            fields = {k: row.get(k) or "" for k in MT_FIELDS}
            words = words_of(row.get("TrialText") or "")
            try:
                d = decode_row(fields)
            except CharEventsError as e:
                print(f"trial {key}: DECODE ERROR: {e}")
                status = 1
                continue
            st = d["stats"]
            n_state = sum(1 for e in d["events"] if e["kind"] in ("c", "n", "o"))
            size = sum(len(fields[k]) for k in MT_FIELDS)
            print(f"trial {key}: {len(d['events'])} events ({n_state} state changes), {len(d['trace'])} trace samples, "
                  f"{len(d['snapshots'])} layout(s), payload {size} B; coalesced={st.get('coal')} maxb={st.get('maxb')} "
                  f"mindt={st.get('mindt')} ms hmax={st.get('hmax')} us tsrc={st.get('tsrc')} trunc={st.get('trunc')}")
            if legacy:
                # compare each legacy row's Index with the recorded state at that responseTime
                offsets = span_offsets(words)
                t0 = _t0(d)
                agree = total = 0
                for lr in legacy:
                    try:
                        rt = float(lr.get("responseTime"))
                        idx = int(float(lr.get("Index")))
                    except (TypeError, ValueError):
                        continue
                    T = rt - t0
                    state = OUT
                    for ev in d["events"]:
                        if ev["T"] > T:
                            break
                        if ev["kind"] == "c":
                            state = ev["num"]
                        elif ev["kind"] == "n":
                            state = NONE
                        elif ev["kind"] == "o":
                            state = OUT
                    if state == OUT:
                        continue
                    want = -1 if state == NONE else word_of_global(offsets, state)[0]
                    total += 1
                    agree += (want == idx)
                pct = 100 * agree / total if total else float("nan")
                print(f"trial {key}: legacy rows {len(legacy)}, compared {total}, Index agreement {pct:.1f}%")
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="ROWS.json", help="JSON array of rows (browser debug output) to decode and compare")
    args = ap.parse_args(argv)
    if args.check:
        with open(args.check, encoding="utf-8") as fh:
            rows = json.load(fh)
        if isinstance(rows, dict):
            rows = [rows]
        return _check(rows)
    ap.print_help()
    return 0



# ---------------------------------------------------------------------------
# Synthetic layout (mirror of test/sample-layout.js fakeTable) for simulation and tests

def fake_table(words: list[str], char_w=10, line_chars=60, line_h=40, glyph_h=21, left=120, top=180, block_pad=20) -> dict:
    """Monospace layout: `char_w` px per code point, one trailing space per word (omitted at
    line ends), wrapped after `line_chars` characters; leading spaces are zero-width."""
    table: dict = {"block": None, "words": []}
    line = col = max_col = 0
    for w in words:
        n = word_length(w)
        if col > 0 and col + n > line_chars:
            line += 1
            col = 0
        x0 = left + col * char_w
        t = top + line * line_h
        xs = [x0 + j * char_w for j in range(n + 1)]
        col += n
        if col < line_chars:
            xs.append(x0 + (n + 1) * char_w)
            col += 1
        max_col = max(max_col, col)
        table["words"].append({"rect": [x0, t, xs[-1], t + glyph_h], "frags": [{"k0": 1, "top": t, "bottom": t + glyph_h, "xs": xs}]})
    right = left + max_col * char_w
    table["block"] = [left - block_pad, top - block_pad, right + block_pad, top + line * line_h + glyph_h + block_pad]
    return table


if __name__ == "__main__":
    sys.exit(main())
