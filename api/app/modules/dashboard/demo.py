"""DEVELOPMENT-ONLY DEMO DATA. Nothing here is real telemetry.

Addresses are documentation ranges (RFC 5737) and every device name starts with DEMO-.
service.get_source() only uses this with MONICOMM_DEMO_DATA=true and MONICOMM_ENV=dev.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from app.modules.dashboard.models import (
    Alert,
    AlertCode,
    Device,
    DeviceDetails,
    DeviceStatus,
    DeviceType,
    Event,
    Interface,
    Metrics,
    Severity,
    Source,
    severity_group,
)


class Row(NamedTuple):
    name: str
    ip: str
    vendor: str | None
    model: str | None
    type: DeviceType
    status: DeviceStatus
    os: str | None
    site: str | None


XE17 = "IOS-XE 17.12.4"
XE9 = "IOS-XE 17.9.5"
XE6 = "IOS-XE 17.6.6"
J22 = "Junos 22.4R3"
J21 = "Junos 21.4R3"
JMX = "Junos 22.2R3"
A, B = "Site A", "Site B"

ROWS = [
    Row("DEMO-core-sw-01", "192.0.2.1", "Cisco", "C9500-48Y4C", "switch", "online", XE17, A),
    Row("DEMO-core-sw-02", "192.0.2.2", "Cisco", "C9500-48Y4C", "switch", "warning", XE17, A),
    Row("DEMO-dist-sw-01", "192.0.2.11", "Cisco", "C9300-48P", "switch", "online", XE9, A),
    Row("DEMO-dist-sw-02", "192.0.2.12", "Juniper", "EX4300-48T", "switch", "online", J22, A),
    Row("DEMO-acc-sw-01", "192.0.2.21", "Cisco", "C9200L-24P", "switch", "online", XE9, A),
    Row("DEMO-acc-sw-02", "192.0.2.22", "Cisco", "C9200L-24P", "switch", "offline", XE9, A),
    Row("DEMO-acc-sw-03", "192.0.2.23", "Juniper", "EX2300-24P", "switch", "online", J21, B),
    Row(
        "DEMO-acc-sw-04",
        "192.0.2.24",
        "Juniper",
        "EX2300-24P",
        "switch",
        "suspected_offline",
        J21,
        B,
    ),
    Row("DEMO-edge-rtr-01", "198.51.100.1", "Cisco", "ASR1001-X", "router", "online", XE6, A),
    Row("DEMO-edge-rtr-02", "198.51.100.2", "Cisco", "ASR1001-X", "router", "critical", XE6, B),
    Row("DEMO-wan-mx-01", "198.51.100.11", "Juniper", "MX204", "router", "online", JMX, A),
    Row("DEMO-wan-mx-02", "198.51.100.12", "Juniper", "MX204", "router", "online", JMX, B),
    Row("DEMO-fw-srx-01", "198.51.100.21", "Juniper", "SRX1500", "firewall", "online", J22, A),
    Row("DEMO-fw-srx-02", "198.51.100.22", "Juniper", "SRX1500", "firewall", "warning", J22, B),
    Row("DEMO-srv-dns-01", "203.0.113.10", None, None, "server", "online", None, A),
    Row("DEMO-srv-ntp-01", "203.0.113.11", None, None, "server", "online", None, A),
    Row("DEMO-srv-log-01", "203.0.113.12", None, None, "server", "online", None, None),
    Row("DEMO-ap-101", "203.0.113.101", "Cisco", "C9120AXI", "access_point", "online", XE9, A),
    Row("DEMO-ap-102", "203.0.113.102", "Cisco", "C9120AXI", "access_point", "online", XE9, A),
    Row(
        "DEMO-ap-201",
        "203.0.113.201",
        "Cisco",
        "C9120AXI",
        "access_point",
        "suspected_offline",
        XE9,
        B,
    ),
    Row("DEMO-ap-202", "203.0.113.202", "Cisco", "C9120AXI", "access_point", "online", XE9, B),
    Row("DEMO-unknown-01", "203.0.113.250", None, None, "unknown", "online", None, None),
]

# minutes ago, device index, kind, severity, message
EVENTS: list[tuple[int, int, str, Severity | None, str]] = [
    (1, 9, "syslog", "crit", "%ENVMON-2-TEMP: Temperature sensor 1 exceeded critical threshold"),
    (2, 9, "syslog", "err", "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/2, state to down"),
    (2, 9, "trap", None, "linkDown (.1.3.6.1.6.3.1.1.5.3) ifIndex=2"),
    (4, 1, "syslog", "warning", "Interface GigabitEthernet1/0/1 input utilization above 90%"),
    (6, 13, "syslog", "warning", "Interface ge-0/0/0 input utilization above 90%"),
    (8, 0, "syslog", "notice", "%SYS-5-CONFIG_I: Configured from console by demo-operator"),
    (11, 4, "syslog", "notice", "%LINEPROTO-5-UPDOWN: GigabitEthernet1/0/5, state to up"),
    (15, 12, "syslog", "info", "UI_COMMIT_COMPLETED: commit complete"),
    (19, 10, "syslog", "warning", "RPD_BGP_NEIGHBOR_STATE_CHANGED: 198.51.100.2 now Idle"),
    (20, 10, "trap", None, "bgpBackwardTransition (.1.3.6.1.2.1.15.7.2)"),
    (26, 8, "syslog", "warning", "%SEC_LOGIN-4-LOGIN_FAILED: Login failed [user: demo]"),
    (33, 2, "syslog", "info", "%SYS-6-LOGOUT: User demo-operator has exited tty session 2"),
    (41, 11, "syslog", "notice", "RPD_OSPF_NBRUP: OSPF neighbor 198.51.100.11 now Full"),
    (52, 6, "syslog", "debug", "pfe: periodic statistics collection finished"),
    (96, 12, "syslog", "err", "CHASSISD_FRU_OFFLINE_NOTICE: Taking PEM 1 offline: Removal"),
    (188, 2, "syslog", "err", "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/8, state to down"),
    (188, 0, "trap", None, "linkDown (.1.3.6.1.6.3.1.1.5.3) ifIndex=8"),
    (240, 20, "syslog", "info", "AP joined controller"),
    (410, 17, "syslog", "notice", "Radio slot 1 channel changed to 44"),
]

# minutes ago, device index, severity, code
ALERTS: list[tuple[int, int, str, AlertCode]] = [
    (1, 9, "critical", "high_temperature"),
    (2, 9, "critical", "interface_down"),
    (184, 5, "critical", "device_unreachable"),
    (4, 1, "warning", "high_utilization"),
    (4, 7, "warning", "device_unreachable"),
    (4, 19, "warning", "device_unreachable"),
    (6, 13, "warning", "high_utilization"),
]

POLL_AGE_MINUTES: dict[str, float] = {"offline": 187, "suspected_offline": 7}


def _ago(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def _noise(a: int, b: int) -> float:
    """Stable pseudo-random number in [0, 1), so the demo looks the same on every load."""
    return (math.sin(a * 127.1 + b * 311.7) * 43758.5453) % 1


def _id(index: int) -> str:
    return f"demo-{index + 1}"


def _unreachable(status: DeviceStatus) -> bool:
    return status in POLL_AGE_MINUTES


def _device(i: int, row: Row) -> Device:
    return Device(
        id=_id(i),
        name=row.name,
        ip=row.ip,
        vendor=row.vendor,
        model=row.model,
        type=row.type,
        status=row.status,
        os_version=row.os,
        serial=f"DEMO{1000 + i * 37}" if row.model else None,
        site=row.site,
        last_poll_at=_ago(POLL_AGE_MINUTES.get(row.status, 0.5)),
    )


def _interface(i: int, row: Row, n: int) -> Interface:
    disabled = n > 3 and _noise(i, n + 50) > 0.85
    failed = (n > 1 and _noise(i, n + 90) > 0.85) or (row.status == "critical" and n == 1)
    down = disabled or failed
    hot = row.status == "warning" and n == 0
    idle = down or _unreachable(row.status)
    return Interface(
        if_index=str(n + 1),
        name=f"ge-0/0/{n}" if row.vendor == "Juniper" else f"GigabitEthernet1/0/{n + 1}",
        alias="uplink" if n == 0 else None,
        admin_status="down" if disabled else "up",
        oper_status="down" if down else "up",
        speed_mbps=10_000 if n == 0 and row.type != "access_point" else 1000,
        in_util_pct=None if idle else 91.4 if hot else round(_noise(i, n) * 45, 1),
        out_util_pct=None if idle else 78.2 if hot else round(_noise(i, n + 20) * 38, 1),
        in_errors=1284 if hot else 0,
        out_errors=0,
    )


def _interfaces(i: int, row: Row) -> list[Interface]:
    count = {"switch": 12, "router": 6, "firewall": 6, "access_point": 2}.get(row.type, 0)
    return [_interface(i, row, n) for n in range(count)]


def _metrics(i: int, row: Row) -> Metrics:
    if _unreachable(row.status) or row.type == "unknown":
        return Metrics(cpu_pct=None, memory_pct=None, temperature_c=None, uptime_seconds=None)
    temperature = 88 if row.status == "critical" else round(34 + _noise(i, 3) * 14)
    return Metrics(
        cpu_pct=round(8 + _noise(i, 1) * 50),
        memory_pct=round(30 + _noise(i, 2) * 40),
        temperature_c=None if row.type == "server" else temperature,
        uptime_seconds=round(86_400 * (3 + _noise(i, 4) * 200)),
    )


class DemoSource:
    source: Source = "demo"

    def devices(self) -> list[Device]:
        return [_device(i, row) for i, row in enumerate(ROWS)]

    def device(self, device_id: str) -> DeviceDetails | None:
        for i, row in enumerate(ROWS):
            if _id(i) == device_id:
                return DeviceDetails(
                    **_device(i, row).model_dump(),
                    interfaces=_interfaces(i, row),
                    metrics=_metrics(i, row),
                )
        return None

    def events(self) -> list[Event]:
        return [
            Event(
                id=f"demo-event-{i + 1}",
                kind=kind,
                severity=severity,
                severity_group=severity_group(severity),
                device_id=_id(d),
                device_name=ROWS[d].name,
                source_ip=ROWS[d].ip,
                received_at=_ago(minutes),
                message=message,
            )
            for i, (minutes, d, kind, severity, message) in enumerate(EVENTS)
        ]

    def open_alerts(self) -> list[Alert]:
        return [
            Alert(
                id=f"demo-alert-{i + 1}",
                severity=severity,
                code=code,
                device_id=_id(d),
                device_name=ROWS[d].name,
                opened_at=_ago(minutes),
            )
            for i, (minutes, d, severity, code) in enumerate(ALERTS)
        ]
