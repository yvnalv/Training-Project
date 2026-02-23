from pathlib import Path
import csv

# Path to CSV (safe for local, Docker, RPi)
MPN_TABLE_PATH = Path(__file__).parent / "mpn_table.csv"

# Internal lookup dict
# {
#   "Pxyz": { "mpn": str, "low": str, "high": str }
# }
_MPN_TABLE = {}


def load_mpn_table():
    """
    Load MPN table CSV into memory.
    Must be called once at startup.
    """
    global _MPN_TABLE
    _MPN_TABLE.clear()

    with open(MPN_TABLE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row["pattern"].strip()
            _MPN_TABLE[key] = {
                "mpn": row["mpn_per_g"],
                "low": row["ci_low"],
                "high": row["ci_high"],
            }


def lookup_mpn(x: int, y: int, z: int):
    """
    Lookup MPN result from positive tube counts.

    Args:
        x: positives at 0.1 g (0–3)
        y: positives at 0.01 g (0–3)
        z: positives at 0.001 g (0–3)

    Returns:
        dict: { pattern, mpn, low, high }
    """

    key = f"P{x}{y}{z}"

    if key not in _MPN_TABLE:
        # Instead of crashing system, return safe fallback
        return {
            "pattern": key,
            "mpn": None,
            "low": None,
            "high": None,
        }

    return {
        "pattern": key,
        **_MPN_TABLE[key],
    }