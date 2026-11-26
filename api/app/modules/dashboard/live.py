"""Live Dashboard data from the collectors' SNMP files, and the dev-only demo + live mix."""

import re
from datetime import UTC, datetime

from app.core import live_snmp
from app.modules.dashboard.models import (
    Alert,
    DataSource,
    Device,
    DeviceDetails,
    DeviceType,
    Event,
    Interface,
    Metrics,
    Source,
)

VENDORS = {".1.3.6.1.4.1.9.": "Cisco", ".1.3.6.1.4.1.2636.": "Juniper"}
FIREWALL = re.compile(r"\b(srx\d*|asa\d*|firewall|firepower)\b", re.I)
SWITCH = re.compile(
    r"\b(switch|c2960\w*|c3[0-9]{3}\w*|c9[0-9]{3}\w*|ws-c\w*|ex[0-9]{4}\w*|qfx\w*|nexus)", re.I
)
ROUTER = re.compile(r"\b(router|isr\w*|asr\w*|csr\w*|mx[0-9]+\w*|c8[0-9]{3}\w*)", re.I)


def device_id(ip: str) -> str:
    return f"live-{ip}"


def vendor(d: live_snmp.LiveDevice) -> str | None:
    for prefix, name in VENDORS.items():
        if (d.object_id or "").startswith(prefix):
            return name
    text = (d.descr or "").lower()
    if "cisco" in text:
        return "Cisco"
    if "juniper" in text or "junos" in text:
        return "Juniper"
    return None


def model(d: live_snmp.LiveDevice) -> str | None:
    if d.model:
        return d.model
    descr = d.descr or ""
    if m := re.search(r"Software, (\S+) Software", descr):  # Cisco IOS: "..., C2960X Software (..."
        return m.group(1)
    if m := re.search(r"Juniper Networks, Inc\. (\S+)", descr):
        return m.group(1).upper()
    return None


def os_version(d: live_snmp.LiveDevice) -> str | None:
    descr = d.descr or ""
    if m := re.search(r"JUNOS ([^\s,\[]+)", descr, re.I):
        return f"Junos {m.group(1)}"
    if m := re.search(r"Version ([^\s,\[]+)", descr):
        xe = "IOS-XE" if re.search(r"IOS[- ]XE", descr) else "IOS"
        return f"{xe} {m.group(1)}" if "cisco" in descr.lower() else m.group(1)
    return d.software


def device_type(d: live_snmp.LiveDevice) -> DeviceType:
    text = f"{model(d) or ''} {d.descr or ''}"
    for kind, pattern in (("firewall", FIREWALL), ("switch", SWITCH), ("router", ROUTER)):
        if pattern.search(text):
            return kind  # type: ignore[return-value]
    return "unknown"


def to_device(d: live_snmp.LiveDevice) -> Device:
    return Device(
        id=device_id(d.ip),
        name=d.name,
        ip=d.ip,
        vendor=vendor(d),
        model=model(d),
        type=device_type(d),
        status="online" if d.up else "offline",
        os_version=os_version(d),
        serial=d.serial,
        site=d.location,
        last_poll_at=d.last_poll_at,
    )


def to_interface(p: live_snmp.Port) -> Interface:
    return Interface(
        if_index=p.index,
        name=p.name,
        alias=p.alias,
        admin_status="up" if p.admin_up else "down",
        oper_status="up" if p.oper_up else "down",
        speed_mbps=p.speed_mbps,
        in_util_pct=p.in_util_pct,
        out_util_pct=p.out_util_pct,
        in_errors=p.in_errors,
        out_errors=p.out_errors,
    )


class LiveSource:
    source: Source = "live"

    def __init__(self, ingest_dir: str) -> None:
        self.ingest_dir = ingest_dir

    def live_devices(self) -> list[live_snmp.LiveDevice]:
        return live_snmp.snapshot(self.ingest_dir)

    def devices(self) -> list[Device]:
        return [to_device(d) for d in self.live_devices()]

    def device(self, device_id_: str) -> DeviceDetails | None:
        for d in self.live_devices():
            if device_id(d.ip) == device_id_:
                return DeviceDetails(
                    **to_device(d).model_dump(),
                    interfaces=[to_interface(p) for p in d.ports],
                    metrics=Metrics(
                        cpu_pct=d.cpu_pct,
                        memory_pct=d.memory_pct,
                        temperature_c=d.temperature_c,
                        uptime_seconds=d.uptime_seconds,
                    ),
                )
        return None

    def events(self) -> list[Event]:
        return []  # syslog and traps are the Investigator's for now

    def open_alerts(self) -> list[Alert]:
        return [
            Alert(
                id=f"live-alert-{d.ip}",
                severity="critical",
                code="device_unreachable",
                device_id=device_id(d.ip),
                device_name=d.name,
                opened_at=d.last_poll_at or datetime.now(UTC),
            )
            for d in self.live_devices()
            if not d.up
        ]


class CombinedSource:
    """Dev demo mode with a collector attached: demo devices plus the real ones.

    Labelled "demo" so the UI keeps its DEMO banner while any fabricated data is on screen.
    Code that must not pass live data on (a cloud model) uses .demo instead.
    """

    source: Source = "demo"

    def __init__(self, demo: DataSource, live: DataSource) -> None:
        self.demo = demo
        self.live = live

    def devices(self) -> list[Device]:
        return self.demo.devices() + self.live.devices()

    def device(self, device_id_: str) -> DeviceDetails | None:
        return self.demo.device(device_id_) or self.live.device(device_id_)

    def events(self) -> list[Event]:
        return self.demo.events() + self.live.events()

    def open_alerts(self) -> list[Alert]:
        return self.demo.open_alerts() + self.live.open_alerts()
