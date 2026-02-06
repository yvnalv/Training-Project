from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from . import api
from .mpn.mpn_lookup import load_mpn_table

app = FastAPI()

# Load MPN table once at startup
load_mpn_table()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API router
app.include_router(api.router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
