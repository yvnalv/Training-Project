# Product Requirements Document (PRD)

## 1. Summary

VialVision is a single-device web tool that reads a **9-tube MPN (Most Probable
Number)** bacterial-contamination test rack from an image or live camera feed and
reports the bacterial concentration (MPN/g), its 95 % confidence interval, and a
food-safety risk level. It targets the **Raspberry Pi 4** as the primary appliance,
with desktop browsers for development and ad-hoc use.

## 2. Problem & motivation

Reading an MPN rack by eye and manually looking up the pattern in a reference table
is slow and error-prone. Operators must correctly identify which of the 9 tubes are
positive (yellow + bubble), group them into the three dilution levels, derive the
pattern, look up the MPN value, and interpret the risk. VialVision automates the
detection, lookup, and interpretation from a single photo.

## 3. Goals

- Detect the 9 tubes and classify each as positive/negative from a photo or frame.
- Compute the MPN pattern, value, and 95 % CI automatically.
- Present a clear, color-coded risk classification.
- Work hands-free on a Raspberry Pi appliance (boot → fullscreen → ready).
- Keep a browsable, exportable history of past readings.

## 4. Non-goals

- Not a multi-user SaaS; no authentication, accounts, or multi-tenancy.
- Not a laboratory LIMS; results are advisory, not a certified measurement.
- No cloud storage or external integrations; all data stays on the device.
- Not an accounting/inventory/ERP system (despite the docs template origin).

## 5. Users

| User | Need |
|---|---|
| Lab/field operator | Quick, repeatable MPN reading without manual lookup |
| Reviewer | Browse history, confirm results, export CSV for records |
| Maintainer/developer | Run locally, adjust thresholds, retrain the model |

## 6. Functional requirements

| # | Requirement |
|---|---|
| FR-1 | Accept an uploaded image and return detections + MPN result + annotated image |
| FR-2 | Stream live inference from a browser webcam (client mode) |
| FR-3 | Stream live inference from the server's Pi/USB camera (server mode) |
| FR-4 | Capture a single still from the server camera for analysis |
| FR-5 | Detect exactly 9 tubes; suppress duplicates; never report more than 9 |
| FR-6 | Map detections → tubes → (x,y,z) → pattern → MPN value + 95 % CI |
| FR-7 | Classify risk: Safe / Low / Moderate / High |
| FR-8 | Persist every prediction (with annotated image) and list it in History |
| FR-9 | Delete a history record (and its image); export all history as CSV |
| FR-10 | Persist UI settings (camera mode, FPS, resolution, flip, confidence) |
| FR-11 | Provide an MPN guideline reference view (all 40 patterns) |
| FR-12 | Show the device LAN IP for easy access from other devices |

## 7. Non-functional requirements

| # | Requirement |
|---|---|
| NFR-1 | Runs on Raspberry Pi 4 with acceptable latency (downscale 50 % before inference) |
| NFR-2 | Serves over HTTPS (self-signed) to enable browser camera access |
| NFR-3 | Survives DB write failures without losing the user-facing prediction |
| NFR-4 | Auto-prunes history to the most recent 500 records |
| NFR-5 | Starts automatically on Pi boot into fullscreen Chromium |
| NFR-6 | Responsive UI down to a 7" RPi LCD (≤ 480 px / ≤ 320 px) |

## 8. Constraints & assumptions

- The physical rack **always** has exactly 9 tubes in 3 groups of 3.
- A positive tube is **yellow with a bubble** (`Yellow_Bubble`).
- Inference quality depends on lighting and a ~19 cm Pi-camera capture distance.
- Single trained model (`best.pt`); COCO classes are not used.

## 9. Success metrics

- Correct tube count (= 9) on well-framed, well-lit images.
- Correct positive/negative classification per tube.
- MPN value matches the manual reference-table lookup for the detected pattern.

## 10. Out-of-scope / future

See [ROADMAP.md](ROADMAP.md): automated tests, model accuracy improvements, better
under/over-detection UX, optional packaging.
