# Materials

All stimuli live in this folder as CSV files with a single shared schema. They are bundled
into the experiment at build time (`npm run build`), so any change requires a rebuild.

| file | contents |
|---|---|
| `items.csv` | Every critical item in every condition (one row per item × condition). Source of truth; **not** loaded by the app directly. |
| `lists/list_NN.csv` | One list per participant group, generated from `items.csv` by `scripts/make_lists.py` (or hand-made). Each participant sees exactly one list. |
| `fillers.csv` | Filler sentences shown to every participant. |
| `practice.csv` | Practice sentences shown before the main trials (`nPractice` in `src/config.js`). |

## Columns

| column | required | meaning |
|---|---|---|
| `item_id` | yes | Identifier of the item. Must be unique within a file and must **not** contain `_` (postprocessing joins `item_id` and `condition_id` with `_` and later splits on the first `_`). Use e.g. `1…N` for items, `f1…` for fillers, `p1…` for practice. |
| `condition_id` | yes | Condition label (underscores allowed, e.g. `long_plausible`). Fillers use `filler`, practice items use `practice`. |
| `text` | yes | The sentence. Words are separated by single spaces; each whitespace-separated token becomes one clickable region and one row in the reading-measure output. Punctuation attached to a word (`error.`) stays with that word. |
| `question` | no | Comprehension/judgment question shown after reading. If empty, the default question from `src/config.js` is used (or none, if it is disabled). |
| `options` | no | Answer options for `question`, separated by `\|`, e.g. `Yes\|No`. |
| `correct` | no | The correct option (must match one of `options` exactly). Used by `postprocessing/3_aggregate.py` to compute accuracy. |

Any extra columns are preserved in the lists and available in the app as `trial.row.<column>`.

## Generating lists

```bash
python scripts/make_lists.py                 # Latin square: one list per condition
python scripts/make_lists.py --n-lists 8     # more lists (conditions cycle; order is shuffled in-app)
```

Lists are assigned at runtime by the URL parameter `?LIST_ID=N` (see `chooseListId` in
`src/materials.js`); without it, `defaultList` in `src/config.js` applies.
