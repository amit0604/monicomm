import asyncio
import json

import pytest

from app.ai import llm_client
from app.modules.investigator import analysis

INCIDENT = {
    "id": "abcdef012345",
    "title": "Link down: 10.0.0.1 Gi1/0/24 <-> 10.0.0.2 ge-0/0/1",
    "root_cause": {"summary": "link down", "event_ids": ["e1"], "confidence": "high"},
    "possible_causes": [],
    "impact": [{"device": "10.0.0.2", "what": "OSPF down", "event_ids": ["e2"]}],
    "timeline": [
        {"id": "e1", "raw": "LINK-3-UPDOWN Gi1/0/24 down " + "x" * 1000},
        {"id": "e2", "raw": "OSPF-5-ADJCHG neighbor down"},
    ],
}


def run(monkeypatch, reply):
    sent = []

    async def fake_chat(messages):
        sent.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    return asyncio.run(analysis.analyze(INCIDENT)), sent


def test_evidence_in_user_message_not_system(monkeypatch):
    reply = json.dumps({"summary": "s", "root_cause": "r", "impact": "i", "sources": ["e1"]})
    out, sent = run(monkeypatch, reply)
    system, user = sent[0]
    assert system["role"] == "system" and user["role"] == "user"
    assert "OSPF-5-ADJCHG" not in system["content"]
    data = json.loads(user["content"])
    assert data["title"] == INCIDENT["title"]
    assert len(data["timeline"][0]["raw"]) == analysis.MAX_RAW
    assert out["summary"] == "s" and out["sources"] == ["e1"]
    assert set(out) == {"summary", "root_cause", "impact", "sources", "model", "created_at"}


def test_unknown_sources_dropped(monkeypatch):
    reply = json.dumps({"summary": "s", "root_cause": "r", "impact": "i", "sources": ["e2", "zz"]})
    out, _ = run(monkeypatch, reply)
    assert out["sources"] == ["e2"]


def test_fenced_json_parsed(monkeypatch):
    reply = '```json\n{"summary": "s", "root_cause": "r", "impact": "i", "sources": ["e1"]}\n```'
    out, _ = run(monkeypatch, reply)
    assert out["root_cause"] == "r" and out["sources"] == ["e1"]


def test_garbage_reply_becomes_summary(monkeypatch):
    out, _ = run(monkeypatch, "I think the link flapped.")
    assert out["summary"] == "I think the link flapped."
    assert out["sources"] == []


def test_model_down_raises_model_unavailable(monkeypatch):
    with pytest.raises(analysis.ModelUnavailable):
        run(monkeypatch, llm_client.LLMUnavailable("down"))
