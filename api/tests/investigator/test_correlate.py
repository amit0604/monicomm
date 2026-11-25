import itertools
import sys
import types
from datetime import UTC, datetime, timedelta

import pytest

try:
    from app.modules.investigator import reroute  # noqa: F401
except ImportError:  # reroute.py is written in parallel; tests patch compute anyway
    sys.modules["app.modules.investigator.reroute"] = types.ModuleType("reroute")

from app.modules.investigator import correlate  # noqa: E402
from app.modules.investigator.correlate import Correlator  # noqa: E402
from app.modules.investigator.events import NetEvent  # noqa: E402
from tests.investigator.test_topology import core_topology  # noqa: E402

T0 = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
_ids = itertools.count()
A, B, C, D = "10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.9"


def ev(
    sec,
    device,
    type_,
    state=None,
    interface=None,
    peer=None,
    *,
    abnormal=None,
    sev="err",
    code=None,
):
    if abnormal is None:
        abnormal = state == "down" or type_ in ("hw_env", "cluster_failover", "stp_change")
    return NetEvent(
        id=f"e{next(_ids):05d}",
        type=type_,
        state=state,
        device=device,
        hostname=None,
        interface=interface,
        peer=peer,
        severity=sev,
        ts=T0 + timedelta(seconds=sec),
        code=code,
        raw=f"{type_} {state} {interface or peer or ''}",
        abnormal=abnormal,
    )


def run(c, events):
    out = []
    for e in events:
        out.extend(c.feed(e))
    return {i["id"]: i for i in out}


def test_core_link_scenario_gives_one_incident_with_link_root_cause():
    c = Correlator(window_s=120, topology=core_topology())
    incidents = run(
        c,
        [
            ev(0, A, "link", "down", "GigabitEthernet1/0/24"),
            ev(1, B, "link", "down", "ge-0/0/1"),
            ev(5, A, "ospf", "down", peer=B),
            ev(6, B, "ospf", "down", peer=A),
            ev(40, C, "bgp", "down", peer=B),
        ],
    )
    assert len(incidents) == 1
    inc = next(iter(incidents.values()))
    assert inc["root_cause"]["summary"] == (
        "Link failure between 10.0.0.1 GigabitEthernet1/0/24 and 10.0.0.2 ge-0/0/1"
    )
    assert inc["root_cause"]["confidence"] == "high"
    assert inc["title"] == "Link down: 10.0.0.1 GigabitEthernet1/0/24 <-> 10.0.0.2 ge-0/0/1"
    assert inc["severity"] == "critical" and inc["status"] == "open"
    assert inc["devices"] == [A, B, C]
    whats = {(i["device"], i["what"]) for i in inc["impact"]}
    assert whats == {
        (A, "Interface GigabitEthernet1/0/24 down"),
        (B, "Interface ge-0/0/1 down"),
        (A, "OSPF adjacency to 10.0.0.2 down"),
        (B, "OSPF adjacency to 10.0.0.1 down"),
        (C, "BGP session to 10.0.0.2 down"),
    }
    ids = {r["id"] for r in inc["timeline"]}
    cited = inc["root_cause"]["event_ids"] + [i for x in inc["impact"] for i in x["event_ids"]]
    assert cited and set(cited) <= ids
    assert [r["ts"] for r in inc["timeline"]] == sorted(r["ts"] for r in inc["timeline"])
    assert inc["timeline"][0]["ts"] == "2026-11-25T10:00:00Z"
    assert len(inc["id"]) == 12 and inc["started_at"] == "2026-11-25T10:00:00Z"


def test_unrelated_or_far_apart_events_give_separate_incidents():
    c = Correlator(window_s=120, topology=core_topology())
    first = c.feed(ev(0, A, "link", "down", "Gi1/0/2"))
    other_device = c.feed(ev(600, D, "link", "down", "Gi1/0/2"))
    same_device_later = c.feed(ev(1200, A, "link", "down", "Gi1/0/2"))
    assert len({first[0]["id"], other_device[0]["id"], same_device_later[0]["id"]}) == 3
    # an unrelated device inside the window does not join either
    assert (
        c.feed(ev(1210, D, "bgp", "down", peer="192.0.2.1"))[0]["id"] != same_device_later[0]["id"]
    )


def test_normal_only_stream_never_opens_an_incident():
    c = Correlator(window_s=120, topology=core_topology())
    normal = [
        ev(0, A, "link", "up", "Gi1/0/24"),
        ev(1, A, "config_change"),
        ev(2, B, "other", sev="info"),
        ev(3, B, "login_failed", peer="192.0.2.7"),
        ev(4, A, "link", "down", "Gi1/0/5", abnormal=False),  # admin down
        ev(5, B, "bgp", "up", peer=A),
    ]
    assert all(c.feed(e) == [] for e in normal)


def test_config_change_before_link_down_is_a_possible_cause():
    c = Correlator(window_s=120, topology=core_topology())
    too_old = ev(-200, A, "config_change")
    cfg = ev(0, A, "config_change")
    elsewhere = ev(10, D, "config_change")
    for e in (too_old, cfg, elsewhere):
        assert c.feed(e) == []
    (inc,) = c.feed(ev(30, A, "link", "down", "Gi1/0/2"))
    assert inc["possible_causes"] == [
        {"summary": "Config change on 10.0.0.1 30 s before", "event_ids": [cfg.id]}
    ]
    assert cfg.id in {r["id"] for r in inc["timeline"]}
    assert inc["root_cause"]["confidence"] == "low"
    assert inc["title"] == "Interface Gi1/0/2 down on 10.0.0.1"


def flaps(c, n, admin=False):
    out = []
    for i in range(n):
        out += c.feed(ev(i * 10, A, "link", "down", "Gi1/0/7", abnormal=not admin))
        out += c.feed(ev(i * 10 + 5, A, "link", "up", "Gi1/0/7"))
    return out


def test_oper_flapping_adds_a_flapping_impact_item():
    c = Correlator()
    inc = flaps(c, 3)[-1]
    assert len({i["id"] for i in flaps(Correlator(), 3)}) == 1
    flap = [i for i in inc["impact"] if "flapping" in i["what"]]
    assert flap[0]["what"] == "Interface Gi1/0/7 flapping (3 times)"
    assert len(flap[0]["event_ids"]) == 3 and flap[0]["recovered"]
    two = flaps(Correlator(), 2)[-1]
    assert not [i for i in two["impact"] if "flapping" in i["what"]]


def test_admin_flapping_opens_an_incident_only_from_three_downs():
    assert flaps(Correlator(), 2, admin=True) == []
    out = flaps(Correlator(), 3, admin=True)
    assert out and all(r["abnormal"] for r in out[-1]["timeline"] if r["state"] == "down")


def test_failed_login_burst():
    c = Correlator()
    results = [
        c.feed(ev(i * 60, A, "login_failed", peer="192.0.2.7", sev="warning")) for i in range(5)
    ]
    assert results[:4] == [[], [], [], []]
    (inc,) = results[4]
    assert inc["impact"][0]["what"] == "5 failed logins" and inc["severity"] == "warning"
    c4 = Correlator()
    assert all(c4.feed(ev(i * 60, A, "login_failed", peer="192.0.2.7")) == [] for i in range(4))
    spread = Correlator()
    assert all(spread.feed(ev(i * 100, A, "login_failed")) == [] for i in range(5))


def test_recovery_and_load_resume():
    c = Correlator(window_s=120)
    c.feed(ev(0, A, "link", "down", "Gi1/0/24"))
    (inc,) = c.feed(ev(2, A, "ospf", "down", peer=B))
    assert c.feed(ev(3, A, "link", "up", "Gi1/0/9")) == []  # no matching item
    link_up = ev(30, A, "link", "up", "GigabitEthernet1/0/24")
    (inc,) = c.feed(link_up)
    assert inc["status"] == "open"
    assert c.feed(link_up) == []  # same event twice changes nothing
    (inc,) = c.feed(ev(40, A, "ospf", "up", peer=B))
    assert inc["status"] == "recovered" and all(i["recovered"] for i in inc["impact"])
    assert inc["updated_at"] == "2026-11-25T10:00:40Z"

    resumed = Correlator(window_s=120)
    resumed.load([inc])
    (joined,) = resumed.feed(ev(100, A, "bgp", "down", peer=C))
    assert joined["id"] == inc["id"] and joined["status"] == "open"

    closed = dict(joined, status="closed")
    resumed.load([closed])
    (fresh,) = resumed.feed(ev(110, A, "bgp", "down", peer=D))
    assert fresh["id"] != inc["id"]
    assert resumed.feed(ev(120, A, "bgp", "up", peer=C)) == []  # closed is never changed


def test_root_cause_cause_then_adjacency_drops_and_severity():
    topo = core_topology()
    c = Correlator(topology=topo)
    hw = ev(0, A, "hw_env", sev="crit")
    (inc,) = run(c, [hw, ev(5, B, "ospf", "down", peer=A)]).values()
    assert inc["root_cause"]["event_ids"] == [hw.id]
    assert inc["root_cause"]["confidence"] == "medium"
    assert inc["severity"] == "critical"
    assert inc["title"] == "Hardware/environment alarm on 10.0.0.1 (+1 more devices)"

    link = ev(0, A, "link", "down", "Gi1/0/5")  # far end unknown: no link pair
    (inc,) = run(Correlator(topology=topo), [link, ev(5, B, "bgp", "down", peer=A)]).values()
    assert inc["root_cause"]["event_ids"] == [link.id]
    assert inc["root_cause"]["confidence"] == "high"

    (inc,) = run(
        Correlator(), [ev(0, A, "stp_change", interface="Gi1/0/1", sev="warning")]
    ).values()
    assert inc["severity"] == "warning" and inc["root_cause"]["confidence"] == "low"
    assert inc["impact"][0]["what"] == "Spanning-tree topology change on Gi1/0/1"
    assert inc["status"] == "open"


def test_memory_caps(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(correlate, "MAX_TIMELINE", 2)
    monkeypatch.setattr(correlate, "MAX_OPEN", 2)
    c = Correlator()
    (inc,) = run(c, [ev(i, A, "bgp", "down", peer=f"192.0.2.{i}") for i in range(4)]).values()
    assert len(inc["timeline"]) == 2
    for i in range(3):
        c.feed(ev(1000 * (i + 1), D, "cluster_failover"))
    assert len(c._open) == 2 and inc["id"] not in c._open


def lineproto(sec, device=A, port="GigabitEthernet1/0/3"):
    return ev(sec, device, "link", "down", port, code="LINEPROTO-5-UPDOWN")


def admin_down(sec, device=A, port="GigabitEthernet1/0/3"):
    return ev(sec, device, "link", "down", port, abnormal=False, code="LINK-5-CHANGED")


def test_ios_shutdown_lineproto_down_is_not_an_incident():
    before = Correlator()  # usual order: admin-down line, then LINEPROTO
    stream = [admin_down(0), lineproto(1), ev(10, D, "config_change")]
    assert all(before.feed(e) == [] for e in stream)
    assert before.flush(T0 + timedelta(seconds=60)) == []

    after = Correlator()  # LINEPROTO first, admin-down 2 s later (UDP reordering)
    assert after.feed(lineproto(0)) == [] and after.feed(admin_down(2)) == []
    assert after.feed(ev(10, D, "config_change")) == []

    bounce = Correlator()  # held down already came back up: nothing left to report
    assert bounce.feed(lineproto(0)) == [] and bounce.feed(ev(2, A, "link", "up", "Gi1/0/3")) == []
    assert bounce.flush(T0 + timedelta(seconds=10)) == []


def test_lineproto_down_without_admin_down_opens_after_hold():
    c = Correlator()
    down = lineproto(0)
    assert c.feed(down) == []
    (inc,) = c.flush(T0 + timedelta(seconds=correlate.HOLD_S))
    assert inc["root_cause"]["event_ids"] == [down.id]
    # released by the next fed event too, merged with what that event changed
    c2 = Correlator()
    c2.feed(lineproto(0))
    (inc,) = c2.feed(ev(6, A, "ospf", "down", peer=B))
    assert len(inc["impact"]) == 2
    # Cisco logs LINK-3-UPDOWN and LINEPROTO per flap: flapping counts each flap once
    c3 = Correlator()
    for i in range(2):
        c3.feed(ev(i * 20, A, "link", "down", "Gi1/0/3", code="LINK-3-UPDOWN"))
        c3.feed(lineproto(i * 20 + 1))
    out = c3.flush(T0 + timedelta(seconds=60))
    assert not [i for i in out[0]["impact"] if "flapping" in i["what"]]


def test_load_keeps_only_newest_max_open(monkeypatch):
    monkeypatch.setattr(correlate, "MAX_OPEN", 2)
    c = Correlator()
    c.load(
        [
            {"id": f"{n:012x}", "status": "open", "updated_at": f"2026-11-25T10:00:0{n}Z"}
            for n in range(4)
        ]
    )
    assert sorted(c._open) == [f"{2:012x}", f"{3:012x}"]


@pytest.fixture
def fake_compute(monkeypatch):
    calls = []

    def compute(topology, failed_links, failed_devices, ref_bw_mbps, util_warn, now):
        calls.append((failed_links, failed_devices, ref_bw_mbps, util_warn, now))
        return {"flows": [], "fake": len(calls)}

    monkeypatch.setattr(correlate.reroute, "compute", compute, raising=False)
    return calls


def test_link_down_incident_carries_reroute(fake_compute):
    c = Correlator(topology=core_topology(), ref_bw_mbps=1000.0, util_warn=0.5)
    (inc,) = run(
        c, [ev(0, A, "link", "down", "GigabitEthernet1/0/24"), ev(1, B, "link", "down", "ge-0/0/1")]
    ).values()
    assert inc["reroute"] == {"flows": [], "fake": 2}
    # A's only LLDP link is down: A is cut off (reroute reports it isolated), not a failed device
    links, devices, ref_bw, warn, now = fake_compute[-1]
    assert links == [(A, "GigabitEthernet1/0/24"), (B, "ge-0/0/1")]
    assert devices == [] and (ref_bw, warn) == (1000.0, 0.5)
    assert now == T0 + timedelta(seconds=1)


def test_recovered_link_is_not_failed(fake_compute):
    c = Correlator(topology=core_topology())
    c.feed(ev(0, A, "link", "down", "GigabitEthernet1/0/24"))
    c.feed(ev(1, B, "link", "down", "ge-0/0/2"))
    (inc,) = c.feed(ev(5, B, "link", "up", "ge-0/0/2"))
    assert fake_compute[-1][:2] == ([(A, "GigabitEthernet1/0/24")], [])
    calls = len(fake_compute)
    (inc,) = c.feed(ev(6, A, "link", "up", "Gi1/0/24"))
    assert inc["reroute"] is None and len(fake_compute) == calls  # nothing failed: not called


def test_cold_start_is_a_failed_device(fake_compute):
    c = Correlator(topology=core_topology())
    (inc,) = c.feed(ev(0, D, "hw_env", code=".1.3.6.1.6.3.1.1.5.1", sev="warning"))
    assert fake_compute[-1][:2] == ([], [D]) and inc["reroute"]["fake"] == 1
    assert Correlator().feed(ev(0, D, "hw_env", sev="crit"))[0]["reroute"] is None


def test_reroute_error_keeps_incident(monkeypatch):
    def boom(*args):
        raise RuntimeError("bug")

    monkeypatch.setattr(correlate.reroute, "compute", boom, raising=False)
    (inc,) = Correlator(topology=core_topology()).feed(ev(0, A, "link", "down", "Gi1/0/24"))
    assert inc["reroute"] is None and inc["root_cause"]


def test_normal_only_stream_never_calls_reroute(fake_compute):
    c = Correlator(topology=core_topology())
    assert c.feed(ev(0, A, "link", "down", "Gi1/0/24", abnormal=False)) == []
    assert c.feed(ev(1, A, "link", "up", "Gi1/0/24")) == [] and fake_compute == []
