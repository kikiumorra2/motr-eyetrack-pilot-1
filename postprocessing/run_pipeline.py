#!/usr/bin/env python3
"""
Run the whole MoTR postprocessing pipeline with ONE command.

    python3 postprocessing/run_pipeline.py --experiment-id 42 --csv results/raw/export.csv

What it does:
  0. If the Python packages are missing, creates a private environment in .venv/ and installs
     them (one-time, needs internet) - no manual setup required.
  1. 1_fetch_and_flatten.py        raw submissions -> flat sample file + participants table
  2. 2_compute_reading_measures.py  -> per-participant reading measures (the MoTR pipeline)
  3. 3_aggregate.py                 -> output/exp_<ID>/reading_measures_all.csv
  4. check_reading_measures.py      sanity checks: invariants of the measures + an independent
                                    recomputation from the association files (fails loudly)

Options (all optional):
  --db                    read from the magpie database instead of a CSV export (see README)
  --require-prolific-id   keep only participants with a 24-character Prolific ID
  --min-trials N          drop participants who finished fewer than N trials
  --low-thres / --up-thres  fixation duration thresholds in ms (default 160 / 4000)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_packages():
    """Re-run this script inside .venv (creating it if needed) when pandas is unavailable."""
    try:
        import pandas  # noqa: F401
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    if Path(sys.prefix).resolve() == VENV.resolve():
        sys.exit("packages are missing inside .venv; delete the .venv folder and run again")
    if not VENV_PY.exists():
        print(f"Creating a private Python environment in {VENV} (one-time) ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    print("Installing required packages (one-time, may take a minute) ...")
    subprocess.check_call([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")])
    print("Restarting inside the environment ...\n")
    os.execv(str(VENV_PY), [str(VENV_PY)] + sys.argv)


def run(step, *args):
    cmd = [sys.executable, str(HERE / step), *map(str, args)]
    print("\n" + "=" * 78 + f"\n{step}\n" + "=" * 78, flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", required=True, help="the magpie experiment ID (magpie.config.js)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=Path, help="CSV export downloaded from the magpie server")
    src.add_argument("--db", action="store_true", help="read straight from the magpie database")
    parser.add_argument("--require-prolific-id", action="store_true")
    parser.add_argument("--min-trials", type=int, default=0)
    parser.add_argument("--low-thres", type=int, default=160)
    parser.add_argument("--up-thres", type=int, default=4000)
    parser.add_argument("--char-events", choices=["auto", "expand", "ignore", "keep"], default="auto",
                        help="how step 1 treats charEvents rows (samplingMode 'events'); default auto")
    parser.add_argument("--resample", type=float, default=None, metavar="MS",
                        help="step 1: expand charEvents rows into fixed-interval rows every MS ms")
    args = parser.parse_args()

    if args.csv and not args.csv.exists():
        sys.exit(f"file not found: {args.csv}")

    step1 = ["--experiment-id", args.experiment_id, "--min-trials", args.min_trials]
    step1 += ["--db"] if args.db else ["--csv", args.csv]
    if args.require_prolific_id:
        step1.append("--require-prolific-id")
    step1 += ["--char-events", args.char_events]
    if args.resample is not None:
        step1 += ["--resample", args.resample]
    run("1_fetch_and_flatten.py", *step1)
    run("2_compute_reading_measures.py", "--experiment-id", args.experiment_id,
        "--low-thres", args.low_thres, "--up-thres", args.up_thres)
    run("3_aggregate.py", "--experiment-id", args.experiment_id)
    run("check_reading_measures.py", "--experiment-id", args.experiment_id,
        "--low-thres", args.low_thres, "--up-thres", args.up_thres)

    out = ROOT / "output" / f"exp_{args.experiment_id}" / "reading_measures_all.csv"
    print("\n" + "=" * 78 + f"\nDone. Your data: {out}\n" + "=" * 78, flush=True)


if __name__ == "__main__":
    ensure_packages()
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"\nstep failed: {' '.join(map(str, e.cmd[1:2]))} (see messages above)")
