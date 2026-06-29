# Business Rules

The domain rules that govern VialVision's behavior. These are stable invariants; code
that violates them is a bug. Mechanics for several rules live in
[MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) and [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md).

## BR-1 — A rack has exactly 9 tubes
The physical MPN rack always has exactly 9 tubes, in 3 dilution groups of 3. The
detector never reports more than 9 (hard cap), and an MPN result is only produced
when exactly 9 are detected.

## BR-2 — Positive = Yellow_Bubble
A tube is **positive (value 1)** only when classified `Yellow_Bubble` (yellow color
with a gas bubble). Every other classification is **negative (0)**. This direction is
fixed and must never be reversed.

## BR-3 — Dilution grouping
Tubes are grouped left-to-right: tubes 1–3 = 0.1 g (`x`), tubes 4–6 = 0.01 g (`y`),
tubes 7–9 = 0.001 g (`z`). The pattern is `P{x}{y}{z}` with each value `0–3`.

## BR-4 — MPN comes only from the lookup table
The MPN/g value and 95 % CI are taken **verbatim** from `mpn_table.csv` for the
detected pattern. They are never computed or interpolated in code. Values may be
non-numeric strings (`"<3.0"`, `">1100"`, `"–"`).

## BR-5 — No MPN without a valid count
When the detected count ≠ 9, VialVision reports the detections and annotated image
but **no MPN** (all MPN fields `null`). It never estimates a result from a partial
rack.

## BR-6 — Risk classification thresholds
| MPN / g | Risk |
|---|---|
| < 3 | Safe |
| 3 – 20 | Low |
| 21 – 110 | Moderate |
| > 110 | High |

## BR-7 — Every saved prediction keeps its annotated image
A persisted prediction always has a corresponding annotated JPEG in `data/results/`.
Deleting a record (manually or via pruning) deletes its image too.

## BR-8 — History is capped at 500
The most recent 500 predictions are retained; older ones (and their images) are
pruned automatically on startup and after each save.

## BR-9 — Predictions are saved even with a partial count
A prediction is persisted regardless of tube count, so partial/failed reads are still
recorded (with `null` MPN fields). DB failure does not block the response.

## BR-10 — Settings are per-device, server-side
UI settings are stored in the server database (not the browser), so they are shared
by every browser hitting that device. Only the allow-listed keys are persisted.

## BR-11 — Platform decides the default camera mode
On a device with `picamera2` available (Raspberry Pi), the default camera mode is
**server**; otherwise it is **client** (browser webcam). The user can override this
in Settings.

## BR-12 — Live stream is ephemeral
WebSocket streaming results are shown live but **never written to history**. Only
`POST /predict` (and `GET /capture` → upload) produces a saved record.

## BR-13 — Confidence threshold is bounded
Any confidence threshold (upload form or `set_conf`) is clamped to `0.05–0.95` before
inference.
