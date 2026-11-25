"""DEVELOPMENT-ONLY DEMO LINK LIST. Nothing here is a real network.

The devices are the Dashboard's demo inventory (every name starts with DEMO-), so the map and the
Dashboard always agree. service.get_link_source() only uses this with MONICOMM_DEMO_DATA=true and
MONICOMM_ENV=dev.
"""

from typing import NamedTuple

from app.modules.dashboard.models import Source
from app.modules.mapper.models import LinkEnd, LinkRecord, LinkStatus, Medium


class Row(NamedTuple):
    a: str
    a_port: str
    b: str
    b_port: str
    medium: Medium
    speed_mbps: int | None
    reported: LinkStatus | None = None


GI = "GigabitEthernet1/0/"

ROWS = [
    # Site A core and distribution
    Row("core-sw-01", GI + "1", "core-sw-02", GI + "1", "fiber", 10_000),
    Row("core-sw-01", GI + "2", "dist-sw-01", GI + "1", "fiber", 1000),
    Row("core-sw-02", GI + "2", "dist-sw-02", "ge-0/0/0", "fiber", 1000),
    Row("core-sw-01", GI + "3", "dist-sw-02", "ge-0/0/1", "fiber", 1000),
    # Site A access, servers and wireless
    Row("dist-sw-01", GI + "2", "acc-sw-01", GI + "1", "copper", 1000),
    Row("dist-sw-01", GI + "3", "acc-sw-02", GI + "1", "copper", 1000),
    Row("dist-sw-02", "ge-0/0/2", "srv-dns-01", "eth0", "copper", 1000),
    Row("dist-sw-02", "ge-0/0/3", "srv-ntp-01", "eth0", "copper", 1000),
    Row("core-sw-02", GI + "3", "srv-log-01", "eth0", "copper", 1000),
    Row("acc-sw-01", GI + "2", "ap-101", GI + "1", "copper", 1000),
    Row("ap-101", "Dot11Radio1", "ap-102", "Dot11Radio1", "wireless", 867, "up"),
    # Site A edge
    Row("core-sw-01", GI + "4", "fw-srx-01", "ge-0/0/0", "fiber", 1000),
    Row("fw-srx-01", "ge-0/0/1", "edge-rtr-01", GI + "1", "copper", 1000),
    Row("edge-rtr-01", GI + "2", "wan-mx-01", "ge-0/0/0", "fiber", 1000),
    # Between the sites: a provider circuit and an IPsec tunnel
    Row("wan-mx-01", "ge-0/0/1", "wan-mx-02", "ge-0/0/1", "wan", 500),
    Row("fw-srx-01", "st0.0", "fw-srx-02", "st0.0", "wan", 200, "up"),
    # Site B
    Row("wan-mx-02", "ge-0/0/0", "edge-rtr-02", GI + "2", "fiber", 1000),
    Row("edge-rtr-02", GI + "1", "fw-srx-02", "ge-0/0/0", "copper", 1000),
    Row("fw-srx-02", "ge-0/0/1", "acc-sw-03", "ge-0/0/0", "fiber", 1000),
    Row("acc-sw-03", "ge-0/0/1", "acc-sw-04", "ge-0/0/0", "copper", 1000),
    Row("acc-sw-03", "ge-0/0/2", "ap-202", GI + "1", "copper", 1000),
    Row("acc-sw-04", "ge-0/0/1", "ap-201", GI + "1", "copper", 1000),
    Row("ap-202", "Dot11Radio1", "ap-201", "Dot11Radio1", "wireless", 867, "up"),
]


class DemoLinks:
    source: Source = "demo"

    def links(self) -> list[LinkRecord]:
        return [
            LinkRecord(
                a=LinkEnd(device=f"DEMO-{r.a}", port=r.a_port),
                b=LinkEnd(device=f"DEMO-{r.b}", port=r.b_port),
                medium=r.medium,
                speed_mbps=r.speed_mbps,
                reported_status=r.reported,
            )
            for r in ROWS
        ]
