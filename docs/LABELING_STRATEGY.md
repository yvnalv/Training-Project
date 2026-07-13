# Labeling Strategy

_Purpose: how to label the dataset for retraining the tube model (current YOLOv8n →
future YOLO26), so that positives/negatives are learned reliably. Companion to
[MODEL_AND_DATA.md](MODEL_AND_DATA.md), [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md),
and the migration discussion._

> Confirmed with the domain owner (2026-06-29). This is the source of truth for the
> label schema and annotation conventions.

---

## 1. The domain truth table

Each tube shows one of **four physical conditions** (color × bubble), and exactly one
is positive:

| Condition (class) | Color | Bubble | Result |
|---|---|---|---|
| `Yellow_Bubble` | yellow | yes | **POSITIVE (1)** |
| `Yellow_NoBubble` | yellow | no | negative (0) |
| `Purple_Bubble` | purple | yes | negative (0) |
| `Purple_NoBubble` | purple | no | negative (0) |

**The positive is a conjunction: _yellow AND bubble_.** The current code rule —
`label == "Yellow_Bubble" ? 1 : 0` — is **correct** and does not change. See
[MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) Rule 1 and
[BUSINESS_RULES.md](BUSINESS_RULES.md) BR-2.

---

## 2. Decision 1 — Label 4 classes, not 2  ✅ (recommended)

**Label all four conditions as distinct classes. Do NOT collapse to
positive/negative at annotation time.** Collapse to binary only in code (one line,
already present).

### Why 4 classes beats 2
- **The positive is a conjunction.** The two hardest negatives are the "one attribute
  right" cases: `Purple_Bubble` (bubble, wrong color) and `Yellow_NoBubble` (right
  color, no bubble). With 2 classes the model must learn "yellow AND bubble"
  *implicitly*, and the "bubble" feature points at both a positive (Yellow_Bubble) and
  a negative (Purple_Bubble) — a confusing signal.
- **4 classes give explicit supervision** on every condition; the strong yellow-vs-
  purple color cue becomes a clean learnable axis. The model is directly taught that
  the bubble-but-purple case is *not* positive.
- **Debuggability & metrics.** When a tube reads negative you know *why* (purple vs
  yellow-no-bubble), enabling per-condition accuracy and error analysis.
- **Future-proof.** If the positive rule ever changes (e.g. a purple-indicator test is
  added), the labels already carry the full information — only the code mapping changes.

### The binary collapse (unchanged, in code)
```
positive (1)  ⟺  class == Yellow_Bubble
negative (0)  ⟺  Yellow_NoBubble | Purple_Bubble | Purple_NoBubble
```

### Cost / mitigation
4 classes need adequate examples of each and careful class balance (see §8). This is
manageable given existing 4-class data + new collection.

---

## 3. Decision 2 — Annotation format depends on the model architecture

The **four condition labels are identical** in both paths below; only the annotation
*container* differs. Old detection data and new single-tube photos can feed **either**
path (see §7), so this decision does not waste data.

### Path A — Detection (current architecture)
YOLO detects and classifies all 9 tubes in a full-rack image.
- Annotation = **bounding box per tube** + class, in YOLO txt format (§4).
- New single-tube photos must also get a box (trivial — one box per image, or composite
  tubes into rack-like scenes).
- Keeps the current [inference.py](../app/inference.py) pipeline.

### Path B — Fixed-ROI + per-tube classification  ✅ CHOSEN (fixed jig confirmed 2026-06-29)
Skip detection; crop the 9 known tube positions and classify each crop.
- Annotation = **one label per image/crop** (ImageFolder layout, §5). Your "single
  photo per category" data is natively this.
- Old detection boxes → **crop them out** to produce classification images (reuse).
- Requires a **mechanical fixture** + ROI calibration, but is both **more accurate**
  (full-res centered crops) and **faster** (tiny classifier) on a fixed rig.
- Changes [inference.py](../app/inference.py) from "detect" to "crop-ROIs → classify".

> **Decision (2026-06-29):** the fixed jig (Pi + camera + rack) is confirmed, so
> **Path B is chosen** — it best serves the stated priority (accuracy first, still
> fast). Path A remains the documented fallback if the jig ever cannot guarantee tube
> position. Either way, **label the 4 conditions** — the schema below serves both. The
> full build plan is in [NEXT_STEPS.md](NEXT_STEPS.md).

---

## 4. Class schema & IDs — PRESERVE EXACTLY

The current model uses this class order. **Keep the names *and* the integer IDs
identical**, so you can fine-tune from `best.pt`, keep the frontend/history compatible,
and avoid silent index mismatches.

| ID | Class name |
|---|---|
| 0 | `Purple_Bubble` |
| 1 | `Purple_NoBubble` |
| 2 | `Yellow_Bubble` |
| 3 | `Yellow_NoBubble` |

> ⚠️ **Do not reorder or rename.** A different ID→name mapping in a new dataset will
> mistrain the model and break the `Yellow_Bubble` positive rule. This is the single
> most common dataset-migration bug.

### `data.yaml` (detection, Path A)
```yaml
path: ./dataset          # dataset root
train: images/train
val:   images/val
test:  images/test       # = the held-out eval set (never train on it)
names:
  0: Purple_Bubble
  1: Purple_NoBubble
  2: Yellow_Bubble
  3: Yellow_NoBubble
```

---

## 5. Annotation formats

### Path A — Detection (YOLO txt)
One `.txt` per image, one line per tube:
```
<class_id> <x_center> <y_center> <width> <height>
```
- Coordinates **normalized** to `[0,1]` relative to image size.
- One box per physical tube (up to 9 per rack image).
- **Box extent must be consistent** — pick one convention and document it: either the
  **whole tube** or the **liquid/reaction region only**. Consistency matters more than
  the choice. (Recommended: whole tube, tight, including the visible liquid + any
  headspace where a bubble forms.)

Directory layout:
```
dataset/
  images/{train,val,test}/*.jpg
  labels/{train,val,test}/*.txt   # same basename as the image
  data.yaml
```

### Path B — Classification (ImageFolder)
Ultralytics classification expects folder-per-class:
```
dataset/
  train/Yellow_Bubble/*.jpg
  train/Yellow_NoBubble/*.jpg
  train/Purple_Bubble/*.jpg
  train/Purple_NoBubble/*.jpg
  val/...    (same 4 subfolders)
  test/...   (same 4 subfolders)
```
- Each image = one centered tube crop (from a single-tube photo, or cropped from a
  rack image's box).
- Folder names are the class names — keep the exact 4.

---

## 6. Labeling conventions & edge-case rules

Ambiguity is the enemy of a clean model. Decide these **once**, write them down, and
label consistently. Suggested rules (adjust to your reality, but be explicit):

| Situation | Rule |
|---|---|
| **What counts as a "bubble"** | Any visible gas bubble in the reaction/headspace. Define a minimum (e.g. a clearly visible bubble, not a pinpoint speck or surface froth). |
| **Meniscus / reflection / glare** | Not a bubble. Do not label as Bubble. |
| **Color borderline** (yellow↔purple transition) | Assign the *dominant* color. If genuinely indeterminate, exclude the sample or add a documented tie-break. |
| **Partial / tiny bubble** | Apply the minimum-bubble rule above consistently. |
| **Occluded / heavily blurred tube** | Exclude from training (don't teach noise). Keep a few in the *test* set only if they reflect real deployment. |
| **Empty / missing tube position** | Not a class — exclude, or (Path B) handle as a separate "empty" bucket if it can occur. |
| **Multiple bubbles** | Still one tube = one label (Bubble). |

Keep a short **labeling guide with example images** for each of the 4 classes and each
edge rule so multiple annotators stay consistent.

---

## 7. Combining the old and new datasets

You are merging **previous data** (rack images, 4-class boxes) with **new data**
(single-tube photos per category). Both are usable in either path:

| Source | → Path A (detection) | → Path B (classification) |
|---|---|---|
| Old rack images + boxes | Use directly | **Crop each box** → labeled crop |
| New single-tube photos | Add a box (whole image ≈ one tube) or composite into racks | Use directly (folder = its class) |

Guidance:
- **Match the deployment rig.** New captures should use the same camera / lighting /
  ~19 cm distance as production. Domain match matters more than raw volume.
- **Keep a manifest** (CSV) recording each image's source, capture date, condition, and
  (for Path A) rack pattern — for traceability and debugging.
- **De-duplicate** near-identical frames (e.g. consecutive video frames) so the same
  tube doesn't dominate.

---

## 8. Class balance (critical for accuracy)

Real MPN racks are often **positive-sparse** — `Yellow_Bubble` may be the rarest class,
yet it is the *only* one that matters for the result. Mitigate:
- **Deliberately over-collect positives** — capture positive-heavy racks / single tubes
  so `Yellow_Bubble` is well represented across all 9 positions.
- **Balance the four classes** in training (target roughly comparable counts, or use
  class weights / oversampling of minority classes).
- **Cover all 9 tube positions** and a spread of patterns (Path A) to avoid position
  bias.
- Track **per-class counts** before training; fix gaps rather than training on a skewed set.

---

## 9. Dataset splits

- **Split by sample, not by crop.** All crops/boxes from one rack photo must land in the
  *same* split — otherwise near-identical tubes leak between train and val, inflating
  scores. For single-tube photos, split by physical tube/session.
- **Hold out a dedicated test set = the Phase-0 eval set** ([NEXT_STEPS.md](NEXT_STEPS.md)).
  **Never train or tune on it.** It is the only honest measure of improvement.
- Suggested ratios: ~70% train / ~15% val / ~15% test, adjusted to keep every class
  present in each split.

---

## 10. Quality control

- **Review pass:** a second person spot-checks labels against the labeling guide.
- **Per-condition metrics:** report accuracy for each of the 4 classes, plus the
  collapsed **binary positive/negative** accuracy (what the client experiences) and the
  end-to-end **MPN-pattern** accuracy.
- **Confusion matrix:** watch specifically for `Yellow_Bubble ↔ Yellow_NoBubble`
  (missed/false positives — the costly errors) and `Yellow_Bubble ↔ Purple_Bubble`
  (color confusion).

---

## 11. Deliverables checklist

- [ ] Labeling guide (this doc + example images per class + edge-case rules)
- [ ] `data.yaml` (Path A) or ImageFolder tree (Path B) with the **exact 4 classes / IDs**
- [ ] Old data converted/verified into the chosen format
- [ ] New rig captures labeled, balanced (esp. positives), all 9 positions covered
- [ ] Manifest CSV (source, date, condition, pattern)
- [ ] Train/val/test split by sample; test = held-out eval set
- [ ] Per-class counts reviewed; imbalance addressed
- [ ] QC review pass complete

---

## 12. Open items to confirm

- ~~**Architecture (Decision 2):** detection vs classification~~ — **resolved
  2026-06-29: Path B (fixed-ROI classification)**, jig confirmed.
- **Crop framing convention (Path B):** how much of the tube each ROI crop includes
  (whole tube incl. headspace vs liquid/reaction region) — pick and document, apply
  consistently across all crops.
- **Minimum-bubble definition:** set the threshold with example images.
- **ROI margins:** generous enough to absorb rack-insertion tolerance (see
  [NEXT_STEPS.md](NEXT_STEPS.md) Phase 0.2).
