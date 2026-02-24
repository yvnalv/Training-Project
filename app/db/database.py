"""
database.py
-----------
SQLite connection, schema creation, and maintenance (auto-delete).

Layout on disk:
    <project_root>/
    └── data/
        ├── vialvision.db      ← database file
        └── results/           ← annotated JPEG images
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Resolve from project root (two levels up from app/db/)
_PROJECT_ROOT  = Path(__file__).parent.parent.parent
DATA_DIR       = _PROJECT_ROOT / "data"
RESULTS_DIR    = DATA_DIR / "results"
DB_PATH        = DATA_DIR / "vialvision.db"

# Maximum number of prediction records to keep.
# When exceeded, the oldest records (and their image files) are pruned.
MAX_HISTORY: int = 500


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    filename    TEXT,
    total_tubes INTEGER,
    pattern     TEXT,
    mpn         TEXT,
    ci_low      TEXT,
    ci_high     TEXT,
    tubes       TEXT,       -- JSON array  e.g. "[1,0,0,0,0,0,0,0,0]"
    detections  TEXT,       -- JSON array  full detection list
    image_path  TEXT        -- relative path e.g. "data/results/abc123.jpg"
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_created_at ON predictions (created_at DESC);
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection with sensible defaults.
    Using check_same_thread=False is safe here because FastAPI's async
    endpoints are run on a single thread by default (via the event loop),
    and we never share a connection object between coroutines.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent read perf
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Initialisation  (called once at startup from main.py)
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create directories, initialise the database schema, and run the
    startup cleanup pass to prune any records that exceed MAX_HISTORY.
    """
    # Ensure data/ and data/results/ exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_INDEX)
        conn.commit()
        logger.info("Database ready at %s", DB_PATH)
    finally:
        conn.close()

    # Prune on startup in case a previous run left us over the limit
    _prune_oldest()


# ---------------------------------------------------------------------------
# Auto-delete / pruning
# ---------------------------------------------------------------------------

def _prune_oldest() -> None:
    """
    Delete the oldest records (and their image files on disk) so the
    total count stays at or below MAX_HISTORY.
    Called after every INSERT and once at startup.
    """
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        excess = count - MAX_HISTORY

        if excess <= 0:
            return

        # Fetch the oldest `excess` records so we can delete their images too
        rows = conn.execute(
            "SELECT id, image_path FROM predictions "
            "ORDER BY created_at ASC LIMIT ?",
            (excess,)
        ).fetchall()

        ids_to_delete = [r["id"] for r in rows]

        # Delete image files from disk
        for row in rows:
            if row["image_path"]:
                img_file = _PROJECT_ROOT / row["image_path"]
                try:
                    img_file.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Could not delete image file %s: %s", img_file, e)

        # Delete DB rows
        conn.execute(
            f"DELETE FROM predictions WHERE id IN "
            f"({','.join('?' * len(ids_to_delete))})",
            ids_to_delete
        )
        conn.commit()
        logger.info("Pruned %d old record(s) to stay within MAX_HISTORY=%d.", excess, MAX_HISTORY)

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Called from queries.py after every INSERT
# ---------------------------------------------------------------------------

def maybe_prune() -> None:
    """Public hook for queries.py to call after saving a new record."""
    _prune_oldest()