"""AI root-cause explanation for an incident, via the local LLM (plan Phase 4)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.ai import llm_client
from app.core.config import get_settings

PROMPT_FILE = Path(__file__).resolve().parents[2] / "ai" / "prompts" / "investigator_root_cause.md"
MAX_EVENTS = 200
MAX_RAW = 300
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class ModelUnavailable(Exception):
    """The local model could not be reached."""


def _evidence(incident: dict) -> dict:
    # ponytail: keeps the first 200 events; summarise/sample if long incidents need the tail
    timeline = [
        {**ev, "raw": (ev.get("raw") or "")[:MAX_RAW]}
        for ev in incident.get("timeline", [])[:MAX_EVENTS]
    ]
    return {
        "title": incident.get("title"),
        "root_cause": incident.get("root_cause"),
        "possible_causes": incident.get("possible_causes", []),
        "impact": incident.get("impact", []),
        "timeline": timeline,
    }


def _parse(reply: str) -> dict:
    m = _FENCE_RE.search(reply)
    text = m.group(1) if m else reply
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return {"summary": reply.strip(), "root_cause": "", "impact": "", "sources": []}
    return data


async def analyze(incident: dict) -> dict:
    evidence = _evidence(incident)
    messages = [
        {"role": "system", "content": PROMPT_FILE.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
    ]
    try:
        reply = await llm_client.chat(messages)
    except (llm_client.LLMUnavailable, llm_client.ExternalEndpointError) as e:
        raise ModelUnavailable(str(e)) from e  # misconfigured counts as unavailable (503)

    data = _parse(reply)
    known = {ev.get("id") for ev in incident.get("timeline", [])}
    sources = data.get("sources")
    sources = sources if isinstance(sources, list) else []
    return {
        "summary": str(data.get("summary") or ""),
        "root_cause": str(data.get("root_cause") or ""),
        "impact": str(data.get("impact") or ""),
        "sources": list(dict.fromkeys(s for s in sources if isinstance(s, str) and s in known)),
        "model": get_settings().llm_model,
        "created_at": datetime.now(UTC).isoformat(),
    }
