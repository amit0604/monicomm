"""Change impact analysis REST API, mounted at /api/v1/analyzer/impact. Simulation only."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.modules.analyzer import parse as parser
from app.modules.analyzer import service
from app.modules.analyzer.models import (
    Change,
    Report,
    ReportSummary,
    Topology,
    TopologySource,
    UnknownTarget,
)
from app.modules.analyzer.simulate import simulate
from app.modules.analyzer.store import ReportStore


def source_or_503() -> TopologySource:
    try:
        return service.get_source()
    except service.NoDataSource:
        raise HTTPException(503, "no_data_source") from None


router = APIRouter(prefix="/api/v1/analyzer/impact", tags=["analyzer"])
SourceDep = Annotated[TopologySource, Depends(source_or_503)]
StoreDep = Annotated[ReportStore, Depends(service.get_store)]


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ParseOut(BaseModel):
    change: Change


class ReportIn(BaseModel):
    change: Change


@router.get("/topology")
def topology(source: SourceDep) -> Topology:
    return source.topology()


@router.post("/parse")
async def parse(body: ParseIn, source: SourceDep) -> ParseOut:
    try:
        change = await parser.parse(body.text, source.topology())
    except parser.Unparsed as e:
        raise HTTPException(422, f"unparsed: {e}") from None
    except parser.ModelUnavailable:
        raise HTTPException(503, "model_unavailable") from None
    return ParseOut(change=change)


@router.post("/reports", status_code=201)
def create_report(body: ReportIn, source: SourceDep, store: StoreDep) -> Report:
    try:
        report = simulate(source.topology(), body.change)
    except UnknownTarget as e:
        raise HTTPException(422, str(e) or "unknown device or interface") from None
    store.save(report)
    return report


@router.get("/reports")
def list_reports(store: StoreDep) -> list[ReportSummary]:
    return store.list()


@router.get("/reports/{report_id}")
def get_report(report_id: str, store: StoreDep) -> Report:
    report = store.get(report_id)
    if report is None:
        raise HTTPException(404, "report not found")
    return report
