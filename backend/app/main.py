from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import create_db_and_tables

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"
DASHBOARD_PATH = STATIC_DIR / "dashboard.html"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend scaffold for Fitbit segment ingestion, prediction, and Dify analysis.",
)


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_PATH)


@app.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api/v1")
