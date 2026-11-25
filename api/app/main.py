"""Monicomm API entry point."""

from fastapi import FastAPI

from app.core.config import get_settings

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


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


@app.get("/api/v1/modules")
def modules() -> list[dict[str, str]]:
    return MODULES
