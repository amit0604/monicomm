import dpkt
import pytest
from app.modules.pcap import parser
from conftest import REQ, RESP, C, S


def test_analyze_summary(sample_pcap):
    r = parser.analyze(sample_pcap)
    assert r["packet_count"] == 9
    assert r["duration_s"] == pytest.approx(1.1)
    assert r["truncated_after_packet"] is None
    protos = {p["name"]: p["packets"] for p in r["protocols"]}
    assert protos == {"TCP": 5, "HTTP": 3, "DNS": 1}


def test_conversations(sample_pcap):
    convs = parser.analyze(sample_pcap)["conversations"]
    assert len(convs) == 3
    web = convs[0]
    assert web["app_protocol"] == "HTTP"
    assert web["packets"] == 7
    assert {web["a"]["port"], web["b"]["port"]} == {80, 40000}
    assert web["handshake_rtt_ms"] == pytest.approx(300, abs=1)


def test_anomalies_cite_packets(sample_pcap):
    found = {(a["type"], a["packet"]) for a in parser.analyze(sample_pcap)["anomalies"]}
    assert found == {
        ("slow_handshake", 2),
        ("tcp_retransmission", 5),
        ("tcp_reset", 7),
        ("syn_no_response", 9),
    }


def test_port_scan_folds_resets(tmp_path):
    from conftest import ACK, RST, SYN, tcp, write_pcap

    pkts = []
    for port in range(1, 151):
        pkts.append((port * 0.01, tcp(C, S, 50000, port, SYN, seq=1)))
        pkts.append((port * 0.01 + 0.001, tcp(S, C, port, 50000, RST | ACK, ack=2)))
    r = parser.analyze(write_pcap(tmp_path / "scan.pcap", pkts))
    types = [a["type"] for a in r["anomalies"]]
    assert types == ["port_scan"]
    assert "150 ports" in r["anomalies"][0]["detail"]


def test_beacon_internal_to_external(tmp_path):
    from conftest import SYN, tcp, write_pcap

    ext = "198.51.100.66"
    pkts = [(i * 30.0, tcp(C, ext, 40000 + i, 8443, SYN, seq=1)) for i in range(6)]
    pkts += [
        (i * 30.0 + 0.01, tcp(ext, C, 8443, 40000 + i, SYN | dpkt.tcp.TH_ACK, ack=2))
        for i in range(6)
    ]
    pkts.sort(key=lambda p: p[0])
    beacons = [
        a
        for a in parser.analyze(write_pcap(tmp_path / "b.pcap", pkts))["anomalies"]
        if a["type"] == "beacon"
    ]
    assert len(beacons) == 1 and "every 30.0 s" in beacons[0]["detail"]


def test_metadata(sample_pcap):
    r = parser.analyze(sample_pcap)
    assert r["http"] == [
        {"packet": 4, "method": "GET", "host": "intranet.local", "uri": "/index.html"}
    ]
    assert r["dns"][0]["query"] == "core-sw-01.lan" and r["dns"][0]["packet"] == 8


def test_follow_stream_drops_retransmission(sample_pcap):
    conv = parser.analyze(sample_pcap)["conversations"][0]
    segs = parser.follow_stream(sample_pcap, conv)
    assert [s["packet"] for s in segs] == [4, 6]
    assert segs[0]["text"] == REQ.decode() and segs[1]["text"] == RESP.decode()
    assert segs[0]["from"] != segs[1]["from"]


def test_not_a_capture(tmp_path):
    bad = tmp_path / "x.pcap"
    bad.write_bytes(b"hello world, not a capture")
    with pytest.raises(parser.PcapError):
        parser.analyze(bad)


@pytest.mark.parametrize("cut", [5, 10, 30])
def test_truncated_file_does_not_crash(sample_pcap, cut):
    sample_pcap.write_bytes(sample_pcap.read_bytes()[:-cut])
    r = parser.analyze(sample_pcap)
    assert r["packet_count"] >= 8


def test_pcapng(tmp_path):
    import dpkt
    from conftest import scenario

    p = tmp_path / "s.pcapng"
    with open(p, "wb") as f:
        w = dpkt.pcapng.Writer(f)
        for ts, buf in scenario():
            w.writepkt(buf, ts=ts)
    assert parser.analyze(p)["packet_count"] == 9


def test_follow_stream_binary_is_readable(tmp_path):
    from conftest import ACK, PSH, tcp, write_pcap

    pkt = tcp(C, S, 40000, 445, PSH | ACK, seq=1, data=b"\xfeSMB\x00\x01ok\r\n")
    p = write_pcap(tmp_path / "bin.pcap", [(1.0, pkt)])
    conv = parser.analyze(p)["conversations"][0]
    assert parser.follow_stream(p, conv)[0]["text"] == ".SMB..ok\r\n"


def _client_hello(sni: bytes) -> bytes:
    name = b"\x00" + len(sni).to_bytes(2, "big") + sni
    ext = (
        b"\x00\x00"
        + (len(name) + 2).to_bytes(2, "big")
        + len(name).to_bytes(2, "big")
        + name
    )
    body = (
        b"\x03\x03"
        + b"\x00" * 32
        + b"\x00"
        + b"\x00\x02\x13\x01"
        + b"\x01\x00"
        + len(ext).to_bytes(2, "big")
        + ext
    )
    hs = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + len(hs).to_bytes(2, "big") + hs


def test_tls_sni(tmp_path):
    from conftest import ACK, PSH, tcp, write_pcap

    pkt = tcp(
        C, S, 40000, 443, PSH | ACK, seq=1, data=_client_hello(b"portal.example.com")
    )
    r = parser.analyze(write_pcap(tmp_path / "t.pcap", [(1.0, pkt)]))
    assert r["tls"] == [{"packet": 1, "sni": "portal.example.com", "conversation": 0}]


def test_bad_dns_rdata_does_not_crash(tmp_path):
    from conftest import udp, write_pcap

    m = dpkt.dns.DNS(
        id=1,
        qr=dpkt.dns.DNS_R,
        qd=[dpkt.dns.DNS.Q(name="x.lan", type=dpkt.dns.DNS_A)],
        an=[
            dpkt.dns.DNS.RR(name="x.lan", type=dpkt.dns.DNS_A, rdata=b"\x01\x02\x03"),
            dpkt.dns.DNS.RR(
                name="x.lan", type=dpkt.dns.DNS_A, rdata=b"\x0a\x00\x00\x01"
            ),
        ],
    )
    r = parser.analyze(
        write_pcap(
            tmp_path / "d.pcap", [(1.0, udp("10.0.0.53", C, 53, 5353, bytes(m)))]
        )
    )
    assert r["dns"][0]["answers"] == ["10.0.0.1"]


def test_http_query_string_never_stored(tmp_path):
    from conftest import ACK, PSH, tcp, write_pcap

    req = b"GET /login?user=admin&password=S3cret HTTP/1.1\r\nHost: app\x07.lan\r\n\r\n"
    pkt = tcp(C, S, 40000, 80, PSH | ACK, seq=1, data=req)
    r = parser.analyze(write_pcap(tmp_path / "h.pcap", [(1.0, pkt)]))
    assert r["http"] == [
        {"packet": 1, "method": "GET", "host": "app?.lan", "uri": "/login"}
    ]


def test_keepalive_is_not_retransmission(tmp_path):
    from conftest import ACK, PSH, tcp, write_pcap

    pkts = [(1.0, tcp(C, S, 40000, 80, PSH | ACK, seq=1, data=b"hello"))]
    pkts += [
        (1.0 + 45 * i, tcp(C, S, 40000, 80, ACK, seq=5, data=b"\x00"))
        for i in range(1, 6)
    ]
    assert parser.analyze(write_pcap(tmp_path / "k.pcap", pkts))["anomalies"] == []


def test_retransmission_flood_does_not_hide_scan(tmp_path, monkeypatch):
    from conftest import ACK, PSH, RST, SYN, tcp, write_pcap

    monkeypatch.setattr(parser, "MAX_PER_ANOMALY_TYPE", 10)
    pkts = [
        (0.001 * i, tcp(C, S, 40000, 80, PSH | ACK, seq=1, data=b"abc"))
        for i in range(50)
    ]
    for port in range(1, 151):
        pkts.append((1 + port * 0.01, tcp("10.0.0.7", S, 50000, port, SYN, seq=1)))
        pkts.append(
            (1 + port * 0.01, tcp(S, "10.0.0.7", port, 50000, RST | ACK, ack=2))
        )
    r = parser.analyze(write_pcap(tmp_path / "f.pcap", pkts))
    assert "port_scan" in {a["type"] for a in r["anomalies"]}
    assert r["anomaly_counts"]["tcp_retransmission"] == 49
    assert sum(a["type"] == "tcp_retransmission" for a in r["anomalies"]) == 10


def test_conversation_cap_bounds_memory(tmp_path, monkeypatch):
    from conftest import SYN, tcp, write_pcap

    monkeypatch.setattr(parser, "MAX_CONVERSATIONS", 5)
    pkts = [(i * 0.001, tcp(C, S, 1000 + i, 80, SYN, seq=1)) for i in range(20)]
    r = parser.analyze(write_pcap(tmp_path / "c.pcap", pkts))
    assert len(r["conversations"]) == 5 and r["untracked_packets"] == 15
