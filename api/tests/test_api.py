from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_six_modules_in_nav_order():
    res = client.get("/api/v1/modules")
    assert res.status_code == 200
    assert [m["id"] for m in res.json()] == [
        "dashboard",
        "chat",
        "analyzer",
        "investigator",
        "mapper",
        "pcap",
    ]


def test_openapi_is_served():
    assert client.get("/api/openapi.json").status_code == 200
