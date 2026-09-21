# `motr-ce/1` — MoTR character-event trial payload

This is the wire/storage format produced by `src/charEvents/` (browser) and decoded by
`postprocessing/motr_char_events.py`. Both sides also contain an encoder + decoder so the
two implementations can be checked against each other byte-for-byte (`test/fixtures/`).

## One row per trial

In `samplingMode: "events"` (and `"both"`) each trial records **one** magpie row when the
participant clicks "Done Reading":

| field | value |
|---|---|
| `Experiment`, `Condition`, `ItemId` | as on every other row of the trial |
| `TrialType` | `"charEvents"` |
| `TrialText` | the trial text (the decoder splits it on whitespace into words) |
| `mtFormat` | `"motr-ce/1"` |
| `mtLayout` | layout snapshots (below) |
| `mtEvents` | state-change events (below) |
| `mtTrace` | raw pointer trace (below), `""` when `charEvents.recordRawTrace` is off |
| `mtStats` | `key=value` pairs (below) |

The row has **no `Index`** field, so a pipeline that does not know the format treats it
like a summary row. magpie adds `responseTime` (ms since screen start) as usual.

All `mt*` strings use only `[0-9A-Za-z .,:;@#_=/-]` — safe inside JSON, CSV, the
magpie `flattenData` pipe-join and the Postgres `text[]` CSV export (no quotes,
backslashes, braces or `|`). They are plain string scalars (never arrays/objects).

## Character model

The reading screen renders one `<span data-index="i"> word </span>` per whitespace token
of `TrialText`; the span's text node is `" word "` — leading space, the word's code points,
trailing space. Local character index `k` of span `i`:

| `k` | character |
|---|---|
| `0` | leading space |
| `1 … len_i` | the word's code points (`Array.from(word)` / `list(word)`) |
| `len_i + 1` | trailing space |

The **global** character index is `g = Σ_{j<i} (len_j + 2) + k`. The decoder maps `g` back
to `(i, k)`.

Under CSS whitespace collapsing the trailing space of span `i` keeps its advance while the
leading space of span `i+1` collapses to zero width, so the gap between two words belongs to
the *preceding* word — exactly what `document.elementFromPoint` reports today. Both spaces
are measured, so whichever a browser keeps is captured; zero-width characters are simply not
present in the layout and can never be hit.

## Numbers

Every coordinate is written with **at most one decimal**: `t = floor(x·10 + 0.5)` (integer
tenths), then `t/10` printed without a trailing `.0`; `-0` is written `0`. Examples:
`120`, `-1.3`, `0.1`. Both implementations do the same IEEE-754 operations, so they print
identical strings.

## Time

`t0` is the recorder's start time (`performance.now()` in the browser). Sample times `t`
(event `timeStamp`s, same origin) are rounded **once** by the encoder:

    T = floor((t − t0) + 0.5)          integer ms since t0

Events store `dt = T_i − T_{i−1}` (with `T_{−1} = 0`), so the sum of all `dt`s equals the
last `T` exactly — no drift. Timestamps that go backwards are clamped to the previous one
(`dt = 0`); `t < t0` is clamped to `t0`. `mtStats.t0` is `t0` expressed on magpie's
`responseTime` clock (ms since the trial screen started), so a decoded row's
`responseTime = t0 + T` is comparable to legacy rows.

## `mtLayout`

    mtLayout = snapshot ( '#' snapshot )*
    snapshot = 'l' id '@' T
               ' B' l ',' t ',' r ',' b
               ( ' W' l ',' t ',' r ',' b
                 ( ' F' k0 '@' top ',' bottom ':' x0 ( ',' x )+ )*
               )*

* `l<id>@<T>` — snapshot id (0, 1, 2 …) and the time it became active (`T`, ms since
  `t0`). Snapshot `0` is taken when recording starts; a new snapshot is appended only when a
  re-measurement (resize, scroll, zoom, font load, …) differs by more than 0.05 px.
* `B` — bounding rect of the `.readingText` block, viewport (`client`) coordinates.
* `W` — one per span, in order: the span's `getBoundingClientRect()` (this is what the
  legacy `wordPositionTop/Left/Bottom/Right` columns contain).
* `F` — a *fragment*: a run of consecutive non-zero-width characters of that span on one
  line, starting at local index `k0`, occupying the vertical band `[top, bottom)`. A fragment
  with `m + 1` x values covers characters `k0 … k0 + m − 1`; character `k0 + j` occupies the
  half-open box `[x_j, x_{j+1}) × [top, bottom)`. A span that wraps has several fragments.

## `mtEvents`

    mtEvents = ( dt kind [ num ] ';' )*

`dt` is the integer ms since the previous event (first event: since `t0`). Only **changes**
of state are recorded; a sample whose state equals the previous one produces nothing.

| token | meaning |
|---|---|
| `c<g>` | pointer is on global character `g` |
| `n` | inside the text block but on no character (legacy `Index = −1`) |
| `o` | outside the text block (legacy: nothing recorded) |
| `l<id>` | layout snapshot `id` is active from now on |
| `h` / `s` | document became hidden / shown (`visibilitychange`) |
| `e` | "Done Reading" (end of recording) |
| `t` | `maxEvents` reached — later state changes were dropped (`mtStats.drop`); only `e` follows |

Hit-test rule (identical to the legacy sampler): if the point is outside `B` → `o`;
otherwise find the character at `(x, y)`; if none, at `(x, y − 3)` (so the line above still
counts); if none → `n`. "At a point" means what `document.elementFromPoint` means in
Chrome/Blink: the 1 × 1 CSS-px square whose top-left corner is the point is intersected with
the boxes, i.e. a box `[l, r) × [t, b)` is hit iff `x + 1 > l`, `x < r`, `y + 1 > t`, `y < b`;
when several boxes qualify, the right-most (later in DOM order) wins. The same rule is applied
to `B`. Both implementations follow it exactly (verified against the engine in
`test/browser.test.js`).

The coordinates are those of the pointer events, which Chrome reports with sub-pixel
precision on many devices; the legacy sampler's `mousemove` coordinates are truncated to
whole CSS pixels. The rule is the same, the input differs by < 1 px, so the two can disagree
while the pointer rests within a pixel of a box edge (in a validation session on a real
mouse: 0.5 % of the 50 ms rows, in two brief rests). `mtTrace` rounds to `px`, so the
fraction itself is not stored.

## `mtTrace`

Every pointer sample fed to the recorder (all coalesced events, whole document) as
`(T, X, Y)` with `X = floor(x / px + 0.5)`, `Y = floor(y / px + 0.5)` (`px` =
`charEvents.tracePrecisionPx`, reported in `mtStats.px`). The triplets are written as
deltas from the previous sample (the first relative to `(0, 0, 0)`), each delta
zigzag-mapped (`v ≥ 0 → 2v`, `v < 0 → −2v − 1`) and VLQ-coded: 5 data bits per symbol,
least-significant chunk first, bit `0x20` = "continuation", symbol alphabet
`A–Z a–z 0–9 - _`. Deltas below 16 in magnitude take one symbol, so a sample typically
costs 3 characters.

## `mtStats`

Space-separated `key=value`; values are numbers (≤ 1 decimal) or words.

| key | meaning |
|---|---|
| `v` | stats version (1) |
| `t0` | `t0` on magpie's `responseTime` clock (int ms) |
| `tsrc` | `event` (event `timeStamp`s used) or `perf` (fell back to `performance.now()`) |
| `n`, `ne`, `nl`, `nw` | samples fed, events recorded, snapshots, spans |
| `trunc`, `drop`, `tdrop` | 1 if `maxEvents` was hit; events dropped; trace samples dropped |
| `batches`, `coal`, `maxb` | `pointermove` handler calls; 1 if `getCoalescedEvents` was available; max samples in one batch |
| `px` | trace precision in CSS px (0 = no trace) |
| `mindt` | smallest positive raw inter-sample interval seen (ms) — reveals the clock resolution |
| `hmax` | slowest handler call (µs) |
| `ptypes` | pointer types seen, `.`-joined (`mouse`, `pen`, `touch`) |

## Worked example

Text `The cat sat.`, spans `" The "`, `" cat "`, `" sat. "` (global offsets 0, 5, 10),
fake 10 px characters on one line, band 180–201, block 100,150–900,260:

```
mtLayout: l0@0 B100,150,900,260 W120,180,155,201 F1@180,201:120,130,140,150,155 W155,180,190,201 F1@180,201:155,165,175,185,190 W190,180,230,201 F1@180,201:190,200,210,220,230
mtEvents: 812c1;48c2;45c3;35c4;50c6;510n;400o;700e;
mtTrace:  4yByH8LQECQGA
mtStats:  v=1 t0=1043 tsrc=event n=3 ne=8 nl=1 nw=3 trunc=0 drop=0 tdrop=0 batches=1 coal=1 maxb=3 px=1 mindt=7.8 hmax=41 ptypes=mouse
```

`mtTrace` holds the samples `(812.3, 121, 190)`, `(820.1, 123, 191)`, `(828.4, 126, 191)`
→ rounded `(812,121,190)`, deltas `(812,121,190) (8,2,1) (8,3,0)`.

Decoded to legacy rows (`responseTime = 1043 + T`):

| T | Index | Word | note |
|---|---|---|---|
| 812 | 0 | The | `c1` = "T" |
| 860 | 0 | The | `c2` = "h" |
| 905 | 0 | The | `c3` = "e" |
| 940 | 0 | The | `c4` = trailing space of "The" |
| 990 | 1 | cat | `c6` = "c" |
| 1500 | −1 | | `n` |
| — | | | `o`: no row (as legacy) |
| 2600 | −1 | | `e`: end-of-reading marker |

## Decoding rules

| recorded | legacy rows produced |
|---|---|
| `c<g>` (span `i`) | `Index = i`, `Word`, `wordPosition*` from the active snapshot's `W_i`, `mousePositionX/Y` from the last trace sample with the same or earlier `T` (else the character box centre) |
| `n` | `Index = −1`, no `Word`/box |
| `o` | nothing |
| `l`, `h`, `s`, `t` | nothing (present in the char-level table) |
| `e` | `Index = −1` end marker (closes the last association) |

Consecutive rows with the same `Index` are merged by the existing pipeline
(`mergeAssociations.py`), so character-level detail never changes word-level durations
other than by being more precise in time.

## Size

A typical 10 s trial with a 125 Hz mouse and ~150 state changes is ≈ 1 KB layout +
1 KB events + 3.8 KB trace ≈ 6 KB, versus ≈ 66 KB of JSON for the legacy 20 Hz rows.
Defaults (`maxEvents 20000`, `maxTraceSamples 120000`) bound a trial at ≈ 0.6 MB.
