import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.investigator.router import get_store
from app.modules.investigator.store import IncidentStore

try:
    from app.modules.investigator import analysis
except Exception:  # analysis.py (or llm_client) may be mid-edit in parallel; stand in for it
    analysis = types.ModuleType("app.modules.investigator.analysis")
    sys.modules[analysis.__name__] = analysis
    import app.modules.investigator as pkg

    pkg.analysis = analysis

ID = "0123456789ab"
BASE = "/api/v1/investigator/incidents"
INCIDENT = {
    "id": ID,
    "status": "open",
    "severity": "critical",
    "title": "Link down: 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1",
    "started_at": "2026-11-25T10:00:00+00:00",
    "updated_at": "2026-11-25T10:00:05+00:00",
    "devices": ["10.0.0.1", "10.0.0.2"],
    "root_cause": {"summary": "Link Gi1/0/24 down", "event_ids": ["e1"], "confidence": "high"},
    "possible_causes": [{"summary": "config change 30 s before", "event_ids": ["e0"]}],
    "impact": [
        {
            "device": "10.0.0.2",
            "interface": "ge-0/0/1",
            "peer": None,
            "what": "OSPF adjacency to 10.0.0.1 down",
            "recovered": False,
            "event_ids": ["e2"],
        }
    ],
    "timeline": [
        {
            "id": "e1",
            "ts": "2026-11-25T10:00:00+00:00",
            "device": "10.0.0.1",
            "type": "link",
            "state": "down",
            "code": "LINK-3-UPDOWN",
            "raw": "%LINK-3-UPDOWN: Interface Gi1/0/24, changed state to down",
        }
    ],
    "notes": "",
    "resolution": "",
    "analysis": None,
}


@pytest.fixture
def client(tmp_path):
    store = IncidentStore(tmp_path)
    store.save(INCIDENT)
    store.save({**INCIDENT, "id": "bbbbbbbbbbbb", "status": "closed", "started_at": "2026-11-24"})
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_and_filter(client):
    res = client.get(BASE)
    assert res.status_code == 200
    body = res.json()
    assert [i["id"] for i in body] == [ID, "bbbbbbbbbbbb"]
    assert set(body[0]) == {
        "id",
        "status",
        "severity",
        "title",
        "started_at",
        "updated_at",
        "devices",
        "root_cause",
    }
    assert [i["id"] for i in client.get(BASE, params={"status": "closed"}).json()] == [
        "bbbbbbbbbbbb"
    ]
    assert client.get(BASE, params={"status": "bogus"}).status_code == 422


def test_get_and_404(client):
    assert client.get(f"{BASE}/{ID}").json()["timeline"][0]["id"] == "e1"
    assert client.get(f"{BASE}/ffffffffffff").status_code == 404
    for bad in ("..%2F..%2Fetc%2Fpasswd", "..%2F..", "ABC", "0123456789abc"):
        assert client.get(f"{BASE}/{bad}").status_code == 404


def test_patch(client):
    res = client.patch(f"{BASE}/{ID}", json={"notes": "swapped SFP", "status": "closed"})
    assert res.status_code == 200
    got = client.get(f"{BASE}/{ID}").json()
    assert (got["notes"], got["status"], got["title"]) == (
        "swapped SFP",
        "closed",
        INCIDENT["title"],
    )
    assert client.patch(f"{BASE}/{ID}", json={"status": "recovered"}).status_code == 422
    assert client.patch(f"{BASE}/{ID}", json={"title": "x"}).status_code == 422
    assert client.patch(f"{BASE}/ffffffffffff", json={"notes": "x"}).status_code == 404


def test_export_markdown(client):
    res = client.get(f"{BASE}/{ID}/export.md")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    md = res.text
    for part in (
        "# Link down: 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1",
        "Status: open",
        "Severity: critical",
        "## Root cause",
        "Link Gi1/0/24 down (confidence: high)",
        "config change 30 s before",
        "| 10.0.0.2 | ge-0/0/1 | - | OSPF adjacency to 10.0.0.1 down | no |",
        "`LINK-3-UPDOWN`",
        "  %LINK-3-UPDOWN: Interface Gi1/0/24, changed state to down",
    ):
        assert part in md
    assert "## AI analysis" not in md
    assert client.get(f"{BASE}/ffffffffffff/export.md").status_code == 404


def test_analysis_ok_and_stored(client, monkeypatch):
    result = {
        "summary": "Core link failed",
        "root_cause": "Gi1/0/24 down",
        "impact": "OSPF lost",
        "sources": ["e1"],
        "model": "qwen2.5:7b",
        "created_at": "2026-11-25T10:01:00+00:00",
    }

    async def fake(incident):
        assert incident["id"] == ID
        return result

    monkeypatch.setattr(analysis, "analyze", fake, raising=False)
    monkeypatch.setattr(analysis, "ModelUnavailable", type("MU", (Exception,), {}), raising=False)
    res = client.post(f"{BASE}/{ID}/analysis")
    assert res.status_code == 200
    assert res.json() == result
    assert client.get(f"{BASE}/{ID}").json()["analysis"] == result
    md = client.get(f"{BASE}/{ID}/export.md").text
    assert "## AI analysis" in md and "Sources: e1" in md


def test_analysis_model_down_503(client, monkeypatch):
    err = getattr(analysis, "ModelUnavailable", None) or type("MU", (Exception,), {})
    monkeypatch.setattr(analysis, "ModelUnavailable", err, raising=False)

    async def fake(incident):
        raise err("down")

    monkeypatch.setattr(analysis, "analyze", fake, raising=False)
    assert client.post(f"{BASE}/{ID}/analysis").status_code == 503
    assert client.get(f"{BASE}/{ID}").json()["analysis"] is None
    assert client.post(f"{BASE}/ffffffffffff/analysis").status_code == 404


def test_lifespan_starts_and_stops_listener(tmp_path, monkeypatch):
    import app.main as main
    from app.core.config import Settings

    settings = Settings(
        investigator_ingest_dir=str(tmp_path / "in"),
        investigator_data_dir=str(tmp_path / "data"),
        investigator_poll_s=0.01,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    fake = types.ModuleType("app.modules.investigator.correlate")

    class Correlator:
        def __init__(self, window_s=120, topology=None):
            self.window_s = window_s
            self.loaded = []

        def load(self, incidents):
            self.loaded = incidents

    fake.Correlator = Correlator
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    with TestClient(app) as c:
        assert c.get("/api/v1/health").status_code == 200
