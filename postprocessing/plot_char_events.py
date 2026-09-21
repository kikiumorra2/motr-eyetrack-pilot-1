#!/usr/bin/env python3
"""
Visualise one trial recorded in character-event mode (samplingMode "events" or "both").

Input (one of):
  --rows rows.json   JSON array of rows as the app prints them in debug mode. In the browser
                     console: copy(JSON.stringify(window.__motrRows)) and paste into rows.json.
                     A single charEvents row (e.g. the harness's out.row) also works.
  --csv export.csv   magpie export (serverless download or classic table dump) / scripts/simulate_results.py output.

Trial selection: --item ITEM [--condition COND] [--submission ID] or --trial K (K-th charEvents
row found, default 0); --list prints the available trials.

Panels:
  1. reconstructed scanpath: character under the pointer vs time since the first mouse
     movement (words as bands); gaps where
     the pointer was on no word / outside the text; layout / visibility markers; the legacy
     50 ms rows overlaid when the same trial also has them ("both" mode)
  2. the recorded layout: character boxes coloured by dwell time, raw pointer trace coloured
     by time, character-change points. The panel is framed on the text and its height follows
     from the text's aspect ratio (--fit block / all frame the recorded block / everything).
  3. dwell time per word
  4. sampling diagnostics: inter-sample intervals of the raw trace, event dts, stats

Usage:
  python postprocessing/plot_char_events.py --rows rows.json --out scanpath.png
  python postprocessing/plot_char_events.py --csv results/exp_0/simulated_export.csv --item 3 --condition obj_rc --show
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import motr_char_events as ce  # noqa: E402

STATE_KINDS = ("c", "n", "o", "e")


# ---------------------------------------------------------------------------
# input

def _parse_results_cell():
    spec = importlib.util.spec_from_file_location("fetch_and_flatten", HERE / "1_fetch_and_flatten.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_results_cell


def load_rows(rows_path: Path | None, csv_path: Path | None) -> list[dict]:
    if rows_path:
        with open(rows_path, encoding="utf-8") as fh:
            data = json.load(fh)
        rows = [data] if isinstance(data, dict) else list(data)
        for r in rows:
            r.setdefault("submission_row_id", 0)
        return rows
    parse = _parse_results_cell()
    rows = []
    csv.field_size_limit(sys.maxsize)          # a submission's `results` cell can exceed 128 KB
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "results" in (reader.fieldnames or []):
            # classic magpie-backend table: one line per submission, its rows as a JSON array
            for rec in reader:
                for r in parse(rec["results"]):
                    r["submission_row_id"] = rec.get("id")
                    rows.append(r)
        else:
            # magpie-serverless download: already one line per row, grouped by submission_id
            for rec in reader:
                r = dict(rec)
                r["submission_row_id"] = r.pop("submission_id", 0)
                rows.append(r)
    return rows


def _same_trial(a: dict, b: dict) -> bool:
    return (str(a.get("ItemId")) == str(b.get("ItemId")) and str(a.get("Condition")) == str(b.get("Condition"))
            and str(a.get("submission_row_id")) == str(b.get("submission_row_id")))


def select_trial(rows: list[dict], item=None, condition=None, submission=None, trial=0):
    compact = [r for r in rows if ce.is_char_events_row(r)]
    if item is not None:
        compact = [r for r in compact if str(r.get("ItemId")) == str(item)]
    if condition is not None:
        compact = [r for r in compact if str(r.get("Condition")) == str(condition)]
    if submission is not None:
        compact = [r for r in compact if str(r.get("submission_row_id")) == str(submission)]
    if not compact:
        sys.exit("no charEvents row matches (use --list to see what is available)")
    if trial >= len(compact):
        sys.exit(f"--trial {trial}: only {len(compact)} matching trials")
    row = compact[trial]
    legacy = [r for r in rows if ce.is_legacy_sample_row(r) and _same_trial(r, row)]
    return row, legacy


def list_trials(rows: list[dict]):
    for r in rows:
        if ce.is_char_events_row(r):
            try:
                st = ce.decode_stats(r.get("mtStats") or "")
                info = f"{st.get('ne', '?')} events, {st.get('n', '?')} samples, mindt {st.get('mindt', '?')} ms"
            except ce.CharEventsError as e:
                info = f"undecodable ({e})"
            print(f"submission {r.get('submission_row_id')}  item {r.get('ItemId')}  condition {r.get('Condition')}  "
                  f"subject {r.get('SubjectId', '?')}  {info}")


# ---------------------------------------------------------------------------
# analysis

def dwell_by_state(events: list[dict]):
    """(char dwell ms per global index, list of (T_start, T_end, kind, num) state runs)."""
    states = [e for e in events if e["kind"] in STATE_KINDS]
    runs, char_dwell = [], defaultdict(int)
    for cur, nxt in zip(states, states[1:]):
        runs.append((cur["T"], nxt["T"], cur["kind"], cur["num"]))
        if cur["kind"] == "c":
            char_dwell[cur["num"]] += nxt["T"] - cur["T"]
    return char_dwell, runs


def word_dwell(char_dwell: dict, offsets: list[int], n_words: int) -> np.ndarray:
    out = np.zeros(n_words)
    for g, ms in char_dwell.items():
        i, _ = ce.word_of_global(offsets, g)
        out[i] += ms
    return out


# ---------------------------------------------------------------------------
# plotting

# The figure is laid out in inches rather than with a fixed gridspec: the layout panel
# draws CSS pixels at aspect 1:1, so its height follows from the text it has to show —
# giving it a fixed share of a fixed-height figure either squashes the words to nothing
# or leaves a band of empty paper above and below them.
FIG_W = 15.0                                   # inches
M_L, M_R, M_T, M_B = 0.95, 0.5, 0.8, 1.4       # figure margins (bottom: rotated word labels)
H_SCAN, H_DIAG = 3.4, 2.5                      # scanpath / diagnostics row heights
GAP_SCAN, GAP_DIAG = 0.9, 0.75                 # gaps (x labels above, titles below)
CB_STRIP = 1.0                                 # colour bars + legend under the layout panel
MAX_LAYOUT_H = 6.5                             # inches; taller texts are scaled down
MAX_ZOOM = 3.2                                 # never magnify the text more than this (1 = 96 dpi CSS px)
MAX_CHAR_PT = 17.0                             # cap for the drawn characters
MIN_CHAR_PT = 3.0                              # below this a character is not worth drawing


def text_bbox(snap: dict) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of the characters themselves — not of the block they sit in."""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for w in snap["words"]:
        for f in w["frags"]:
            if len(f["xs"]) < 2:
                continue
            x0, x1 = min(x0, f["xs"][0]), max(x1, f["xs"][-1])
            y0, y1 = min(y0, f["top"]), max(y1, f["bottom"])
    if x0 == float("inf"):                                   # no fragments: use the word rects
        for w in snap["words"]:
            l, t, r, b = w["rect"]
            x0, y0, x1, y1 = min(x0, l), min(y0, t), max(x1, r), max(y1, b)
    if x0 == float("inf"):                                   # no words at all
        return snap["block"][0], snap["block"][1], snap["block"][2], snap["block"][3]
    return x0, y0, x1, y1


def view_box(fit: str, snap: dict, pts) -> tuple[float, float, float, float]:
    """Area the layout panel draws, as (x0, y0, x1, y1); `pts` are the trace/marker points.

    "text" (default) frames the characters and follows the pointer a short way out of them
    horizontally; the block is usually far wider and taller than the line(s) actually set in
    it, and framing that is what makes the words tiny. How far the frame follows the pointer
    *vertically* is decided by `panel_geometry`, where the vertical room is nearly free.
    """
    B = snap["block"]
    if fit == "block":
        return B[0] - 15, B[1] - 15, B[2] + 15, B[3] + 15
    tx0, ty0, tx1, ty1 = text_bbox(snap)
    padx = max(6.0, 0.02 * (tx1 - tx0))
    pady = max(6.0, 0.20 * (ty1 - ty0))
    box = [tx0 - padx, ty0 - pady, tx1 + padx, ty1 + pady]
    if not len(pts):
        return tuple(box)
    dx0, dy0 = float(np.min(pts[:, 0])), float(np.min(pts[:, 1]))
    dx1, dy1 = float(np.max(pts[:, 0])), float(np.max(pts[:, 1]))
    if fit == "all":
        return (min(box[0], dx0, B[0]) - 5, min(box[1], dy0, B[1]) - 5,
                max(box[2], dx1, B[2]) + 5, max(box[3], dy1, B[3]) + 5)
    slack_x = 0.175 * (box[2] - box[0])          # widening the frame shrinks the characters
    return (min(box[0], max(dx0, box[0] - slack_x)), box[1],
            max(box[2], min(dx1, box[2] + slack_x)), box[3])


def line_height(snap: dict) -> float:
    """Median height of a text fragment box, i.e. one line of the rendered paragraph."""
    hs = [f["bottom"] - f["top"] for w in snap["words"] for f in w["frags"]]
    return float(np.median(hs)) if hs else 20.0


def panel_geometry(fit: str, snap: dict, pts):
    """(view box, layout panel width, its height, figure height) — inches for the last three.

    The character size follows from panel width / view width, so vertical room is nearly free
    until the panel runs out of paper. In "text" fit the frame therefore follows the pointer
    up to one line above and below the text — enough for the hovering just under the line
    people read with, but not for the strokes that enter and leave the screen, which would
    stretch the panel into mostly empty paper (--fit all keeps those).
    """
    vbox = list(view_box(fit, snap, pts))
    avail = FIG_W - M_L - M_R
    w = min(avail, MAX_ZOOM * (vbox[2] - vbox[0]) / 96.0)
    if fit == "text" and len(pts):
        px_per_in = (vbox[2] - vbox[0]) / w
        room = max(0.0, MAX_LAYOUT_H - (vbox[3] - vbox[1]) / px_per_in) * px_per_in
        slack = min(line_height(snap), room / 2)
        vbox[3] += min(slack, max(0.0, float(np.max(pts[:, 1])) - vbox[3]))
        vbox[1] -= min(slack, max(0.0, vbox[1] - float(np.min(pts[:, 1]))))
    vw, vh = max(vbox[2] - vbox[0], 1e-6), max(vbox[3] - vbox[1], 1e-6)
    h = w * vh / vw
    if h > MAX_LAYOUT_H:
        w, h = w * MAX_LAYOUT_H / h, MAX_LAYOUT_H
    fig_h = M_T + H_SCAN + GAP_SCAN + h + CB_STRIP + GAP_DIAG + H_DIAG + M_B
    return tuple(vbox), w, h, fig_h


def plot_trial(row: dict, legacy: list[dict], out: Path | None, show: bool, dpi: int, layout_id: int | None,
               fit: str = "text"):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    from matplotlib.patches import Rectangle

    words = ce.words_of(row.get("TrialText") or "")
    fields = {k: row.get(k) or "" for k in ce.MT_FIELDS}
    dec = ce.decode_row(fields)
    events, trace, stats, snapshots = dec["events"], dec["trace"], dec["stats"], dec["snapshots"]
    table = ce.char_table(fields, words)
    offsets = ce.span_offsets(words)
    t0 = int(stats.get("t0", 0))
    T_end = events[-1]["T"] if events else 0
    # Times are shown relative to the first mouse movement (the first raw sample; without a
    # trace, the first recorded change), like the legacy readingTime, not to the moment the
    # screen appeared — participants often pause before they start moving.
    t_first = trace[0]["T"] if trace else (events[0]["T"] if events else 0)
    char_dwell, runs = dwell_by_state(events)
    wdwell = word_dwell(char_dwell, offsets, len(words))
    nbytes = sum(len(v) for v in fields.values())

    # snapshot to draw: the one active for most character events
    by_layout = defaultdict(int)
    for r in table:
        if r["kind"] == "c":
            by_layout[r["layout_id"]] += 1
    if layout_id is None:
        layout_id = max(by_layout, key=by_layout.get) if by_layout else 0
    snap = snapshots[layout_id]

    # ---- geometry: the layout panel sizes the figure -------------------------
    marks = [(p["x"], p["y"]) for p in trace]
    marks += [(r["x"], r["y"]) for r in table if r["kind"] == "c"]
    for r in legacy:
        try:
            marks.append((float(r["mousePositionX"]), float(r["mousePositionY"])))
        except (TypeError, ValueError, KeyError):
            pass
    marks = np.array(marks, dtype=float) if marks else np.empty((0, 2))
    vbox, lay_w, lay_h, fig_h = panel_geometry(fit, snap, marks)
    n_clipped = int(np.sum((marks[:, 0] < vbox[0]) | (marks[:, 0] > vbox[2]) |
                           (marks[:, 1] < vbox[1]) | (marks[:, 1] > vbox[3]))) if len(marks) else 0

    fig = plt.figure(figsize=(FIG_W, fig_h))

    def rect_in(x, y, w, h):                     # inches (y from the bottom) -> figure fractions
        return [x / FIG_W, y / fig_h, w / FIG_W, h / fig_h]

    avail = FIG_W - M_L - M_R
    lay_x = M_L + (avail - lay_w) / 2
    y_scan = fig_h - M_T - H_SCAN
    y_lay = y_scan - GAP_SCAN - lay_h
    col_gap = 0.95
    col_w = (avail - 2 * col_gap) / 3
    ax_time = fig.add_axes(rect_in(M_L, y_scan, avail, H_SCAN))
    ax_lay = fig.add_axes(rect_in(lay_x, y_lay, lay_w, lay_h))
    ax_word = fig.add_axes(rect_in(M_L, M_B, col_w, H_DIAG))
    ax_iv = fig.add_axes(rect_in(M_L + col_w + col_gap, M_B, col_w, H_DIAG))
    ax_dt = fig.add_axes(rect_in(M_L + 2 * (col_w + col_gap), M_B, col_w, H_DIAG))

    # ---- 1. scanpath timeline ------------------------------------------------
    sec = lambda T: (T - t_first) / 1000.0  # noqa: E731
    for i, w in enumerate(words):
        lo, hi = offsets[i], offsets[i + 1]
        ax_time.axhspan(lo, hi, color="0.93" if i % 2 else "0.98", lw=0)
    xs, ys = [], []
    for (a, b, kind, num) in runs:
        if kind == "c":
            xs += [sec(a), sec(b), np.nan]
            ys += [num + 0.5, num + 0.5, np.nan]
    ax_time.plot(xs, ys, color="C0", lw=1.6, solid_capstyle="butt", label="character under pointer")
    # vertical connectors between consecutive character runs
    cruns = [r for r in runs if r[2] == "c"]
    for (a, b, _, num), (a2, _, _, num2) in zip(cruns, cruns[1:]):
        if a2 == b:
            ax_time.plot([sec(b), sec(b)], [num + 0.5, num2 + 0.5], color="C0", lw=0.8, alpha=0.7)
    for (a, b, kind, _) in runs:
        if kind == "n":
            ax_time.axvspan(sec(a), sec(b), color="C1", alpha=0.18, lw=0)
        elif kind == "o":
            ax_time.axvspan(sec(a), sec(b), color="0.6", alpha=0.25, lw=0)
    hidden_since = None
    for e in events:
        if e["kind"] == "l":
            ax_time.axvline(sec(e["T"]), color="C3", ls="--", lw=1)
            ax_time.text(sec(e["T"]), offsets[-1], f" layout {e['num']}", color="C3", fontsize=8, va="top")
        elif e["kind"] == "h":
            hidden_since = e["T"]
        elif e["kind"] == "s" and hidden_since is not None:
            ax_time.axvspan(sec(hidden_since), sec(e["T"]), color="C4", alpha=0.2, lw=0)
            hidden_since = None
        elif e["kind"] == "t":
            ax_time.axvline(sec(e["T"]), color="red", lw=1.5)
            ax_time.text(sec(e["T"]), 0, " truncated", color="red", fontsize=8)
    ax_time.axvline(sec(T_end), color="k", lw=1)
    if legacy:
        lt, ly = [], []
        for r in legacy:
            try:
                idx, rt = int(float(r["Index"])), float(r["responseTime"])
            except (TypeError, ValueError, KeyError):
                continue
            lt.append(sec(rt - t0))
            ly.append(-1.5 if idx < 0 else offsets[idx] + (offsets[idx + 1] - offsets[idx]) / 2)
        ax_time.plot(lt, ly, "x", color="C2", ms=4, mew=1, alpha=0.8, label=f"legacy 50 ms rows (n={len(lt)})")
    ax_time.axhspan(-3, 0, color="C1", alpha=0.18, lw=0)
    ax_time.text(0.998, -1.5, "no word (n) ", fontsize=7, va="center", ha="right", transform=ax_time.get_yaxis_transform())
    ticks = [offsets[i] + (offsets[i + 1] - offsets[i]) / 2 for i in range(len(words))]
    step = max(1, len(words) // 30)
    ax_time.set_yticks(ticks[::step])
    ax_time.set_yticklabels(words[::step], fontsize=8)
    ax_time.set_ylim(-3, offsets[-1])
    ax_time.set_xlim(0, sec(T_end) * 1.02 if T_end > t_first else 1)
    ax_time.set_xlabel("time since first mouse movement (s)")
    ax_time.set_ylabel("word / character")
    ax_time.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax_time.set_title("Reconstructed scanpath (each step = the pointer moved onto another character; shading: no word / outside text)", fontsize=10)

    # ---- 2. layout with dwell heatmap and raw trace ---------------------------
    pt_per_px = lay_w * 72.0 / max(vbox[2] - vbox[0], 1e-6)   # points on paper per CSS pixel
    cw, ch = [], []
    for w in snap["words"]:
        for f in w["frags"]:
            cw += [f["xs"][j + 1] - f["xs"][j] for j in range(len(f["xs"]) - 1)]
            ch.append(f["bottom"] - f["top"])
    # An em is ~2x the average advance and ~0.75 of the line box; draw the characters at the
    # size the browser drew them, scaled by however much the panel magnifies the layout.
    em_px = min(2.0 * np.median(cw), 0.75 * np.median(ch)) if cw else 10.0
    char_pt = min(em_px * pt_per_px, MAX_CHAR_PT)

    B = snap["block"]
    ax_lay.add_patch(Rectangle((B[0], B[1]), B[2] - B[0], B[3] - B[1], fill=False, ec="0.7", lw=1, ls="--"))
    dmax = max(char_dwell.values()) if char_dwell else 1
    norm_d = Normalize(0, dmax)
    cmap_d = plt.get_cmap("YlOrRd")
    for i, w in enumerate(snap["words"]):
        l, t, r, b = w["rect"]
        ax_lay.add_patch(Rectangle((l, t), r - l, b - t, fill=False, ec="0.5", lw=0.6))
        for f in w["frags"]:
            for j in range(len(f["xs"]) - 1):
                g = offsets[i] + f["k0"] + j
                d = char_dwell.get(g, 0)
                x0, x1 = f["xs"][j], f["xs"][j + 1]
                ax_lay.add_patch(Rectangle((x0, f["top"]), x1 - x0, f["bottom"] - f["top"],
                                           fc=cmap_d(norm_d(d)) if d > 0 else "white", ec="0.85", lw=0.4))
                if char_pt >= MIN_CHAR_PT and (x1 - x0) * pt_per_px >= 2.0 and i < len(words):
                    ax_lay.text((x0 + x1) / 2, (f["top"] + f["bottom"]) / 2, ce.char_at(words[i], f["k0"] + j),
                                ha="center", va="center", fontsize=char_pt, color="0.25")
    if trace:
        pts = np.array([[p["x"], p["y"]] for p in trace])
        tt = np.array([p["T"] - t_first for p in trace])
        segs = np.stack([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(segs, cmap="viridis", norm=Normalize(0, max(T_end - t_first, 1)), lw=1.2, alpha=0.9)
        lc.set_array(tt[:-1])
        ax_lay.add_collection(lc)
    else:
        ax_lay.text(0.5, 0.02, "no raw trace recorded (positions synthesised from character boxes)",
                    transform=ax_lay.transAxes, ha="center", fontsize=8, color="0.4")
    cx = [r["x"] for r in table if r["kind"] == "c"]
    cy = [r["y"] for r in table if r["kind"] == "c"]
    ax_lay.plot(cx, cy, ".", color="k", ms=3, alpha=0.6, label=f"character changes (n={len(cx)})")
    if legacy:
        lx = [float(r["mousePositionX"]) for r in legacy if r.get("mousePositionX") not in (None, "", "NA")]
        lyy = [float(r["mousePositionY"]) for r in legacy if r.get("mousePositionY") not in (None, "", "NA")]
        ax_lay.plot(lx, lyy, "o", mfc="none", mec="C2", ms=5, mew=0.8, alpha=0.8, label="legacy 50 ms samples")
    ax_lay.set_xlim(vbox[0], vbox[2])
    ax_lay.set_ylim(vbox[3], vbox[1])
    ax_lay.set_aspect("equal", adjustable="box", anchor="C")
    ax_lay.set_xlabel("x (CSS px, viewport)", labelpad=2)
    ax_lay.set_ylabel("y (CSS px)")
    ax_lay.tick_params(labelsize=8)
    extra = f" — {len(snapshots)} layouts, showing #{layout_id}" if len(snapshots) > 1 else ""
    if n_clipped:
        extra += f" — {n_clipped} pointer position(s) outside the view (--fit all to include them)"
    ax_lay.set_title(f"Recorded layout, dwell per character and raw pointer trace{extra}", fontsize=10)

    # ---- colour bars and legend in the strip below the layout panel -----------
    # Both maps are laid out horizontally side by side: stacked vertically against the panel
    # their labels sit in each other's tick labels.
    bar_w = min(3.0, 0.30 * lay_w)
    bar_h, bar_y = 0.17, y_lay - 0.68
    ax_cb_d = fig.add_axes(rect_in(lay_x, bar_y, bar_w, bar_h))
    cb_d = fig.colorbar(plt.cm.ScalarMappable(norm=norm_d, cmap=cmap_d), cax=ax_cb_d, orientation="horizontal")
    cb_d.set_label("dwell per character (ms)", fontsize=9, labelpad=2)
    cb_d.ax.tick_params(labelsize=8)
    if trace:
        ax_cb_t = fig.add_axes(rect_in(lay_x + bar_w + 1.1, bar_y, bar_w, bar_h))
        cb_t = fig.colorbar(lc, cax=ax_cb_t, orientation="horizontal")
        cb_t.set_label("trace time since first movement (ms)", fontsize=9, labelpad=2)
        cb_t.ax.tick_params(labelsize=8)
    handles, labels = ax_lay.get_legend_handles_labels()
    if handles:
        # anchored to the page, not to the panel: a narrow panel would put the legend on top
        # of its own centred x label
        fig.legend(handles, labels, loc="upper right", fontsize=8, framealpha=0.9,
                   bbox_to_anchor=rect_in(M_L, y_lay - CB_STRIP, avail, CB_STRIP - 0.45),
                   bbox_transform=fig.transFigure)

    # ---- 3. word dwell --------------------------------------------------------
    ax_word.bar(range(len(words)), wdwell, color="C0")
    ax_word.set_xticks(range(len(words)))
    ax_word.set_xticklabels(words, rotation=90, fontsize=7)
    ax_word.set_ylabel("total dwell (ms)")
    ax_word.set_title("Dwell per word", fontsize=10)

    # ---- 4. diagnostics -------------------------------------------------------
    if len(trace) > 1:
        iv = np.diff([p["T"] for p in trace])
        iv = iv[iv > 0]
        ax_iv.hist(iv, bins=min(60, max(5, int(iv.max()))) if len(iv) else 10, color="C4")
        ax_iv.set_title(f"raw sampling intervals (median {np.median(iv):.0f} ms ≈ {1000 / max(np.median(iv), 1e-9):.0f} Hz)", fontsize=9)
    else:
        ax_iv.set_title("no raw trace", fontsize=9)
    ax_iv.set_xlabel("ms between pointer samples")
    dts = np.array([e["dt"] for e in events if e["kind"] == "c"])
    if len(dts):
        bins = np.logspace(0, np.log10(max(dts.max(), 2)), 40)
        ax_dt.hist(np.clip(dts, 1, None), bins=bins, color="C0")
        ax_dt.set_xscale("log")
    ax_dt.set_xlabel("ms between character changes (log)")
    ax_dt.set_title(f"character-change intervals (n={len(dts)}, median {np.median(dts) if len(dts) else 0:.0f} ms)", fontsize=9)

    info = (f"item {row.get('ItemId')} / {row.get('Condition')} — {len(words)} words · {stats.get('ne')} events · "
            f"{stats.get('n')} pointer samples · {len(snapshots)} layout(s) · {nbytes} bytes · "
            f"mindt {stats.get('mindt')} ms · coalesced {stats.get('coal')} · handler max {stats.get('hmax')} µs · "
            f"first movement after {t_first / 1000:.2f} s · reading {(T_end - t_first) / 1000:.2f} s"
            + ("  ⚠ TRUNCATED" if stats.get("trunc") else ""))
    fig.suptitle(info, fontsize=10, y=1 - 0.3 / fig_h)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        print(f"wrote {out}")
    if show:
        plt.show()
    plt.close(fig)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--rows", type=Path, help="JSON array of rows (browser debug output)")
    src.add_argument("--csv", type=Path, help="magpie export / simulated export CSV")
    ap.add_argument("--item", help="ItemId of the trial")
    ap.add_argument("--condition", help="Condition of the trial")
    ap.add_argument("--submission", help="submission id (CSV: the id column)")
    ap.add_argument("--trial", type=int, default=0, help="K-th matching charEvents row (default 0)")
    ap.add_argument("--layout", type=int, default=None, help="layout snapshot to draw (default: the most used)")
    ap.add_argument("--fit", choices=("text", "block", "all"), default="text",
                    help="what the layout panel frames: the text (default), the recorded text block, "
                         "or everything the pointer touched")
    ap.add_argument("--list", action="store_true", help="list the charEvents trials in the input and exit")
    ap.add_argument("--out", type=Path, default=None, help="PNG/PDF path (default output/char_events/<item>_<condition>.png)")
    ap.add_argument("--show", action="store_true", help="open an interactive window")
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args(argv)

    rows = load_rows(args.rows, args.csv)
    if args.list:
        list_trials(rows)
        return 0
    row, legacy = select_trial(rows, args.item, args.condition, args.submission, args.trial)
    out = args.out
    if out is None and not args.show:
        out = ROOT / "output" / "char_events" / f"{row.get('ItemId')}_{row.get('Condition')}_s{row.get('submission_row_id')}.png"
    plot_trial(row, legacy, out, args.show, args.dpi, args.layout, args.fit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
