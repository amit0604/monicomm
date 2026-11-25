import socket

import dpkt
import pytest

C, S = "10.0.0.1", "10.0.0.2"  # client, server


def eth(src, dst, l4, proto):
    ip = dpkt.ip.IP(src=socket.inet_aton(src), dst=socket.inet_aton(dst), p=proto, data=l4)
    ip.len = len(ip)
    return bytes(dpkt.ethernet.Ethernet(type=dpkt.ethernet.ETH_TYPE_IP, data=ip))


def tcp(src, dst, sport, dport, flags, seq=0, ack=0, data=b""):
    return eth(
        src,
        dst,
        dpkt.tcp.TCP(sport=sport, dport=dport, flags=flags, seq=seq, ack=ack, data=data),
        dpkt.ip.IP_PROTO_TCP,
    )


def udp(src, dst, sport, dport, data):
    u = dpkt.udp.UDP(sport=sport, dport=dport, data=data)
    u.ulen = len(u)
    return eth(src, dst, u, dpkt.ip.IP_PROTO_UDP)


def write_pcap(path, packets):
    """packets: list of (ts, bytes)."""
    with open(path, "wb") as f:
        w = dpkt.pcap.Writer(f)
        for ts, buf in packets:
            w.writepkt(buf, ts=ts)
    return path


SYN, ACK, PSH, RST = dpkt.tcp.TH_SYN, dpkt.tcp.TH_ACK, dpkt.tcp.TH_PUSH, dpkt.tcp.TH_RST
REQ = b"GET /index.html HTTP/1.1\r\nHost: intranet.local\r\n\r\n"
RESP = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi"


def dns_query():
    q = dpkt.dns.DNS(id=1, qd=[dpkt.dns.DNS.Q(name="core-sw-01.lan", type=dpkt.dns.DNS_A)])
    return udp(C, "10.0.0.53", 5353, 53, bytes(q))


def scenario():
    """Packets 1-3 handshake (300 ms SYN/ACK), 4 request, 5 retransmitted request,
    6 response, 7 RST, 8 DNS query, 9 unanswered SYN."""
    return [
        (1.000, tcp(C, S, 40000, 80, SYN, seq=100)),
        (1.300, tcp(S, C, 80, 40000, SYN | ACK, seq=500, ack=101)),
        (1.301, tcp(C, S, 40000, 80, ACK, seq=101, ack=501)),
        (1.302, tcp(C, S, 40000, 80, PSH | ACK, seq=101, ack=501, data=REQ)),
        (1.800, tcp(C, S, 40000, 80, PSH | ACK, seq=101, ack=501, data=REQ)),
        (
            1.810,
            tcp(S, C, 80, 40000, PSH | ACK, seq=501, ack=101 + len(REQ), data=RESP),
        ),
        (1.900, tcp(S, C, 80, 40000, RST, seq=501 + len(RESP))),
        (2.000, dns_query()),
        (2.100, tcp(C, "10.0.0.9", 40001, 22, SYN, seq=1)),
    ]


@pytest.fixture
def sample_pcap(tmp_path):
    return write_pcap(tmp_path / "sample.pcap", scenario())
