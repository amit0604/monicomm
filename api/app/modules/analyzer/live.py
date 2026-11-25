"""Live topology for change impact analysis, from the collector data the Dashboard also uses."""

from datetime import UTC, datetime

from app.core import live_snmp
from app.modules.analyzer.models import End, Link, Node, Topology, TopologySource
from app.modules.dashboard.live import device_type, vendor
from app.modules.mapper.live import links_from


def _util(*ports: live_snmp.Port | None) -> float | None:
    values = [u for p in ports if p for u in (p.in_util_pct, p.out_util_pct) if u is not None]
    return max(values) if values else None


def topology_from(devices: list[live_snmp.LiveDevice]) -> Topology:
    named = {d.name: d for d in devices if d.name}
    nodes = [
        Node(
            id=name,
            type=device_type(d),
            role="other",  # the collectors don't tell core from access yet
            vendor=vendor(d),
            site=d.location,
            interfaces=sorted(p.name for p in d.ports),
        )
        for name, d in named.items()
    ]
    links = []
    for record in links_from(devices):
        a, b = named.get(record.a.device), named.get(record.b.device)
        if a is None or b is None:  # neighbor not polled: no node to attach it to
            continue
        a_port = next((p for p in a.ports if p.name == record.a.port), None)
        b_port = next((p for p in b.ports if p.name == record.b.port), None)
        links.append(
            Link(
                id=f"live-L{len(links) + 1}",
                a=End(device=a.name or a.ip, interface=record.a.port),
                b=End(device=b.name or b.ip, interface=record.b.port),
                capacity_mbps=record.speed_mbps,
                util_pct=_util(a_port, b_port),
            )
        )
    return Topology(source="live", as_of=datetime.now(UTC), nodes=nodes, links=links)


class LiveTopology:
    source = "live"

    def __init__(self, ingest_dir: str) -> None:
        self.ingest_dir = ingest_dir

    def topology(self) -> Topology:
        return topology_from(live_snmp.snapshot(self.ingest_dir))


class CombinedTopology:
    """Demo topology plus the live one; labelled "demo" like the combined inventory."""

    source = "demo"

    def __init__(self, demo: TopologySource, live: TopologySource) -> None:
        self.demo = demo
        self.live = live

    def topology(self) -> Topology:
        demo, live = self.demo.topology(), self.live.topology()
        return Topology(
            source="demo",
            as_of=datetime.now(UTC),
            nodes=demo.nodes + live.nodes,
            links=demo.links + live.links,
        )
