#!/usr/bin/env python3
"""
Step 1 - turn raw magpie submissions into one flat CSV of mouse samples.

Input, one of:
  --csv FILE   a CSV export, in either format (detected from the columns):
               * magpie-serverless "download results": already flattened, one line per
                 submitted row, with a `submission_id` column grouping the rows of one
                 submission (this is what https://magpie-serverless.vercel.app produces);
               * classic magpie-backend results table: columns id, experiment_id, results,
                 where `results` holds one submission's rows as a JSON array.
  --db         read the same table straight from the magpie Postgres database. Needs
               psycopg2 and the environment variables MOTR_DB_NAME, MOTR_DB_USER,
               MOTR_DB_PASS, MOTR_DB_HOST (optionally MOTR_DB_TABLE, default "results").

Output (default directory results/exp_<ID>/):
  results_processed_exp_<ID>_<date>.csv   one row per mouse sample / trial summary,
                                          in the format step 2 expects
  participants_exp_<ID>_<date>.csv        one row per participant
  items_processed.csv                     the materials in the format step 2 expects

Examples:
  python postprocessing/1_fetch_and_flatten.py --experiment-id 42 --csv results/raw/export.csv
  python postprocessing/1_fetch_and_flatten.py --experiment-id 42 --db --require-prolific-id
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motr_char_events  # noqa: E402  (character-event payloads, see src/charEvents/FORMAT.md)

ROOT = Path(__file__).resolve().parent.parent

# Columns that are constant per participant but only present on some rows.
PARTICIPANT_COLS = [
    "SubjectId", "ListId", "hand", "device", "feedback",
    "experiment_start_time", "experiment_end_time", "experiment_duration",
    "zoomPercent", "devicePixelRatio",
]
# Reported in the participants table only (not broadcast to every sample row).
PARTICIPANT_ONLY_COLS = ["screenWidth", "screenHeight", "windowInnerWidth", "windowInnerHeight", "userAgent"]
# Participant columns recorded as whole numbers; sample rows lack them, so pandas would keep
# them as floats ("2.0") after the broadcast - store them as integers.
INTEGER_PARTICIPANT_COLS = ["ListId", "experiment_start_time", "experiment_end_time", "experiment_duration", "zoomPercent"]
# Columns the downstream pipeline reads; created (empty) if missing.
REQUIRED_COLS = [
    "Index", "Word", "ItemId", "Condition", "Experiment", "responseTime",
    "mousePositionX", "mousePositionY",
    "wordPositionTop", "wordPositionLeft", "wordPositionRight", "wordPositionBottom",
    "userResponse", "TrialType",
]


def parse_results_cell(cell):
    """Return the list of row dicts stored in one `results` cell."""
    if isinstance(cell, list):
        return cell
    if isinstance(cell, dict):
        return [cell]
    s = str(cell)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, list) else [obj]
    except json.JSONDecodeError:
        pass
    # CSV exports of a Postgres text[] column look like {"{\"Word\": ...}","{...}"}.
    s = s.replace('"{', "{").replace('}"', "}").replace("\\\\", "\\").replace('\\"', '"')
    return json.loads("[" + s[1:-1] + "]")


def read_csv_export(path, experiment_id):
    """Submissions as [{"id", "results"}] from either export format (see the module docstring)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)   # empty cells stay "" (magpie's own filler)
    if "experiment_id" in df.columns and experiment_id is not None:
        df = df[df["experiment_id"].astype(str) == str(experiment_id)]
    if "results" in df.columns:
        # classic magpie-backend table: one line per submission, rows as a JSON array
        return [{"id": row.get("id"), "results": row["results"]} for row in df.to_dict("records")]
    if "submission_id" in df.columns:
        # magpie-serverless: one line per row; a submission's rows are consecutive and share submission_id
        records = []
        for sid, group in df.groupby("submission_id", sort=False):
            rows = group.drop(columns=["submission_id", "experiment_id"], errors="ignore").to_dict("records")
            records.append({"id": sid, "results": rows})
        return records
    sys.exit("unrecognised export: expected a 'results' column (magpie-backend table) "
             "or a 'submission_id' column (magpie-serverless download)")


def read_db(experiment_id):
    try:
        import psycopg2
    except ImportError:
        sys.exit("--db needs psycopg2 (pip install psycopg2-binary)")
    env = {k: os.environ.get(f"MOTR_DB_{k}") for k in ("NAME", "USER", "PASS", "HOST")}
    missing = [f"MOTR_DB_{k}" for k, v in env.items() if not v]
    if missing:
        sys.exit("missing environment variables: " + ", ".join(missing))
    table = os.environ.get("MOTR_DB_TABLE", "results")
    conn = psycopg2.connect(
        dbname=env["NAME"], user=env["USER"], password=env["PASS"], host=env["HOST"]
    )
    cur = conn.cursor()
    cur.execute(f"SELECT id, results FROM {table} WHERE experiment_id = %s ORDER BY id", (experiment_id,))
    records = [{"id": rid, "results": results} for rid, results in cur]
    conn.close()
    return records


def broadcast(df, cols, by=None):
    """Fill NaNs in `cols` with the one non-null value (per group if `by` is given)."""
    for col in cols:
        if col not in df.columns:
            continue
        if by is None:
            values = df[col].dropna().unique()
            if len(values) == 1:
                df[col] = df[col].fillna(values[0])
        else:
            df[col] = df[col].fillna(df.groupby(by)[col].transform("first"))
    return df


def _integer_if_integral(s):
    """`s` as a nullable integer column if every non-null value is a whole number, else unchanged."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().sum() != s.notna().sum() or not (num.dropna() % 1 == 0).all():
        return s
    return num.astype("Int64")


def flatten(records, char_events="auto", resample_ms=None):
    """Legacy-shaped sample rows for all submissions (see flatten_all)."""
    return flatten_all(records, char_events, resample_ms)[0]


def flatten_all(records, char_events="auto", resample_ms=None):
    """
    Turn submissions into (df, char_df, warnings).

    df       one row per sample / marker / summary row, exactly as the legacy 20 Hz format;
             charEvents rows (samplingMode "events") are expanded by motr_char_events
             according to `char_events` (auto | expand | ignore | keep) and `resample_ms`.
    char_df  one row per recorded character event (empty when there are none).
    """
    frames, char_frames, warnings = [], [], []
    for rec in records:
        raw_rows = parse_results_cell(rec["results"])
        if not raw_rows:
            continue
        rows, char_rows, warns = motr_char_events.expand_submission(raw_rows, char_events, resample_ms)
        warnings.extend(f"submission {rec['id']}: {w}" for w in warns)
        if char_rows:
            cdf = pd.DataFrame(char_rows)
            cdf["submission_row_id"] = rec["id"]
            subject = next((r.get("SubjectId") for r in raw_rows if motr_char_events._present(r.get("SubjectId"))), np.nan)
            cdf["SubjectId"] = subject
            char_frames.append(cdf)
        if not rows:
            continue
        # magpie fills columns a row does not have with "" (addEmptyColumns); older exports use "NA"
        df = pd.DataFrame(rows).replace(["NA", ""], np.nan)
        df["submission_row_id"] = rec["id"]
        if "SubjectId" not in df.columns or df["SubjectId"].isna().all():
            # magpie alone puts the experiment-level data on the first row of ALL data, i.e. only
            # in a participant's first per-trial submission; src/submit.js adds it to every one.
            warnings.append(f"submission {rec['id']}: no SubjectId on any of its {len(df)} rows - "
                            "it cannot be assigned to a participant and will be DROPPED")
        frames.append(broadcast(df, PARTICIPANT_COLS))
    if not frames:
        sys.exit("no submissions found")
    df = pd.concat(frames, ignore_index=True)
    if "SubjectId" not in df.columns:
        sys.exit("submissions contain no SubjectId column")
    df = broadcast(df, PARTICIPANT_COLS, by="SubjectId")
    for col in INTEGER_PARTICIPANT_COLS:
        if col in df.columns:
            df[col] = _integer_if_integral(df[col])
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = np.nan
    # Keep each participant's samples together and in the order they were recorded.
    df["experiment_start_time"] = pd.to_numeric(df["experiment_start_time"], errors="coerce")
    ids = pd.to_numeric(df["submission_row_id"], errors="coerce")
    if ids.notna().all():
        df["submission_row_id"] = ids                                # numeric order, not "9" > "10"
    df = df.sort_values(["SubjectId", "experiment_start_time", "submission_row_id"], kind="stable")
    char_df = pd.concat(char_frames, ignore_index=True) if char_frames else pd.DataFrame()
    if len(char_df):
        char_df = char_df.sort_values(["SubjectId", "submission_row_id", "t"], kind="stable").reset_index(drop=True)
    return df.reset_index(drop=True), char_df, warnings


def participants_table(df):
    trials = df[df["TrialType"] == "trial"] if "TrialType" in df.columns else df.iloc[0:0]
    cols = [c for c in PARTICIPANT_COLS + PARTICIPANT_ONLY_COLS if c in df.columns and c != "SubjectId"]
    out = df.groupby("SubjectId")[cols].first()
    # every per-trial submission carries its own end time / duration: report the last one
    for col in ("experiment_end_time", "experiment_duration"):
        if col in cols:
            out[col] = df.groupby("SubjectId")[col].max()
    out["n_trials"] = trials.groupby("SubjectId").size()
    out["n_trials"] = out["n_trials"].fillna(0).astype(int)
    return out.reset_index().rename(columns={"SubjectId": "submission_id"})


def items_table(materials_dir):
    frames = []

    for name in ("items.csv", "fillers.csv", "practice.csv"):
        path = materials_dir / name
        if path.exists():
            frames.append(pd.read_csv(path, dtype=str))

    lists_dir = materials_dir / "lists"

    if lists_dir.exists():
        for path in sorted(lists_dir.glob("list_*.csv")):
            frames.append(pd.read_csv(path, dtype=str))

    items = pd.concat(frames, ignore_index=True)

    items = items.drop_duplicates(
        subset=["item_id", "condition_id", "text"]
    )

    items["item_id"] = (
        items["item_id"].str.strip()
        + "_"
        + items["condition_id"].str.strip()
    )

    return items[["item_id", "condition_id", "text"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", required=True, help="magpie experiment ID (magpie.config.js)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=Path, help="CSV export: magpie-serverless download or classic results-table dump (auto-detected)")
    src.add_argument("--db", action="store_true", help="read from the magpie database (see docstring)")
    parser.add_argument("--materials-dir", type=Path, default=ROOT / "materials")
    parser.add_argument("--out-dir", type=Path, default=None, help="default: results/exp_<ID>/")
    parser.add_argument("--require-prolific-id", action="store_true",
                        help="drop participants whose ID is not a 24-character hex Prolific ID")
    parser.add_argument("--min-trials", type=int, default=0,
                        help="drop participants with fewer completed trials than this")
    parser.add_argument("--char-events", choices=motr_char_events.MODES, default="auto",
                        help="charEvents rows (samplingMode 'events'): expand into sample rows, ignore them, "
                             "keep them raw, or auto (expand unless legacy sample rows are present; default)")
    parser.add_argument("--resample", type=float, default=None, metavar="MS",
                        help="with --char-events expand: emit fixed-interval rows every MS ms instead of "
                             "one row per character change (for comparison with the 20 Hz format)")
    args = parser.parse_args()

    out_dir = args.out_dir or ROOT / "results" / f"exp_{args.experiment_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    records = read_db(args.experiment_id) if args.db else read_csv_export(args.csv, args.experiment_id)
    print(f"{len(records)} submissions")
    df, char_df, warnings = flatten_all(records, args.char_events, args.resample)
    for w in warnings:
        print("warning:", w)

    participants = participants_table(df)
    keep = pd.Series(True, index=participants.index)
    if args.require_prolific_id:
        keep &= participants["submission_id"].astype(str).str.fullmatch(r"[0-9a-fA-F]{24}")
    keep &= participants["n_trials"] >= args.min_trials
    dropped = participants.loc[~keep, "submission_id"].tolist()
    if dropped:
        print(f"dropping {len(dropped)} participants: {dropped}")
    participants = participants[keep]
    n_orphan = int(df["SubjectId"].isna().sum())
    df = df[df["SubjectId"].isin(participants["submission_id"])]
    if len(char_df):
        char_df = char_df[char_df["SubjectId"].isin(participants["submission_id"])].copy()
        char_df["ItemId"] = char_df["ItemId"].astype(str) + "_" + char_df["Condition"].astype(str)
        char_df = char_df.rename(columns={"SubjectId": "submission_id"})

    # Mouse-sample / trial-summary rows only (drops survey rows, which have no ItemId).
    df = df[df["ItemId"].notna()].copy()
    df["ItemId"] = df["ItemId"].astype(str) + "_" + df["Condition"].astype(str)
    df = df.rename(columns={"userResponse": "response", "SubjectId": "submission_id"})
    df = df.drop(columns=[c for c in ["feedback", "userAgent", "screenWidth", "screenHeight"] if c in df.columns])

    # Readable column order: key columns first, everything else alphabetically.
    first = ["submission_id", "ListId", "Experiment", "ItemId", "Condition", "TrialType", "TrialId",
             "Index", "Word", "responseTime", "mousePositionX", "mousePositionY",
             "wordPositionTop", "wordPositionLeft", "wordPositionBottom", "wordPositionRight",
             "response", "correctResponse", "readingTime", "TrialText"]
    df = df[[c for c in first if c in df.columns] + sorted(c for c in df.columns if c not in first)]

    results_path = out_dir / f"results_processed_exp_{args.experiment_id}_{today}.csv"
    participants_path = out_dir / f"participants_exp_{args.experiment_id}_{today}.csv"
    items_path = out_dir / "items_processed.csv"
    df.to_csv(results_path, index=False)
    participants.to_csv(participants_path, index=False)
    items_table(args.materials_dir).to_csv(items_path, index=False)
    print(f"{len(participants)} participants, {len(df)} rows")
    print(f"wrote {results_path}\nwrote {participants_path}\nwrote {items_path}")
    if len(char_df):
        char_path = out_dir / f"char_events_exp_{args.experiment_id}_{today}.csv"
        first_c = ["submission_id", "Experiment", "ItemId", "Condition", "t", "T", "dt", "kind",
                   "word_idx", "char_idx", "char", "global_idx", "layout_id", "x", "y", "num", "submission_row_id"]
        char_df = char_df[[c for c in first_c if c in char_df.columns] + sorted(c for c in char_df.columns if c not in first_c)]
        char_df.to_csv(char_path, index=False)
        print(f"{len(char_df)} character events, wrote {char_path}")
    if n_orphan:
        print(f"WARNING: {n_orphan} rows in {sum('no SubjectId' in w for w in warnings)} submissions carry no SubjectId "
              "and were dropped (see the warnings above). Every submission must have the participant's "
              "SubjectId on its first row - the app does this in src/submit.js.")


if __name__ == "__main__":
    main()
