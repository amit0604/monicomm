"""Live link list from the collectors' LLDP neighbor tables, and the dev-only demo + live mix."""

from app.core import live_snmp
from app.core.snmp_names import ifkey, remote_port, short_name
from app.modules.dashboard.models import Source
from app.modules.mapper.models import LinkEnd, LinkRecord, LinkSource


def _remote_port(remote: live_snmp.LiveDevice | None, n: live_snmp.Neighbor) -> str:
    """The remote device's ifName for the neighbor's port, else what LLDP says.

    Same rules as the Investigator (app.core.snmp_names): a MAC or bare number is no name, and
    "Gi1/0/1" matches "GigabitEthernet1/0/1"."""
    named = remote_port(n.port_id, n.port_desc)
    if remote is not None and named:
        key = ifkey(named)
        for p in remote.ports:
            if named == p.index or key in (ifkey(p.name), ifkey(p.alias)):
                return p.name
    return named or "?"


def links_from(devices: list[live_snmp.LiveDevice]) -> list[LinkRecord]:
    by_name = {short_name(d.name): d for d in devices if d.name}
    by_ip = {d.ip: d for d in devices}
    seen: set[frozenset[tuple[str, str]]] = set()
    links = []
    for d in devices:
        if not d.name:
            continue
        ports = {p.index: p for p in d.ports}
        for n in d.neighbors:
            local = ports.get(n.local_port)
            remote = by_name.get(short_name(n.sys_name)) if n.sys_name else None
            remote = remote or by_ip.get(n.chassis_id)
            a = LinkEnd(device=d.name, port=local.name if local else n.local_port)
            b_name = remote.name if remote and remote.name else n.sys_name or n.chassis_id
            b = LinkEnd(device=b_name, port=_remote_port(remote, n))
            key = frozenset({(a.device, a.port), (b.device, b.port)})
            if key in seen:  # the other side reports the same link
                continue
            seen.add(key)
            # LLDP doesn't say copper or fiber; copper is a placeholder until the ifType mapping
            links.append(
                LinkRecord(
                    a=a, b=b, medium="copper", speed_mbps=local.speed_mbps if local else None
                )
            )
    return links


class LiveLinks:
    source: Source = "live"

    def __init__(self, ingest_dir: str) -> None:
        self.ingest_dir = ingest_dir

    def links(self) -> list[LinkRecord]:
        return links_from(live_snmp.snapshot(self.ingest_dir))


class CombinedLinks:
    """Demo links plus live ones; labelled "demo" like the combined inventory."""

    source: Source = "demo"

    def __init__(self, demo: LinkSource, live: LinkSource) -> None:
        self.demo = demo
        self.live = live

    def links(self) -> list[LinkRecord]:
        return self.demo.links() + self.live.links()
