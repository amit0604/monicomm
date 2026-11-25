"""Dashboard data shapes and the one seam to where data comes from.

A real source (the database fed by the collectors) implements DataSource; routes and UI stay as is.
"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

Source = Literal["demo", "live"]
DeviceStatus = Literal["online", "warning", "critical", "suspected_offline", "offline"]
DeviceType = Literal["router", "switch", "firewall", "server", "access_point", "unknown"]
Severity = Literal["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
SeverityGroup = Literal["critical", "warning", "info", "neutral"]
AlertCode = Literal["device_unreachable", "interface_down", "high_temperature", "high_utilization"]

STATUSES: tuple[DeviceStatus, ...] = (
    "online",
    "warning",
    "critical",
    "suspected_offline",
    "offline",
)


class Device(BaseModel):
    id: str
    name: str | None
    ip: str
    vendor: str | None
    model: str | None
    type: DeviceType
    status: DeviceStatus
    os_version: str | None
    serial: str | None
    site: str | None
    last_poll_at: datetime | None


class Interface(BaseModel):
    if_index: str
    name: str
    alias: str | None
    admin_status: Literal["up", "down"]
    oper_status: Literal["up", "down"]
    speed_mbps: int | None
    in_util_pct: float | None
    out_util_pct: float | None
    in_errors: int | None
    out_errors: int | None


class Metrics(BaseModel):
    cpu_pct: float | None
    memory_pct: float | None
    temperature_c: float | None
    uptime_seconds: int | None


class DeviceDetails(Device):
    interfaces: list[Interface]
    metrics: Metrics


class Event(BaseModel):
    id: str
    kind: Literal["syslog", "trap"]
    severity: Severity | None  # traps carry none
    severity_group: SeverityGroup
    device_id: str | None
    device_name: str | None
    source_ip: str
    received_at: datetime
    message: str


class Alert(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    code: AlertCode
    device_id: str
    device_name: str | None
    opened_at: datetime


class DeviceCounts(BaseModel):
    total: int
    by_status: dict[DeviceStatus, int]


class Summary(BaseModel):
    source: Source
    generated_at: datetime
    devices: DeviceCounts
    open_alerts: list[Alert]
    recent_events: list[Event]


class DeviceList(BaseModel):
    source: Source
    total: int
    vendors: list[str]
    items: list[Device]


class DeviceView(BaseModel):
    source: Source
    device: DeviceDetails
    events: list[Event]


class EventList(BaseModel):
    source: Source
    total: int
    items: list[Event]


class DataSource(Protocol):
    source: Source

    def devices(self) -> list[Device]: ...
    def device(self, device_id: str) -> DeviceDetails | None: ...
    def events(self) -> list[Event]: ...
    def open_alerts(self) -> list[Alert]: ...


def severity_group(severity: Severity | None) -> SeverityGroup:
    """Mapping from PROJECT.md section 6A. Events with no severity (traps) are neutral."""
    if severity in ("emerg", "alert", "crit"):
        return "critical"
    if severity in ("err", "warning"):
        return "warning"
    if severity in ("notice", "info"):
        return "info"
    return "neutral"
