#!/usr/bin/env python3
"""
Plot the mouse samples of one trial on top of the recorded word bounding boxes.

Useful for sanity-checking a participant's data or making figures.

Example:
  python postprocessing/plot_trial_mouse_overlay.py --input results/exp_42/results_processed_exp_42_2026-01-01.csv \
      --submission-id 5f1a... --item-id 3_obj_rc --output output/exp_42/trial_3_obj_rc.png
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "ItemId",
    "submission_id",
    "TrialText",
    "Word",
    "Index",
    "mousePositionX",
    "mousePositionY",
    "wordPositionTop",
    "wordPositionLeft",
    "wordPositionRight",
    "wordPositionBottom",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Visualize mouse samples over word positions for one trial in a "
            "reading experiment CSV."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Flat sample CSV from step 1 (results/exp_<ID>/results_processed_exp_<ID>_<date>.csv).",
    )
    parser.add_argument(
        "--item-id",
        type=str,
        default=None,
        help=(
            "ItemId value to visualize. Must be used together with --submission-id. "
            "If omitted (and --submission-id is omitted), the script uses values from "
            "the first row in the file."
        ),
    )
    parser.add_argument(
        "--submission-id",
        type=str,
        default=None,
        help=(
            "submission_id value to visualize. Must be used together with --item-id. "
            "If omitted (and --item-id is omitted), the script uses values from the "
            "first row in the file."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trial_mouse_overlay.png"),
        help="Path to save output figure.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="Rows per chunk when reading CSV.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Output figure DPI.",
    )
    return parser.parse_args()


def normalize_key_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def get_first_item_submission_pair(csv_path: Path, chunksize: int) -> tuple[str, str]:
    for chunk in pd.read_csv(csv_path, chunksize=chunksize):
        missing = [col for col in ["ItemId", "submission_id"] if col not in chunk.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return (
            normalize_key_value(chunk["ItemId"].iloc[0]),
            normalize_key_value(chunk["submission_id"].iloc[0]),
        )

    return "", ""


def load_trial_rows(
    csv_path: Path, item_id: str, submission_id: str, chunksize: int
) -> pd.DataFrame:
    target_item_id = normalize_key_value(item_id)
    target_submission_id = normalize_key_value(submission_id)
    matches = []
    for chunk in pd.read_csv(csv_path, chunksize=chunksize):
        missing = [col for col in REQUIRED_COLUMNS if col not in chunk.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        item_series = chunk["ItemId"].apply(normalize_key_value)
        submission_series = chunk["submission_id"].apply(normalize_key_value)
        filtered = chunk.loc[
            (item_series == target_item_id)
            & (submission_series == target_submission_id),
            REQUIRED_COLUMNS,
        ].copy()
        if not filtered.empty:
            matches.append(filtered)

    if not matches:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    return pd.concat(matches, ignore_index=True)


def get_submission_ids_for_item(csv_path: Path, item_id: str, chunksize: int) -> list[str]:
    target_item_id = normalize_key_value(item_id)
    submission_ids: set[str] = set()
    for chunk in pd.read_csv(csv_path, usecols=["ItemId", "submission_id"], chunksize=chunksize):
        item_series = chunk["ItemId"].apply(normalize_key_value)
        submission_series = chunk["submission_id"].apply(normalize_key_value)
        matched = submission_series[item_series == target_item_id]
        matched = matched[matched != ""]
        submission_ids.update(matched.tolist())
    return sorted(submission_ids)


def make_output_path_for_submission(base_output: Path, submission_id: str) -> Path:
    safe_submission = re.sub(r"[^A-Za-z0-9._-]+", "_", submission_id).strip("_")
    if not safe_submission:
        raise ValueError(f"Could not create safe filename from submission_id='{submission_id}'.")
    return base_output.with_name(f"{base_output.stem}__{safe_submission}{base_output.suffix}")


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "Index",
        "mousePositionX",
        "mousePositionY",
        "wordPositionTop",
        "wordPositionLeft",
        "wordPositionRight",
        "wordPositionBottom",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def extract_trial_text(df: pd.DataFrame, item_id: str, submission_id: str) -> str:
    if "TrialText" not in df.columns:
        raise ValueError("Missing required column: TrialText")
    text_values = df["TrialText"].dropna().astype(str).str.strip()
    text_values = text_values[text_values != ""]
    if text_values.empty:
        raise ValueError(
            "No TrialText found for "
            f"ItemId='{item_id}', submission_id='{submission_id}'."
        )
    return text_values.iloc[0]


def make_figure(
    df: pd.DataFrame, item_id: str, submission_id: str, out_path: Path, dpi: int
) -> None:
    trial_text = extract_trial_text(df, item_id, submission_id)
    df = coerce_numeric_columns(df).dropna(
        subset=[
            "mousePositionX",
            "mousePositionY",
            "wordPositionTop",
            "wordPositionLeft",
            "wordPositionRight",
            "wordPositionBottom",
        ]
    )
    if df.empty:
        raise ValueError(
            "No valid rows after cleanup for "
            f"ItemId='{item_id}', submission_id='{submission_id}'."
        )

    observed_words = (
        df[
            [
                "Word",
                "Index",
                "wordPositionTop",
                "wordPositionLeft",
                "wordPositionRight",
                "wordPositionBottom",
            ]
        ]
        .drop_duplicates()
        .sort_values(by=["wordPositionTop", "wordPositionLeft", "Index"])
    )

    fig, ax = plt.subplots(figsize=(14, 6))

    initial_x = pd.concat(
        [
            df["mousePositionX"],
            observed_words["wordPositionLeft"],
            observed_words["wordPositionRight"],
        ]
    )
    initial_y = pd.concat(
        [
            df["mousePositionY"],
            observed_words["wordPositionTop"],
            observed_words["wordPositionBottom"],
        ]
    )
    pad = 25
    ax.set_xlim(initial_x.min() - pad, initial_x.max() + pad)
    ax.set_ylim(initial_y.min() - pad, initial_y.max() + pad)
    # Screen coordinates have origin in top-left, so invert y-axis for readability.
    ax.invert_yaxis()
    ax.set_aspect("equal", adjustable="box")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    # Estimate one global font size so all words are rendered consistently.
    probe_text = ax.text(
        0,
        0,
        "M",
        ha="center",
        va="center",
        fontsize=10,
        fontfamily = "monospace",
        alpha=0.0,
        zorder=0,
    )
    per_word_limits = []
    for _, row in observed_words.iterrows():
        left = row["wordPositionLeft"]
        right = row["wordPositionRight"]
        top = row["wordPositionTop"]
        bottom = row["wordPositionBottom"]
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            continue

        box_top_left = ax.transData.transform((left, top))
        box_bottom_right = ax.transData.transform((right, bottom))
        box_w_px = abs(box_bottom_right[0] - box_top_left[0])
        box_h_px = abs(box_bottom_right[1] - box_top_left[1])
        if box_w_px <= 0 or box_h_px <= 0:
            continue

        word_text = str(row["Word"]).strip()
        if not word_text:
            continue

        probe_text.set_text(word_text)
        probe_text.set_fontsize(10)
        extent = probe_text.get_window_extent(renderer=renderer)
        if extent.width <= 0 or extent.height <= 0:
            continue

        width_limit = 10.0 * (box_w_px * 0.95) / extent.width
        height_limit = 10.0 * (box_h_px * 0.90) / extent.height
        per_word_limits.append(min(width_limit, height_limit))

    probe_text.remove()
    if not per_word_limits:
        raise ValueError(
            "Could not estimate global font size from word boxes for "
            f"ItemId='{item_id}', submission_id='{submission_id}'."
        )
    global_fontsize = max(1.0, min(per_word_limits))
    tokens = trial_text.strip().split()
    if not tokens:
        raise ValueError(
            "TrialText is empty after tokenization for "
            f"ItemId='{item_id}', submission_id='{submission_id}'."
        )

    observed_for_anchor = observed_words.dropna(
        subset=["Index", "wordPositionLeft", "wordPositionRight", "wordPositionTop", "wordPositionBottom"]
    ).copy()
    observed_for_anchor["Index"] = pd.to_numeric(
        observed_for_anchor["Index"], errors="coerce"
    ).astype("Int64")
    observed_for_anchor = observed_for_anchor.dropna(subset=["Index"]).copy()
    observed_for_anchor["Index"] = observed_for_anchor["Index"].astype(int)
    observed_for_anchor = observed_for_anchor.sort_values(
        by=["Index", "wordPositionLeft"]
    ).drop_duplicates(subset=["Index"], keep="first")
    if observed_for_anchor.empty:
        raise ValueError(
            "No observed word boxes available for sentence anchoring for "
            f"ItemId='{item_id}', submission_id='{submission_id}'."
        )
    max_observed_index = int(observed_for_anchor["Index"].max())
    if max_observed_index >= len(tokens):
        raise ValueError(
            "TrialText token count is incompatible with observed word indices for "
            f"ItemId='{item_id}', submission_id='{submission_id}'. "
            f"max observed index={max_observed_index}, token count={len(tokens)}"
        )

    # Compute relative token centers in data units at the global font size.
    px_per_data_x = abs(
        ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0]
    )
    if px_per_data_x <= 0:
        raise ValueError("Could not compute pixel/data transform for x-axis.")
    probe = ax.text(0, 0, "M", fontsize=global_fontsize, fontfamily = "monospace", alpha=0.0)
    token_widths = []
    for token in tokens:
        probe.set_text(token)
        extent = probe.get_window_extent(renderer=renderer)
        if extent.width <= 0:
            raise ValueError(f"Could not measure rendered width for token '{token}'.")
        token_widths.append(extent.width / px_per_data_x)
    probe.set_text(" ")
    space_extent = probe.get_window_extent(renderer=renderer)
    probe.remove()
    space_width = max(0.0, space_extent.width / px_per_data_x)

    rel_centers = []
    cursor_x = 0.0
    for width in token_widths:
        rel_centers.append(cursor_x + (width / 2.0))
        cursor_x += width + space_width

    # Estimate left-anchor x by aligning observed token centers.
    x0_candidates = []
    for _, row in observed_for_anchor.iterrows():
        idx = int(row["Index"])
        observed_center = (float(row["wordPositionLeft"]) + float(row["wordPositionRight"])) / 2.0
        x0_candidates.append(observed_center - rel_centers[idx])
    sentence_x_left = float(np.median(x0_candidates))
    sentence_y_center = float(
        np.median(
            observed_for_anchor["wordPositionTop"]
            + (observed_for_anchor["wordPositionBottom"] - observed_for_anchor["wordPositionTop"]) * 0.65
        )
    )

    sentence_artist = ax.text(
        sentence_x_left,
        sentence_y_center,
        trial_text.strip(),
        ha="left",
        va="center",
        fontsize=global_fontsize,
        fontfamily = "monospace",
        color="#1f1f1f",
        zorder=1,
    )
    fig.canvas.draw()
    sentence_bbox_px = sentence_artist.get_window_extent(renderer=renderer)
    sentence_bbox_data = ax.transData.inverted().transform(
        [[sentence_bbox_px.x0, sentence_bbox_px.y0], [sentence_bbox_px.x1, sentence_bbox_px.y1]]
    )
    sentence_x0 = float(min(sentence_bbox_data[0][0], sentence_bbox_data[1][0]))
    sentence_x1 = float(max(sentence_bbox_data[0][0], sentence_bbox_data[1][0]))
    sentence_y0 = float(min(sentence_bbox_data[0][1], sentence_bbox_data[1][1]))
    sentence_y1 = float(max(sentence_bbox_data[0][1], sentence_bbox_data[1][1]))

    # Final limits use full sentence extents + all mouse samples.
    full_x = pd.concat([df["mousePositionX"], pd.Series([sentence_x0, sentence_x1])])
    full_y = pd.concat([df["mousePositionY"], pd.Series([sentence_y0, sentence_y1])])
    ax.set_xlim(full_x.min() - pad, full_x.max() + pad)
    ax.set_ylim(full_y.min() - pad, full_y.max() + pad)

    sample_order = np.arange(len(df))
    cmap = plt.get_cmap("viridis")
    if len(df) > 1:
        normed = sample_order / (len(df) - 1)
    else:
        normed = np.array([0.0])

    marker_alpha = 0.5

    if len(df) > 1:
        points = np.column_stack((df["mousePositionX"].to_numpy(), df["mousePositionY"].to_numpy()))
        segments = np.stack([points[:-1], points[1:]], axis=1)
        segment_colors = cmap(normed[:-1])
        line_collection = LineCollection(
            segments,
            colors=segment_colors,
            linewidths=0.8,
            alpha=marker_alpha,
            zorder=1.8,
        )
        ax.add_collection(line_collection)

    scatter = ax.scatter(
        df["mousePositionX"],
        df["mousePositionY"],
        c=sample_order,
        cmap=cmap,
        s=160,
        alpha=marker_alpha,
        edgecolors="none",
        zorder=2,
    )
    cax = ax.inset_axes([1.02, 0.0, 0.03, 1.0])
    cbar = fig.colorbar(scatter, cax=cax)
    cbar.set_label("Sample order (early -> late)")
    ax.set_xlabel("X position (px)")
    ax.set_ylabel("Y position (px)")
    ax.set_title(
        "Mouse Samples Over Word Layout "
        f"(ItemId='{item_id}', submission_id='{submission_id}')"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Remove figure-level whitespace while preserving room for colorbar.
    fig.subplots_adjust(left=0.01, right=0.90, bottom=0.05, top=0.93)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", pad_inches=0.0)
    pdf_path = out_path.with_suffix(".pdf")
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    if args.submission_id is not None and args.item_id is None:
        raise ValueError(
            "If --submission-id is provided, --item-id must also be provided."
        )

    if args.item_id is None and args.submission_id is None:
        item_id, submission_id = get_first_item_submission_pair(args.input, args.chunksize)
        submission_ids = [submission_id]
        print(
            "No keys provided. Using first row values: "
            f"ItemId='{item_id}', submission_id='{submission_id}'"
        )
    elif args.item_id is not None and args.submission_id is None:
        item_id = normalize_key_value(args.item_id)
        if item_id == "":
            raise ValueError("Selected --item-id is empty. Provide a non-empty value.")
        submission_ids = get_submission_ids_for_item(args.input, item_id, args.chunksize)
        if not submission_ids:
            raise ValueError(f"No submission_id values found for ItemId='{item_id}'.")
        print(
            f"No --submission-id provided. Found {len(submission_ids)} submission_id "
            f"values for ItemId='{item_id}'. Generating one plot per submission."
        )
    else:
        item_id = normalize_key_value(args.item_id)
        submission_id = normalize_key_value(args.submission_id)
        submission_ids = [submission_id]

    if item_id == "":
        raise ValueError("Selected --item-id is empty. Provide a non-empty value.")
    if any(sid == "" for sid in submission_ids):
        raise ValueError(
            "Selected key contains an empty submission_id value. Provide explicit "
            "non-empty --submission-id."
        )

    for submission_id in submission_ids:
        trial_df = load_trial_rows(args.input, item_id, submission_id, args.chunksize)
        if trial_df.empty:
            raise ValueError(
                f"No rows found for ItemId='{item_id}', submission_id='{submission_id}'."
            )
        out_path = (
            make_output_path_for_submission(args.output, submission_id)
            if len(submission_ids) > 1
            else args.output
        )
        make_figure(trial_df, item_id, submission_id, out_path, args.dpi)
        print(f"Saved plot to: {out_path}")
        print(f"Saved plot to: {out_path.with_suffix('.pdf')}")
        print(f"Rows plotted: {len(trial_df)}")


if __name__ == "__main__":
    main()
