"""Monicomm API entry point."""

from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.chat.router import router as chat_router
from app.modules.dashboard.router import router as dashboard_router

MODULES = [
    {"id": "dashboard", "name": "Dashboard"},
    {"id": "chat", "name": "Chat AI"},
    {"id": "analyzer", "name": "Analyzer"},
    {"id": "investigator", "name": "Incident Investigator"},
    {"id": "mapper", "name": "Mapper"},
    {"id": "pcap", "name": "Chatchup"},
]

app = FastAPI(
    title="Monicomm API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


app.include_router(dashboard_router)
app.include_router(chat_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


@app.get("/api/v1/modules")
def modules() -> list[dict[str, str]]:
    return MODULES
