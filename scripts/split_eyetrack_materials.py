from pathlib import Path
import argparse
import re

import pandas as pd


def parse_options(value):
    """
    Convert:

        (r) First option　　　　Second option (u)

    into:

        ["First option", "Second option"]
    """

    text = str(value).strip()

    # Remove the (r) marker at the beginning
    text = re.sub(r"^\(r\)\s*", "", text)

    # Remove the (u) marker at the end
    text = re.sub(r"\s*\(u\)\s*$", "", text)

    # The original file separates the two options with
    # Japanese/full-width spaces.
    parts = [
        part.strip()
        for part in re.split(r"\u3000+", text)
        if part.strip()
    ]

    if len(parts) != 2:
        raise ValueError(
            f"Could not split options into two choices:\n"
            f"{value!r}\n"
            f"Parsed as: {parts}"
        )

    return parts


def get_correct_answer(row):
    """
    Convert answer=r/u into the actual answer text.

    Blank answer means both answers are acceptable,
    so write NA for MotrTrial.vue.
    """

    options = parse_options(row["options"])

    if pd.isna(row["answer"]):
        return "NA"

    answer = str(row["answer"]).strip().lower()

    if answer == "r":
        return options[0]

    if answer == "u":
        return options[1]

    raise ValueError(
        f"Unexpected answer value {row['answer']!r} "
        f"for item {row['itemID']}"
    )


def convert_rows(df):
    """Convert the old format into the current MoTR format."""

    output = pd.DataFrame()

    output["item_id"] = df["itemID"].astype(str)
    output["condition_id"] = df["condition"].astype(str)
    output["text"] = df["Sentence"].astype(str)
    output["question"] = df["question"].astype(str)

    output["options"] = df["options"].apply(
        lambda value: "|".join(parse_options(value))
    )

    output["correct"] = df.apply(
        get_correct_answer,
        axis=1,
    )

    return output


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
        help="Original eyetrackDataSource file",
    )

    parser.add_argument(
        "--output-dir",
        default="materials",
        help="Folder where items.csv, fillers.csv, and practice.csv are written",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # IMPORTANT:
    # The source file is tab-separated despite having a .csv extension.
    df = pd.read_csv(
        input_path,
        sep="\t",
        dtype=str,
    )

    # -------------------------------------------------
    # Split the original table
    # -------------------------------------------------

    practice_raw = df[
        df["condition"] == "Practice"
    ].copy()

    fillers_raw = df[
        df["condition"].str.startswith("FILLER", na=False)
    ].copy()

    items_raw = df[
        (df["condition"] != "Practice")
        & ~df["condition"].str.startswith("FILLER", na=False)
    ].copy()

    # -------------------------------------------------
    # Convert to MoTR format
    # -------------------------------------------------

    items = convert_rows(items_raw)
    fillers = convert_rows(fillers_raw)
    practice = convert_rows(practice_raw)

    # -------------------------------------------------
    # Remove repetitions caused by lists a-r
    #
    # item_id + condition_id is the key used by the
    # postprocessing metadata merge.
    # -------------------------------------------------

    items = items.drop_duplicates(
        subset=["item_id", "condition_id"],
        keep="first",
    )

    fillers = fillers.drop_duplicates(
        subset=["item_id", "condition_id"],
        keep="first",
    )

    practice = practice.drop_duplicates(
        subset=["item_id", "condition_id"],
        keep="first",
    )

    # -------------------------------------------------
    # Write files
    # -------------------------------------------------

    items_path = output_dir / "items.csv"
    fillers_path = output_dir / "fillers.csv"
    practice_path = output_dir / "practice.csv"

    items.to_csv(items_path, index=False)
    fillers.to_csv(fillers_path, index=False)
    practice.to_csv(practice_path, index=False)

    print()
    print("Done.")
    print(f"items.csv:    {len(items)} rows")
    print(f"fillers.csv:  {len(fillers)} rows")
    print(f"practice.csv: {len(practice)} rows")

    print()
    print("Wrote:")
    print(items_path)
    print(fillers_path)
    print(practice_path)


if __name__ == "__main__":
    main()
