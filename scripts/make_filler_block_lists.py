#make lists from the master csv eyetrackDataSource

from pathlib import Path
import pandas as pd

input_file = Path("materials/eyetrackDataSource.csv")

block2_folder = Path("materials/lists_filler_block_2")
block3_folder = Path("materials/lists_filler_block_3")

block2_folder.mkdir(exist_ok=True)
block3_folder.mkdir(exist_ok=True)

df=pd.read_csv(input_file, sep="\t")

df=df.dropna(axis=1,how="all")

is_filler = (
    df["condition"].str.upper().str.startswith("FILLER")
)

filler_df = df[is_filler].copy()

#make one csv for each list in each block

for list_name in sorted(filler_df["list"].unique()):

    #block 2
    block2 = filler_df[
        (filler_df["block"] == 2)
        & (filler_df["list"] == list_name)
    ]

    block2.to_csv(
        block2_folder / f"list_{list_name}.csv",
        index = False
    )

    print(
        f"Block 2, list {list_name}: "
        f"{len(block2)} items"
    )

    #block 3
    block3 = filler_df[
        (filler_df["block"] == 3)
        & (filler_df["list"] == list_name)
    ]

    block3.to_csv(
        block3_folder / f"list_{list_name}.csv",
        index = False
    )

    print(
        f"Block 3, list {list_name}: "
        f"{len(block2)} items"
    )

print("Done.")
