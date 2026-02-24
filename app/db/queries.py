"""
queries.py
----------
All database read/write operations for the predictions table.

Public API:
    save_prediction(...)      → int (new record id)
    list_predictions(...)     → list[dict]
    delete_prediction(id)     → bool
    export_csv()              → str (CSV text)
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from .database import (
    RESULTS_DIR,
    _PROJECT_ROOT,
    get_connection,
    maybe_prune,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_prediction(
    *,
    filename: str,
    total_tubes: int,
    pattern: str | None,
    mpn: str | None,
    ci_low: str | None,
    ci_high: str | None,
    tubes: list,
    detections: list,
    annotated_image_bytes: bytes,
) -> int:
    """
    Persist one prediction result to SQLite and save the annotated image
    to data/results/.

    Returns:
        The new record's integer id.
    """
    # ---- Save image file ----
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id  = uuid.uuid4().hex[:8]
    image_name = f"{timestamp}_{unique_id}.jpg"
    image_abs  = RESULTS_DIR / image_name
    image_rel  = f"data/results/{image_name}"   # stored in DB; served via /results/

    try:
        image_abs.write_bytes(annotated_image_bytes)
    except OSError as e:
        logger.error("Failed to write image file %s: %s", image_abs, e)
        raise

    # ---- Insert DB row ----
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO predictions
                (filename, total_tubes, pattern, mpn, ci_low, ci_high,
                 tubes, detections, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                total_tubes,
                pattern,
                mpn,
                ci_low,
                ci_high,
                json.dumps(tubes),
                json.dumps(detections),
                image_rel,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        logger.info("Saved prediction id=%d  pattern=%s  image=%s", new_id, pattern, image_name)
    finally:
        conn.close()

    # Prune oldest records if we're over MAX_HISTORY
    maybe_prune()

    return new_id


# ---------------------------------------------------------------------------
# List  (paginated)
# ---------------------------------------------------------------------------

def list_predictions(limit: int = 20, offset: int = 0) -> list[dict]:
    """
    Return a page of predictions, newest first.

    Args:
        limit:  Number of records per page  (max capped at 100).
        offset: Number of records to skip.

    Returns:
        List of dicts with all columns. tubes / detections are parsed back
        to Python lists so the caller gets native objects, not JSON strings.
    """
    limit = min(limit, 100)   # hard cap — never let a client ask for 10 000 rows

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, filename, total_tubes,
                   pattern, mpn, ci_low, ci_high,
                   tubes, detections, image_path
            FROM predictions
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            # Parse JSON strings back to Python lists
            d["tubes"]      = _safe_json(d.get("tubes"), fallback=[])
            d["detections"] = _safe_json(d.get("detections"), fallback=[])
            results.append(d)

        return results

    finally:
        conn.close()


def count_predictions() -> int:
    """Return total number of prediction records."""
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_prediction(record_id: int) -> bool:
    """
    Delete a single prediction record and its image file from disk.

    Returns:
        True  if the record existed and was deleted.
        False if no record with that id was found.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT image_path FROM predictions WHERE id = ?", (record_id,)
        ).fetchone()

        if row is None:
            logger.warning("delete_prediction: id=%d not found.", record_id)
            return False

        # Delete image file first
        if row["image_path"]:
            img_file = _PROJECT_ROOT / row["image_path"]
            try:
                img_file.unlink(missing_ok=True)
            except OSError as e:
                # Log but continue — we still want to remove the DB row
                logger.warning("Could not delete image file %s: %s", img_file, e)

        conn.execute("DELETE FROM predictions WHERE id = ?", (record_id,))
        conn.commit()
        logger.info("Deleted prediction id=%d", record_id)
        return True

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def export_csv() -> str:
    """
    Export all prediction records as a CSV string, newest first.

    Columns exported (image path excluded — not useful outside the device):
        id, created_at, filename, total_tubes, pattern, mpn, ci_low, ci_high, tubes
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, filename, total_tubes,
                   pattern, mpn, ci_low, ci_high, tubes
            FROM predictions
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id", "created_at", "filename", "total_tubes",
        "pattern", "mpn_per_g", "ci_low", "ci_high", "tubes"
    ])

    # Rows — tubes stays as a compact JSON string in the CSV (e.g. [1,0,0,...])
    for row in rows:
        writer.writerow([
            row["id"],
            row["created_at"],
            row["filename"],
            row["total_tubes"],
            row["pattern"],
            row["mpn"],
            row["ci_low"],
            row["ci_high"],
            row["tubes"],
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_json(value: str | None, fallback):
    """Parse a JSON string, returning fallback on any error."""
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse JSON value: %r", value)
        return fallback