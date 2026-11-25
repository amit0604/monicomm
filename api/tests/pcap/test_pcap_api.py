import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.pcap import router, service

from .conftest import REQ


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_DIR", tmp_path / "data")
    app = FastAPI()
    app.include_router(router.router, prefix="/api/v1/pcap")
    return TestClient(app)


def upload(client, path, name="sample.pcap"):
    with open(path, "rb") as f:
        return client.post("/api/v1/pcap/captures", files={"file": (name, f)})


def test_upload_process_and_read(client, sample_pcap):
    r = upload(client, sample_pcap)
    assert r.status_code == 202
    cid = r.json()["id"]
    # TestClient runs background tasks before returning
    cap = client.get(f"/api/v1/pcap/captures/{cid}").json()
    assert cap["status"] == "done"
    assert cap["analysis"]["packet_count"] == 9
    assert [c["id"] for c in client.get("/api/v1/pcap/captures").json()] == [cid]

    s = client.get(f"/api/v1/pcap/captures/{cid}/streams/0").json()
    assert s["segments"][0]["text"] == REQ.decode()

    assert client.delete(f"/api/v1/pcap/captures/{cid}").status_code == 204
    assert client.get(f"/api/v1/pcap/captures/{cid}").status_code == 404


def test_rejects_non_capture(client, tmp_path):
    p = tmp_path / "evil.pcap"
    p.write_bytes(b"MZ\x90\x00 not a pcap")
    assert upload(client, p).status_code == 400
    assert upload(client, p, name="x.exe").status_code == 400


def test_rejects_oversize(client, sample_pcap, monkeypatch):
    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 100)
    assert upload(client, sample_pcap).status_code == 413
    assert client.get("/api/v1/pcap/captures").json() == []


@pytest.mark.parametrize("bad", ["..", "..%2F..%2Fetc", "abc", "0" * 31 + "g"])
def test_bad_ids_are_404(client, bad):
    assert client.get(f"/api/v1/pcap/captures/{bad}").status_code == 404


def test_unknown_stream_is_404(client, sample_pcap):
    cid = upload(client, sample_pcap).json()["id"]
    assert client.get(f"/api/v1/pcap/captures/{cid}/streams/99").status_code == 404


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    async def fake(messages):
        calls.append(messages)
        return "Port 80 session was reset [#7] after a retransmission [#5]. Bogus [#999]."

    monkeypatch.setattr(service, "_llm_chat", fake)
    return calls


def test_summary_and_chat(client, sample_pcap, fake_llm):
    cid = upload(client, sample_pcap).json()["id"]

    s = client.post(f"/api/v1/pcap/captures/{cid}/summary").json()
    assert s["sources"] == [5, 7]  # [#999] is outside the capture, dropped
    assert s["ai"] is True
    client.post(f"/api/v1/pcap/captures/{cid}/summary")  # cached
    assert len(fake_llm) == 1

    system, data = fake_llm[0][0], fake_llm[0][1]
    assert (
        system["role"] == "system" and '"packet_count"' not in system["content"]
    )  # data not in system role
    assert data["role"] == "user" and data["content"].startswith("<capture_analysis>")
    assert REQ.decode() not in data["content"] and "HTTP/1.1" not in data["content"]  # no payloads

    a = client.post(f"/api/v1/pcap/captures/{cid}/chat", json={"question": "why the reset?"}).json()
    assert a["sources"] == [5, 7]
    hist = client.get(f"/api/v1/pcap/captures/{cid}/chat").json()
    assert [m["role"] for m in hist] == ["user", "assistant"]

    client.post(f"/api/v1/pcap/captures/{cid}/chat", json={"question": "and then?"})
    assert [m["role"] for m in fake_llm[-1]] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]


def test_chat_validation(client, sample_pcap, fake_llm):
    cid = upload(client, sample_pcap).json()["id"]
    assert (
        client.post(f"/api/v1/pcap/captures/{cid}/chat", json={"question": ""}).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/pcap/captures/" + "0" * 32 + "/chat", json={"question": "x"}
        ).status_code
        == 404
    )


def test_llm_context_caps_lists(sample_pcap):
    from app.modules.pcap import parser

    a = parser.analyze(sample_pcap)
    a["dns"] = a["dns"] * 100
    ctx = service.llm_context(a)
    assert len(ctx["dns"]) == service.LLM_LIMITS["dns"]
    assert ctx["dns_omitted"] == 100 - service.LLM_LIMITS["dns"]
    json.dumps(ctx)


def test_oversize_rejected_from_header_before_parsing(client, monkeypatch):
    monkeypatch.setattr(service, "MAX_UPLOAD_BYTES", 10)
    r = client.post(
        "/api/v1/pcap/captures",
        content=b"x" * 200_000,
        headers={"content-type": "multipart/form-data; boundary=b"},
    )
    assert r.status_code == 413


def test_missing_file_field(client):
    r = client.post("/api/v1/pcap/captures", data={"other": "x"})
    assert r.status_code == 400


def test_llm_down_is_503(client, sample_pcap, monkeypatch):
    async def broken(messages):
        raise service.LLMUnavailable("connection refused")

    monkeypatch.setattr(service, "_llm_chat", broken)
    cid = upload(client, sample_pcap).json()["id"]
    assert client.post(f"/api/v1/pcap/captures/{cid}/summary").status_code == 503
    assert (
        client.post(f"/api/v1/pcap/captures/{cid}/chat", json={"question": "x"}).status_code == 503
    )
    assert client.get(f"/api/v1/pcap/captures/{cid}/chat").json() == []  # failed turn not stored


def test_delete_while_processing_does_not_crash(client, sample_pcap, monkeypatch):
    real = service.process

    def delete_first(cid):
        service.delete_capture(cid)
        real(cid)

    monkeypatch.setattr(service, "process", delete_first)
    assert upload(client, sample_pcap).status_code == 202


def test_conversations_paged_and_capture_trimmed(client, sample_pcap, monkeypatch):
    monkeypatch.setattr(service, "CAPTURE_CONVERSATIONS", 1)
    cid = upload(client, sample_pcap).json()["id"]
    a = client.get(f"/api/v1/pcap/captures/{cid}").json()["analysis"]
    assert a["conversations_total"] == 3 and len(a["conversations"]) == 1
    page = client.get(f"/api/v1/pcap/captures/{cid}/conversations?offset=1&limit=1").json()
    assert page["total"] == 3 and [c["id"] for c in page["items"]] == [1]


def test_llm_context_puts_serious_anomalies_first(sample_pcap):
    from app.modules.pcap import parser

    a = parser.analyze(sample_pcap)
    noise = [{"type": "tcp_retransmission", "packet": i, "detail": ""} for i in range(1, 100)]
    a["anomalies"] = noise + [{"type": "port_scan", "packet": 500, "detail": "scan"}]
    assert service.llm_context(a)["anomalies"][0]["type"] == "port_scan"
