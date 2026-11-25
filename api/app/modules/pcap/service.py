"""Catchup service: capture storage, background analysis, AI summary and scoped chat.

ponytail: captures live on disk as JSON next to the file (MONICOMM_PCAP_DATA_DIR/<id>/), analysis
runs in FastAPI BackgroundTasks. Move to DB tables + the shared worker queue once those exist;
a capture left 'processing' by a restart stays that way until then.
"""

import asyncio
import json
import re
import shutil
import time
import uuid
from collections import defaultdict
from pathlib import Path

from app.ai import llm_client
from app.core.config import get_settings

from . import network, parser

DATA_DIR = Path(get_settings().pcap_data_dir)
MAX_UPLOAD_BYTES = get_settings().pcap_max_upload_mb * 1024 * 1024
ALLOWED_SUFFIXES = (".pcap", ".pcapng", ".cap")
PROMPTS = Path(__file__).resolve().parents[2] / "ai" / "prompts"
_ID = re.compile(r"^[0-9a-f]{32}$")

# What the LLM sees: metadata only, never payload bytes. Caps keep the prompt small.
LLM_LIMITS = {"conversations": 40, "anomalies": 60, "dns": 60, "http": 40, "tls": 40}
# Most telling first, so floods of minor anomalies never push these out of the prompt.
SEVERITY = [
    "port_scan",
    "beacon",
    "syn_no_response",
    "tcp_reset",
    "slow_handshake",
    "tcp_retransmission",
]
CAPTURE_CONVERSATIONS = 200  # largest conversations returned with GET /captures/{id}
_chat_locks = defaultdict(asyncio.Lock)  # ponytail: per-process lock, fine for one api replica


class NotFound(Exception):
    pass


class LLMUnavailable(Exception):
    pass


def _dir(capture_id: str) -> Path:
    if not _ID.match(capture_id or ""):
        raise NotFound(capture_id)
    d = DATA_DIR / capture_id
    if not d.is_dir():
        raise NotFound(capture_id)
    return d


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), "utf-8")
    tmp.replace(path)  # atomic, readers never see half a file


def new_capture(filename: str) -> tuple[str, Path]:
    capture_id = uuid.uuid4().hex
    d = DATA_DIR / capture_id
    d.mkdir(parents=True)
    _write(
        d / "meta.json",
        {
            "id": capture_id,
            "filename": filename,
            "status": "uploading",
            "size": 0,
            "uploaded_at": time.time(),
            "error": None,
        },
    )
    return capture_id, d / "capture.bin"


def set_meta(capture_id: str, **fields) -> dict:
    d = DATA_DIR / capture_id
    meta = _read(d / "meta.json")
    if meta is None:  # deleted while processing
        return {}
    meta.update(fields)
    _write(d / "meta.json", meta)
    return meta


def process(capture_id: str) -> None:
    """Background job: parse the file and store the analysis."""
    d = DATA_DIR / capture_id
    set_meta(capture_id, status="processing")
    try:
        result = parser.analyze(d / "capture.bin")
    except parser.PcapError as e:
        set_meta(capture_id, status="failed", error=str(e))
        return
    except Exception as e:
        if not d.is_dir():
            return  # deleted while processing
        set_meta(capture_id, status="failed", error=f"parser crashed: {type(e).__name__}")
        raise  # keep the record honest instead of stuck in 'processing', and log it
    if not d.is_dir():
        return
    _write(d / "timebins.json", result.pop("time_bins"))  # only the network views read it
    _write(d / "analysis.json", result)
    set_meta(capture_id, status="done")


def list_captures() -> list[dict]:
    if not DATA_DIR.is_dir():
        return []
    metas = [_read(d / "meta.json") for d in DATA_DIR.iterdir() if _ID.match(d.name)]
    return sorted((m for m in metas if m), key=lambda m: m["uploaded_at"], reverse=True)


def get_capture(capture_id: str) -> dict:
    d = _dir(capture_id)
    a = _read(d / "analysis.json")
    if a:  # full list is paged via conversations(); keep this response small
        convs = a.pop("conversations")
        a["conversations_total"] = len(convs)
        a["conversations"] = sorted(convs, key=lambda c: c["bytes"], reverse=True)[
            :CAPTURE_CONVERSATIONS
        ]
    return {**_read(d / "meta.json"), "analysis": a}


def _network_inputs(capture_id: str):
    return _analysis(capture_id), _read(_dir(capture_id) / "timebins.json")


def graph(capture_id: str, protocol: str, min_packets: int, t_start, t_end) -> dict:
    return network.graph(*_network_inputs(capture_id), protocol, min_packets, t_start, t_end)


def overview(capture_id: str, t_start, t_end) -> dict:
    return network.overview(*_network_inputs(capture_id), t_start, t_end)


def timeline(capture_id: str) -> dict:
    return network.timeline(*_network_inputs(capture_id))


def host(capture_id: str, ip: str) -> dict:
    h = network.host(_analysis(capture_id), ip)
    if h is None:
        raise NotFound(ip)
    return h


def conversations(capture_id: str, offset: int, limit: int) -> dict:
    convs = _analysis(capture_id)["conversations"]
    return {"total": len(convs), "items": convs[offset : offset + limit]}


def _analysis(capture_id: str) -> dict:
    a = _read(_dir(capture_id) / "analysis.json")
    if a is None:
        raise NotFound(capture_id)
    return a


def stream(capture_id: str, conv_id: int) -> dict:
    a = _analysis(capture_id)
    if not 0 <= conv_id < len(a["conversations"]):
        raise NotFound(conv_id)
    conv = a["conversations"][conv_id]
    return {
        "conversation": conv,
        "segments": parser.follow_stream(_dir(capture_id) / "capture.bin", conv),
    }


def delete_capture(capture_id: str) -> None:
    shutil.rmtree(_dir(capture_id))
    _chat_locks.pop(capture_id, None)


# ---- AI ------------------------------------------------------------------------------------------


async def _llm_chat(messages: list[dict]) -> str:
    """The one place this module talks to the model (CLAUDE.md rule 1)."""
    try:
        return await llm_client.chat(messages)
    except (llm_client.LLMUnavailable, llm_client.ExternalEndpointError) as e:
        raise LLMUnavailable(str(e)) from e


def llm_context(a: dict) -> dict:
    """Compact, payload-free view of the analysis for the prompt."""
    keys = (
        "packet_count",
        "duration_s",
        "truncated_after_packet",
        "protocols",
        "anomaly_counts",
    )
    ctx = {k: a.get(k) for k in keys}
    a = {
        **a,
        "anomalies": sorted(a["anomalies"], key=lambda x: (_rank(x["type"]), x["packet"])),
    }
    convs = sorted(a["conversations"], key=lambda c: c["bytes"], reverse=True)
    ctx["conversations_total"] = len(convs)
    for key, cap in LLM_LIMITS.items():
        items = convs if key == "conversations" else a[key]
        ctx[key] = items[:cap]
        if len(items) > cap:
            ctx[f"{key}_omitted"] = len(items) - cap
    return ctx


def _rank(anomaly_type: str) -> int:
    return SEVERITY.index(anomaly_type) if anomaly_type in SEVERITY else len(SEVERITY)


def _sources(text: str, a: dict) -> list[int]:
    """Packet numbers the answer cites as [#123], kept only if they exist in the capture."""
    nums = {int(n) for n in re.findall(r"\[#(\d+)\]", text)}
    return sorted(n for n in nums if 1 <= n <= a["packet_count"])


def _context(prompt_file: str, a: dict) -> list[dict]:
    """System prompt, then the capture data as a separate, clearly marked message.

    Hostnames, URIs and DNS names come from the capture and may be attacker-controlled,
    so they never go in the system role.
    """
    prompt = (PROMPTS / prompt_file).read_text("utf-8")
    data = json.dumps(llm_context(a))
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"<capture_analysis>\n{data}\n</capture_analysis>"},
    ]


async def summary(capture_id: str, refresh: bool = False) -> dict:
    d = _dir(capture_id)
    cached = _read(d / "summary.json")
    if cached and not refresh:
        return cached
    a = _analysis(capture_id)
    text = await _llm_chat(
        [
            *_context("pcap_summary.md", a),
            {"role": "user", "content": "Summarize this capture."},
        ]
    )
    result = {
        "text": text,
        "sources": _sources(text, a),
        "ai": True,
        "created_at": time.time(),
    }
    _write(d / "summary.json", result)
    return result


async def chat(capture_id: str, question: str) -> dict:
    d = _dir(capture_id)
    a = _analysis(capture_id)
    async with _chat_locks[capture_id]:  # two chats at once must not lose a turn
        history = _read(d / "chat.json", [])
        # ponytail: last 10 turns only, add summarization of older turns if threads get long
        msgs = _context("pcap_chat.md", a)
        msgs += [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
        msgs.append({"role": "user", "content": question})
        asked = time.time()
        text = await _llm_chat(msgs)
        answer = {
            "role": "assistant",
            "content": text,
            "sources": _sources(text, a),
            "ai": True,
            "ts": time.time(),
        }
        history += [{"role": "user", "content": question, "ts": asked}, answer]
        _write(d / "chat.json", history)
    return answer


def chat_history(capture_id: str) -> list[dict]:
    return _read(_dir(capture_id) / "chat.json", [])
