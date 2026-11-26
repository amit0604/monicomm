"""Dashboard queries. Other modules use these functions, never the data source's internals."""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.modules.dashboard.demo import DemoSource
from app.modules.dashboard.live import CombinedSource, LiveSource
from app.modules.dashboard.models import (
    STATUSES,
    DataSource,
    DeviceCounts,
    DeviceList,
    DeviceView,
    Event,
    EventList,
    Summary,
)

RECENT_EVENTS = 8
DEVICE_EVENTS = 20
MAX_EVENTS = 200


class NoDataSource(RuntimeError):
    """No data source is configured."""


def get_source() -> DataSource:
    """Demo data (dev only, never on a real site), live collector data, or in dev both together."""
    settings = get_settings()
    ingest = settings.investigator_ingest_dir
    if settings.demo_data and settings.env == "dev":
        return CombinedSource(DemoSource(), LiveSource(ingest)) if ingest else DemoSource()
    if ingest:
        return LiveSource(ingest)
    raise NoDataSource


def without_live(source: DataSource) -> DataSource | None:
    """The demo-only part of a source, for a model outside the closed network. None = no demo."""
    if isinstance(source, CombinedSource):
        return source.demo
    return source if source.source == "demo" else None


def newest_first(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: e.received_at, reverse=True)


def _matches(query: str, *values: str | None) -> bool:
    needle = query.strip().lower()
    return any(needle in v.lower() for v in values if v)


def summary(source: DataSource) -> Summary:
    devices = source.devices()
    counts = {s: sum(d.status == s for d in devices) for s in STATUSES}
    return Summary(
        source=source.source,
        generated_at=datetime.now(UTC),
        devices=DeviceCounts(total=len(devices), by_status=counts),
        open_alerts=source.open_alerts(),
        recent_events=newest_first(source.events())[:RECENT_EVENTS],
    )


def list_devices(
    source: DataSource, q: str = "", status: str = "", type_: str = "", vendor: str = ""
) -> DeviceList:
    devices = source.devices()
    wanted = ("offline", "suspected_offline") if status == "disconnected" else (status,)
    items = [
        d
        for d in devices
        if (not status or d.status in wanted)
        and (not type_ or d.type == type_)
        and (not vendor or d.vendor == vendor)
        and (not q or _matches(q, d.name, d.ip, d.vendor, d.model))
    ]
    vendors = sorted({d.vendor for d in devices if d.vendor})
    return DeviceList(source=source.source, total=len(devices), vendors=vendors, items=items)


def device_view(source: DataSource, device_id: str) -> DeviceView | None:
    device = source.device(device_id)
    if device is None:
        return None
    events = [e for e in source.events() if e.device_id == device_id]
    return DeviceView(
        source=source.source, device=device, events=newest_first(events)[:DEVICE_EVENTS]
    )


def list_events(source: DataSource, q: str = "", severity: str = "", kind: str = "") -> EventList:
    events = source.events()
    items = [
        e
        for e in events
        if (not severity or e.severity_group == severity)
        and (not kind or e.kind == kind)
        and (not q or _matches(q, e.message, e.device_name, e.source_ip))
    ]
    return EventList(
        source=source.source, total=len(events), items=newest_first(items)[:MAX_EVENTS]
    )
