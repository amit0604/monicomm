"""Change impact analysis data shapes (plans/change-impact/plan.md, "Contracts").

Owned by the conductor: builders code against these, nobody changes them without updating the plan.
"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

Source = Literal["demo", "live"]
NodeType = Literal[
    "switch",
    "router",
    "firewall",
    "server",
    "access_point",
    "host",
    "vm",
    "container",
    "unknown",
]
Role = Literal["core", "distribution", "access", "edge", "other"]
ChangeKind = Literal["interface_down", "device_down"]
Risk = Literal["low", "medium", "high"]
ItemStatus = Literal["critical", "warning", "neutral"]  # neutral = unknown, never "ok"


class Node(BaseModel):
    id: str
    type: NodeType
    role: Role
    vendor: str | None = None
    site: str | None = None
    interfaces: list[str] = []
    endpoints: int = 0  # hosts seen behind this node (MAC table)
    services: list[str] = []  # e.g. ["dns"]


class End(BaseModel):
    device: str
    interface: str | None


class Link(BaseModel):
    id: str
    a: End
    b: End
    capacity_mbps: int | None
    util_pct: float | None  # None = not polled / unknown
    hourly_util_pct: list[float] | None = Field(default=None, min_length=24, max_length=24)


class Topology(BaseModel):
    source: Source
    as_of: datetime
    nodes: list[Node]
    links: list[Link]


class Change(BaseModel):
    kind: ChangeKind
    device: str = Field(min_length=1, max_length=200)
    interface: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _interface_needed(self) -> "Change":
        if self.kind == "interface_down" and not self.interface:
            raise ValueError("interface_down needs an interface")
        return self


class Affected(BaseModel):
    kind: Literal["node", "endpoints", "service", "link"]
    id: str
    label: str
    detail: str
    status: ItemStatus


class LinkLoad(BaseModel):
    link: str
    label: str
    util_before: float | None
    util_after: float | None


class Reroute(BaseModel):
    link: str  # the link that goes away
    via: list[str]  # link ids of the alternate path, [] = no alternate path
    load_mbps: float | None
    after: list[LinkLoad]


class Spof(BaseModel):
    kind: Literal["node", "link"]
    id: str
    label: str


class Window(BaseModel):
    start_hour: int
    end_hour: int
    avg_util_pct: float


class Report(BaseModel):
    id: str
    created_at: datetime
    source: Source
    data_as_of: datetime
    change: Change
    title: str
    risk: Risk
    summary: str
    affected: list[Affected]
    reroutes: list[Reroute]
    new_spofs: list[Spof]
    maintenance_window: Window | None
    rollback: str
    warnings: list[str]
    unknowns: list[str]
    data_used: list[str]


class ReportSummary(BaseModel):
    id: str
    created_at: datetime
    title: str
    risk: Risk
    source: Source


class TopologySource(Protocol):
    def topology(self) -> Topology: ...


class UnknownTarget(ValueError):
    """The change names a device or interface that isn't in the topology."""
