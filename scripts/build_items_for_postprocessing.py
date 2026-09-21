from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MATERIALS = ROOT / "materials"

LIST_FOLDERS = [
    MATERIALS / "lists_exp_block_2_shuffled",
    MATERIALS / "lists_filler_block_2",
    MATERIALS / "lists_exp_block_3_shuffled",
    MATERIALS / "lists_filler_block_3",
]

files = []

# Add all list files from all four folders
for folder in LIST_FOLDERS:
    files.extend(sorted(folder.glob("list_*.csv")))

# Add practice trials too
practice_file = MATERIALS / "practice.csv"

if practice_file.exists():
    files.append(practice_file)

if not files:
    raise RuntimeError("No material files found.")

dfs = []

for path in files:
    print("Reading:", path)
    dfs.append(pd.read_csv(path))

all_items = pd.concat(dfs, ignore_index=True)

# Keep each actual item/condition/text only once.
# The same item occurs across different participant lists,
# so duplicates across lists should not appear repeatedly.
all_items = all_items.drop_duplicates(
    subset=["item_id", "condition_id", "text"]
)

# Keep the columns used by the experiment/postprocessing.
wanted_columns = [
    "item_id",
    "condition_id",
    "text",
    "question",
    "options",
    "correct",
]

# Create missing optional columns if necessary.
for column in wanted_columns:
    if column not in all_items.columns:
        all_items[column] = ""

all_items = all_items[wanted_columns]

output = MATERIALS / "items.csv"

all_items.to_csv(output, index=False)

print()
print(f"Wrote {len(all_items)} unique trials to:")
print(output)
