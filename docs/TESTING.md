# Testing

> **Current state:** there is **no automated test suite**. Verification is manual
> (run the app and exercise the flows). The two root scripts `test_api.py` and
> `test_local.py` are **stale** — they call an old `inference.run_inference(...)`
> signature and a non-existent `zidane.jpg`, and predate the MPN pipeline. Treat them
> as historical, not as a working test harness. Adding real tests is a Phase-1
> roadmap item ([ROADMAP.md](ROADMAP.md)).

## Manual verification

### 1. Server starts
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# expect logs: MPN table loaded, Database ready, "VialVision startup complete."
curl -k https://localhost:8000/health   # {"status":"ok","model":"best.pt"}
```

### 2. Image upload → MPN
- Open the app, upload a clear photo of a 9-tube rack.
- Expect: 9 boxes, `1`/`0` labels, a tube table, an MPN value + 95 % CI + risk level.
- Try an image that yields ≠ 9 tubes → expect MPN shown as `N/A` (no crash), result
  still recorded in History.

### 3. Live stream
- **Client mode** (desktop/phone): Stream view → Start → annotated frames update.
- **Server mode** (Pi/USB): set camera source to Server → Start → frames from the
  device camera.
- Adjust the confidence threshold → detections change accordingly.

### 4. History
- Confirm the new prediction appears, open the detail modal, delete it (image removed
  from `data/results/`), and export CSV.

### 5. Settings persistence
- Change FPS/resolution/flip/confidence, reload the page → values are restored from
  the server.

### 6. Raspberry Pi
- Color is correct (no blue/red swap), framing is not over-zoomed, autostart opens
  Chromium fullscreen after boot. See
  [../raspberry_pi_startup_guide.md](../raspberry_pi_startup_guide.md).

## Recommended automated tests (when added)

Pure functions in `app/inference.py` and `app/mpn/mpn_lookup.py` are the easiest,
highest-value targets (no I/O, deterministic):

| Target | Cases |
|---|---|
| `suppress_duplicate_tubes` | overlapping boxes deduped; stacked duplicates deduped; > 9 capped to top-9; left-to-right ordering |
| `detections_to_tubes` | `Yellow_Bubble`→1 / else→0; raises on ≠ 9 |
| `tubes_to_xyz` | correct group sums |
| `lookup_mpn` | known pattern returns table values; unknown returns `None`s, no raise |
| `_compute_mpn` (api) | `total_count != 9` → all `None`/`[]`; `== 9` → full fields |
| `_safe_json` (queries) | valid JSON parsed; bad JSON → fallback |

Suggested tooling: `pytest`. Keep tests offline (don't require a camera or GPU); the
model load can be mocked or the pure helpers tested directly without invoking YOLO.

## Verifying via the run/verify skills

You can also use the harness `/run` or `/verify` skills to launch the app and confirm
a change behaves as expected end-to-end.
