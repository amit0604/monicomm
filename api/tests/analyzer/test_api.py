import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.analyzer import router as router_mod
from app.modules.analyzer import service
from app.modules.analyzer.models import Change, Report, Topology, UnknownTarget
from app.modules.analyzer.store import ReportStore

BASE = "/api/v1/analyzer/impact"
T0 = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
TOPO = Topology(
    source="demo",
    as_of=T0,
    nodes=[
        {"id": "DEMO-core-sw-01", "type": "switch", "role": "core", "interfaces": ["Gi1/0/1"]},
    ],
    links=[],
)


def make_report(rid: str, created: datetime, change: Change | None = None) -> Report:
    return Report(
        id=rid,
        created_at=created,
        source="demo",
        data_as_of=T0,
        change=change or Change(kind="device_down", device="DEMO-core-sw-01"),
        title=f"report {rid}",
        risk="low",
        summary="nothing breaks",
        affected=[],
        reroutes=[],
        new_spofs=[],
        maintenance_window=None,
        rollback="power it back on",
        warnings=[],
        unknowns=[],
        data_used=["demo topology"],
    )


class FakeSource:
    def topology(self) -> Topology:
        return TOPO


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path)


@pytest.fixture
def client(store, monkeypatch):
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[router_mod.source_or_503] = FakeSource
    app.dependency_overrides[service.get_store] = lambda: store

    def fake_simulate(topo, change):
        if change.device != "DEMO-core-sw-01":
            raise UnknownTarget(f"unknown device {change.device}")
        return make_report("imp-20261125-abcdef", datetime.now(UTC), change)

    monkeypatch.setattr(router_mod, "simulate", fake_simulate)
    return TestClient(app)


def test_topology(client):
    r = client.get(f"{BASE}/topology")
    assert r.status_code == 200
    assert r.json()["nodes"][0]["id"] == "DEMO-core-sw-01"


def test_no_source_503(client, monkeypatch):
    client.app.dependency_overrides.pop(router_mod.source_or_503)

    def none():
        raise service.NoDataSource

    monkeypatch.setattr(service, "get_source", none)
    assert client.get(f"{BASE}/topology").json() == {"detail": "no_data_source"}
    r = client.post(f"{BASE}/reports", json={"change": {"kind": "device_down", "device": "x"}})
    assert r.status_code == 503


def test_create_then_get_and_list(client):
    change = {"kind": "device_down", "device": "DEMO-core-sw-01", "interface": None}
    r = client.post(f"{BASE}/reports", json={"change": change})
    assert r.status_code == 201
    rid = r.json()["id"]
    got = client.get(f"{BASE}/reports/{rid}")
    assert got.status_code == 200 and got.json()["change"] == change
    listed = client.get(f"{BASE}/reports").json()
    assert [i["id"] for i in listed] == [rid]
    assert set(listed[0]) == {"id", "created_at", "title", "risk", "source"}


def test_unknown_target_422(client, store):
    r = client.post(f"{BASE}/reports", json={"change": {"kind": "device_down", "device": "nope"}})
    assert r.status_code == 422 and "nope" in r.json()["detail"]
    assert store.list() == []


def test_unsupported_kind_422(client):
    r = client.post(f"{BASE}/reports", json={"change": {"kind": "vlan_change", "device": "x"}})
    assert r.status_code == 422


def test_interface_down_without_interface_422(client, store):
    change = {"kind": "interface_down", "device": "DEMO-core-sw-01"}
    assert client.post(f"{BASE}/reports", json={"change": change}).status_code == 422
    assert store.list() == []


def test_unknown_id_404(client):
    assert client.get(f"{BASE}/reports/imp-20261125-000000").status_code == 404


def test_invalid_id_404_without_fs(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("touched the filesystem")

    monkeypatch.setattr(Path, "is_file", boom)
    monkeypatch.setattr(Path, "read_text", boom)
    for bad in ("..%5Cx", "..", "imp-20261125-ABCDEF", "imp-20261125-abcdef.json"):
        assert client.get(f"{BASE}/reports/{bad}").status_code == 404


def test_store_rejects_bad_ids(store, monkeypatch):
    monkeypatch.setattr(Path, "is_file", lambda *a: pytest.fail("touched the filesystem"))
    assert store.get("../x") is None
    assert store.get("imp-20261125-abcdef/../../etc") is None
    with pytest.raises(ValueError):
        store.save(make_report("../evil", T0))


def test_store_newest_first(store, tmp_path):
    assert store.list() == []
    for i, rid in enumerate(["imp-20261125-000001", "imp-20261125-000003", "imp-20261125-000002"]):
        store.save(make_report(rid, T0 + timedelta(minutes=[1, 3, 2][i])))
    (tmp_path / "reports" / "junk.json").write_text("{}", encoding="utf-8")  # ignored
    assert [r.id for r in store.list()] == [
        "imp-20261125-000003",
        "imp-20261125-000002",
        "imp-20261125-000001",
    ]
    assert store.get("imp-20261125-000003").created_at == T0 + timedelta(minutes=3)
    assert not list((tmp_path / "reports").glob("*.tmp"))


def test_corrupt_file_skipped(store, tmp_path, caplog):
    store.save(make_report("imp-20261125-000001", T0))
    bad = tmp_path / "reports" / "imp-20261125-00000f.json"
    bad.write_text("{not json secret-content", encoding="utf-8")
    assert [r.id for r in store.list()] == ["imp-20261125-000001"]
    assert store.get("imp-20261125-00000f") is None
    assert "imp-20261125-00000f.json" in caplog.text and "secret-content" not in caplog.text


def test_id_trailing_newline_rejected(store):
    store.save(make_report("imp-20261125-000001", T0))
    assert store.get("imp-20261125-000001" + chr(10)) is None


def test_corrupt_file_api_404(client, tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "imp-20261125-00000f.json").write_text("[]", encoding="utf-8")
    assert client.get(f"{BASE}/reports").json() == []
    assert client.get(f"{BASE}/reports/imp-20261125-00000f").status_code == 404


def test_get_source_demo_only_in_dev(monkeypatch):
    demo = types.ModuleType("app.modules.analyzer.demo")
    demo.DemoTopology = FakeSource
    monkeypatch.setitem(sys.modules, demo.__name__, demo)
    for demo_data, env, ok in ((True, "dev", True), (True, "prod", False), (False, "dev", False)):
        settings = types.SimpleNamespace(demo_data=demo_data, env=env)
        monkeypatch.setattr(service, "get_settings", lambda s=settings: s)
        if ok:
            assert isinstance(service.get_source(), FakeSource)
        else:
            with pytest.raises(service.NoDataSource):
                service.get_source()


def test_get_store_uses_setting(monkeypatch, tmp_path):
    settings = types.SimpleNamespace(analyzer_data_dir=str(tmp_path))
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    assert service.get_store().dir == tmp_path / "reports"


def test_mounted_in_main_app(store):
    from app.main import app

    app.dependency_overrides[service.get_store] = lambda: store
    try:
        r = TestClient(app).get(f"{BASE}/reports")
    finally:
        app.dependency_overrides.pop(service.get_store)
    assert r.status_code == 200 and r.json() == []
