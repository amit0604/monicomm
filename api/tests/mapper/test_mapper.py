from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.modules.dashboard.demo import DemoSource
from app.modules.dashboard.models import Device, DeviceStatus, Interface
from app.modules.mapper import service
from app.modules.mapper.models import MEDIUMS, LinkEnd, LinkRecord

client = TestClient(app)
URL = "/api/v1/mapper/topology"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "dev")
    monkeypatch.setenv("MONICOMM_DEMO_DATA", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def topology():
    res = client.get(URL)
    assert res.status_code == 200
    return res.json()


def link(body, a, b):
    """The link between two demo devices, by short name."""
    ids = {n["name"]: n["id"] for n in body["nodes"]}
    pair = {ids[f"DEMO-{a}"], ids[f"DEMO-{b}"]}
    return next(x for x in body["links"] if {x["a"]["device_id"], x["b"]["device_id"]} == pair)


@pytest.mark.parametrize("env,flag", [("prod", "true"), ("dev", "false")])
def test_demo_data_never_appears_unless_dev_and_enabled(monkeypatch, env, flag):
    monkeypatch.setenv("MONICOMM_ENV", env)
    monkeypatch.setenv("MONICOMM_DEMO_DATA", flag)
    get_settings.cache_clear()
    res = client.get(URL)
    assert res.status_code == 503
    assert res.json()["detail"] == "no_data_source"


def test_no_link_source_is_503_even_with_an_inventory(monkeypatch):
    def none():
        raise service.NoLinkSource

    monkeypatch.setattr(service, "get_link_source", none)
    assert client.get(URL).status_code == 503


def test_topology_is_marked_demo_and_uses_the_dashboard_inventory():
    body = topology()
    assert body["source"] == "demo"
    assert [n["id"] for n in body["nodes"]] == [d.id for d in DemoSource().devices()]
    assert body["unresolved_links"] == 0


def test_every_link_joins_two_known_nodes_and_has_a_unique_id():
    body = topology()
    ids = {n["id"] for n in body["nodes"]}
    for x in body["links"]:
        assert {x["a"]["device_id"], x["b"]["device_id"]} <= ids
        assert x["a"]["port"] and x["b"]["port"]
    assert len({x["id"] for x in body["links"]}) == len(body["links"])


def test_demo_shows_every_medium_and_status():
    body = topology()
    assert {x["medium"] for x in body["links"]} == set(MEDIUMS)
    assert {x["status"] for x in body["links"]} == {"up", "degraded", "down", "unknown"}


def test_link_status_follows_the_dashboard_ports_and_devices():
    body = topology()
    hot = link(body, "core-sw-01", "core-sw-02")  # core-sw-02 uplink at 91% in the demo
    assert (hot["status"], hot["reason"]) == ("degraded", "high_utilization")
    offline = link(body, "dist-sw-01", "acc-sw-02")
    assert (offline["status"], offline["reason"]) == ("down", "device_offline")
    port = link(body, "wan-mx-02", "edge-rtr-02")  # edge-rtr-02 Gi1/0/2 is down
    assert (port["status"], port["reason"]) == ("down", "port_down")
    silent = link(body, "acc-sw-03", "acc-sw-04")
    assert (silent["status"], silent["reason"]) == ("unknown", "not_polled")
    radio = link(body, "ap-101", "ap-102")  # no SNMP ports: the controller's report
    assert (radio["medium"], radio["status"], radio["reason"]) == ("wireless", "up", "reported")
    server = link(body, "dist-sw-02", "srv-dns-01")  # only the switch side is polled
    assert (server["status"], server["a"]["port"], server["b"]["port"]) == (
        "up",
        "ge-0/0/2",
        "eth0",
    )


def test_a_device_without_links_is_still_on_the_map():
    body = topology()
    lonely = next(n for n in body["nodes"] if n["name"] == "DEMO-unknown-01")
    assert all(
        lonely["id"] not in (x["a"]["device_id"], x["b"]["device_id"]) for x in body["links"]
    )


# link_status rules on their own


def device(status: DeviceStatus = "online") -> Device:
    return Device(
        id="d",
        name="d",
        ip="192.0.2.1",
        vendor=None,
        model=None,
        type="switch",
        status=status,
        os_version=None,
        serial=None,
        site=None,
        last_poll_at=None,
    )


def port(oper="up", util=10.0, errors=0) -> Interface:
    return Interface(
        if_index="1",
        name="p",
        alias=None,
        admin_status="up",
        oper_status=oper,
        speed_mbps=1000,
        in_util_pct=None,
        out_util_pct=util,
        in_errors=errors,
        out_errors=None,
    )


@pytest.mark.parametrize(
    "statuses,ports,reported,expected",
    [
        (("online", "online"), (port(), port()), None, ("up", None)),
        (("online", "online"), (port(), None), None, ("up", None)),
        (("online", "online"), (port(util=80), port()), None, ("degraded", "high_utilization")),
        (("online", "online"), (port(), port(errors=3)), None, ("degraded", "errors")),
        (("online", "online"), (port(oper="down"), port(util=95)), None, ("down", "port_down")),
        (("offline", "online"), (port(), port()), "up", ("down", "device_offline")),
        (("online", "suspected_offline"), (None, None), "up", ("unknown", "not_polled")),
        (("online", "online"), (None, None), None, ("unknown", "no_port_data")),
        (("online", "online"), (None, None), "degraded", ("degraded", "reported")),
    ],
)
def test_link_status_rules(statuses, ports, reported, expected):
    devices = (device(statuses[0]), device(statuses[1]))
    assert service.link_status(devices, ports, reported, 0.8) == expected


def test_high_utilization_follows_the_shared_link_load_threshold():
    devices = (device(), device())
    busy = (port(util=70), port())
    assert service.link_status(devices, busy, None, 0.8) == ("up", None)
    assert service.link_status(devices, busy, None, 0.6) == ("degraded", "high_utilization")


def test_the_api_uses_the_configured_link_load_threshold(monkeypatch):
    # core-sw-02's uplink is at 91% in the demo: over the default 80%, under a 95% threshold
    monkeypatch.setenv("MONICOMM_LINK_UTIL_WARN", "0.95")
    get_settings.cache_clear()
    hot = link(topology(), "core-sw-01", "core-sw-02")
    assert hot["reason"] != "high_utilization"


class FakeInventory:
    source = "live"

    def devices(self):
        return [device().model_copy(update={"id": "x", "name": "sw-x"})]

    def device(self, _id):
        return None

    def events(self):
        return []

    def open_alerts(self):
        return []


class FakeLinks:
    source = "live"

    def links(self):
        end = LinkEnd(device="sw-x", port="p1")
        return [
            LinkRecord(a=end, b=LinkEnd(device="not-in-inventory", port="p2"), medium="copper"),
            LinkRecord(a=end, b=LinkEnd(device="sw-x", port="p3"), medium="fiber"),
        ]


def test_links_to_unknown_devices_are_counted_not_drawn():
    t = service.topology(FakeInventory(), FakeLinks(), 0.8)
    assert t.source == "live"
    assert t.unresolved_links == 1
    assert len(t.links) == 1
    # the inventory has no port details for sw-x, so nothing can confirm the link
    assert (t.links[0].status, t.links[0].reason) == ("unknown", "no_port_data")
    assert t.collected_at <= datetime.now(UTC)


def test_link_source_refuses_demo_data_outside_dev(monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "prod")
    get_settings.cache_clear()
    with pytest.raises(service.NoLinkSource):
        service.get_link_source()
