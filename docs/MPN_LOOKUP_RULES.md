# MPN Lookup Rules

> _This document occupies the template slot originally named `POSTING_RULES`. In an
> accounting system "posting rules" map transactions to ledger entries; here the
> analogous deterministic mapping turns detections into an MPN result._

These rules are the **single source of truth** for how a set of YOLO detections
becomes an MPN reading. They are implemented in `app/inference.py` and
`app/mpn/mpn_lookup.py`.

## Rule 1 — Label → tube value

```
Yellow_Bubble  → 1  (positive)
anything else  → 0  (negative)
```

Implemented in `detections_to_tubes()`. **This direction must not be reversed** — it
was once swapped (`Yellow_NoBubble` was wrongly treated as positive) and produced
inverted results. See [../CHANGELOG.md](../CHANGELOG.md) entry _2026-04-16 — reversed
positive label_.

## Rule 2 — Ordering

Detections are sorted **left-to-right** by horizontal box center
`((x1 + x2) / 2)` before being converted to tubes. Tube index 0 is the leftmost tube.
Ordering happens at the end of `suppress_duplicate_tubes()`.

## Rule 3 — Exactly 9 tubes

`detections_to_tubes()` raises `ValueError` if it does not receive exactly 9
detections. The API never calls it unless `total_tubes == 9`; `_compute_mpn()` short-
circuits to all-`None` MPN fields otherwise. The detector also enforces a **hard cap
of 9** (see [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md)).

## Rule 4 — Group sums (x, y, z)

```
x = sum(tubes[0:3])   # group 1, 0.1 g dilution
y = sum(tubes[3:6])   # group 2, 0.01 g dilution
z = sum(tubes[6:9])   # group 3, 0.001 g dilution
```

Each of `x, y, z` is in `0..3`. Implemented in `tubes_to_xyz()`.

## Rule 5 — Pattern key

```
pattern = f"P{x}{y}{z}"        # e.g. (2,1,0) → "P210"
```

## Rule 6 — Table lookup

`lookup_mpn(x, y, z)` looks the pattern up in the in-memory table loaded from
`app/mpn/mpn_table.csv`.

- **Found:** returns `{ "pattern", "mpn", "low", "high" }` (all strings).
- **Not found:** logs a warning and returns `{ "pattern": key, "mpn": None,
  "low": None, "high": None }`. **It never raises** — an unusual but
  combinatorially-possible triple that isn't tabulated must not crash a request.

## Rule 7 — Result assembly

`_compute_mpn()` (in `app/api.py`) returns:

```json
{ "tubes": [...], "pattern": "P210", "mpn": "15", "ci_low": "3.7", "ci_high": "42" }
```

When `total_count != 9` it instead returns:

```json
{ "tubes": [], "pattern": null, "mpn": null, "ci_low": null, "ci_high": null }
```

## Reference table format (`mpn_table.csv`)

CSV with a header and 40 data rows:

```csv
"pattern","mpn_per_g","ci_low","ci_high"
"P000","<3.0","–","9.5"
"P001","3","0.15","9.6"
"P010","3","0.15","11"
"P011","6.1","1.2","18"
...
```

`load_mpn_table()` validates that all required columns
(`pattern, mpn_per_g, ci_low, ci_high`) are present and fails fast with a clear error
if the header is wrong or the file is missing/empty. Values are kept as strings (note
the non-numeric forms like `"<3.0"` and `"–"`).

## Invariants

- The same `(x, y, z)` always produces the same pattern and MPN values (pure lookup).
- MPN values are strings; do not assume numeric.
- No MPN result is ever produced for a non-9 tube count.
