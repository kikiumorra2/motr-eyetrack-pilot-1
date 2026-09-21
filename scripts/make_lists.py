#!/usr/bin/env python3
"""
Generate Latin-square lists from materials/items.csv into materials/lists/list_NN.csv.

Each list contains every item exactly once; across lists, every item appears in every
condition. Conditions are ordered by first appearance in items.csv, items likewise.
List k (1-based) shows item i (0-based) in condition (i + k - 1) mod n_conditions.

Trial order is shuffled by the app at runtime, so lists are written in item order.

Usage:
    python scripts/make_lists.py
    python scripts/make_lists.py --items materials/items.csv --out materials/lists --n-lists 4
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, default=ROOT / "materials" / "items.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "materials" / "lists")
    parser.add_argument("--n-lists", type=int, default=None, help="default: number of conditions")
    args = parser.parse_args()

    with open(args.items, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    for col in ("item_id", "condition_id", "text"):
        if col not in fieldnames:
            sys.exit(f"items file is missing required column '{col}'")

    items, conditions = [], []
    by_key = {}
    for row in rows:
        item, cond = row["item_id"].strip(), row["condition_id"].strip()
        if "_" in item:
            sys.exit(f"item_id '{item}' contains '_', which is reserved (see materials/README.md)")
        if item not in items:
            items.append(item)
        if cond not in conditions:
            conditions.append(cond)
        if (item, cond) in by_key:
            sys.exit(f"duplicate row for item {item}, condition {cond}")
        by_key[(item, cond)] = row

    missing = [(i, c) for i in items for c in conditions if (i, c) not in by_key]
    if missing:
        sys.exit("every item needs every condition; missing: " + ", ".join(f"{i}/{c}" for i, c in missing))

    n_lists = args.n_lists or len(conditions)
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("list_*.csv"):
        old.unlink()

    for k in range(1, n_lists + 1):
        path = args.out / f"list_{k:02d}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i, item in enumerate(items):
                cond = conditions[(i + k - 1) % len(conditions)]
                writer.writerow(by_key[(item, cond)])
        print(f"wrote {path.relative_to(ROOT)} ({len(items)} items)")

    print(f"{len(items)} items x {len(conditions)} conditions -> {n_lists} lists")


if __name__ == "__main__":
    main()
