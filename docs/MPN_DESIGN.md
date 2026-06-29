# MPN Design

> _This document occupies the template slot originally named `ACCOUNTING_DESIGN`. It
> describes the domain core of VialVision: the Most Probable Number method and the
> risk model._

## What MPN is

The **Most Probable Number (MPN)** method estimates the concentration of viable
microorganisms in a sample using **serial dilution** and a statistical lookup. Rather
than counting colonies directly, it observes which dilution tubes show growth
(positive) and infers the most probable concentration from the pattern of positives.

VialVision implements the common **3×3 (9-tube)** scheme.

## The 9-tube rack

Nine tubes are arranged in **three dilution groups of three tubes each**:

| Group | Tubes (left→right) | Dilution (sample mass) |
|---|---|---|
| 1 | 1–3 | 0.1 g |
| 2 | 4–6 | 0.01 g |
| 3 | 7–9 | 0.001 g |

Each tube is read as:

- **Positive (1)** — yellow color **with** a gas bubble (microbial growth detected).
- **Negative (0)** — anything else (clear, or yellow without a bubble).

The positive count per group gives a triple `(x, y, z)`, where each value is `0–3`.

## From rack to result

```
9 tubes (left→right, ordered)
   │  Yellow_Bubble = 1, else 0
   ▼
[t1 t2 t3 | t4 t5 t6 | t7 t8 t9]
   │  group sums
   ▼
x = t1+t2+t3   y = t4+t5+t6   z = t7+t8+t9
   │
   ▼
pattern = "P{x}{y}{z}"     e.g. (2,1,0) → "P210"
   │  lookup in mpn_table.csv (40 valid patterns)
   ▼
{ mpn_per_g, ci_low, ci_high }
   │  classify
   ▼
risk level (Safe / Low / Moderate / High)
```

The mapping rules and edge cases are specified in
[MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md). The code path is in
[INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

## Pattern format

Patterns follow `P{x}{y}{z}` where `x`, `y`, `z` ∈ `0..3` are the positive counts in
groups 1, 2, 3 respectively.

| Pattern | Meaning | Example MPN/g |
|---|---|---|
| `P000` | all negative | `<3.0` |
| `P210` | 2, 1, 0 positives | `15` |
| `P333` | all positive | `>1100` |

There are 40 reference patterns in `app/mpn/mpn_table.csv` (the standard MPN index
for the 3-tube, 3-dilution scheme; not all 64 combinatorial triples are tabulated).

## MPN values are strings, not floats

Reference values can be non-numeric: `"<3.0"`, `">1100"`, and a CI bound can be `"–"`
(none). They are stored and returned **as strings** throughout (DB columns are TEXT;
`lookup_mpn` returns strings). Do not coerce them to numbers without handling these
forms. See [DATABASE.md](DATABASE.md).

## Risk model

The MPN/g value maps to a color-coded risk level:

| MPN / g | Risk | Color |
|---|---|---|
| < 3 | Safe | green `#22C55E` |
| 3 – 20 | Low | yellow `#EAB308` |
| 21 – 110 | Moderate | orange `#F97316` |
| > 110 | High | red `#EF4444` |

Risk classification is presented in the UI (the annotated result and the result
panel). The thresholds are part of the [BUSINESS_RULES.md](BUSINESS_RULES.md).

## Why the count must be exactly 9

The entire pattern→MPN mapping assumes exactly 9 tubes in 3 groups of 3. If the
detector returns any other count, the grouping is undefined, so VialVision returns
**no MPN** (all MPN fields `null`) rather than guessing. The inference pipeline
enforces a hard cap of 9 and the API gates MPN computation on `total_tubes == 9`.
