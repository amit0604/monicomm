"""Live device state from the collectors' SNMP files (read-only).

Reads the tail of <ingest_dir>/<YYYY-MM-DD>/snmp_metric.jsonl (today's, plus yesterday's when
today's is still short), keeps the newest record per (device, measurement, index) and the one
before it for interfaces, so utilization = delta(HC octets) * 8 / dt / speed. Results are cached
for a few seconds. A missing or empty directory is simply no live devices.
"""

import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.snmp_names import octet_rate

FILE = "snmp_metric.jsonl"
READ_BUDGET = 4 * 1024 * 1024  # bytes read per refresh across today's and yesterday's file
UP_WITHIN_S = 180  # a device is up if its last snmp_system poll is younger than this
LLDP_STALE_S = 120  # neighbors older than the device's newest LLDP poll by more are gone
CACHE_S = 10.0
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Record = dict[str, Any]
_clock = time.time  # wall clock, replaceable in tests


@dataclass
class Port:
    index: str
    name: str
    alias: str | None
    admin_up: bool
    oper_up: bool
    speed_mbps: int | None
    in_errors: int | None
    out_errors: int | None
    in_util_pct: float | None
    out_util_pct: float | None


@dataclass
class Neighbor:
    local_port: str  # localPortNum from the LLDP index
    chassis_id: str
    port_id: str
    port_desc: str
    sys_name: str


@dataclass
class LiveDevice:
    ip: str
    name: str | None
    up: bool
    last_poll_at: datetime | None
    uptime_seconds: int | None = None
    descr: str | None = None
    object_id: str | None = None
    location: str | None = None
    model: str | None = None  # from ENTITY-MIB when the device has it
    serial: str | None = None
    software: str | None = None
    cpu_pct: float | None = None
    memory_pct: float | None = None
    temperature_c: float | None = None
    ports: list[Port] = field(default_factory=list)
    neighbors: list[Neighbor] = field(default_factory=list)


def polled_at(rec: Record) -> float | None:
    """Unix seconds. polled_at is Unix ms; tolerate seconds, ISO strings and the timestamp field."""
    for value in (rec.get("polled_at"), rec.get("timestamp")):
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return value / 1000 if value > 1e11 else float(value)
        if isinstance(value, str) and value:
            try:
                return float(value) / 1000 if value.isdigit() else _iso(value)
            except ValueError:
                continue
    return None


def _iso(value: str) -> float:
    text = value.replace("Z", "+00:00")
    # Python's fromisoformat takes at most 6 fractional digits; collectors send 9
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    ts = datetime.fromisoformat(text)
    return (ts if ts.tzinfo else ts.replace(tzinfo=UTC)).timestamp()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _util(new: Record, old: Record | None, key: str, speed: int | None) -> float | None:
    if old is None or not speed:
        return None
    a, b = _int(old["fields"].get(key)), _int(new["fields"].get(key))
    if a is None or b is None:
        return None
    bps = octet_rate(old["_t"], a, new["_t"], b)  # None on a counter reset or wrap
    return None if bps is None else round(min(bps / (speed * 1e6) * 100, 100.0), 1)


def _port(new: Record, old: Record | None) -> Port:
    f, tags = new["fields"], new["tags"]
    index = _str(tags.get("index"))
    speed = _int(f.get("ifHighSpeed")) or None
    return Port(
        index=index,
        name=_str(tags.get("ifName")) or _str(f.get("ifName")) or _str(f.get("ifDescr")) or index,
        alias=_str(f.get("ifAlias")) or _str(tags.get("ifAlias")) or None,
        admin_up=_int(f.get("ifAdminStatus")) == 1,
        oper_up=_int(f.get("ifOperStatus")) == 1,
        speed_mbps=speed,
        in_errors=_int(f.get("ifInErrors")),
        out_errors=_int(f.get("ifOutErrors")),
        in_util_pct=_util(new, old, "ifHCInOctets", speed),
        out_util_pct=_util(new, old, "ifHCOutOctets", speed),
    )


def _max(values: Iterable[float | None]) -> float | None:
    seen = [v for v in values if v is not None]
    return max(seen) if seen else None


def _metrics(dev: LiveDevice, recs: dict[str, list[Record]]) -> None:
    cisco = recs.get("snmp_cisco_cpu", [])
    dev.cpu_pct = _max(_float(r["fields"].get("cpmCPUTotal5minRev")) for r in cisco)
    mem = []
    for r in cisco:
        used, free = (
            _float(r["fields"].get("cpmCPUMemoryUsed")),
            _float(r["fields"].get("cpmCPUMemoryFree")),
        )
        if used is not None and free is not None and used + free > 0:
            mem.append(round(used / (used + free) * 100, 1))
    dev.memory_pct = _max(mem)
    juniper = recs.get("snmp_juniper_operating", [])
    if juniper:
        dev.cpu_pct = _max(
            [dev.cpu_pct, *(_float(r["fields"].get("jnxOperatingCPU")) for r in juniper)]
        )
        buffers = (_float(r["fields"].get("jnxOperatingBuffer")) for r in juniper)
        dev.memory_pct = _max([dev.memory_pct, *buffers])
        temps = (_float(r["fields"].get("jnxOperatingTemp")) for r in juniper)
        dev.temperature_c = _max(t for t in temps if t)  # 0 = component has no sensor


def _entity(dev: LiveDevice, recs: list[Record]) -> None:
    def has_model(r: Record) -> bool:
        return bool(_str(r["fields"].get("entPhysicalModelName")))

    chassis = [r for r in recs if _int(r["fields"].get("entPhysicalClass")) == 3]
    best = next((r for r in chassis + recs if has_model(r)), None)
    if best is not None:
        f = best["fields"]
        dev.model = _str(f.get("entPhysicalModelName")) or None
        dev.serial = _str(f.get("entPhysicalSerialNum")) or None
        dev.software = _str(f.get("entPhysicalSoftwareRev")) or None


def _neighbors(recs: list[Record]) -> list[Neighbor]:
    if not recs:
        return []
    newest = max(r["_t"] for r in recs)
    out = []
    for r in recs:
        if r["_t"] < newest - LLDP_STALE_S:
            continue
        parts = _str(r["tags"].get("index")).split(".")
        f = r["fields"]
        out.append(
            Neighbor(
                local_port=parts[1] if len(parts) >= 3 else parts[0],
                chassis_id=_str(f.get("lldpRemChassisId")),
                port_id=_str(f.get("lldpRemPortId")),
                port_desc=_str(f.get("lldpRemPortDesc")),
                sys_name=_str(f.get("lldpRemSysName")),
            )
        )
    return out


def build(lines: Iterable[str], now: float | None = None) -> list[LiveDevice]:
    """Turn snmp_metric lines into one LiveDevice per source IP. Bad lines are skipped."""
    now = _clock() if now is None else now
    latest: dict[tuple[str, str, str], Record] = {}
    previous: dict[tuple[str, str, str], Record] = {}  # snmp_interface only
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("fields"), dict):
            continue
        tags = rec.get("tags") if isinstance(rec.get("tags"), dict) else {}
        rec["tags"] = tags
        ip = _str(rec.get("source_ip")) or _str(tags.get("source"))
        measurement = _str(rec.get("measurement"))
        t = polled_at(rec)
        if not ip or not measurement or t is None:
            continue
        rec["_t"] = t
        key = (ip, measurement, _str(tags.get("index")))
        old = latest.get(key)
        if old is None or t >= old["_t"]:
            latest[key] = rec
            if old is not None and t > old["_t"] and measurement == "snmp_interface":
                previous[key] = old
        elif measurement == "snmp_interface" and t > previous.get(key, {"_t": -1})["_t"]:
            previous[key] = rec

    by_ip: dict[str, dict[str, list[Record]]] = {}
    for (ip, measurement, _), rec in latest.items():
        by_ip.setdefault(ip, {}).setdefault(measurement, []).append(rec)

    devices = []
    for ip, recs in sorted(by_ip.items()):
        system = max(recs.get("snmp_system", []), key=lambda r: r["_t"], default=None)
        newest = max((r for rs in recs.values() for r in rs), key=lambda r: r["_t"])
        named = system or newest
        name = _str(named["tags"].get("sysName")) or next(
            (
                _str(r["tags"].get("sysName"))
                for rs in recs.values()
                for r in rs
                if r["tags"].get("sysName")
            ),
            "",
        )
        dev = LiveDevice(
            ip=ip,
            name=name or None,
            up=system is not None and now - system["_t"] < UP_WITHIN_S,
            last_poll_at=datetime.fromtimestamp((system or newest)["_t"], UTC),
        )
        if system is not None:
            ticks = _int(system["fields"].get("sysUpTime"))
            dev.uptime_seconds = ticks // 100 if ticks is not None else None  # TimeTicks = 1/100 s
        identity = recs.get("snmp_identity")
        if identity:
            f = max(identity, key=lambda r: r["_t"])["fields"]
            dev.descr = _str(f.get("sysDescr")) or None
            dev.object_id = _str(f.get("sysObjectID")) or None
            dev.location = _str(f.get("sysLocation")) or None
        _entity(dev, recs.get("snmp_entity", []))
        _metrics(dev, recs)
        ports = [
            _port(r, previous.get((ip, "snmp_interface", _str(r["tags"].get("index")))))
            for r in recs.get("snmp_interface", [])
        ]
        dev.ports = sorted(
            ports, key=lambda p: (_int(p.index) is None, _int(p.index) or 0, p.index)
        )
        dev.neighbors = _neighbors(recs.get("snmp_lldp_neighbor", []))
        devices.append(dev)
    return devices


def _tail(path: Path, budget: int) -> list[str]:
    if budget <= 0 or not path.is_file():
        return []
    size = path.stat().st_size
    start = max(0, size - budget)
    with path.open("rb") as f:
        f.seek(start)
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if start > 0 else lines  # the first line was cut by the seek


def read_lines(ingest_dir: str | Path) -> list[str]:
    root = Path(ingest_dir)
    if not root.is_dir():
        return []
    days = sorted(p for p in root.iterdir() if p.is_dir() and DAY.match(p.name))[-2:]
    if not days:
        return []
    today = days[-1] / FILE
    today_size = today.stat().st_size if today.is_file() else 0
    older = _tail(days[0] / FILE, READ_BUDGET - today_size) if len(days) == 2 else []
    return older + _tail(today, READ_BUDGET)


_cache: dict[str, tuple[float, list[LiveDevice]]] = {}


def snapshot(ingest_dir: str | Path) -> list[LiveDevice]:
    """Current live devices, re-read at most every CACHE_S seconds. Never raises on bad data."""
    key = str(ingest_dir)
    hit = _cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    try:
        devices = build(read_lines(key))
    except OSError:
        devices = []
    _cache[key] = (time.monotonic(), devices)
    return devices


def clear_cache() -> None:
    _cache.clear()
