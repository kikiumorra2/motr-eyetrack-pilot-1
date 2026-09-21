import pandas as pd


df = pd.read_csv(
    "output/exp_345/reading_measures/reader_lusha_reading_measures.csv"
)

practice = df[
    df["para_nr"].astype(str).str.contains("practice")
]

print(
    practice[
        [
            "para_nr",
            "word_nr",
            "word",
            "first_duration",
            "gaze_duration",
            "total_duration",
        ]
    ].to_string(index=False)
)


main = df[
    ~df["para_nr"].astype(str).str.contains("practice")
]

print(
    main[
        [
            "para_nr",
            "word_nr",
            "word",
            "first_duration",
            "gaze_duration",
            "total_duration",
        ]
    ].head(50).to_string(index=False)
)
