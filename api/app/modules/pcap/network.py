"""Network views of an analyzed capture: host graph, overview stats, host details, timeline.

Built from the stored analysis (conversations) and its time bins, so no view re-reads the file.
Time windows are offsets in seconds from the first packet; their precision is the bin width
(1 s for most captures, coarser for very long or very busy ones).
Graph/overview ideas follow the PCAP Lab workshop app (hubs, suspicious hosts, top talkers/ports).
"""

from collections import Counter, defaultdict

from .parser import is_internal

TIMELINE_BUCKETS = 60
TOP_N = 10
HUB_MIN_DEGREE = (
    4  # a hub talks to at least this many peers and is in the top ~10% by degree
)
PATTERN_TYPES = ("port_scan", "beacon")  # anomalies that mark hosts as suspicious

WELL_KNOWN = {
    ("TCP", 20): "FTP data", ("TCP", 21): "FTP", ("TCP", 22): "SSH", ("TCP", 23): "Telnet",
    ("TCP", 25): "SMTP", ("TCP", 53): "DNS", ("UDP", 53): "DNS", ("UDP", 67): "DHCP",
    ("UDP", 68): "DHCP", ("UDP", 69): "TFTP", ("TCP", 80): "HTTP", ("UDP", 123): "NTP",
    ("TCP", 110): "POP3", ("TCP", 143): "IMAP", ("UDP", 161): "SNMP", ("UDP", 162): "SNMP trap",
    ("TCP", 389): "LDAP", ("TCP", 443): "HTTPS", ("UDP", 443): "QUIC", ("TCP", 445): "SMB",
    ("UDP", 514): "Syslog", ("TCP", 514): "Syslog", ("TCP", 636): "LDAPS", ("TCP", 993): "IMAPS",
    ("TCP", 1883): "MQTT", ("TCP", 3306): "MySQL", ("TCP", 3389): "RDP", ("UDP", 5353): "mDNS",
    ("TCP", 5432): "PostgreSQL", ("TCP", 8080): "HTTP-alt", ("TCP", 8443): "HTTPS-alt",
    ("TCP", 9100): "Printer",
}  # fmt: skip


def _server_port(c: dict) -> int | None:
    """The service side of a conversation: the SYN receiver, else a well-known port, else the lower one."""
    if c["protocol"] not in ("TCP", "UDP"):
        return None
    if c["client"]:
        return c["b"]["port"] if c["a"]["ip"] == c["client"] else c["a"]["port"]
    a, b = c["a"]["port"], c["b"]["port"]
    if (c["protocol"], a) in WELL_KNOWN:
        return a
    if (c["protocol"], b) in WELL_KNOWN:
        return b
    return min(a, b)


def _windowed(analysis: dict, bins: dict, t_start, t_end):
    """Yield (conversation, packets, bytes) with the traffic inside [t_start, t_end]."""
    if t_start is None and t_end is None:
        for c in analysis["conversations"]:
            yield c, c["packets"], c["bytes"]
        return
    lo = t_start or 0.0
    hi = t_end if t_end is not None else float("inf")
    width = bins["width_s"]
    per_conv = bins["conversations"]
    for c in analysis["conversations"]:
        p = b = 0
        for i, (bp, bb) in per_conv.get(str(c["id"]), {}).items():
            start = int(i) * width
            if start + width > lo and start <= hi:  # bin overlaps the window
                p += bp
                b += bb
        if p:
            yield c, p, b


def _suspicious(analysis: dict, conv_ids: set | None = None) -> list[dict]:
    """Scan/beacon findings, optionally only those with traffic among conv_ids."""
    out = []
    for a in analysis["anomalies"]:
        if a["type"] in PATTERN_TYPES and (
            conv_ids is None or conv_ids & set(a.get("conversations", []))
        ):
            out.append(a)
    return out


def graph(
    analysis: dict, bins: dict, protocol: str, min_packets: int, t_start, t_end
) -> dict:
    """Hosts as nodes; one undirected edge per host pair, weighted by packets and bytes."""
    edges = {}
    for c, p, b in _windowed(analysis, bins, t_start, t_end):
        if protocol and c["protocol"] != protocol:
            continue
        src, dst = sorted((c["a"]["ip"], c["b"]["ip"]))
        e = edges.setdefault(
            (src, dst),
            {
                "source": src,
                "target": dst,
                "packets": 0,
                "bytes": 0,
                "protocols": set(),
                "services": set(),
            },
        )
        e["packets"] += p
        e["bytes"] += b
        e["protocols"].add(c["protocol"])
        service = WELL_KNOWN.get((c["protocol"], _server_port(c)))
        if service:
            e["services"].add(service)

    kept = [e for e in edges.values() if e["packets"] >= min_packets]
    degree, packets, volume = Counter(), Counter(), Counter()
    for e in kept:
        e["protocols"] = sorted(e["protocols"])
        e["services"] = sorted(e["services"])
        e["protocol"] = e["protocols"][0] if len(e["protocols"]) == 1 else "Mixed"
        for ip in (e["source"], e["target"]):
            degree[ip] += 1
            packets[ip] += e["packets"]
            volume[ip] += e["bytes"]

    degrees = sorted(degree.values(), reverse=True)
    hub_at = max(HUB_MIN_DEGREE, degrees[len(degrees) // 10] if degrees else 0)
    flagged = {ip for a in _suspicious(analysis) for ip in a["hosts"]}
    nodes = [
        {
            "id": ip,
            "internal": is_internal(ip),
            "packets": packets[ip],
            "bytes": volume[ip],
            "degree": d,
            "hub": d >= hub_at,
            "suspicious": ip in flagged,
        }
        for ip, d in degree.items()
    ]
    return {"nodes": nodes, "edges": kept}


def overview(analysis: dict, bins: dict, t_start, t_end) -> dict:
    """Totals, protocol mix, top talkers, top ports and findings for the whole capture or a window."""
    full = t_start is None and t_end is None
    rows = list(_windowed(analysis, bins, t_start, t_end))
    talkers = defaultdict(lambda: {"packets": 0, "bytes": 0})
    ports = Counter()
    protocols = Counter()
    for c, p, b in rows:
        for ip in (c["a"]["ip"], c["b"]["ip"]):
            talkers[ip]["packets"] += p
            talkers[ip]["bytes"] += b
        port = _server_port(c)
        if port is not None:
            ports[(c["protocol"], port)] += p
        protocols[c["app_protocol"]] += p

    if full:  # exact packet-level mix, including ARP and non-IP
        protocols = Counter({x["name"]: x["packets"] for x in analysis["protocols"]})
    duration = analysis["duration_s"]
    lo = 0.0 if t_start is None else max(0.0, t_start)
    hi = duration if t_end is None else min(duration, t_end)
    top = sorted(talkers.items(), key=lambda kv: kv[1]["bytes"], reverse=True)[:TOP_N]
    return {
        "window": None if full else {"t_start": lo, "t_end": hi},
        "precision_s": None if full else bins["width_s"],
        "packets": analysis["packet_count"] if full else sum(p for _, p, _ in rows),
        "bytes": (
            sum(x["bytes"] for x in analysis["protocols"])
            if full
            else sum(b for _, _, b in rows)
        ),
        "hosts": len(talkers),
        "duration": round(hi - lo, 3),
        "start": (analysis["start"] or 0) + lo,
        "protocols": dict(protocols.most_common()),
        "top_talkers": [{"ip": ip, "internal": is_internal(ip), **v} for ip, v in top],
        "top_ports": [
            {
                "protocol": proto,
                "port": port,
                "service": WELL_KNOWN.get((proto, port)),
                "packets": n,
            }
            for (proto, port), n in ports.most_common(TOP_N)
        ],
        "suspicious": [
            {
                "type": a["type"],
                "packet": a["packet"],
                "hosts": a["hosts"],
                "message": a["detail"],
            }
            for a in _suspicious(
                analysis, None if full else {c["id"] for c, _, _ in rows}
            )
        ],
        "anomaly_counts": analysis.get("anomaly_counts", {}),
    }


def host(analysis: dict, ip: str) -> dict | None:
    """Whole-capture counters for one host, or None if it never appears."""
    h = {
        "ip": ip,
        "packets_sent": 0,
        "packets_received": 0,
        "bytes_sent": 0,
        "bytes_received": 0,
    }
    peers, protocols, seen = set(), set(), []
    for c in analysis["conversations"]:
        if ip == c["a"]["ip"]:
            sent_p, sent_b, peer = c["a_packets"], c["a_bytes"], c["b"]["ip"]
        elif ip == c["b"]["ip"]:
            sent_p, sent_b, peer = (
                c["packets"] - c["a_packets"],
                c["bytes"] - c["a_bytes"],
                c["a"]["ip"],
            )
        else:
            continue
        h["packets_sent"] += sent_p
        h["bytes_sent"] += sent_b
        h["packets_received"] += c["packets"] - sent_p
        h["bytes_received"] += c["bytes"] - sent_b
        if peer != ip:
            peers.add(peer)
        protocols.add(c["protocol"])
        seen += [c["start"], c["end"]]
    if not seen:
        return None
    return {
        **h,
        "internal": is_internal(ip),
        "peers": len(peers),
        "protocols": sorted(protocols),
        "first_seen": min(seen),
        "last_seen": max(seen),
        "findings": [a for a in _suspicious(analysis) if ip in a["hosts"]],
    }


def timeline(analysis: dict, bins: dict) -> dict:
    """Packets and bytes per time bucket across the capture (tracked IP conversations)."""
    duration = analysis["duration_s"]
    n = TIMELINE_BUCKETS
    width = max(duration, bins["width_s"]) / n
    buckets = [{"t": round(i * width, 3), "packets": 0, "bytes": 0} for i in range(n)]
    for conv_bins in bins["conversations"].values():
        for i, (p, b) in conv_bins.items():
            k = min(int(int(i) * bins["width_s"] / width), n - 1)
            buckets[k]["packets"] += p
            buckets[k]["bytes"] += b
    return {"duration": duration, "bucket_s": round(width, 3), "buckets": buckets}
