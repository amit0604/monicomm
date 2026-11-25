"""Catchup PCAP parser: turns a .pcap/.pcapng file into a compact, JSON-safe analysis.

Pure Python (dpkt), streaming, one pass. Packet numbers are 1-based, like Wireshark,
so every finding can cite the packets it came from (PROJECT.md AI rule 4).
"""

import ipaddress
import itertools
import socket
from collections import Counter, defaultdict
from struct import error as struct_error

import dpkt

PCAP_MAGICS = {
    b"\xa1\xb2\xc3\xd4",
    b"\xd4\xc3\xb2\xa1",
    b"\xa1\xb2\x3c\x4d",
    b"\x4d\x3c\xb2\xa1",
}
PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"

# ponytail: fixed thresholds/caps, tune on real captures from our network
SLOW_HANDSHAKE_S = 0.2  # SYN -> SYN/ACK slower than this is flagged
MAX_ITEMS = 1000  # cap per list (dns/http/tls) so the JSON stays small
MAX_PER_ANOMALY_TYPE = 200  # per type, so floods of one kind never hide another
MAX_CONVERSATIONS = 20_000  # bounds memory on SYN floods/spoofing; later flows only counted
MAX_TEXT = 200  # max length of payload-derived strings (host, uri, dns, sni)
MAX_TIME_BINS = 200_000  # per-conversation time bins kept for time-window views
MAX_STREAM_BYTES = 1_000_000  # follow-stream payload cap
# Wireshark-style ASCII view: printable bytes and \t \n \r as-is, everything else "."
_ASCII_VIEW = bytes(b if 32 <= b < 127 or b in (9, 10, 13) else 46 for b in range(256))
PORT_SCAN_PORTS = 100  # one client opening more distinct ports than this on one server = scan
BEACON_MIN_CONNECTIONS = 5  # internal -> external connections needed to judge regularity
BEACON_JITTER = 0.10  # every gap within 10% of the mean gap = timer-driven check-in
INTERNAL_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "127.0.0.0/8",
        "fc00::/7",
        "fe80::/10",
        "::1/128",
    )
]

HTTP_METHODS = (
    b"GET ",
    b"POST ",
    b"PUT ",
    b"DELETE ",
    b"HEAD ",
    b"OPTIONS ",
    b"PATCH ",
)


class PcapError(ValueError):
    """The file is not a capture we can read."""


def is_capture(head: bytes) -> bool:
    return head[:4] in PCAP_MAGICS or head[:4] == PCAPNG_MAGIC


def _reader(f):
    head = f.read(4)
    f.seek(0)
    try:
        if head == PCAPNG_MAGIC:
            return dpkt.pcapng.Reader(f)
        if head in PCAP_MAGICS:
            return dpkt.pcap.Reader(f)
    except (ValueError, dpkt.dpkt.Error) as e:
        raise PcapError(f"unreadable capture header: {e}") from e
    raise PcapError("not a pcap/pcapng file")


def _ip(buf: bytes, linktype: int):
    """Return the IP/IP6 layer (or ARP/None) for the common link types."""
    if linktype == dpkt.pcap.DLT_EN10MB:
        return dpkt.ethernet.Ethernet(buf).data
    if linktype in (12, 14, 101):  # raw IP
        return dpkt.ip6.IP6(buf) if buf and buf[0] >> 4 == 6 else dpkt.ip.IP(buf)
    if linktype == 113:  # Linux cooked capture
        return dpkt.sll.SLL(buf).data
    return None


def _addr(raw: bytes) -> str:
    return socket.inet_ntop(socket.AF_INET6 if len(raw) == 16 else socket.AF_INET, raw)


class _Truncated(Exception):
    def __init__(self, at):
        self.at = at


def _packets(f):
    """Yield (packet_no, ts, ip_layer, wire_len). Stops quietly on a truncated tail."""
    reader = _reader(f)
    linktype = reader.datalink()
    it = iter(reader)
    n = 0
    while True:
        try:
            ts, buf = next(it)
        except StopIteration:
            return
        except (dpkt.dpkt.Error, ValueError, EOFError, OSError) as e:
            raise _Truncated(n) from e
        n += 1
        try:
            layer = _ip(buf, linktype)
        except (dpkt.dpkt.Error, ValueError, IndexError):
            layer = None
        yield n, ts, layer, len(buf)


def _conv_key(proto, src, sport, dst, dport):
    """Direction-independent key; endpoint 'a' is the smaller (ip, port)."""
    a, b = (src, sport), (dst, dport)
    return (proto, *a, *b) if a <= b else (proto, *b, *a)


def _app_proto(transport, sport, dport, payload):
    if transport == "UDP" and 53 in (sport, dport):
        return "DNS"
    if not payload:
        return transport
    if payload.startswith(HTTP_METHODS) or payload.startswith(b"HTTP/1."):
        return "HTTP"
    if len(payload) > 2 and payload[0] in (0x14, 0x15, 0x16, 0x17) and payload[1] == 3:
        return "TLS"
    return transport


def _sni(payload: bytes):
    """server_name from a ClientHello in this segment.

    ponytail: a ClientHello split over several TCP segments (big post-quantum key shares)
    loses its SNI; add per-flow buffering of the first record if that shows up a lot.
    """
    try:
        rec = dpkt.ssl.TLSRecord(payload)
        if rec.type != 22:
            return None
        hs = dpkt.ssl.TLSHandshake(rec.data)
        if hs.type != 1:
            return None
        for ext_type, data in getattr(hs.data, "extensions", []):
            # server_name_list: u16 list len, then entries of u8 type + u16 len + name
            if ext_type == 0 and len(data) >= 5 and data[2] == 0:
                name_len = int.from_bytes(data[3:5], "big")
                return _text(data[5 : 5 + name_len].decode("ascii", "replace"))
    except (dpkt.dpkt.Error, ValueError, IndexError, struct_error):
        return None
    return None


def _text(s):
    """Payload-derived string: bounded length, no control characters."""
    if s is None:
        return None
    if isinstance(s, bytes):
        s = s.decode("utf-8", "replace")
    return "".join(ch if ch.isprintable() else "?" for ch in s[:MAX_TEXT])


def _append(lst, item):
    if len(lst) < MAX_ITEMS:
        lst.append(item)


class _TimeBins:
    """Per-conversation (packets, bytes) histogram over capture time, for time-window views.

    Starts at 1 s bins; whenever the total number of bins passes MAX_TIME_BINS the width
    doubles and bins merge, so memory stays bounded however long or busy the capture is.
    """

    def __init__(self):
        self.width = 1.0
        self.bins = defaultdict(dict)  # conv id -> {bin index: [packets, bytes]}
        self.total = 0

    def add(self, conv_id, offset_s, size):
        b = self.bins[conv_id].get(i := int(offset_s // self.width))
        if b is None:
            self.bins[conv_id][i] = [1, size]
            self.total += 1
            if self.total > MAX_TIME_BINS:
                self._coarsen()
        else:
            b[0] += 1
            b[1] += size

    def _coarsen(self):
        self.width *= 2
        self.total = 0
        for conv_id, old in self.bins.items():
            new = {}
            for i, (p, b) in old.items():
                cell = new.setdefault(i // 2, [0, 0])
                cell[0] += p
                cell[1] += b
            self.bins[conv_id] = new
            self.total += len(new)

    def export(self):
        return {
            "width_s": self.width,
            "conversations": {str(k): v for k, v in self.bins.items()},
        }


def _anomaly(anomalies, counts, item):
    counts[item["type"]] += 1
    if counts[item["type"]] <= MAX_PER_ANOMALY_TYPE:
        anomalies.append(item)


def analyze(path) -> dict:
    """One pass over the capture. Raises PcapError if the file isn't a capture.

    Memory is bounded: at most MAX_CONVERSATIONS flows are tracked (later ones are only
    counted), and per-direction TCP state is one integer.
    """
    protocols = Counter()
    proto_bytes = Counter()
    convs = {}  # key -> dict
    untracked = 0  # packets of flows beyond MAX_CONVERSATIONS
    dns, http, tls, anomalies = [], [], [], []
    anomaly_counts = Counter()
    tcp_state = {}  # (src, sport, dst, dport) -> highest seq end seen
    pending_syn = {}  # (src, sport, dst, dport) -> (packet_no, ts)
    bins = _TimeBins()
    first_ts = last_ts = None
    count = 0
    truncated_at = None

    with open(path, "rb") as f:
        try:
            for n, ts, ip, size in _packets(f):
                count = n
                first_ts = ts if first_ts is None else first_ts
                last_ts = ts
                if isinstance(ip, dpkt.arp.ARP):
                    protocols["ARP"] += 1
                    proto_bytes["ARP"] += size
                    continue
                if not isinstance(ip, dpkt.ip.IP | dpkt.ip6.IP6):
                    protocols["Other"] += 1
                    proto_bytes["Other"] += size
                    continue

                src, dst = _addr(ip.src), _addr(ip.dst)
                l4 = ip.data
                if isinstance(l4, dpkt.tcp.TCP):
                    transport, sport, dport = "TCP", l4.sport, l4.dport
                    payload = bytes(l4.data)
                elif isinstance(l4, dpkt.udp.UDP):
                    transport, sport, dport = "UDP", l4.sport, l4.dport
                    payload = bytes(l4.data)
                elif isinstance(l4, dpkt.icmp.ICMP | dpkt.icmp6.ICMP6):
                    transport, sport, dport, payload = "ICMP", 0, 0, b""
                else:
                    transport, sport, dport, payload = "IP", 0, 0, b""

                app = _app_proto(transport, sport, dport, payload)
                protocols[app] += 1
                proto_bytes[app] += size

                key = _conv_key(transport, src, sport, dst, dport)
                c = convs.get(key)
                if c is None:
                    if len(convs) >= MAX_CONVERSATIONS:
                        untracked += 1
                        continue
                    c = convs[key] = _new_conv(len(convs), transport, app, key, n, ts)
                c["packets"] += 1
                c["bytes"] += size
                c["end"] = ts
                if (src, sport) == (key[1], key[2]):  # sent by endpoint a
                    c["a_packets"] += 1
                    c["a_bytes"] += size
                bins.add(c["id"], ts - first_ts, size)
                if c["app_protocol"] in ("TCP", "UDP") and app not in ("TCP", "UDP"):
                    c["app_protocol"] = app

                if transport == "TCP":
                    retrans = _tcp_checks(
                        n,
                        ts,
                        l4,
                        src,
                        dst,
                        payload,
                        c,
                        tcp_state,
                        pending_syn,
                        anomalies,
                        anomaly_counts,
                    )
                    if retrans:
                        continue  # don't count its metadata twice

                if app == "DNS":
                    _dns(n, payload, dns)
                elif app == "HTTP" and payload.startswith(HTTP_METHODS):
                    _append(http, _http(n, payload))
                elif app == "TLS":
                    sni = _sni(payload)
                    if sni:
                        _append(tls, {"packet": n, "sni": sni, "conversation": c["id"]})
        except _Truncated as t:
            truncated_at = t.at

    conv_list = sorted(convs.values(), key=lambda c: c["id"])
    scanned = _detect_patterns(conv_list, anomalies, anomaly_counts)
    for c in conv_list:
        if c["resets"] and c["id"] not in scanned:
            _anomaly(
                anomalies,
                anomaly_counts,
                {
                    "type": "tcp_reset",
                    "packet": c["first_reset_packet"],
                    "conversation": c["id"],
                    "detail": f"{c['resets']} RST packet(s)",
                },
            )
    for (src, sport, dst, dport), (n, _ts) in pending_syn.items():
        conv = convs[_conv_key("TCP", src, sport, dst, dport)]
        if conv["id"] not in scanned:
            _anomaly(
                anomalies,
                anomaly_counts,
                {
                    "type": "syn_no_response",
                    "packet": n,
                    "conversation": conv["id"],
                    "detail": f"{src}:{sport} -> {dst}:{dport} SYN never answered",
                },
            )

    anomalies.sort(key=lambda a: a["packet"])
    return {
        "packet_count": count,
        "start": first_ts,
        "end": last_ts,
        "duration_s": round(last_ts - first_ts, 6) if count else 0,
        "truncated_after_packet": truncated_at,
        "protocols": [
            {"name": k, "packets": v, "bytes": proto_bytes[k]} for k, v in protocols.most_common()
        ],
        "conversations": conv_list,
        "untracked_packets": untracked,
        "dns": dns,
        "http": http,
        "tls": tls,
        "anomalies": anomalies,
        "anomaly_counts": dict(anomaly_counts),  # true totals, past the per-type cap too
        "time_bins": bins.export(),  # stored apart by the service; feeds time-window views
    }


def _new_conv(conv_id, transport, app, key, n, ts):
    return {
        "id": conv_id,
        "protocol": transport,
        "app_protocol": app,
        "a": {"ip": key[1], "port": key[2]},
        "b": {"ip": key[3], "port": key[4]},
        "packets": 0,
        "bytes": 0,
        "a_packets": 0,  # sent by endpoint a; b sent the rest
        "a_bytes": 0,
        "first_packet": n,
        "start": ts,
        "end": ts,
        "handshake_rtt_ms": None,
        "client": None,  # SYN sender, TCP only
        "resets": 0,
        "first_reset_packet": None,
    }


def _http(n, payload):
    """Request line + Host. The query string is dropped: it often carries credentials."""
    try:
        req = dpkt.http.Request(payload)
        method, host, uri = req.method, req.headers.get("host"), req.uri
    except (dpkt.dpkt.Error, ValueError):
        method, host, uri = (
            payload.split(b" ", 1)[0].decode("ascii", "replace"),
            None,
            None,
        )
    if uri:
        uri = uri.split("?", 1)[0].split("#", 1)[0]
    return {
        "packet": n,
        "method": _text(method),
        "host": _text(host),
        "uri": _text(uri),
    }


def _seq_after(a, b):
    """a > b in 32-bit TCP sequence space (handles wraparound)."""
    return 0 < ((a - b) & 0xFFFFFFFF) < 0x80000000


def _tcp_checks(n, ts, tcp, src, dst, payload, conv, tcp_state, pending_syn, anomalies, counts):
    """Handshake/reset/retransmission checks. Returns True if this is a retransmission.

    ponytail: a data segment that ends at or before the highest byte already seen in that
    direction counts as a retransmission, so out-of-order arrivals count too (Wireshark
    separates them). One int per direction keeps memory flat; add a small window if needed.
    """
    fwd = (src, tcp.sport, dst, tcp.dport)
    flags = tcp.flags
    syn, ack = flags & dpkt.tcp.TH_SYN, flags & dpkt.tcp.TH_ACK
    if syn and not ack:
        pending_syn.setdefault(fwd, (n, ts))
        if conv["client"] is None:
            conv["client"] = src
    elif syn and ack:
        rev = (dst, tcp.dport, src, tcp.sport)
        if rev in pending_syn:
            _, syn_ts = pending_syn.pop(rev)
            rtt = ts - syn_ts
            conv["handshake_rtt_ms"] = round(rtt * 1000, 3)
            if rtt > SLOW_HANDSHAKE_S:
                _anomaly(
                    anomalies,
                    counts,
                    {
                        "type": "slow_handshake",
                        "packet": n,
                        "conversation": conv["id"],
                        "detail": f"SYN/ACK after {rtt * 1000:.0f} ms",
                    },
                )
    if flags & dpkt.tcp.TH_RST:
        conv["resets"] += 1
        if conv["first_reset_packet"] is None:
            conv["first_reset_packet"] = n
    if not payload:
        return False
    end = (tcp.seq + len(payload)) & 0xFFFFFFFF
    highest = tcp_state.get(fwd)
    if highest is None or _seq_after(end, highest):
        tcp_state[fwd] = end
        return False
    if len(payload) <= 1:
        return False  # keep-alive / zero-window probe, not a retransmission
    _anomaly(
        anomalies,
        counts,
        {
            "type": "tcp_retransmission",
            "packet": n,
            "conversation": conv["id"],
            "detail": f"seq {tcp.seq} len {len(payload)} from {src}:{tcp.sport}",
        },
    )
    return True


def is_internal(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in INTERNAL_NETS if net.version == addr.version)


def _detect_patterns(convs, anomalies, counts) -> set:
    """Port scans and beacons over TCP conversations. Returns ids of conversations in a scan,
    so their resets/unanswered SYNs are reported once as the scan, not one by one.

    ponytail: whole-capture counts, no sliding window; add one if long captures give false scans.
    """
    by_pair = defaultdict(list)
    for c in convs:
        if c["protocol"] == "TCP" and c["client"]:
            server = c["b"] if c["a"]["ip"] == c["client"] else c["a"]
            by_pair[(c["client"], server["ip"])].append((c, server["port"]))

    scanned = set()
    for (client, server), items in by_pair.items():
        ports = {p for _, p in items}
        first = min(items, key=lambda i: i[0]["first_packet"])[0]
        ids = [c["id"] for c, _ in items]
        if len(ports) > PORT_SCAN_PORTS:
            scanned.update(ids)
            span = max(c["end"] for c, _ in items) - first["start"]
            _anomaly(
                anomalies,
                counts,
                {
                    "type": "port_scan",
                    "packet": first["first_packet"],
                    "hosts": [client, server],
                    "conversations": ids[:50],
                    "detail": f"{client} probed {len(ports)} ports on {server} in {span:.1f} s",
                },
            )
            continue
        if len(items) < BEACON_MIN_CONNECTIONS or not is_internal(client) or is_internal(server):
            continue
        starts = sorted(c["start"] for c, _ in items)
        gaps = [b - a for a, b in itertools.pairwise(starts)]
        mean = sum(gaps) / len(gaps)
        if mean > 0 and all(abs(g - mean) <= BEACON_JITTER * mean for g in gaps):
            _anomaly(
                anomalies,
                counts,
                {
                    "type": "beacon",
                    "packet": first["first_packet"],
                    "hosts": [client, server],
                    "conversations": ids[:50],
                    "detail": (
                        f"{client} connected to {server} {len(items)} times every {mean:.1f} s"
                    ),
                },
            )
    return scanned


def _dns(n, payload, out):
    try:
        msg = dpkt.dns.DNS(payload)
    except (dpkt.dpkt.Error, ValueError, IndexError, struct_error):
        return
    if not msg.qd:
        return
    q = msg.qd[0]
    item = {
        "packet": n,
        "query": _text(q.name),
        "qtype": q.type,
        "response": msg.qr == dpkt.dns.DNS_R,
    }
    if item["response"]:
        item["rcode"] = msg.rcode
        item["answers"] = [
            _addr(rr.rdata)
            for rr in msg.an
            if (rr.type, len(rr.rdata)) in ((dpkt.dns.DNS_A, 4), (dpkt.dns.DNS_AAAA, 16))
        ]
    _append(out, item)


def follow_stream(path, conv: dict) -> list[dict]:
    """Payload segments of one conversation (from analyze()['conversations']), in capture order.

    ponytail: capture order, exact-duplicate retransmissions dropped; no out-of-order
    reassembly. Add seq-based reassembly if technicians hit reordered streams.
    """
    a = (conv["a"]["ip"], conv["a"]["port"])
    b = (conv["b"]["ip"], conv["b"]["port"])
    proto = conv["protocol"]
    out, total, seen = [], 0, set()
    with open(path, "rb") as f:
        try:
            for n, ts, ip, _size in _packets(f):
                if not isinstance(ip, dpkt.ip.IP | dpkt.ip6.IP6):
                    continue
                l4 = ip.data
                if proto == "TCP" and not isinstance(l4, dpkt.tcp.TCP):
                    continue
                if proto == "UDP" and not isinstance(l4, dpkt.udp.UDP):
                    continue
                if proto not in ("TCP", "UDP"):
                    return out
                src, dst = (_addr(ip.src), l4.sport), (_addr(ip.dst), l4.dport)
                if {src, dst} != {a, b}:
                    continue
                payload = bytes(l4.data)
                if not payload:
                    continue
                if proto == "TCP":
                    seg = (src, l4.seq, len(payload))
                    if seg in seen:
                        continue
                    seen.add(seg)
                take = payload[: MAX_STREAM_BYTES - total]
                out.append(
                    {
                        "packet": n,
                        "ts": ts,
                        "from": "a" if src == a else "b",
                        "text": take.translate(_ASCII_VIEW).decode("ascii"),
                        "bytes": len(payload),
                    }
                )
                total += len(take)
                if total >= MAX_STREAM_BYTES:
                    break
        except _Truncated:
            pass
    return out
