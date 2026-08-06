# Labeling, Preprocessing & Augmentation Strategy

_Purpose: how to label, preprocess, and augment the dataset for retraining the tube
detector (current YOLOv8n → **YOLO26 object detection**), so positives/negatives are
learned reliably without corrupting the color/bubble signal. Companion to
[NEXT_STEPS.md](NEXT_STEPS.md), [MODEL_AND_DATA.md](MODEL_AND_DATA.md),
[ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md)._

> Confirmed with the domain owner (2026-06-29). Source of truth for the label schema
> and the Roboflow preprocessing/augmentation policy.

---

## 1. The domain truth table → 3 labels

There are **four physical conditions** (color × bubble); they map to **3 labels**
(decided 2026-06-29). Only **yellow + bubble** is positive:

| Physical condition | Color | Bubble | Label | Result |
|---|---|---|---|---|
| yellow + bubble | yellow | yes | **`yellow_positive`** | **POSITIVE (1)** |
| yellow + no bubble | yellow | no | `yellow_negative` | negative (0) |
| purple + bubble | purple | yes | `purple_negative` ⚠️ | negative (0) |
| purple + no bubble | purple | no | `purple_negative` | negative (0) |

**The positive is a conjunction: _yellow AND bubble_.** Note that **both** purple
conditions collapse into `purple_negative` — including **purple + bubble**, which is
the *hard negative* (a bubble that is NOT positive because it is purple). Ensure
`purple_negative` actually contains purple-with-bubble examples (§7).

The code positive rule becomes `label == "yellow_positive"` (was `"Yellow_Bubble"` — a
rename that requires a code change, see §3). See
[MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) Rule 1, [BUSINESS_RULES.md](BUSINESS_RULES.md) BR-2.

---

## 2. Architecture: object detection (Path A) — chosen ✅

Decision (2026-06-29): **keep object detection.** The existing dataset is a proper
detection dataset (mixed 1-tube and 9-tube photos, **every tube boxed**), and the
current app is already a detection pipeline, so this is the lowest-risk upgrade.

The fixed jig is still valuable — consistent framing + locked lighting improve
detection accuracy — it just isn't used for ROI cropping. The **fixed-ROI + per-tube
classification** alternative (Path B) remains a documented fallback if detection
accuracy ever plateaus:

> **Path B (fallback):** on a fixed jig, skip detection, crop the 9 known ROIs, and
> classify each crop with a `yolo26n-cls` model. More accurate/faster in principle, but
> needs ROI calibration + an `inference.py` rewrite. Not pursued now.

---

## 3. Class schema — 3 classes (final)

| ID* | Class | Meaning | Tube value |
|---|---|---|---|
| — | **`yellow_positive`** | yellow + bubble | **1 (positive)** |
| — | `yellow_negative` | yellow, no bubble | 0 |
| — | `purple_negative` | purple (any bubble state) | 0 |

\* Use whatever IDs your downloaded `data.yaml` assigns — they don't need to match the
old model (we train fresh from `yolo26n.pt`); only the **names** matter.

Rules:
- **`yellow_positive` must be spelled exactly** — the app keys the positive off that
  string.
- Everything non-`yellow_positive` → 0.

### ⚠️ Code change required (class rename)
The current code hardcodes the old positive label `"Yellow_Bubble"` in four places:
[inference.py:107](../app/inference.py#L107), [inference.py:203](../app/inference.py#L203),
[script.js:573](../static/js/script.js#L573), [script.js:984](../static/js/script.js#L984).
When the YOLO26 model is integrated, these must change to `"yellow_positive"`.
**If missed, every tube reads 0 and MPN is always `P000` — a silent, catastrophic bug.**
Recommended: introduce a single constant (e.g. `POSITIVE_LABEL = "yellow_positive"`) so
the string lives in one place. Tracked in [NEXT_STEPS.md](NEXT_STEPS.md) Phase 4.

---

## 4. Annotation format (detection)

YOLO txt: one `.txt` per image, one line per tube:
```
<class_id> <x_center> <y_center> <width> <height>     # coords normalized [0,1]
```
- **One box per physical tube** (up to 9 per rack image; 1 per single-tube photo).
- **Box extent must be consistent** — pick one convention and document it: whole tube,
  or liquid/reaction region only. Consistency matters more than the choice.
  (Recommended: whole tube, tight, including the liquid + the headspace where a bubble
  forms.)
- Export from Roboflow in the **YOLO26** format (or YOLOv11/YOLOv8 — identical txt
  format). Yields `data.yaml` + `images/` + `labels/`.

`data.yaml` (3-class; IDs as in your downloaded YOLO26 export — Roboflow typically
orders alphabetically):
```yaml
path: ./dataset
train: images/train
val:   images/val
test:  images/test        # held-out; new-jig eval set — never train on it
names:
  0: purple_negative
  1: yellow_negative
  2: yellow_positive
```

---

## 5. Preprocessing & augmentation policy 🔑

The whole task rides on **color (yellow vs purple)** and **fine bubble detail**. The
wrong augmentation destroys exactly that signal. Two separate concepts:

- **Preprocessing** applies to *all* images (train/val/test) **and at inference** — it
  must match how the Pi sees images.
- **Augmentation** applies to *training only* — it invents variations.

> Speed note: augmentation does **not** affect Pi inference speed. Speed comes from
> **model size (n/s) + `imgsz` + NCNN export**. The only speed lever here is the resize
> resolution.

### 5.1 Preprocessing (Roboflow)

| Option | Setting | Why |
|---|---|---|
| **Auto-Orient** | ✅ On | Strips EXIF rotation so boxes align |
| **Resize** | ✅ **640×640, "Fit"/letterbox** | Matches `imgsz=640`; "Fit" preserves tube aspect (don't "Stretch") |
| **Grayscale** | ❌ Never | Color is core signal |
| **Auto-Adjust Contrast** | ❌ Skip | Lighting is jig-locked; adds variance |
| **Tile / Static Crop / Isolate** | ❌ Off | Not needed at 640 for rack detection |

`imgsz=640` is the accuracy/speed sweet spot; going smaller (416) speeds things up but
risks losing bubble detail. Accuracy-first → stay at 640.

### 5.2 Augmentation (Roboflow) — minimal & color-safe

The rig is controlled and Ultralytics augments internally, so keep Roboflow light.

**✅ Safe (modest):** Brightness ±10%, Exposure ±10%, Rotation ±5° (max ±10°).
**Multiplier ≤ 3×.**

**❌ Avoid — these damage the signal:**

| Augmentation | Why it hurts |
|---|---|
| **Hue** 🔴 | Shifts yellow↔green/orange, purple↔blue — corrupts the core yellow-vs-purple cue. **Never.** |
| Saturation | Alters color distinctness — skip or ≤5% |
| Vertical flip | Bubble is at the *top*; upside-down is unphysical |
| Blur / Noise | Erases fine bubble detail |
| Cutout / Mosaic (Roboflow) | Can erase a tube/bubble; Ultralytics handles mosaic itself |
| Grayscale (%) | Destroys color |

*(Horizontal flip is geometrically fine — the app re-sorts tubes left→right — but low
value on a fixed jig; optional.)*

### 5.3 Protect color again at train time (Ultralytics)

Ultralytics' default training augmentation includes a hue shift (`hsv_h=0.015`) and its
own flips. Override so you don't double-augment or shift hue:

```python
model.train(
    data="path/to/data.yaml", epochs=100, imgsz=640, patience=20,
    hsv_h=0.0,      # 🔴 no hue shift — protect yellow vs purple
    hsv_s=0.3, hsv_v=0.4,   # modest saturation/brightness OK
    flipud=0.0,     # no vertical flip (bubble at top)
    fliplr=0.5, degrees=5.0,
)
```

### 5.4 Augmentation ≠ balance fix

Roboflow augmentation multiplies the **whole** training set, so it does **not** fix the
`Yellow_NoBubble` shortage — the ratio stays the same. Real data is the fix (§7).

---

## 6. Current dataset snapshot (old-jig bootstrap)

| Class | Count | Assessment |
|---|---|---|
| `yellow_positive` (positive) | **422** | ✅ Great |
| `purple_negative` (negative) | 231 | OK — ensure purple-**with-bubble** is represented inside |
| `yellow_negative` (negative) | **58** | 🔴 Too few — the critical yellow boundary |

Imbalance ~7:1. Good enough to **bootstrap** the pipeline and get an early signal; not
the final set. Dataset already downloaded from Roboflow in **YOLO26** format. See
[NEXT_STEPS.md](NEXT_STEPS.md) Phases 1–2 (interim) and 5 (new-jig).

---

## 7. Class balance & the `Yellow_NoBubble` gap (critical)

`yellow_positive` vs `yellow_negative` (same color, differ only by bubble) is the
**hardest and most consequential** boundary — errors here are the client-facing false
pos/neg. **Confirmed empirically:** in the interim YOLO26n training (2026-08-03),
`yellow_negative` was the **weakest class** (test mAP50 0.885 / recall 0.900) while
`purple_negative` was near-perfect and `yellow_positive` strong. A bigger model
(`yolo26s`) gave no gain — so the fix is **data, not capacity**.
- **Top priority for new-jig collection: many more `yellow_negative` examples** (the
  `VialVision2.0 v1` export had 453 train instances — better than the earlier 58, but
  still the limiting class).
- Ensure `purple_negative` has enough **purple-with-bubble** hard negatives.
- Keep the strong `yellow_positive` set; cover all **9 positions**; add **real 9-tube
  rack photos** (interim data was single-tube only).
- Consider class weights / oversampling at train time as a stopgap, but collect real
  data.

---

## 8. Dataset splits

- **Split by sample, not by tube.** All boxes from one rack photo stay in the same split
  (no leakage). For single-tube photos, split by physical tube/session.
- **Test split = the new-jig eval set** ([NEXT_STEPS.md](NEXT_STEPS.md) Phase 0.2) —
  **never train or tune on it**, and keep it **new-jig only** (old-jig images must not
  enter the test set, or metrics will lie).
- ~70/15/15, keeping every class present in each split.

---

## 9. Labeling conventions & edge-case rules

Decide these **once**, document with example images, label consistently:

| Situation | Rule |
|---|---|
| **What counts as a "bubble"** | Any visible gas bubble in the headspace; define a minimum (not a pinpoint speck or surface froth) |
| **Meniscus / reflection / glare** | Not a bubble |
| **Color borderline** (yellow↔purple) | Assign the dominant color; if indeterminate, exclude or document a tie-break |
| **Occluded / heavily blurred tube** | Exclude from training; keep a few in the test set only if realistic |
| **Empty / missing position** | Don't box it |
| **Multiple bubbles** | Still one box = Bubble |

---

## 10. Quality control

- **Review pass:** a second person spot-checks against the guide.
- **Metrics:** per-class mAP, collapsed **binary** accuracy (client-facing), end-to-end
  **MPN-pattern** accuracy.
- **Confusion watch:** `yellow_positive ↔ yellow_negative` (costly false pos/neg) and
  `yellow_positive ↔ purple_negative` (color error).

---

## 11. Deliverables checklist

- [x] Class schema = 3 (`yellow_positive`, `yellow_negative`, `purple_negative`)
- [ ] Roboflow preprocessing applied (Auto-Orient + Resize 640 Fit; no grayscale)
- [ ] Roboflow augmentation applied per policy (no hue / vertical-flip / blur / cutout)
- [x] Export in **YOLO26** format (`data.yaml` + images/labels) — done
- [ ] Labeling guide with example images + edge rules
- [ ] Box-extent convention documented and applied consistently
- [ ] `purple_negative` verified to include purple-with-bubble hard negatives
- [ ] Train/val/test split by sample; test = new-jig eval set
- [ ] Per-class counts reviewed; `yellow_negative` collection planned (~200+)
- [ ] Code positive-label updated `Yellow_Bubble` → `yellow_positive` at integration
- [ ] QC review pass complete

---

## 12. Open items to confirm

- ~~Class count~~ — **resolved: 3 classes** (`yellow_positive`, `yellow_negative`,
  `purple_negative`).
- **Box-extent convention:** whole tube vs liquid region — pick and document.
- **Minimum-bubble definition:** set the threshold with example images.
- **`purple_negative` composition:** confirm it includes purple-with-bubble examples.
