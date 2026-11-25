import json

import pytest
from app.modules.pcap import network, parser
from conftest import ACK, PSH, SYN, C, S, tcp, write_pcap
from test_api import client, upload  # noqa: F401  (fixture + helper)


def _inputs(path):
    a = parser.analyze(path)
    return a, json.loads(json.dumps(a.pop("time_bins")))  # same shape as stored on disk


def test_graph_nodes_edges(sample_pcap):
    a, bins = _inputs(sample_pcap)
    g = network.graph(a, bins, "", 1, None, None)
    assert {n["id"] for n in g["nodes"]} == {C, S, "10.0.0.53", "10.0.0.9"}
    web = next(e for e in g["edges"] if {e["source"], e["target"]} == {C, S})
    assert (
        web["packets"] == 7 and web["services"] == ["HTTP"] and web["protocol"] == "TCP"
    )
    assert all(
        e["protocol"] == "UDP"
        for e in network.graph(a, bins, "UDP", 1, None, None)["edges"]
    )
    assert len(network.graph(a, bins, "", 5, None, None)["edges"]) == 1  # min_packets


def test_time_window_uses_bins(tmp_path):
    pkts = [
        (100.0 + i, tcp(C, S, 40000, 80, PSH | ACK, seq=1 + i, data=b"x" * 10))
        for i in range(5)
    ]
    pkts += [
        (200.0 + i, tcp(C, "10.0.0.7", 40001, 22, PSH | ACK, seq=1 + i, data=b"y" * 10))
        for i in range(3)
    ]
    a, bins = _inputs(write_pcap(tmp_path / "w.pcap", pkts))
    early = network.overview(a, bins, 0, 50)
    late = network.overview(a, bins, 99, 110)
    assert early["packets"] == 5 and early["hosts"] == 2
    assert late["packets"] == 3 and {t["ip"] for t in late["top_talkers"]} == {
        C,
        "10.0.0.7",
    }
    g = network.graph(a, bins, "", 1, 99, None)
    assert [(e["source"], e["target"]) for e in g["edges"]] == [(C, "10.0.0.7")]


def test_bins_coarsen_but_keep_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "MAX_TIME_BINS", 4)
    pkts = [
        (float(i), tcp(C, S, 40000, 80, PSH | ACK, seq=1 + i, data=b"z"))
        for i in range(20)
    ]
    a, bins = _inputs(write_pcap(tmp_path / "c.pcap", pkts))
    assert bins["width_s"] >= 4
    assert sum(p for cb in bins["conversations"].values() for p, _ in cb.values()) == 20
    assert sum(b["packets"] for b in network.timeline(a, bins)["buckets"]) == 20


def test_suspicious_hosts_and_host_details(tmp_path):
    pkts = []
    for port in range(1, 151):
        pkts.append((port * 0.01, tcp("10.0.0.66", S, 50000, port, SYN, seq=1)))
    pkts.append((5.0, tcp(C, S, 40000, 80, PSH | ACK, seq=1, data=b"hello")))
    a, bins = _inputs(write_pcap(tmp_path / "s.pcap", pkts))
    nodes = {n["id"]: n for n in network.graph(a, bins, "", 1, None, None)["nodes"]}
    assert (
        nodes["10.0.0.66"]["suspicious"]
        and nodes[S]["suspicious"]
        and not nodes[C]["suspicious"]
    )
    h = network.host(a, C)
    assert h["packets_sent"] == 1 and h["bytes_received"] == 0 and h["peers"] == 1
    assert network.host(a, "10.9.9.9") is None
    assert network.host(a, "10.0.0.66")["findings"][0]["type"] == "port_scan"


def test_network_endpoints(client, sample_pcap):  # noqa: F811
    cid = upload(client, sample_pcap).json()["id"]
    base = f"/api/v1/pcap/captures/{cid}"
    assert client.get(f"{base}/graph").json()["nodes"]
    assert client.get(f"{base}/graph?protocol=ARP").status_code == 422
    # t_start and t_end are separate params (a shared Query object once made t_end read t_start)
    o = client.get(f"{base}/overview?t_start=0.5&t_end=1.05").json()
    assert o["window"] == {"t_start": 0.5, "t_end": 1.05}
    assert client.get(f"{base}/overview?t_start=-1").status_code == 422
    assert (
        len(client.get(f"{base}/timeline").json()["buckets"])
        == network.TIMELINE_BUCKETS
    )
    assert client.get(f"{base}/hosts/{C}").json()["ip"] == C
    assert client.get(f"{base}/hosts/not-an-ip").status_code == 400
    assert client.get(f"{base}/hosts/10.9.9.9").status_code == 404


@pytest.mark.parametrize("path", ["graph", "overview", "timeline", "hosts/10.0.0.1"])
def test_network_endpoints_404(client, path):  # noqa: F811
    assert client.get(f"/api/v1/pcap/captures/{'0' * 32}/{path}").status_code == 404
