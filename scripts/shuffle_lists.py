from pathlib import Path
import pandas as pd
import random
import heapq

INPUT_FOLDER = Path("materials/lists_exp_block_3")
OUTPUT_FOLDER = Path("materials/lists_exp_block_3_shuffled")
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

SEED = 13
CONDITION_COLUMN = "condition_id"

def shuffle_with_constraint(df, seed, condition_column):
    rng = random.Random(seed)

    groups = {}

    for condition, group in df.groupby(condition_column, sort = False):
        rows = group.to_dict("records")
        rng.shuffle(rows)
        groups[condition] = rows

    n_rows = len(df)

    largest_group = max(len(rows) for rows in groups.values())

    if largest_group > (n_rows+ 1)//2:
        raise ValueError("Impossible to arrange rows without having the same condition twice in a row.")

    heap = []

    for condition, rows in groups.items():
        heapq.heappush(
            heap,
            (
                    -len(rows),
                    rng.random(),
                    condition,
            )
        )
    result = []
    previous = None

    while heap:
        count, _, condition = heapq.heappop(heap)
        result.append(groups[condition].pop())
        count += 1

        if previous is not None:
            heapq.heappush(heap, previous)

        if count <0:
            previous=(
                count,
                rng.random(),
                condition,
            )
        else:
            previous=None

    shuffled_df = pd.DataFrame(result)

    #verify
    conditions = shuffled_df[condition_column]

    if (conditions == conditions.shift()).any():
        raise RuntimeError("Two identical conditions ended up adjacent.")
    return shuffled_df

#process every csv in folder
for file in sorted(INPUT_FOLDER.glob("*.csv")):
    print(f"Processing {file.name}")

    df = pd.read_csv(file)

    shuffled_df = shuffle_with_constraint(
        df,
        seed = SEED,
        condition_column = CONDITION_COLUMN,
    )

    output_file = OUTPUT_FOLDER / file.name

    shuffled_df.to_csv(
        output_file,
        index=False,
    )

    print(f"Saved: {output_file}")

print("Done.")
