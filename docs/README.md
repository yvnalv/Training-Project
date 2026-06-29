# VialVision — Documentation Index

VialVision is a web-based bacterial-contamination detection system. It uses a
YOLOv8 Nano model to read a **9-tube MPN (Most Probable Number)** test rack from a
photo or live camera stream and reports an MPN value, a 95 % confidence interval,
and a food-safety risk level.

This folder is the canonical project documentation. Root-level docs
([../README.md](../README.md), [../CHANGELOG.md](../CHANGELOG.md),
[../CLAUDE.md](../CLAUDE.md), [../Setup.md](../Setup.md)) link back here.

---

## A note on this structure

The folder layout follows a standard project-docs template. That template includes
several **accounting/ERP-specific** documents (accounting design, posting rules,
inventory, approval workflow, multi-tenancy, integration events) that have **no
meaning for a computer-vision app**. Those slots have been **repurposed** to the
VialVision domain:

| Template slot | This project |
|---|---|
| `ACCOUNTING_DESIGN` | [MPN_DESIGN.md](MPN_DESIGN.md) — the MPN method and risk model |
| `POSTING_RULES` | [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) — detection→tube→pattern→MPN rules |
| `INVENTORY_DESIGN` | [MODEL_AND_DATA.md](MODEL_AND_DATA.md) — model weights, datasets, training |
| `WORKFLOW_APPROVAL` | [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md) — the end-to-end inference flow |
| `MULTI_TENANCY` | [CAMERA.md](CAMERA.md) — camera abstraction (picamera2 / OpenCV) |
| `INTEGRATION_EVENTS` | [STREAMING.md](STREAMING.md) — WebSocket live-stream protocol |

---

## Index

### Product & planning
| Doc | Description |
|---|---|
| [STATUS.md](STATUS.md) | Where we are, milestones, what's next |
| [NEXT_STEPS.md](NEXT_STEPS.md) | Sequenced, gated action plan for the accuracy work |
| [PRD.md](PRD.md) | Product requirements — goals, scope, users |
| [ROADMAP.md](ROADMAP.md) | Phased plan of future work |
| [DECISIONS.md](DECISIONS.md) | Log of significant decisions |

### Design & architecture
| Doc | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, stack, data flow |
| [MODULES.md](MODULES.md) | Per-module responsibilities and public API |
| [MPN_DESIGN.md](MPN_DESIGN.md) | The MPN method, dilution model, risk levels |
| [MPN_LOOKUP_RULES.md](MPN_LOOKUP_RULES.md) | Detection→tube→pattern→MPN mapping rules |
| [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md) | Detect → dedup → annotate → compute |
| [MODEL_AND_DATA.md](MODEL_AND_DATA.md) | Model weights, training data, assets |
| [ACCURACY_IMPROVEMENT.md](ACCURACY_IMPROVEMENT.md) | Prioritized plan to improve accuracy + YOLO26 upgrade evaluation |
| [HARDWARE.md](HARDWARE.md) | Hardware recommendation (Pi 5 / Hailo / Jetson) with benchmarks |
| [CAMERA.md](CAMERA.md) | Camera abstraction and color/flip pipeline |
| [STREAMING.md](STREAMING.md) | WebSocket protocol and message contracts |

### Interfaces & data
| Doc | Description |
|---|---|
| [API_SPEC.md](API_SPEC.md) | REST endpoints + WebSocket protocol |
| [DATABASE.md](DATABASE.md) | SQLite schema, pruning, persistence |
| [ERROR_HANDLING.md](ERROR_HANDLING.md) | Failure modes and how they're handled |

### Rules & reference
| Doc | Description |
|---|---|
| [BUSINESS_RULES.md](BUSINESS_RULES.md) | Domain rules that govern behavior |
| [GLOSSARY.md](GLOSSARY.md) | Terms and definitions |
| [SECURITY.md](SECURITY.md) | Security posture, HTTPS, threat notes |

### Process
| Doc | Description |
|---|---|
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Style and conventions |
| [TESTING.md](TESTING.md) | How to verify changes |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Running on desktop and Raspberry Pi |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [adr/](adr/) | Architecture Decision Records ([template](adr/0000-template.md)) |

---

## Quick links

- Install & usage walkthrough: [../Setup.md](../Setup.md)
- Raspberry Pi autostart: [../raspberry_pi_startup_guide.md](../raspberry_pi_startup_guide.md)
- Change history: [../CHANGELOG.md](../CHANGELOG.md)
