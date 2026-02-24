import logging

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api
from .db.database import init_db, RESULTS_DIR
from .mpn.mpn_lookup import load_mpn_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="VialVision", version="1.0.0")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# 1. Load MPN lookup table into memory
load_mpn_table()

# 2. Initialise SQLite database + create data/ directories
#    Also runs the startup pruning pass in case we're over MAX_HISTORY
init_db()

logger.info("VialVision startup complete.")


# ---------------------------------------------------------------------------
# Static file mounts
# ---------------------------------------------------------------------------

# Frontend assets (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Saved annotated images — served at /results/<filename>
# RESULTS_DIR is created by init_db() so it always exists by this point.
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(api.router)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)