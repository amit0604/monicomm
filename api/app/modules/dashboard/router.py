"""Dashboard REST API, mounted at /api/v1/dashboard."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.dashboard import service
from app.modules.dashboard.models import (
    DataSource,
    DeviceList,
    DeviceStatus,
    DeviceType,
    DeviceView,
    EventList,
    SeverityGroup,
    Summary,
)


def source_or_503() -> DataSource:
    try:
        return service.get_source()
    except service.NoDataSource:
        raise HTTPException(503, "no_data_source") from None


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
SourceDep = Annotated[DataSource, Depends(source_or_503)]
Search = Annotated[str, Query(max_length=200)]


@router.get("/summary")
def summary(source: SourceDep) -> Summary:
    return service.summary(source)


@router.get("/devices")
def devices(
    source: SourceDep,
    q: Search = "",
    status: DeviceStatus | Literal["", "disconnected"] = "",
    type: DeviceType | Literal[""] = "",
    vendor: Search = "",
) -> DeviceList:
    return service.list_devices(source, q, status, type, vendor)


@router.get("/devices/{device_id}")
def device(source: SourceDep, device_id: str) -> DeviceView:
    view = service.device_view(source, device_id)
    if view is None:
        raise HTTPException(404, "device not found")
    return view


@router.get("/events")
def events(
    source: SourceDep,
    q: Search = "",
    severity: SeverityGroup | Literal[""] = "",
    kind: Literal["", "syslog", "trap"] = "",
) -> EventList:
    return service.list_events(source, q, severity, kind)
