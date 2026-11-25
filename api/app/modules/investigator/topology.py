"""LLDP adjacency map from monicomm.snmp_metric.v1 rows (collector README, 10-all.conf.tmpl).

Rows used:
- any row: tag `sysName` + `source_ip` -> name-to-IP map (resolves lldpRemSysName to a device IP)
- `snmp_interface`: tags `index` (ifIndex) + `ifName`
- `snmp_lldp_neighbor`: tag `index` = "timeMark.localPortNum.remIndex",
  fields `lldpRemSysName`, `lldpRemChassisId`, `lldpRemPortId`, `lldpRemPortDesc`
Assumes lldpLocPortNum == ifIndex (lldpLocPortTable is not polled). Pure, in memory.
"""

import re

_IF = re.compile(r"^([A-Za-z][A-Za-z-]*?)[\s-]*(\d.*)$")
_IFINDEX = re.compile(r"^ifIndex (\d+)$")
_MAC = re.compile(r"^[0-9A-Fa-f]{2}(?:[:-]?[0-9A-Fa-f]{2}){5}$")


def ifkey(name: str | None) -> str | None:
    """Compare key for interface names: 'GigabitEthernet1/0/24' and 'Gi1/0/24' -> 'gi1/0/24'."""
    if not name:
        return None
    name = name.strip()
    m = _IF.match(name)
    return (m[1][:2] + m[2]).lower() if m else name.lower()


def _short(name: str) -> str:
    return name.split(".")[0].lower()  # "r1.example.net" and "R1" are the same device


def _remote_port(fields: dict) -> str | None:
    pid, desc = fields.get("lldpRemPortId"), fields.get("lldpRemPortDesc")
    # port id subtype is not polled: a MAC or a bare ifIndex number is useless, take the description
    if isinstance(pid, str) and re.search(r"[A-Za-z]", pid) and not _MAC.match(pid):
        return pid
    return desc or (str(pid) if pid else None)


class Topology:
    def __init__(self) -> None:
        self._names: dict[str, str] = {}  # short sysName -> device IP
        self._ifnames: dict[str, dict[str, str]] = {}  # device -> ifIndex -> ifName
        self._lldp: dict[str, dict[str, tuple[str, str | None]]] = {}  # device -> port -> remote

    def update(self, metric: dict) -> None:
        tags, fields = metric.get("tags") or {}, metric.get("fields") or {}
        device = metric.get("source_ip") or tags.get("source")
        if not isinstance(device, str) or not device:
            return
        if name := tags.get("sysName"):
            self._names[_short(name)] = device
        measurement, index = metric.get("measurement"), str(tags.get("index") or "")
        if measurement == "snmp_interface" and index and tags.get("ifName"):
            self._ifnames.setdefault(device, {})[index] = tags["ifName"]
        elif measurement == "snmp_lldp_neighbor":
            parts = index.split(".")
            remote = fields.get("lldpRemSysName") or fields.get("lldpRemChassisId")
            if len(parts) == 3 and remote:
                self._lldp.setdefault(device, {})[parts[1]] = (remote, _remote_port(fields))

    def _ip(self, name: str) -> str:
        return self._names.get(_short(name), name)  # unresolved: keep the sysName

    def neighbors(self, device_ip: str) -> set[str]:
        # ponytail: linear scan over all LLDP rows, index by resolved IP if networks get large
        out = {self._ip(r) for r, _ in self._lldp.get(device_ip, {}).values()}
        for device, ports in self._lldp.items():
            if any(self._ip(r) == device_ip for r, _ in ports.values()):
                out.add(device)
        out.discard(device_ip)
        return out

    def link(self, device_ip: str, interface: str | None) -> tuple[str, str | None] | None:
        if not interface:
            return None
        m = _IFINDEX.match(interface)
        key, names = ifkey(interface), self._ifnames.get(device_ip, {})
        for port, (remote, rport) in self._lldp.get(device_ip, {}).items():
            if (m and m[1] == port) or ifkey(names.get(port)) == key:
                return self._ip(remote), rport
        for device, ports in self._lldp.items():  # only the far end reports this link
            for port, (remote, rport) in ports.items():
                if self._ip(remote) == device_ip and ifkey(rport) == key:
                    return device, self._ifnames.get(device, {}).get(port)
        return None
