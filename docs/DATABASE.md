# Database

VialVision uses **SQLite** (WAL mode) with the raw `sqlite3` module — no ORM. The
database file and saved images live under `data/`:

```
<project_root>/data/
├── vialvision.db      ← SQLite database
└── results/           ← annotated JPEG images (one per saved prediction)
```

Paths are resolved from the project root in `app/db/database.py`:
`_PROJECT_ROOT = Path(__file__).parent.parent.parent`.

## Connection

`get_connection()` opens a connection with:

```python
sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row          # rows behave like dicts
conn.execute("PRAGMA journal_mode=WAL") # better concurrent read perf
conn.execute("PRAGMA foreign_keys=ON")
```

`check_same_thread=False` is safe here because FastAPI's async endpoints run on the
event-loop thread and a connection is never shared between coroutines — each call
opens and closes its own connection.

## Schema

### `predictions`

```sql
CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename    TEXT,
    total_tubes INTEGER,
    pattern     TEXT,
    mpn         TEXT,
    ci_low      TEXT,
    ci_high     TEXT,
    tubes       TEXT,       -- JSON array, e.g. "[1,0,0,1,1,0,0,0,0]"
    detections  TEXT,       -- JSON array of detection dicts
    image_path  TEXT        -- relative path, e.g. "data/results/abc123.jpg"
);

CREATE INDEX IF NOT EXISTS idx_created_at ON predictions (created_at DESC);
```

Notes:
- MPN-related columns (`pattern`, `mpn`, `ci_low`, `ci_high`) and `tubes` are stored
  even when `total_tubes != 9` — in that case they are `NULL` / `[]`. Partial
  results are still recorded.
- `tubes` and `detections` are JSON-encoded on write and parsed back on read via
  `_safe_json()`, which returns a fallback (`[]`) rather than raising on bad data.
- `mpn`, `ci_low`, `ci_high` are stored as **TEXT** because reference values can be
  non-numeric strings (e.g. `"<3.0"`, `">1100"`, `"–"`).

### `settings`

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Key-value store for UI preferences. Allowed keys (enforced in the API layer):
`cameraMode`, `fps`, `resolution`, `confidence`, `flipHorizontal`. Upserted with
`INSERT ... ON CONFLICT(key) DO UPDATE SET value = excluded.value`.

## Lifecycle

`init_db()` (called once from `main.py` at startup):
1. Creates `data/` and `data/results/`.
2. Creates both tables and the index (idempotent — `IF NOT EXISTS`).
3. Runs `_prune_oldest()` once in case a previous run left the table over capacity.

## Auto-pruning

`MAX_HISTORY = 500`. Pruning runs on startup and after **every** INSERT
(`maybe_prune()` → `_prune_oldest()`):
1. Count rows; compute `excess = count - MAX_HISTORY`.
2. If `excess > 0`, select the oldest `excess` rows by `created_at ASC`.
3. Delete each row's image file from disk (`unlink(missing_ok=True)`; a missing or
   unremovable file is logged, not fatal).
4. Delete those rows from the table.

## Write path (`save_prediction`)

1. Build a filename `YYYYMMDD_HHMMSS_<8-hex>.jpg`.
2. Write the annotated JPEG bytes to `data/results/`.
3. INSERT the row (storing the **relative** path `data/results/<name>` so it is
   portable and servable at `/results/<name>`).
4. Call `maybe_prune()`.

A failure writing the image raises (the caller — `/predict` — catches it so the
prediction response still succeeds). See [ERROR_HANDLING.md](ERROR_HANDLING.md).

## Read paths

- `list_predictions(limit, offset)` — newest first, `limit` hard-capped at 100,
  JSON fields parsed back to Python objects.
- `count_predictions()` — total count (used for pagination `total`).
- `export_csv()` — all rows, newest first, columns: `id, created_at, filename,
  total_tubes, pattern, mpn_per_g, ci_low, ci_high, tubes` (image path excluded).

## Backups & operational notes

- The DB is a single file; back it up by copying `data/vialvision.db` (and the WAL/
  SHM sidecar files if present) while the server is stopped.
- Deleting `data/vialvision.db` resets all history and settings; it will be
  recreated empty on next startup.
- There is no connection pool; at the current single-device scale this is fine. If
  throughput ever matters, a pooled or long-lived connection would be the first
  optimization.
