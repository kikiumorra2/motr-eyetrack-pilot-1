#!/usr/bin/env python3
"""
Step 4 - sanity checks of the reading measures (run automatically by run_pipeline.py).

Two independent checks of output/exp_<ID>/reading_measures_all.csv:

1. Invariants that must hold on every row / trial, given the definitions in
   READING_MEASURES.md §4 (e.g. total_duration >= first_duration, RegIn_incl = 1 exactly when
   total_duration > right_bounded_rt, FPReg = 1 exactly when go_past_time > right_bounded_rt).
2. A reference recomputation: every measure is derived again with plain loops from the clean
   association files (output/exp_<ID>/associations/reader_<participant>_clean.csv) and must
   equal the pipeline's value for every participant x trial x word.

Exit status 1 if anything fails, so a broken pipeline never produces a quiet data file.

Examples:
  python postprocessing/check_reading_measures.py --experiment-id 42
  python postprocessing/check_reading_measures.py --file some_reading_measures.csv --associations-dir output/exp_42/associations
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DURATIONS = ["first_duration", "gaze_duration", "first_pass_duration", "total_duration", "right_bounded_rt", "go_past_time"]
BINARY = ["FPFix", "FPReg", "RegIn_incl", "RegIn_excl"]
MEASURES = DURATIONS + BINARY


# ---------------------------------------------------------------------------
# 1. Invariants

def invariant_violations(df, low_thres=160, up_thres=4000):
    """
    [(rule, number of rows violating it)] for the rules that fail; [] if all hold.
    Works on reading_measures_all.csv and on the per-participant reader_*_reading_measures.csv.
    Assumes low_thres >= 0 (every surviving association then has a positive duration).
    """
    missing = [c for c in MEASURES if c not in df.columns]
    if missing:
        raise ValueError(f"missing measure columns: {missing}")
    d = df[MEASURES].apply(pd.to_numeric, errors="coerce")
    fd, gz, fp, tot, rb, gp = (d[c] for c in DURATIONS)
    fix, reg, rin, rex = (d[c] for c in BINARY)
    rules = {
        "every measure is a number": d.isna().any(axis=1),
        "durations are non-negative integers": (d[DURATIONS] < 0).any(axis=1) | (d[DURATIONS] % 1 != 0).any(axis=1),
        "binary columns are 0/1": ~d[BINARY].isin([0, 1]).all(axis=1),
        "first_duration > 0 <=> total_duration > 0": (fd > 0) != (tot > 0),
        "first_duration <= total_duration": fd > tot,
        "first_duration = 0 or low_thres < first_duration < up_thres": (fd != 0) & ~((fd > low_thres) & (fd < up_thres)),
        "gaze_duration in {0, first_duration}": (gz != 0) & (gz != fd),
        "gaze_duration <= first_pass_duration <= right_bounded_rt <= go_past_time": (gz > fp) | (fp > rb) | (rb > gp),
        "first_pass_duration <= total_duration": fp > tot,
        "right_bounded_rt <= total_duration": rb > tot,
        "FPFix = 1 <=> gaze_duration > 0 <=> first_pass_duration > 0 <=> right_bounded_rt > 0 <=> go_past_time > 0":
            ((fix == 1) != (gz > 0)) | ((fix == 1) != (fp > 0)) | ((fix == 1) != (rb > 0)) | ((fix == 1) != (gp > 0)),
        "FPFix = 1 => gaze_duration = first_duration": (fix == 1) & (gz != fd),
        "FPFix = 0 and total_duration > 0 => RegIn_incl = 1": (fix == 0) & (tot > 0) & (rin != 1),
        "RegIn_incl = 1 <=> total_duration > right_bounded_rt": (rin == 1) != (tot > rb),
        "RegIn_excl = RegIn_incl and FPFix": rex != ((rin == 1) & (fix == 1)).astype(int),
        "FPReg = 1 => FPFix = 1": (reg == 1) & (fix != 1),
        "FPReg = 1 <=> go_past_time > right_bounded_rt": (reg == 1) != (gp > rb),
    }
    out = [(rule, int(mask.sum())) for rule, mask in rules.items() if mask.any()]
    # per-trial consistency
    keys = [c for c in ("submission_id", "cond_id", "para_nr") if c in df.columns]
    if keys and "word_nr" in df.columns:
        g = df.groupby(keys, sort=False, dropna=False)
        for col in ("response_chosen", "trial_num"):
            if col in df.columns:
                n = int((g[col].transform("nunique") > 1).sum())
                if n:
                    out.append((f"{col} is constant within a trial", n))
        wn = pd.to_numeric(df["word_nr"], errors="coerce")
        bad = g["word_nr"].transform(lambda s: not (sorted(pd.to_numeric(s, errors="coerce")) == list(range(len(s)))))
        if bad.any():
            out.append(("word_nr is 0..n-1 exactly once within a trial", int(bad.sum())))
        if wn.isna().any():
            out.append(("word_nr is a number", int(wn.isna().sum())))
    return out


# ---------------------------------------------------------------------------
# 2. Reference recomputation from the associations

def reference_measures(assoc):
    """
    All ten measures recomputed with plain loops from clean associations - a DataFrame with
    columns sbm_id, para_nr, word_nr, duration, one row per surviving association in reading
    order (the *_clean.csv files). Returns one row per (sbm_id, para_nr, word_nr) that has at
    least one association; words without one are all-zero by definition.
    Definitions (READING_MEASURES.md §4): "entry" = the first association on w, provided no
    word to the right of w had been visited before it.
    """
    rows = []
    for (sbm, para), g in assoc.groupby(["sbm_id", "para_nr"], sort=False):
        seq = list(zip(pd.to_numeric(g["word_nr"]).astype(int), pd.to_numeric(g["duration"]).astype(int)))
        for w in sorted({x for x, _ in seq}):
            on_w = [i for i, (x, _) in enumerate(seq) if x == w]
            first_right = next((i for i, (x, _) in enumerate(seq) if x > w), len(seq))   # first visit to a word right of w
            first = seq[on_w[0]][1]
            total = sum(seq[i][1] for i in on_w)
            entry = on_w[0] if on_w[0] < first_right else None
            fpfix = int(entry is not None)
            gaze = first if fpfix else 0
            fpd = rb = gp = fpreg = 0
            if fpfix:
                j = entry                                   # consecutive associations on w from the entry
                while j < len(seq) and seq[j][0] == w:
                    fpd += seq[j][1]
                    j += 1
                gp = sum(d for i, (x, d) in enumerate(seq) if entry <= i < first_right)      # until a word to the right
                rb = sum(d for i, (x, d) in enumerate(seq) if x == w and i < first_right)     # on w, before any word to the right
                fpreg = int(any(seq[i][0] == w and i + 1 < len(seq) and seq[i + 1][0] < w for i in range(first_right)))
            regin = int(any(i > first_right for i in on_w))                                  # on w after a word to the right
            rows.append({"sbm_id": str(sbm), "para_nr": str(para), "word_nr": w,
                         "first_duration": first, "gaze_duration": gaze, "first_pass_duration": fpd, "total_duration": total,
                         "right_bounded_rt": rb, "go_past_time": gp,
                         "FPFix": fpfix, "FPReg": fpreg, "RegIn_incl": regin, "RegIn_excl": int(regin and fpfix)})
    return pd.DataFrame(rows, columns=["sbm_id", "para_nr", "word_nr"] + MEASURES)


def compare_with_reference(measures, assoc):
    """
    Rows of `measures` (reading_measures_all.csv, or a per-participant file plus a
    `submission_id` column) whose values differ from the reference recomputation. Empty
    DataFrame = everything agrees. Also flags trials the associations know but the measures
    lack, and vice versa.
    """
    ref = reference_measures(assoc)
    m = measures.copy()
    m["sbm_id"] = m["submission_id"].astype(str)
    m["para_nr"] = m["para_nr"].astype(str)
    m["word_nr"] = pd.to_numeric(m["word_nr"]).astype(int)
    key = ["sbm_id", "para_nr", "word_nr"]
    joined = m[key + MEASURES].merge(ref, on=key, how="outer", suffixes=("", "_ref"), indicator=True)
    # words without an association are absent from ref: the pipeline must have zeros there
    only_m = joined["_merge"] == "left_only"
    for c in MEASURES:
        joined.loc[only_m, c + "_ref"] = 0
    diff = joined["_merge"] == "right_only"                       # association on a word the measures do not list
    for c in MEASURES:
        diff |= pd.to_numeric(joined[c], errors="coerce") != joined[c + "_ref"]
    # a trial with associations must appear in the measures at all
    trials_m = set(zip(m["sbm_id"], m["para_nr"]))
    diff |= joined["_merge"].eq("right_only") & ~joined.apply(lambda r: (r["sbm_id"], r["para_nr"]) in trials_m, axis=1)
    return joined.loc[diff].drop(columns=["_merge"])


# ---------------------------------------------------------------------------
# CLI

def load_associations(assoc_dir):
    files = sorted(Path(assoc_dir).glob("*_clean.csv"))
    if not files:
        sys.exit(f"no *_clean.csv association files in {assoc_dir}")
    return pd.concat([pd.read_csv(f, dtype={"sbm_id": str, "para_nr": str}) for f in files], ignore_index=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment-id", help="check output/exp_<ID>/reading_measures_all.csv against output/exp_<ID>/associations/")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "output")
    ap.add_argument("--file", type=Path, help="reading-measures CSV to check (default: from --experiment-id)")
    ap.add_argument("--associations-dir", type=Path, help="directory of *_clean.csv files (default: from --experiment-id)")
    ap.add_argument("--low-thres", type=int, default=160)
    ap.add_argument("--up-thres", type=int, default=4000)
    args = ap.parse_args(argv)
    if not args.file and not args.experiment_id:
        ap.error("give --experiment-id or --file")
    exp_dir = args.out_dir / f"exp_{args.experiment_id}" if args.experiment_id else None
    file = args.file or exp_dir / "reading_measures_all.csv"
    assoc_dir = args.associations_dir or (exp_dir / "associations" if exp_dir else None)
    if not file.exists():
        sys.exit(f"not found: {file}")
    df = pd.read_csv(file, dtype={"submission_id": str, "para_nr": str})
    ok = True
    viol = invariant_violations(df, args.low_thres, args.up_thres)
    if viol:
        ok = False
        print(f"INVARIANTS VIOLATED in {file} ({len(df)} rows):")
        for rule, n in viol:
            print(f"  {n:6d} row(s): {rule}")
    else:
        print(f"invariants: OK ({len(df)} rows, {len(df.groupby(['submission_id', 'para_nr']).size()) if 'submission_id' in df.columns else '?'} trials)")
    if assoc_dir and assoc_dir.exists():
        if "submission_id" not in df.columns:
            print("reference recomputation skipped: the file has no submission_id column")
        else:
            diff = compare_with_reference(df, load_associations(assoc_dir))
            if len(diff):
                ok = False
                print(f"REFERENCE RECOMPUTATION DIFFERS for {len(diff)} word(s):")
                pd.set_option("display.width", 250, "display.max_columns", 40)
                print(diff.head(20).to_string(index=False))
            else:
                print("reference recomputation from the association files: every measure matches")
    else:
        print("reference recomputation skipped: no association directory")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
