"""Monicomm API entry point."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.analyzer.router import router as analyzer_router
from app.modules.chat.router import router as chat_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.investigator.router import router as investigator_router
from app.modules.pcap.router import router as pcap_router

MODULES = [
    {"id": "dashboard", "name": "Dashboard"},
    {"id": "chat", "name": "Chat AI"},
    {"id": "analyzer", "name": "Analyzer"},
    {"id": "investigator", "name": "Incident Investigator"},
    {"id": "mapper", "name": "Mapper"},
    {"id": "pcap", "name": "Chatchup"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    task = None
    if settings.investigator_ingest_dir:
        # imported here so the app still starts if the correlator is being changed
        from app.modules.investigator.correlate import Correlator
        from app.modules.investigator.listener import Listener
        from app.modules.investigator.store import IncidentStore

        listener = Listener(
            settings.investigator_ingest_dir,
            settings.investigator_data_dir,
            Correlator(window_s=settings.investigator_window_s),
            IncidentStore(settings.investigator_data_dir),
            settings.investigator_poll_s,
        )
        task = asyncio.create_task(listener.run())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Monicomm API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(investigator_router)
app.include_router(pcap_router, prefix="/api/v1/pcap")
app.include_router(dashboard_router)
app.include_router(chat_router)
app.include_router(analyzer_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().env}


@app.get("/api/v1/modules")
def modules() -> list[dict[str, str]]:
    return MODULES
