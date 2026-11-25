from datetime import UTC, datetime

from app.modules.investigator import reroute
from app.modules.investigator.topology import Topology

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
MBPS = 1_000_000


def build(links):
    """links: (a, b, speed_mbps | None, load_bps | None); ports are numbered per device."""
    topo, ports = Topology(), {}
    for a, b, speed, load in links:
        ends = []
        for dev in (a, b):
            ports[dev] = ports.get(dev, 0) + 1
            ends.append((dev, ports[dev]))
        for (dev, idx), (far, far_idx) in (ends, ends[::-1]):
            base = {"source_ip": dev, "tags": {"source": dev, "sysName": dev}}
            topo.update(
                base
                | {
                    "measurement": "snmp_lldp_neighbor",
                    "tags": base["tags"] | {"index": f"0.{idx}.1"},
                    "fields": {"lldpRemSysName": far, "lldpRemPortId": f"eth{far_idx}"},
                }
            )
            for t, octets in ((0, 0), (60_000, None if load is None else int(load * 60 / 8))):
                fields = {} if speed is None else {"ifHighSpeed": speed}
                if octets is not None:
                    fields |= {"ifHCInOctets": octets, "ifHCOutOctets": 0}
                topo.update(
                    base
                    | {
                        "measurement": "snmp_interface",
                        "tags": base["tags"] | {"index": str(idx), "ifName": f"eth{idx}"},
                        "fields": fields,
                        "polled_at": t,
                    }
                )
    return topo


def square(ab=100 * MBPS, other=100 * MBPS, extra=()):
    return build(
        [
            ("A", "B", 1000, ab),
            ("B", "C", 1000, other),
            ("C", "D", 1000, other),
            ("D", "A", 1000, other),
            *extra,
        ]
    )


def run(topo, links=(), devices=()):
    return reroute.compute(topo, list(links), list(devices), 100_000, 0.8, NOW)


def path(p):
    return [p["hops"][0]["from"]] + [h["to"] for h in p["hops"]]


def test_square_link_down_goes_the_other_way():
    out = run(square(), [("A", "eth1")])
    assert out["computed_at"] == "2026-11-25T12:00:00Z"
    assert out["isolated"] == []
    assert out["assumptions"][0].startswith("Link costs estimated from interface speed")
    assert "100000 Mbps" in out["assumptions"][0]
    assert "ECMP" in out["assumptions"][1] and "LLDP" in out["assumptions"][2]
    assert out["assumptions"][3] == "Moved load = last measured rate on the failed link"
    [flow] = out["flows"]
    assert (flow["from"], flow["to"], flow["load_bps"]) == ("A", "B", 100 * MBPS)
    assert flow["reason"] == "Link A eth1 <-> B eth1 down"
    assert [(h["from"], h["to"], h["status"]) for h in flow["before"]["hops"]] == [("A", "B", "ok")]
    pred = flow["predicted"]
    assert path(pred) == ["A", "D", "C", "B"]
    assert pred["cost"] == 300  # 100000 / 1000 per hop
    assert pred["max_util"] == 0.2 and pred["status"] == "ok"
    assert pred["hops"][0] == {
        "from": "A",
        "from_if": "eth2",
        "to": "D",
        "to_if": "eth2",
        "speed_mbps": 1000.0,
        "load_bps": 100 * MBPS,
        "util_after": 0.2,
        "status": "ok",
    }
    assert flow["recommended"] is None


def test_far_end_name_and_ifindex_find_the_same_link():
    topo = square()
    assert run(topo, [("B", "eth1")])["flows"][0]["reason"] == "Link A eth1 <-> B eth1 down"
    assert run(topo, [("A", "ifIndex 1")])["flows"][0]["reason"] == "Link A eth1 <-> B eth1 down"
    assert len(run(topo, [("A", "eth1"), ("B", "eth1")])["flows"]) == 1


def test_overloaded_cheap_path_gets_a_lighter_recommendation():
    detour = [("A", "E", 1000, 0), ("E", "F", 1000, 0), ("F", "G", 1000, 0), ("G", "B", 1000, 0)]
    out = run(square(ab=400 * MBPS, other=500 * MBPS, extra=detour), [("A", "eth1")])
    flow = out["flows"][0]
    assert path(flow["predicted"]) == ["A", "D", "C", "B"]
    assert flow["predicted"]["max_util"] == 0.9 and flow["predicted"]["status"] == "warning"
    rec = flow["recommended"]
    assert path(rec) == ["A", "E", "F", "G", "B"]
    assert (rec["cost"], rec["max_util"], rec["status"]) == (400, 0.4, "ok")
    assert rec["why"] == (
        "The predicted path would run A -> D at 90 %; this path keeps every link at 40 % or less"
        " (under the 80 % warning level), at estimated cost 400 instead of 300"
    )


def test_critical_with_only_a_slightly_better_path():
    detour = [("A", "E", 1000, 650 * MBPS), ("E", "B", 1000, 650 * MBPS)]
    out = run(square(ab=400 * MBPS, other=620 * MBPS, extra=detour), [("A", "eth1")])
    flow = out["flows"][0]
    pred = flow["predicted"]
    assert path(pred) == ["A", "E", "B"] and pred["cost"] == 200
    assert (pred["max_util"], pred["status"]) == (1.05, "critical")  # 650 + 400 over 1000
    rec = flow["recommended"]
    assert path(rec) == ["A", "D", "C", "B"]
    assert (rec["max_util"], rec["status"]) == (1.02, "critical")
    assert "under the" not in rec["why"]


def test_no_better_path_means_no_recommendation():
    flow = run(square(ab=400 * MBPS, other=500 * MBPS), [("A", "eth1")])["flows"][0]
    assert flow["predicted"]["status"] == "warning"
    assert flow["recommended"] is None


def test_no_alternative_path_isolates_the_far_side():
    topo = build([("A", "B", 1000, MBPS), ("B", "C", 1000, MBPS)])
    out = run(topo, [("B", "eth2")])
    assert out["flows"][0]["predicted"] is None
    assert out["flows"][0]["recommended"] is None
    assert out["isolated"] == ["C"]


def test_missing_speed_or_load_is_unknown_never_ok():
    topo = build(
        [
            ("A", "B", 1000, 100 * MBPS),
            ("B", "C", 1000, None),  # no counters
            ("C", "D", None, 100 * MBPS),  # no speed
            ("D", "A", 1000, 100 * MBPS),
        ]
    )
    pred = run(topo, [("A", "eth1")])["flows"][0]["predicted"]
    assert [h["status"] for h in pred["hops"]] == ["ok", "unknown", "unknown"]
    assert pred["status"] == "unknown" and pred["max_util"] == 0.2
    assert pred["cost"] == 100 + reroute.UNKNOWN_COST + 100

    no_load = build([(a, b, 1000, None if a == "A" else MBPS) for a, b in ("AB", "BC", "CD", "DA")])
    pred = run(no_load, [("A", "eth1")])["flows"][0]["predicted"]
    assert pred["status"] == "unknown" and pred["max_util"] is None


def test_device_failure_flows_between_neighbors_with_unknown_load():
    out = run(square(), devices=["B"])
    [flow] = out["flows"]
    assert (flow["from"], flow["to"], flow["load_bps"]) == ("A", "C", None)
    assert flow["reason"] == "Device B down"
    assert [(h["from"], h["to"]) for h in flow["before"]["hops"]] == [("A", "B"), ("B", "C")]
    assert path(flow["predicted"]) == ["A", "D", "C"]
    assert flow["predicted"]["status"] == "unknown" and flow["recommended"] is None
    assert out["isolated"] == []
    assert out["assumptions"][-1].startswith("Load between the failed device's neighbors")
    assert "Moved load = last measured rate on the failed link" not in out["assumptions"]


def test_device_failure_caps_neighbor_pairs_and_lists_isolated():
    star = build([("H", leaf, 1000, MBPS) for leaf in "LMNOPQ"])
    out = run(star, devices=["H"])
    assert len(out["flows"]) == 10
    assert (out["flows"][0]["from"], out["flows"][0]["to"]) == ("L", "M")
    assert all(f["predicted"] is None for f in out["flows"])
    assert out["isolated"] == ["M", "N", "O", "P", "Q"]  # "L" is kept as the main part


def test_nothing_failed_or_unknown_failure_returns_none():
    topo = square()
    assert run(topo) is None
    assert run(topo, [("A", "eth9"), ("Z", "eth1"), ("A", None)], ["Z"]) is None


def test_single_homed_device_cut_off_is_isolated():
    t = Topology()
    for ip, name in (("10.9.0.1", "hub"), ("10.9.0.2", "leaf"), ("10.9.0.3", "other")):
        t.update({"source_ip": ip, "measurement": "snmp_system", "tags": {"sysName": name}})
    for ip, name, port, rname, rport in (
        ("10.9.0.1", "hub", "1", "leaf", "Gi1"),
        ("10.9.0.1", "hub", "2", "other", "Gi1"),
    ):
        t.update(
            {
                "source_ip": ip,
                "measurement": "snmp_lldp_neighbor",
                "tags": {"sysName": name, "index": f"0.{port}.1"},
                "fields": {"lldpRemSysName": rname, "lldpRemPortId": rport},
            }
        )
    r = reroute.compute(t, [("10.9.0.2", "Gi1")], [], 100000, 0.8, NOW)
    assert r["flows"][0]["predicted"] is None
    assert r["isolated"] == ["10.9.0.2"]
