"""LLDP adjacency map from monicomm.snmp_metric.v1 rows (collector README, 10-all.conf.tmpl).

Rows used:
- any row: tag `sysName` + `source_ip` -> name-to-IP map (resolves lldpRemSysName to a device IP)
- `snmp_interface`: tags `index` (ifIndex) + `ifName`, fields `ifHighSpeed` (Mbps),
  `ifHCInOctets`, `ifHCOutOctets`, row `polled_at` (Unix ms) -> speed and rate per ifIndex
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
        self._speed: dict[tuple[str, str], float] = {}  # (device, ifIndex) -> Mbps
        # (device, ifIndex) -> last two (polled_at ms, in octets, out octets)
        self._samples: dict[tuple[str, str], list[tuple[float, int, int]]] = {}

    def update(self, metric: dict) -> None:
        tags, fields = metric.get("tags") or {}, metric.get("fields") or {}
        device = metric.get("source_ip") or tags.get("source")
        if not isinstance(device, str) or not device:
            return
        if name := tags.get("sysName"):
            self._names[_short(name)] = device
        measurement, index = metric.get("measurement"), str(tags.get("index") or "")
        if measurement == "snmp_interface" and index:
            if tags.get("ifName"):
                self._ifnames.setdefault(device, {})[index] = tags["ifName"]
            self._counters(device, index, fields, metric.get("polled_at"))
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
        if m:  # the far end knows this port by name only
            key = ifkey(names.get(m[1]))
        for device, ports in self._lldp.items():  # only the far end reports this link
            for port, (remote, rport) in ports.items():
                if key and self._ip(remote) == device_ip and ifkey(rport) == key:
                    return device, self._ifnames.get(device, {}).get(port)
        return None

    def _counters(self, device: str, index: str, fields: dict, polled_at: object) -> None:
        key = (device, index)
        speed = fields.get("ifHighSpeed")
        if _num(speed):
            if speed > 0:
                self._speed[key] = float(speed)
            else:  # 0 = the agent doesn't know the speed
                self._speed.pop(key, None)
        ins, outs = fields.get("ifHCInOctets"), fields.get("ifHCOutOctets")
        if _num(ins) and _num(outs) and _num(polled_at):
            samples = self._samples.setdefault(key, [])
            samples.append((float(polled_at), int(ins), int(outs)))
            del samples[:-2]

    def speed(self, device_ip: str, if_index: str) -> float | None:
        return self._speed.get((device_ip, str(if_index)))

    def rate(self, device_ip: str, if_index: str) -> float | None:
        """bits/s from the last two samples, max of in/out; None on counter wrap/reset."""
        samples = self._samples.get((device_ip, str(if_index)), [])
        if len(samples) < 2:
            return None
        (t1, in1, out1), (t2, in2, out2) = samples
        dt = (t2 - t1) / 1000
        if dt <= 0 or in2 < in1 or out2 < out1:
            return None
        return max(in2 - in1, out2 - out1) * 8 / dt

    def edges(self) -> list[dict]:
        """One dict per LLDP link, both ends' reports merged; speed = min, load = max of ends.

        `a_port`/`b_port` = ifIndex of that end, None when LLDP gave only a description/MAC.
        """
        by_key = {d: {ifkey(n): p for p, n in names.items()} for d, names in self._ifnames.items()}
        merged: dict[tuple, list[tuple[str, str | None, str | None]]] = {}
        unresolved: list[tuple[tuple[str, str], tuple, list]] = []
        for device, ports in self._lldp.items():
            for port, (remote, rport) in ports.items():
                far = self._ip(remote)
                if far == device:
                    continue
                m = _IFINDEX.match(rport or "")
                far_port = m[1] if m else by_key.get(far, {}).get(ifkey(rport))
                near = (device, port, self._ifnames.get(device, {}).get(port))
                if far_port is None:
                    # ponytail: unresolved far port (description, MAC) can't merge with the far
                    # end's own report; poll lldpLocPortTable to resolve it
                    key = tuple(sorted([(device, port), (far, f"name:{ifkey(rport)}")]))
                    unresolved.append(((device, port), key, [near, (far, None, rport)]))
                    continue
                end = (far, far_port, self._ifnames.get(far, {}).get(far_port) or rport)
                merged.setdefault(tuple(sorted([(device, port), (far, far_port)])), [near, end])
        # one local port has one neighbor: the far end's resolved report wins over our guess
        used = {end for key in merged for end in key}
        for near_key, key, ends in unresolved:
            if near_key not in used:
                merged.setdefault(key, ends)
        out = []
        for key in sorted(merged):
            ends = sorted(merged[key], key=lambda e: (e[0], e[1] or ""))
            (a, a_port, a_if), (b, b_port, b_if) = ends
            ends = [(a, a_port), (b, b_port)]
            speeds = [s for d, p in ends if p and (s := self.speed(d, p)) is not None]
            loads = [r for d, p in ends if p and (r := self.rate(d, p)) is not None]
            out.append(
                {
                    "a": a,
                    "a_if": a_if,
                    "a_port": a_port,
                    "b": b,
                    "b_if": b_if,
                    "b_port": b_port,
                    "speed_mbps": min(speeds) if speeds else None,
                    "load_bps": max(loads) if loads else None,
                }
            )
        return out


def _num(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
