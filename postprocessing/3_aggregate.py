#!/usr/bin/env python3
"""
Step 3 - combine per-participant reading measures into one analysis-ready file.

Reads output/exp_<ID>/reading_measures/reader_*_reading_measures.csv, adds participant
info (list, device, hand) from step 1 and item metadata (condition, correct answer, any
extra columns) from materials/, and writes output/exp_<ID>/reading_measures_all.csv with
one row per participant x word.

Example:
  python postprocessing/3_aggregate.py --experiment-id 42
"""
import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def newest(pattern):
    files = sorted(glob.glob(pattern))
    return Path(files[-1]) if files else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--materials-dir", type=Path, default=ROOT / "materials")
    parser.add_argument("--participants", type=Path, help="participants file from step 1 (default: newest)")
    args = parser.parse_args()

    exp_dir = args.out_dir / f"exp_{args.experiment_id}"
    files = sorted((exp_dir / "reading_measures").glob("reader_*_reading_measures.csv"))
    if not files:
        sys.exit(f"no reading-measure files in {exp_dir / 'reading_measures'}; run step 2 first")

    frames = []
    for path in files:
        df = pd.read_csv(path, dtype={"para_nr": str, "cond_id": str})
        df.insert(0, "submission_id", path.stem[len("reader_"):-len("_reading_measures")])
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    # item_id / condition_id from the combined "<item>_<condition>" key
    split = df["para_nr"].str.split("_", n=1, expand=True)
    df.insert(1, "item_id", split[0])
    df.insert(2, "condition_id", split[1])
    df = df.drop(columns=["cond_id"], errors="ignore")

    # Step 2 already spreads the (trial-level) answer over every word of the trial; repeat it
    # here as a safety net for per-participant files produced by older versions.
    df["response_chosen"] = df.groupby(["submission_id", "para_nr"])["response_chosen"].transform("first")

    # participant info
    participants = args.participants or newest(
        str(ROOT / "results" / f"exp_{args.experiment_id}" / f"participants_exp_{args.experiment_id}_*.csv")
    )
    if participants and Path(participants).exists():
        p = pd.read_csv(participants, dtype={"submission_id": str})
        keep = [c for c in ("submission_id", "ListId", "device", "hand") if c in p.columns]
        df = df.merge(p[keep], on="submission_id", how="left")

    # item metadata from materials (correct answer + any extra columns)
    meta = []
    for name in ("items.csv", "fillers.csv", "practice.csv"):
        path = args.materials_dir / name
        if path.exists():
            meta.append(pd.read_csv(path, dtype=str))
    if meta:
        meta = pd.concat(meta, ignore_index=True).drop(columns=["text", "question", "options"], errors="ignore")
        meta = meta.rename(columns={"correct": "correct_response"})
        df = df.merge(meta, on=["item_id", "condition_id"], how="left")
        if "correct_response" in df.columns:
            has_key = df["correct_response"].notna() & df["response_chosen"].notna()
            df["accuracy"] = pd.NA
            df.loc[has_key, "accuracy"] = (df.loc[has_key, "response_chosen"] == df.loc[has_key, "correct_response"]).astype(int)

    n_no_answer = df.groupby(["submission_id", "para_nr"])["response_chosen"].first().isna().sum()
    if n_no_answer:
        print(f"warning: {n_no_answer} trials have no response (response_chosen = NA)")

    out = exp_dir / "reading_measures_all.csv"
    df.to_csv(out, index=False)
    print(f"{df['submission_id'].nunique()} participants, {df.groupby(['submission_id', 'para_nr']).ngroups} trials, {len(df)} words")
    if "accuracy" in df.columns and df["accuracy"].notna().any():
        acc = df.dropna(subset=["accuracy"]).groupby(["submission_id", "para_nr"])["accuracy"].first()
        print(f"mean accuracy on items with a correct answer: {acc.mean():.2f}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
