"""Free text -> structured Change via the local LLM, validated against the topology."""

import json
import re
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from app.ai import llm_client
from app.modules.analyzer.models import Change, ChangeKind, Topology
from app.modules.investigator.topology import ifkey

PROMPT_FILE = Path(__file__).resolve().parents[2] / "ai" / "prompts" / "analyzer_change_parse.md"
# ponytail: caps keep the prompt small; past ~300 devices send only names that appear in the text
MAX_DEVICES = 300
MAX_INTERFACES = 100
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class Unparsed(ValueError):
    """The request couldn't be turned into one supported change on a known device."""


class ModelUnavailable(Exception):
    """The local model could not be reached."""


def _reply_json(reply: str) -> dict:
    m = _FENCE_RE.search(reply)
    try:
        data = json.loads(m.group(1) if m else reply)
    except ValueError:
        raise Unparsed("model reply is not JSON") from None
    if not isinstance(data, dict):
        raise Unparsed("model reply is not a JSON object")
    return data


def _named(device_id: str, text: str) -> bool:
    """The device, or its short form ("DEMO-core-sw-01.lab" -> "core-sw-01"), is in the text."""
    full = device_id.lower()
    short = full.removeprefix("demo-").split(".")[0]
    text = text.lower()
    return full in text or short in text


def _validate(data: dict, topo: Topology, text: str) -> Change:
    """Never trust model output: every field is checked against the topology and the text."""
    error = data.get("error")
    if isinstance(error, str) and error.strip():
        raise Unparsed(error.strip()[:200])
    kind, device, interface = data.get("kind"), data.get("device"), data.get("interface")
    if kind not in get_args(ChangeKind):
        raise Unparsed("unsupported change kind")
    if not isinstance(device, str):
        raise Unparsed("no device")
    node = next((n for n in topo.nodes if n.id.lower() == device.strip().lower()), None)
    if node is None:
        raise Unparsed("device not in topology")
    if not _named(node.id, text):  # plan: never a change on a device the request didn't name
        raise Unparsed("device not named in the request")
    if kind == "device_down":
        return Change(kind=kind, device=node.id)
    if not isinstance(interface, str):
        raise Unparsed("no interface")
    key = ifkey(interface)
    name = next((i for i in node.interfaces if ifkey(i) == key), None)
    if name is None:
        raise Unparsed("interface not on that device")
    return Change(kind=kind, device=node.id, interface=name)


async def parse(text: str, topo: Topology) -> Change:
    devices = [
        {"id": n.id, "interfaces": n.interfaces[:MAX_INTERFACES]} for n in topo.nodes[:MAX_DEVICES]
    ]
    messages = [
        {"role": "system", "content": PROMPT_FILE.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps({"request": text, "devices": devices})},
    ]
    try:
        reply = await llm_client.chat(messages)
    except (llm_client.LLMUnavailable, llm_client.ExternalEndpointError) as e:
        raise ModelUnavailable(str(e)) from e  # misconfigured counts as unavailable (503)
    try:
        return _validate(_reply_json(reply), topo, text)
    except ValidationError:  # Change's own rules (lengths, interface_down needs an interface)
        raise Unparsed("not a valid change") from None
