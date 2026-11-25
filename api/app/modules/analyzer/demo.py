"""DEVELOPMENT-ONLY DEMO DATA. Nothing here is real telemetry.

Same DEMO- devices as the Dashboard demo (dashboard/demo.py); addresses there are RFC 5737.
The service layer only uses this with MONICOMM_DEMO_DATA=true and MONICOMM_ENV=dev.

Shape: a redundant core pair, both dist switches dual-homed to both cores, access switches
dual-homed to dist except DEMO-acc-sw-01 (single-homed), firewall -> edge router -> WAN MX
toward the WAN on each side, DNS/NTP servers on DEMO-acc-sw-02.
"""

import math
from datetime import UTC, datetime

from app.modules.analyzer.models import End, Link, Node, Topology
from app.modules.dashboard.demo import ROWS

# id, role, endpoints, services. Type, vendor and site come from the Dashboard demo (one list).
NODES = [
    ("DEMO-core-sw-01", "core", 0, []),
    ("DEMO-core-sw-02", "core", 0, []),
    ("DEMO-dist-sw-01", "distribution", 0, []),
    ("DEMO-dist-sw-02", "distribution", 0, []),
    ("DEMO-acc-sw-01", "access", 40, []),
    ("DEMO-acc-sw-02", "access", 32, []),
    ("DEMO-acc-sw-03", "access", 24, []),
    ("DEMO-acc-sw-04", "access", 18, []),
    ("DEMO-fw-srx-01", "edge", 0, []),
    ("DEMO-fw-srx-02", "edge", 0, []),
    ("DEMO-edge-rtr-01", "edge", 0, []),
    ("DEMO-edge-rtr-02", "edge", 0, []),
    ("DEMO-wan-mx-01", "edge", 0, []),
    ("DEMO-wan-mx-02", "edge", 0, []),
    ("DEMO-srv-dns-01", "other", 0, ["dns"]),
    ("DEMO-srv-ntp-01", "other", 0, ["ntp"]),
    ("DEMO-ap-101", "other", 12, []),
    ("DEMO-ap-102", "other", 9, []),
    ("DEMO-ap-201", "other", 7, []),
    ("DEMO-ap-202", "other", 5, []),
]

# Interfaces that exist on a device but have no known neighbor (spare ports).
SPARE = {"DEMO-core-sw-01": ["GigabitEthernet1/0/48"]}

G = "GigabitEthernet1/0/"
UP = 10000  # uplink capacity, Mbps
# a, a_if, b, b_if, capacity, util_pct (None = not polled)
LINKS = [
    ("DEMO-core-sw-01", G + "1", "DEMO-core-sw-02", G + "1", UP, 20.0),
    ("DEMO-core-sw-01", G + "2", "DEMO-dist-sw-01", G + "1", UP, 45.0),
    ("DEMO-core-sw-02", G + "2", "DEMO-dist-sw-01", G + "2", UP, 40.0),
    ("DEMO-core-sw-01", G + "3", "DEMO-dist-sw-02", "ge-0/0/0", UP, 20.0),
    ("DEMO-core-sw-02", G + "3", "DEMO-dist-sw-02", "ge-0/0/1", UP, 25.0),
    ("DEMO-dist-sw-01", G + "3", "DEMO-acc-sw-01", G + "49", UP, 30.0),
    ("DEMO-dist-sw-01", G + "4", "DEMO-acc-sw-02", G + "49", UP, 22.0),
    ("DEMO-dist-sw-02", "ge-0/0/2", "DEMO-acc-sw-02", G + "50", UP, 18.0),
    ("DEMO-dist-sw-01", G + "5", "DEMO-acc-sw-03", "ge-0/0/48", UP, 15.0),
    ("DEMO-dist-sw-02", "ge-0/0/3", "DEMO-acc-sw-03", "ge-0/0/49", UP, None),
    ("DEMO-dist-sw-01", G + "6", "DEMO-acc-sw-04", "ge-0/0/48", UP, 12.0),
    ("DEMO-dist-sw-02", "ge-0/0/4", "DEMO-acc-sw-04", "ge-0/0/49", UP, 10.0),
    ("DEMO-core-sw-01", G + "4", "DEMO-fw-srx-01", "ge-0/0/0", UP, 35.0),
    ("DEMO-core-sw-02", G + "4", "DEMO-fw-srx-02", "ge-0/0/0", UP, 30.0),
    ("DEMO-fw-srx-01", "ge-0/0/1", "DEMO-edge-rtr-01", G + "1", UP, 33.0),
    ("DEMO-fw-srx-02", "ge-0/0/1", "DEMO-edge-rtr-02", G + "1", UP, 28.0),
    ("DEMO-edge-rtr-01", G + "2", "DEMO-wan-mx-01", "ge-0/0/0", UP, 31.0),
    ("DEMO-edge-rtr-02", G + "2", "DEMO-wan-mx-02", "ge-0/0/0", UP, 27.0),
    ("DEMO-wan-mx-01", "ge-0/0/1", "DEMO-wan-mx-02", "ge-0/0/1", UP, 8.0),
    ("DEMO-acc-sw-02", G + "1", "DEMO-srv-dns-01", "eth0", 1000, 6.0),
    ("DEMO-acc-sw-02", G + "2", "DEMO-srv-ntp-01", "eth0", 1000, 1.5),
    ("DEMO-acc-sw-01", G + "1", "DEMO-ap-101", "GigabitEthernet0", 1000, 14.0),
    ("DEMO-acc-sw-02", G + "3", "DEMO-ap-102", "GigabitEthernet0", 1000, 11.0),
    ("DEMO-acc-sw-03", "ge-0/0/0", "DEMO-ap-201", "GigabitEthernet0", 1000, 9.0),
    ("DEMO-acc-sw-04", "ge-0/0/0", "DEMO-ap-202", "GigabitEthernet0", 1000, 7.0),
]


def _hourly(util: float) -> list[float]:
    """Day curve that peaks at 15:00 at about the current value and bottoms out at 03:00."""
    return [
        round(util * (0.15 + 0.85 * (1 - math.cos(2 * math.pi * (h - 3) / 24)) / 2), 1)
        for h in range(24)
    ]


class DemoTopology:
    source = "demo"

    def topology(self) -> Topology:
        ifaces: dict[str, list[str]] = {n[0]: list(SPARE.get(n[0], [])) for n in NODES}
        links = []
        for i, (a, a_if, b, b_if, cap, util) in enumerate(LINKS, start=1):
            ifaces[a].append(a_if)
            ifaces[b].append(b_if)
            links.append(
                Link(
                    id=f"L{i}",
                    a=End(device=a, interface=a_if),
                    b=End(device=b, interface=b_if),
                    capacity_mbps=cap,
                    util_pct=util,
                    hourly_util_pct=None if util is None else _hourly(util),
                )
            )
        rows = {r.name: r for r in ROWS}
        nodes = [
            Node(
                id=id_,
                type=rows[id_].type,
                role=role,
                vendor=rows[id_].vendor,
                site=rows[id_].site,
                interfaces=sorted(ifaces[id_]),
                endpoints=endpoints,
                services=services,
            )
            for id_, role, endpoints, services in NODES
        ]
        return Topology(source="demo", as_of=datetime.now(UTC), nodes=nodes, links=links)
