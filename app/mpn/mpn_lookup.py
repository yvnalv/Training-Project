import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to CSV — safe for local, Docker, and RPi
MPN_TABLE_PATH = Path(__file__).parent / "mpn_table.csv"

# Expected columns in the CSV
_REQUIRED_COLUMNS = {"pattern", "mpn_per_g", "ci_low", "ci_high"}

# Internal lookup dict: { "P000": { "mpn": str, "low": str, "high": str }, ... }
_MPN_TABLE: dict = {}


def load_mpn_table():
    """
    Load the MPN lookup table from CSV into memory.
    Must be called once at startup (done in main.py).

    Raises:
        FileNotFoundError: if mpn_table.csv does not exist at the expected path.
        ValueError: if the CSV is missing any required columns.
        RuntimeError: if the CSV is empty or otherwise unreadable.
    """
    global _MPN_TABLE
    _MPN_TABLE.clear()

    # FIX: Catch missing file with a clear, actionable message instead of a
    # raw FileNotFoundError with no context.
    if not MPN_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"MPN table not found at: {MPN_TABLE_PATH}\n"
            f"Make sure 'mpn_table.csv' is present in the same directory as mpn_lookup.py."
        )

    try:
        with open(MPN_TABLE_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # FIX: Validate columns up front so a header typo (e.g. "mpn_per_gram"
            # instead of "mpn_per_g") gives a clear error here rather than a
            # cryptic KeyError somewhere deep in a request handler later.
            if reader.fieldnames is None:
                raise RuntimeError(
                    f"MPN table at {MPN_TABLE_PATH} appears to be empty."
                )

            actual_columns = set(reader.fieldnames)
            missing = _REQUIRED_COLUMNS - actual_columns
            if missing:
                raise ValueError(
                    f"MPN table is missing required column(s): {sorted(missing)}\n"
                    f"Found columns: {sorted(actual_columns)}"
                )

            for row in reader:
                key = row["pattern"].strip()
                _MPN_TABLE[key] = {
                    "mpn": row["mpn_per_g"].strip(),
                    "low": row["ci_low"].strip(),
                    "high": row["ci_high"].strip(),
                }

    except (csv.Error, UnicodeDecodeError) as e:
        raise RuntimeError(
            f"Failed to parse MPN table at {MPN_TABLE_PATH}: {e}"
        ) from e

    logger.info("MPN table loaded: %d patterns from %s.", len(_MPN_TABLE), MPN_TABLE_PATH)


def lookup_mpn(x: int, y: int, z: int) -> dict:
    """
    Look up an MPN result from positive tube counts.

    Args:
        x: positives at 0.1 g dilution (0–3)
        y: positives at 0.01 g dilution (0–3)
        z: positives at 0.001 g dilution (0–3)

    Returns:
        dict with keys: pattern, mpn, low, high.
        If the pattern is not found in the table, mpn/low/high are None
        and a warning is logged — the app keeps running rather than crashing.
    """
    key = f"P{x}{y}{z}"

    if key not in _MPN_TABLE:
        logger.warning(
            "Pattern '%s' not found in MPN table. "
            "This may indicate an invalid tube count combination.",
            key,
        )
        return {"pattern": key, "mpn": None, "low": None, "high": None}

    return {"pattern": key, **_MPN_TABLE[key]}