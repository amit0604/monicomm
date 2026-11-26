"""How Monicomm reads names and counters in collector SNMP rows. Pure; shared by the Investigator,
the live Dashboard / Mapper / Analyzer source (`live_snmp`) and the Analyzer parser."""

import re

IFINDEX = re.compile(r"^ifIndex (\d+)$")  # how an event names a port it knows only by index
_IF = re.compile(r"^([A-Za-z][A-Za-z-]*?)[\s-]*(\d.*)$")
_MAC = re.compile(r"^[0-9A-Fa-f]{2}(?:[:-]?[0-9A-Fa-f]{2}){5}$")


def ifkey(name: str | None) -> str | None:
    """Compare key for interface names: 'GigabitEthernet1/0/24' and 'Gi1/0/24' -> 'gi1/0/24'."""
    if not name:
        return None
    name = name.strip()
    m = _IF.match(name)
    return (m[1][:2] + m[2]).lower() if m else name.lower()


def short_name(name: str) -> str:
    """'r1.example.net' and 'R1' are the same device."""
    return name.split(".")[0].lower()


def remote_port(port_id: object, port_desc: object) -> str | None:
    """The LLDP neighbor's port as a name. The port id subtype is not polled: a MAC or a bare
    number is useless as a name, so the description wins then."""
    if isinstance(port_id, str) and re.search(r"[A-Za-z]", port_id) and not _MAC.match(port_id):
        return port_id
    return (port_desc if isinstance(port_desc, str) else None) or (
        str(port_id) if port_id else None
    )


def octet_rate(t1_s: float, octets1: int, t2_s: float, octets2: int) -> float | None:
    """bits/s between two counter readings; None on a counter wrap/reset or no time between."""
    dt = t2_s - t1_s
    if dt <= 0 or octets2 < octets1:
        return None
    return (octets2 - octets1) * 8 / dt
