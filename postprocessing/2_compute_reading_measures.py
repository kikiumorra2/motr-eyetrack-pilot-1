#!/usr/bin/env python3
"""
Step 2 - compute word-level reading measures from the flat mouse-sample file.

This is the MoTR postprocessing pipeline (Wilcox et al., 2024), run in four stages under
<out-dir>/exp_<ID>/:
  divided/            one file per participant
  corrected_divided/  same, after coordinate corrections
  processed_trial/    materials split into one row per word
  associations/       consecutive samples on the same word merged into "associations"
                      (the MoTR analogue of fixations), filtered to
                      low_thres < duration < up_thres ms
  reading_measures/   per participant: first_duration, gaze_duration, first_pass_duration,
                      total_duration, right_bounded_rt, go_past_time, FPFix, FPReg, RegIn_incl,
                      RegIn_excl, response_chosen, trial_num for every word

Example:
  python postprocessing/2_compute_reading_measures.py --experiment-id 42
  (uses the newest results/exp_42/results_processed_exp_42_*.csv and items_processed.csv)
"""
import argparse
import glob
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from utils.divideCsv import FileDivider  # noqa: E402
from utils.mergeAssociations import associationMerger  # noqa: E402
from utils.preprocessTrialData import TrialDataPreprocessor  # noqa: E402
from utils.extractLingusticFeatures import FeatureExtractor  # noqa: E402

STAGES = ["divided", "corrected_divided", "processed_trial", "associations", "reading_measures"]


def make_dirs(base, experiment_id):
    exp_dir = Path(base) / f"exp_{experiment_id}"
    dirs = {name: exp_dir / name for name in STAGES}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def newest(pattern):
    files = sorted(glob.glob(pattern))
    return Path(files[-1]) if files else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--in-file", type=Path, help="flat sample file from step 1 (default: newest in results/exp_<ID>/)")
    parser.add_argument("--trial-file", type=Path, help="items_processed.csv from step 1 (default: results/exp_<ID>/items_processed.csv)")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--low-thres", type=int, default=160, help="min association duration in ms")
    parser.add_argument("--up-thres", type=int, default=4000, help="max association duration in ms")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results_dir = ROOT / "results" / f"exp_{args.experiment_id}"
    in_file = args.in_file or newest(str(results_dir / f"results_processed_exp_{args.experiment_id}_*.csv"))
    trial_file = args.trial_file or results_dir / "items_processed.csv"
    if not in_file or not Path(in_file).exists():
        sys.exit(f"no input file found (looked in {results_dir}); run step 1 first or pass --in-file")
    if not Path(trial_file).exists():
        sys.exit(f"trial file not found: {trial_file}")
    logging.info("input: %s", in_file)

    dirs = make_dirs(args.out_dir, args.experiment_id)

    # 1. one file per participant, with coordinate corrections
    divider = FileDivider(Path(in_file), dirs["divided"])
    divider.divide_raw_file()
    divider.correct_motr_data()

    # 2. materials -> one row per word
    prep = TrialDataPreprocessor(trial_file, dirs["processed_trial"], delim=",")
    prep.split_sentence_into_words()
    prep.filtered_new_df()
    processed_trial = dirs["processed_trial"] / f"filtered_preprocessed_{Path(trial_file).stem}.csv"

    # 3. samples -> associations (fixations)
    for path in sorted(dirs["corrected_divided"].glob("*.csv")):
        logging.info("associations: %s", path.name)
        merger = associationMerger(path, dirs["associations"], args.low_thres, args.up_thres)
        merger.write_out_denoise_merged_associations()

    # 4. associations -> reading measures
    for path in sorted(dirs["associations"].glob("*_clean.csv")):
        logging.info("reading measures: %s", path.name)
        fx = FeatureExtractor(processed_trial, path, dirs["reading_measures"], args.low_thres)
        if fx.input_df_f.empty:
            logging.warning("no associations for %s, skipping", path.name)
            continue
        fx.check_comprehension_answer()
        fx.get_first_duration()
        fx.get_total_duration()
        fx.get_gaze_duration()
        fx.get_first_pass_duration()
        fx.get_right_bounded_rt()
        fx.get_go_past_time()
        fx.get_binary()
        fx.get_trial_num()
        fx.write_out()

    n = len(list(dirs["reading_measures"].glob("*.csv")))
    logging.info("done: %d participant files in %s", n, dirs["reading_measures"])


if __name__ == "__main__":
    main()
