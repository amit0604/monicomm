"""Mapper data shapes: devices are nodes, physical or logical links are edges between two ports."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from app.modules.dashboard.models import DeviceStatus, DeviceType, Source

Medium = Literal["fiber", "copper", "wireless", "wan"]
LinkStatus = Literal["up", "degraded", "down", "unknown"]
# Why a link has its status. None when the inventory shows both ports up and healthy.
# "reported": no SNMP port on either side, so the status is what the link's controller reports.
LinkReason = Literal[
    "device_offline",
    "port_down",
    "not_polled",
    "high_utilization",
    "errors",
    "no_port_data",
    "reported",
]
MEDIUMS: tuple[Medium, ...] = ("fiber", "copper", "wireless", "wan")
LINK_STATUSES: tuple[LinkStatus, ...] = ("up", "degraded", "down", "unknown")


class LinkEnd(BaseModel):
    """One side of a link as a neighbor table reports it: the device's name and its port."""

    device: str
    port: str


class LinkRecord(BaseModel):
    """A row of the link list. Status is worked out from the inventory, not stored here."""

    a: LinkEnd
    b: LinkEnd
    medium: Medium
    speed_mbps: int | None = None
    # Links with no SNMP port on either side (radios, VPN tunnels): what their controller reports.
    reported_status: LinkStatus | None = None


class LinkSource(Protocol):
    source: Source

    def links(self) -> list[LinkRecord]: ...


class Node(BaseModel):
    id: str
    name: str
    ip: str
    type: DeviceType
    status: DeviceStatus
    vendor: str | None
    model: str | None
    site: str | None


class Endpoint(BaseModel):
    device_id: str
    port: str


class Link(BaseModel):
    id: str
    a: Endpoint
    b: Endpoint
    medium: Medium
    speed_mbps: int | None
    status: LinkStatus
    reason: LinkReason | None


class Topology(BaseModel):
    source: Source
    collected_at: datetime
    nodes: list[Node]
    links: list[Link]
    # Links whose devices are not in the inventory. They are left off the map, never guessed.
    unresolved_links: int
