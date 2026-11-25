from datetime import UTC, datetime

import pytest

from app.modules.analyzer.demo import DemoTopology
from app.modules.analyzer.models import Change, End, Link, Node, Topology, UnknownTarget
from app.modules.analyzer.simulate import simulate

G = "GigabitEthernet1/0/"


@pytest.fixture
def demo() -> Topology:
    return DemoTopology().topology()


def shut(topo: Topology, device: str, interface: str):
    return simulate(topo, Change(kind="interface_down", device=device, interface=interface))


def down(topo: Topology, device: str):
    return simulate(topo, Change(kind="device_down", device=device))


def link(id_, a, b, util=10.0, hourly=None, cap=1000, a_if="p1", b_if="p1") -> Link:
    return Link(
        id=id_,
        a=End(device=a, interface=a_if),
        b=End(device=b, interface=b_if),
        capacity_mbps=cap,
        util_pct=util,
        hourly_util_pct=hourly,
    )


def tiny(links: list[Link], vendor: str | None = None) -> Topology:
    """core - x - y triangle style fixtures; interfaces come from the links."""
    names = {e.device for x in links for e in (x.a, x.b)}
    ifaces = {n: [e.interface for x in links for e in (x.a, x.b) if e.device == n] for n in names}
    nodes = [
        Node(
            id=n,
            type="switch",
            role="core" if n.startswith("core") else "access",
            vendor=vendor,
            interfaces=ifaces[n],
        )
        for n in sorted(names)
    ]
    return Topology(source="live", as_of=datetime.now(UTC), nodes=nodes, links=links)


def test_demo_links_point_at_real_nodes_and_interfaces(demo):
    nodes = {n.id: n for n in demo.nodes}
    for x in demo.links:
        for end in (x.a, x.b):
            assert end.interface in nodes[end.device].interfaces
        assert x.hourly_util_pct is None or len(x.hourly_util_pct) == 24
    assert all(n.id.startswith("DEMO-") for n in demo.nodes)


def test_redundant_dist_uplink_down_reroutes_with_low_risk(demo):
    r = shut(demo, "DEMO-dist-sw-02", "ge-0/0/0")
    assert r.risk == "low"
    assert not [a for a in r.affected if a.status == "critical"]
    (rr,) = r.reroutes
    assert rr.load_mbps == 2000.0
    assert rr.via == ["L5"]  # dist-sw-02 sends its load up its other uplink
    assert all(la.util_after > la.util_before for la in rr.after)
    assert r.title == "Shut ge-0/0/0 on DEMO-dist-sw-02"
    assert "delete interfaces ge-0/0/0 disable" in r.rollback
    assert r.id.startswith("imp-")


def test_reroute_pushing_link_over_80_is_a_warning(demo):
    r = shut(demo, "DEMO-core-sw-01", G + "2")
    hot = [a for a in r.affected if a.kind == "link"]
    assert [(a.id, a.status) for a in hot] == [("L3", "warning")]
    assert next(la for la in r.reroutes[0].after if la.link == "L3").util_after == 85.0
    assert r.risk == "medium"
    assert "no shutdown" in r.rollback


def test_single_homed_access_uplink_down_is_high(demo):
    r = shut(demo, "DEMO-dist-sw-01", G + "3")
    assert r.risk == "high"
    lost = {a.id for a in r.affected if a.kind == "node"}
    assert lost == {"DEMO-acc-sw-01", "DEMO-ap-101"}
    assert any(a.label == "40 hosts behind DEMO-acc-sw-01" for a in r.affected)
    assert r.reroutes == []


def test_core_switch_down_reports_other_core_as_new_spof(demo):
    r = down(demo, "DEMO-core-sw-01")
    assert ("node", "DEMO-core-sw-02") in {(s.kind, s.id) for s in r.new_spofs}
    assert r.risk in ("medium", "high")
    assert r.affected[0].status == "warning"
    assert r.title == "Take DEMO-core-sw-01 down (reboot / replace)"
    assert r.rollback.startswith("Power DEMO-core-sw-01 back on")


def test_server_down_loses_service(demo):
    r = down(demo, "DEMO-srv-dns-01")
    assert r.risk == "high"
    assert any(a.kind == "service" and a.label == "dns on DEMO-srv-dns-01" for a in r.affected)


def test_reroute_onto_unknown_link_is_never_low(demo):
    r = shut(demo, "DEMO-dist-sw-01", G + "5")
    (rr,) = r.reroutes
    assert "L10" in rr.via
    assert next(la for la in rr.after if la.link == "L10").util_after is None
    assert r.unknowns
    assert r.risk != "low"
    assert any(a.id == "L10" and a.status == "neutral" for a in r.affected)


def test_unknown_load_on_removed_link():
    topo = tiny([link("L1", "core", "a", util=None), link("L2", "core", "a", a_if="p2", b_if="p2")])
    r = shut(topo, "core", "p1")
    assert r.reroutes[0].load_mbps is None
    assert r.reroutes[0].after[0].util_after == 10.0  # known part only
    assert "load moved onto L2 is partly unknown" in r.unknowns
    assert r.risk == "medium"
    assert r.maintenance_window is None
    assert "bring the port administratively up" in r.rollback


def test_overload_over_100_is_high():
    topo = tiny(
        [link("L1", "core", "a", util=70.0), link("L2", "core", "a", 50.0, a_if="p2", b_if="p2")]
    )
    r = shut(topo, "core", "p1")
    assert r.reroutes[0].after[0].util_after == 120.0
    assert r.risk == "high"


def test_unknown_targets(demo):
    with pytest.raises(UnknownTarget):
        down(demo, "DEMO-nope")
    with pytest.raises(UnknownTarget):
        shut(demo, "DEMO-core-sw-01", "GigabitEthernet9/9/9")


def test_interface_without_neighbor_is_unknown(demo):
    r = shut(demo, "DEMO-core-sw-01", G + "48")
    assert r.reroutes == []
    assert any("No neighbor link known" in u for u in r.unknowns)
    assert r.risk == "medium"


def test_maintenance_window_is_the_night_hour(demo):
    r = shut(demo, "DEMO-dist-sw-02", "ge-0/0/0")
    assert r.maintenance_window.start_hour == 3
    assert r.maintenance_window.end_hour == 4


def test_last_core_down_makes_everything_unreachable():
    topo = tiny([link("L1", "core", "a"), link("L2", "a", "b", a_if="p2")])
    r = down(topo, "core")
    assert any("No core device remains" in w for w in r.warnings)
    assert {a.id for a in r.affected if a.status == "critical"} == {"a", "b"}
    assert r.risk == "high"


def test_core_switch_down_moves_load_onto_the_other_core(demo):
    r = down(demo, "DEMO-core-sw-01")
    by_link = {rr.link: rr for rr in r.reroutes}
    assert "L1" not in by_link  # the core peer link's far end is already core
    assert by_link["L2"].via == ["L3"] and by_link["L2"].load_mbps == 4500.0
    assert by_link["L4"].via == ["L5"]
    assert by_link["L4"].after[0].util_after == 45.0
    assert ("L3", "warning") in {(a.id, a.status) for a in r.affected if a.kind == "link"}
    assert (
        "12 new single points of failure (DEMO-core-sw-02, 5 more devices and 6 links)" in r.summary
    )
    assert len(r.new_spofs) == 12


@pytest.mark.parametrize(
    ("device", "short", "canonical"),
    [
        ("DEMO-core-sw-01", "Gi1/0/2", "GigabitEthernet1/0/2"),
        ("DEMO-dist-sw-02", "ge-0/0/3", "ge-0/0/3"),
        ("DEMO-dist-sw-02", "GE-0/0/3", "ge-0/0/3"),
    ],
)
def test_short_interface_names_match(demo, device, short, canonical):
    r = shut(demo, device, short)
    assert r.title == f"Shut {canonical} on {device}"
    assert canonical in r.rollback
    assert r.reroutes


def test_spof_summary_wording():
    from app.modules.analyzer.models import Spof
    from app.modules.analyzer.simulate import _spof_text

    link_spof = Spof(kind="link", id="L1", label="x")
    assert _spof_text([]) == "no new single points of failure"
    assert _spof_text([link_spof]) == "1 new single point of failure (1 link)"
    two = [Spof(kind="node", id="a", label="a"), Spof(kind="node", id="b", label="b")]
    assert (
        _spof_text([link_spof, *two])
        == "3 new single points of failure (a, 1 more device and 1 link)"
    )


def test_known_overload_survives_a_later_unknown_reroute():
    links = [
        link("XC", "X", "core", util=50.0, a_if="c", b_if="p1"),
        link("YC", "Y", "core", util=50.0, a_if="c", b_if="p2"),
        link("XA", "X", "A", util=90.0, a_if="a", b_if="x"),
        link("XB", "X", "B", util=None, a_if="b", b_if="x"),
        link("YA", "Y", "A", util=0.0, a_if="a", b_if="y"),
        link("YB", "Y", "B", util=0.0, a_if="b", b_if="y"),
    ]
    r = down(tiny(links), "X")  # A: 900 Mbps known, B: unknown, both cross YC
    yc = [a for a in r.affected if a.id == "YC"]
    assert [a.status for a in yc] == ["critical"]
    assert "unknown" in yc[0].detail
    assert any("YC" in u for u in r.unknowns)
    assert r.risk == "high"


def test_topology_without_core_is_unknown_not_low():
    topo = tiny([link("L1", "a", "b"), link("L2", "b", "c", a_if="p2")])
    r = shut(topo, "a", "p1")
    assert any("no core device known" in u for u in r.unknowns)
    assert not any("No core device remains" in w for w in r.warnings)
    assert r.risk == "medium"


def test_access_uplink_down_does_not_hairpin_over_the_core_uplink(demo):
    r = shut(demo, "DEMO-dist-sw-01", "Gi1/0/4")
    (rr,) = r.reroutes
    assert rr.via == ["L8", "L4"]  # acc-sw-02 -> dist-sw-02 -> core, not via L2
    assert r.risk == "medium"  # acc-sw-02 now hangs off dist-sw-02 alone
    assert "(DEMO-dist-sw-02 and 1 link)" in r.summary
    assert r.summary.startswith("0 devices and 0 hosts cut off from core; 1 link rerouted")


def test_touched_links_without_history_are_unknown():
    hourly = [10.0] * 24
    topo = tiny(
        [link("L1", "core", "a", hourly=hourly), link("L2", "core", "a", a_if="p2", b_if="p2")]
    )
    r = shut(topo, "core", "p1")
    assert r.maintenance_window is not None
    assert r.unknowns == ["no traffic history for L2"]
