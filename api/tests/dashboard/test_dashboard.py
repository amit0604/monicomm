import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.modules.dashboard.models import severity_group

client = TestClient(app)
BASE = "/api/v1/dashboard"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "dev")
    monkeypatch.setenv("MONICOMM_DEMO_DATA", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def get(path, status=200):
    res = client.get(BASE + path)
    assert res.status_code == status
    return res.json()


@pytest.mark.parametrize("env,flag", [("prod", "true"), ("dev", "false")])
def test_demo_data_never_appears_unless_dev_and_enabled(monkeypatch, env, flag):
    monkeypatch.setenv("MONICOMM_ENV", env)
    monkeypatch.setenv("MONICOMM_DEMO_DATA", flag)
    get_settings.cache_clear()
    for path in ("/summary", "/devices", "/devices/demo-1", "/events"):
        assert get(path, 503)["detail"] == "no_data_source"


def test_every_response_is_marked_demo():
    for path in ("/summary", "/devices", "/devices/demo-1", "/events"):
        assert get(path)["source"] == "demo"


def test_summary_counts_add_up():
    body = get("/summary")
    assert sum(body["devices"]["by_status"].values()) == body["devices"]["total"]
    assert len(body["open_alerts"]) == 7


def test_device_filters_combine():
    items = get("/devices?vendor=Juniper&type=switch&status=online")["items"]
    assert items
    assert {(d["vendor"], d["type"], d["status"]) for d in items} == {
        ("Juniper", "switch", "online")
    }
    assert len(get("/devices?status=disconnected")["items"]) == 3
    assert get("/devices?q=192.0.2.21")["items"][0]["name"] == "DEMO-acc-sw-01"
    assert get("/devices?q=nothing-like-this")["items"] == []
    get("/devices?status=bogus", 422)


def test_device_details():
    body = get("/devices/demo-10")
    assert body["device"]["status"] == "critical"
    assert body["events"] and all(e["device_id"] == "demo-10" for e in body["events"])
    assert get("/devices/demo-6")["device"]["metrics"]["cpu_pct"] is None
    get("/devices/nope", 404)


def test_events_newest_first_and_filtered():
    times = [e["received_at"] for e in get("/events")["items"]]
    assert times == sorted(times, reverse=True)
    assert {e["severity"] for e in get("/events?severity=warning")["items"]} == {"err", "warning"}
    assert {e["kind"] for e in get("/events?kind=trap")["items"]} == {"trap"}
    assert len(get("/events?q=ENVMON")["items"]) == 1


def test_severity_mapping_follows_project_md():
    levels = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug", None]
    expected = ["critical"] * 3 + ["warning"] * 2 + ["info"] * 2 + ["neutral"] * 2
    assert [severity_group(s) for s in levels] == expected


def test_demo_uses_documentation_addresses_and_names_only():
    for d in get("/devices")["items"]:
        assert re.match(r"(192\.0\.2|198\.51\.100|203\.0\.113)\.", d["ip"])
        assert d["name"].startswith("DEMO-")
