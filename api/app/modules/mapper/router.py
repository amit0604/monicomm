"""Mapper REST API, mounted at /api/v1/mapper. Read-only."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.dashboard.router import SourceDep
from app.modules.mapper import service
from app.modules.mapper.models import LinkSource, Topology


def links_or_503() -> LinkSource:
    try:
        return service.get_link_source()
    except service.NoLinkSource:
        raise HTTPException(503, "no_data_source") from None


router = APIRouter(prefix="/api/v1/mapper", tags=["mapper"])
LinksDep = Annotated[LinkSource, Depends(links_or_503)]


@router.get("/topology")
def topology(inventory: SourceDep, links: LinksDep) -> Topology:
    return service.topology(inventory, links)
