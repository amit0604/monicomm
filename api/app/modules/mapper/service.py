"""Mapper: joins the link list with the device inventory into one topology.

Devices and their ports come from the Dashboard's data source (its public methods only), so the
map shows the same status as the Dashboard. A link's status is worked out from both of its ports.
"""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.graph import util_status
from app.modules.dashboard.models import DataSource, Device, Interface
from app.modules.mapper.demo import DemoLinks
from app.modules.mapper.live import CombinedLinks, LiveLinks
from app.modules.mapper.models import (
    Endpoint,
    Link,
    LinkEnd,
    LinkReason,
    LinkRecord,
    LinkSource,
    LinkStatus,
    Node,
    Topology,
)


class NoLinkSource(RuntimeError):
    """No link source is configured."""


def get_link_source() -> LinkSource:
    """Same rule as the Dashboard's get_source(): demo (dev only), live, or in dev both."""
    settings = get_settings()
    ingest = settings.investigator_ingest_dir
    if settings.demo_data and settings.env == "dev":
        return CombinedLinks(DemoLinks(), LiveLinks(ingest)) if ingest else DemoLinks()
    if ingest:
        return LiveLinks(ingest)
    raise NoLinkSource


def _hot(port: Interface, util_warn: float) -> bool:
    """The shared link-load rule (app.core.graph.util_status); the inventory reports percent."""
    return any(
        u is not None and util_status(u / 100, util_warn) in ("warning", "critical")
        for u in (port.in_util_pct, port.out_util_pct)
    )


def link_status(
    devices: tuple[Device, Device],
    ports: tuple[Interface | None, Interface | None],
    reported: LinkStatus | None,
    util_warn: float,
) -> tuple[LinkStatus, LinkReason | None]:
    """Worst finding wins. Anything the inventory can't see is "unknown", never "up"."""
    seen = [p for p in ports if p is not None]
    if any(d.status == "offline" for d in devices):
        return "down", "device_offline"
    if any(p.oper_status == "down" for p in seen):
        return "down", "port_down"
    if any(d.status == "suspected_offline" for d in devices):
        return "unknown", "not_polled"
    if not seen:
        return (reported, "reported") if reported else ("unknown", "no_port_data")
    if any(_hot(p, util_warn) for p in seen):
        return "degraded", "high_utilization"
    if any((p.in_errors or 0) + (p.out_errors or 0) > 0 for p in seen):
        return "degraded", "errors"
    return "up", None


def _node(d: Device) -> Node:
    return Node(
        id=d.id,
        name=d.name or d.ip,
        ip=d.ip,
        type=d.type,
        status=d.status,
        vendor=d.vendor,
        model=d.model,
        site=d.site,
    )


def topology(inventory: DataSource, link_source: LinkSource, util_warn: float) -> Topology:
    devices = inventory.devices()
    by_name = {d.name: d for d in devices if d.name}
    ports: dict[str, dict[str, Interface]] = {}

    def port_of(device: Device, name: str) -> Interface | None:
        if device.id not in ports:
            details = inventory.device(device.id)
            ports[device.id] = {i.name: i for i in details.interfaces} if details else {}
        return ports[device.id].get(name)

    links: list[Link] = []
    unresolved = 0
    for record in link_source.links():
        a, b = by_name.get(record.a.device), by_name.get(record.b.device)
        if a is None or b is None:
            unresolved += 1
            continue
        status, reason = link_status(
            (a, b),
            (port_of(a, record.a.port), port_of(b, record.b.port)),
            record.reported_status,
            util_warn,
        )
        links.append(_link(record, a, b, status, reason))

    return Topology(
        source="demo" if "demo" in (inventory.source, link_source.source) else "live",
        collected_at=datetime.now(UTC),
        nodes=[_node(d) for d in devices],
        links=links,
        unresolved_links=unresolved,
    )


def _endpoint(device: Device, end: LinkEnd) -> Endpoint:
    return Endpoint(device_id=device.id, port=end.port)


def _link(
    record: LinkRecord, a: Device, b: Device, status: LinkStatus, reason: LinkReason | None
) -> Link:
    return Link(
        id=f"{a.id}:{record.a.port}|{b.id}:{record.b.port}",
        a=_endpoint(a, record.a),
        b=_endpoint(b, record.b),
        medium=record.medium,
        speed_mbps=record.speed_mbps,
        status=status,
        reason=reason,
    )
