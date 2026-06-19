from fastapi import FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings

app = FastAPI(title="Nepali Admin Copilot")

# === STEP 1: API routers ===
from app.api import ocr
app.include_router(ocr.router, prefix="/api")

@app.get("/api/config/status")
async def get_config_status():
    from app.schemas import ConfigStatus
    return ConfigStatus(
        ocr_enabled=True,
        translation_enabled=settings.gemini_api_key is not None
    )

# === STEP 2: API dead-end guard ===
# Catches any /api/... path not matched above and returns JSON 404
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def catch_bad_api_requests(path: str):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"API endpoint '/api/{path}' does not exist."
    )

# === STEP 3: Static assets ===
static_dir = "static_dist"
assets_dir = os.path.join(static_dir, "assets")
has_frontend = os.path.isdir(assets_dir) and os.path.isfile(os.path.join(static_dir, "index.html"))
if has_frontend:
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# === STEP 4: SPA catch-all ===
SPA_HTML = os.path.join(static_dir, "index.html") if has_frontend else None

@app.get("/")
@app.get("/{catchall:path}")
async def serve_spa(catchall: str = ""):
    if SPA_HTML and os.path.isfile(SPA_HTML):
        return FileResponse(SPA_HTML)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Frontend build files are missing."
    )
