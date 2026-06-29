# Contributing

## Getting set up

1. Install dependencies: `pip install -r requirements.txt` (Python 3.10+).
2. Put `best.pt` in the project root.
3. Run the app from the **repo root** (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Before you start

- Read [CLAUDE.md](../CLAUDE.md) for the project at a glance and the conventions that
  matter.
- Skim [ARCHITECTURE.md](ARCHITECTURE.md) and the doc for the area you're touching
  (e.g. [INFERENCE_PIPELINE.md](INFERENCE_PIPELINE.md), [CAMERA.md](CAMERA.md),
  [DATABASE.md](DATABASE.md)).
- Respect the domain invariants in [BUSINESS_RULES.md](BUSINESS_RULES.md).

## Workflow

1. **Branch** off `main` (the repo uses descriptive branch names, e.g.
   `fixing-upload-button`, `bugs/fixing-raspi-camera-mode`).
2. Make focused changes that match the surrounding style
   ([CODING_STANDARDS.md](CODING_STANDARDS.md)).
3. **Verify manually** — there is no automated suite yet ([TESTING.md](TESTING.md)).
   Run the app and exercise the affected flow.
4. **Update docs in the same change:**
   - Behavior change → update the relevant `docs/*` file.
   - API change → update [API_SPEC.md](API_SPEC.md).
   - Any user-visible or bug-fix change → add a dated entry to
     [../CHANGELOG.md](../CHANGELOG.md) (newest first; include problem, root cause,
     fix, files changed — follow the existing format).
   - Significant decision → add to [DECISIONS.md](DECISIONS.md) (and an
     [adr/](adr/) record if it warrants one).
5. **Commit** with a clear message. The changelog already references commit hashes and
   branches; keep that linkage easy to follow.

## Commit / changelog conventions

The CHANGELOG is the project's narrative history and is unusually detailed by design:
each entry states the **problem**, **root cause**, **fix**, and **files changed**.
Preserve that quality — it is how future contributors (and AI assistants) understand
*why* the code looks the way it does.

## Things that are easy to get wrong

- Don't flip the positive label — `Yellow_Bubble` = 1 (see CHANGELOG 2026-04-16).
- Don't "simplify" the camera RGB/BGR + PIL-encode path — it fixes real Pi bugs (see
  [CAMERA.md](CAMERA.md)).
- Don't remove the hard cap of 9 or compute MPN for a non-9 count.
- Don't let DB persistence errors crash `/predict`.
- Start the server from the repo root so `best.pt`, `templates/`, and `static/`
  resolve.

## Reporting bugs / proposing changes

Describe the observed behavior, expected behavior, and steps to reproduce. If it's a
Pi-specific issue, include the OS/compositor and camera module. For larger proposals,
sketch the approach against [ARCHITECTURE.md](ARCHITECTURE.md) and note any decision
in [DECISIONS.md](DECISIONS.md).
