"""ChatIAF: answers from a snapshot of current Monicomm data. It has no tools."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai import llm_client, llm_settings
from app.modules.dashboard.models import DataSource, DeviceDetails, DeviceStatus
from app.modules.dashboard.service import newest_first

PROMPT = Path(__file__).resolve().parents[2] / "ai" / "prompts" / "chat_live.md"
MAX_QUESTION_CHARS = 2000
MAX_REPLY_CHARS = 40_000
MAX_MESSAGES = 101
MAX_HISTORY = 20
MAX_HISTORY_CHARS = 40_000
MAX_CONTEXT_CHARS = 60_000
MAX_DETAILED_DEVICES = 60
MAX_EVENTS = 100
MAX_ALERTS = 100
MAX_EVENT_CHARS = 300
ORDER: list[DeviceStatus] = ["critical", "offline", "suspected_offline", "warning", "online"]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_REPLY_CHARS)


class ChatRequest(BaseModel):
    """The browser holds the conversation and sends it back, ending with the new question."""

    messages: list[Message] = Field(min_length=1, max_length=MAX_MESSAGES)


class Counts(BaseModel):
    devices: int
    alerts: int
    events: int


class Context(BaseModel):
    collected_at: datetime
    included: Counts  # how many records the model was given
    totals: Counts  # how many exist


class ChatReply(BaseModel):
    source: Literal["demo", "live"]
    reply: str
    model: str
    context: Context


class InvalidConversation(ValueError):
    pass


class ExternalModelRefused(RuntimeError):
    """A model outside the closed network may only see demo data."""


def prepare_history(messages: list[Message]) -> list[Message]:
    if len(messages) % 2 == 0:
        raise InvalidConversation
    for i, m in enumerate(messages):
        if m.role != ("assistant" if i % 2 else "user") or not m.content.strip():
            raise InvalidConversation
        if m.role == "user" and len(m.content) > MAX_QUESTION_CHARS:
            raise InvalidConversation
    kept = list(messages)
    while len(kept) > 1 and (
        len(kept) > MAX_HISTORY + 1 or sum(len(m.content) for m in kept) > MAX_HISTORY_CHARS
    ):
        del kept[:2]  # the oldest question and its answer
    return kept


def _detail_facts(d: DeviceDetails) -> dict[str, Any]:
    fields = {
        "name",
        "admin_status",
        "oper_status",
        "speed_mbps",
        "in_util_pct",
        "out_util_pct",
        "in_errors",
        "out_errors",
    }
    return {
        "latest_metrics": d.metrics.model_dump(),
        "interfaces": [i.model_dump(include=fields) for i in d.interfaces],
    }


def collect_context(source: DataSource) -> tuple[str, Context]:
    """Only the fields named here reach the AI. Problem devices come first and are cut last."""
    devices = sorted(source.devices(), key=lambda d: ORDER.index(d.status))
    all_alerts = sorted(source.open_alerts(), key=lambda a: a.opened_at, reverse=True)
    all_events = newest_first(source.events())
    now = datetime.now(UTC)

    device_fields = {
        "name",
        "ip",
        "vendor",
        "model",
        "type",
        "status",
        "os_version",
        "site",
        "last_poll_at",
    }
    device_rows: list[dict[str, Any]] = []
    for i, d in enumerate(devices):
        row = d.model_dump(mode="json", include=device_fields)
        full = source.device(d.id) if i < MAX_DETAILED_DEVICES else None
        device_rows.append(row | _detail_facts(full) if full else row)
    alert_fields = {"severity", "code", "device_name", "opened_at"}
    alert_rows = [a.model_dump(mode="json", include=alert_fields) for a in all_alerts[:MAX_ALERTS]]
    event_fields = {"kind", "severity", "device_name", "source_ip", "received_at"}
    event_rows = [
        e.model_dump(mode="json", include=event_fields) | {"message": e.message[:MAX_EVENT_CHARS]}
        for e in all_events[:MAX_EVENTS]
    ]
    totals = Counts(devices=len(devices), alerts=len(all_alerts), events=len(all_events))
    by_status = {s: sum(d.status == s for d in devices) for s in ORDER}
    demo_label = "DEMO - fabricated demonstration data, NOT real network telemetry"

    def included() -> Counts:
        return Counts(devices=len(device_rows), alerts=len(alert_rows), events=len(event_rows))

    def render() -> str:
        return json.dumps(
            {
                "data_source": demo_label if source.source == "demo" else "live",
                "collected_at": now.isoformat(),
                "totals": totals.model_dump(),
                "included": included().model_dump(),
                "device_counts_by_status": by_status,
                "open_alerts": alert_rows,
                "recent_events": event_rows,
                "devices": device_rows,
            },
            ensure_ascii=False,
        )

    text = render()
    # The healthiest devices lose their interfaces first, then whole records go.
    for row in reversed(device_rows):
        if len(text) <= MAX_CONTEXT_CHARS:
            break
        if row.get("interfaces"):
            row["interfaces"] = "omitted to save space"
            text = render()
    while len(text) > MAX_CONTEXT_CHARS:
        longest = max((device_rows, event_rows, alert_rows), key=len)
        if not longest:
            break
        del longest[int(len(longest) * 0.8) :]
        text = render()
    return text, Context(collected_at=now, included=included(), totals=totals)


async def answer(source: DataSource, messages: list[Message]) -> ChatReply:
    settings = llm_settings.current()
    history = prepare_history(messages)
    if settings.llm_provider == "gemini" and source.source != "demo":
        raise ExternalModelRefused
    data, context = collect_context(source)
    question = f"<MONICOMM_DATA>\n{data}\n</MONICOMM_DATA>\n\nQuestion:\n{history[-1].content}"
    reply = await llm_client.chat(
        [
            {"role": "system", "content": PROMPT.read_text("utf-8")},
            *[m.model_dump() for m in history[:-1]],
            {"role": "user", "content": question},
        ]
    )
    if not reply.strip():
        raise llm_client.LLMUnavailable("empty reply")
    model = settings.gemini_model if settings.llm_provider == "gemini" else settings.llm_model
    return ChatReply(
        source=source.source, reply=reply.strip()[:MAX_REPLY_CHARS], model=model, context=context
    )
