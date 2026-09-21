from pathlib import Path
import pandas as pd
import re

folders = [
    Path("materials/lists_filler_block_2"),
    Path("materials/lists_filler_block_3"),
]

def convert_options_and_answer(options, answer):
    if pd.isna(options):
        return "", ""

    options = str(options).strip()
    

    parts = re.split(r"\u3000+", options)

    if len(parts) != 2:
        raise ValueError(f"Could not split options: {options!r}")

    first_option = re.sub(r"^\(r\)\s*", "", parts[0]).strip()
    second_option = re.sub(r"\s*\(u\)$", "", parts[1]).strip()

    new_options = f"{first_option}|{second_option}"

    if pd.isna(answer):
        correct = "BOTH"
        
    else:
        answer = str(answer).strip().lower()

        if answer=="r":
            correct = first_option
        elif answer=="u":
            correct = second_option
        else:
            raise ValueError(f"Unexpected answer value: {answer!r}")

    return new_options, correct


for folder in folders:
    for file in sorted(folder.glob("*.csv")):

        print(f"Processing {file}")

        df = pd.read_csv(file)

        converted = df.apply(
            lambda row: convert_options_and_answer(
                row["options"],
                row["answer"]
            ),
            axis=1
        )

        df["options"] = [x[0] for x in converted]
        df["correct"] = [x[1] for x in converted]

        #remove old answer column
        df = df.drop(columns=["answer"])

        #rename columns, whil keeping other columns
        df = df.rename(
            columns={
                "itemID": "item_id",
                "condition": "condition_id",
                "Sentence": "text",
            }
        )

        df.to_csv(file, index=False)

print("Done.")
