"""Incident Investigator REST API: /api/v1/investigator."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings

from .store import IncidentStore

router = APIRouter(prefix="/api/v1/investigator", tags=["investigator"])

SUMMARY_KEYS = ("id", "status", "severity", "title", "started_at", "updated_at", "devices")


def get_store() -> IncidentStore:
    return IncidentStore(get_settings().investigator_data_dir)


class IncidentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=20000)
    resolution: str | None = Field(default=None, max_length=20000)
    status: Literal["closed", "open"] | None = None


def _load(store: IncidentStore, incident_id: str) -> dict:
    incident = store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


# async handlers run on the event loop, same thread as the listener: no write races.
@router.get("/incidents")
async def list_incidents(
    status: Literal["open", "recovered", "closed"] | None = None,
    store: IncidentStore = Depends(get_store),  # noqa: B008
) -> list[dict]:
    return [
        {**{k: i.get(k) for k in SUMMARY_KEYS}, "root_cause": i.get("root_cause")}
        for i in store.list(status)
    ]


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, store: IncidentStore = Depends(get_store)) -> dict:  # noqa: B008
    return _load(store, incident_id)


@router.patch("/incidents/{incident_id}")
async def patch_incident(
    incident_id: str,
    body: IncidentPatch,
    store: IncidentStore = Depends(get_store),  # noqa: B008
) -> dict:
    incident = _load(store, incident_id)
    incident.update(body.model_dump(exclude_none=True))
    store.save(incident)
    return incident


@router.post("/incidents/{incident_id}/analysis")
async def analyze_incident(incident_id: str, store: IncidentStore = Depends(get_store)) -> dict:  # noqa: B008
    from . import analysis

    incident = _load(store, incident_id)
    try:
        result = await analysis.analyze(incident)
    except analysis.ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail="local model unavailable") from exc
    incident = _load(store, incident_id)  # re-read: the listener may have saved meanwhile
    incident["analysis"] = result
    store.save(incident)
    return result


@router.get("/incidents/{incident_id}/export.md")
async def export_incident(incident_id: str, store: IncidentStore = Depends(get_store)) -> Response:  # noqa: B008
    md = to_markdown(_load(store, incident_id))
    return Response(md, media_type="text/markdown; charset=utf-8")


def _code(text: object) -> str:
    """Inline code span that survives backticks in device output."""
    s = str(text or "").replace("\n", " ").replace("``", "` `")
    return f"`` {s} ``" if "`" in s else f"`{s}`"


def _cell(text: object) -> str:
    return str(text if text is not None else "-").replace("|", "\\|").replace("\n", " ")


def _pct(util: object) -> str:
    return f"{util * 100:.0f} %" if isinstance(util, int | float) else "unknown"


def _path_md(label: str, path: dict | None, none_text: str) -> list[str]:
    if not path:
        return [f"**{label}:** {none_text}", ""]
    head = f"**{label}:** status {path.get('status', 'unknown')}, cost {path.get('cost', '-')}, "
    out = [head + f"max utilization {_pct(path.get('max_util'))}"]
    if path.get("why"):
        out.append(f"Why: {path['why']}")
    out += [
        f"{n}. {h.get('from')} {h.get('from_if') or '?'} -> {h.get('to')} {h.get('to_if') or '?'}"
        f" ({_pct(h.get('util_after'))}, {h.get('status', 'unknown')})"
        for n, h in enumerate(path.get("hops") or [], 1)
    ]
    return [*out, ""]


def _reroute_md(rr: dict) -> list[str]:
    out = ["## Rerouting", "", "Assumptions:", ""]
    out += [f"- {a}" for a in rr.get("assumptions") or []] + [""]
    for f in rr.get("flows") or []:
        load = f.get("load_bps")
        out += [
            f"### {f.get('from')} -> {f.get('to')}",
            "",
            f"Reason: {f.get('reason', '-')}",
            f"Load moved: {f'{load / 1e6:.1f} Mbps' if load is not None else 'unknown'}",
            "",
        ]
        out += _path_md("Predicted path", f.get("predicted"), "none, the two ends are cut off")
        out += _path_md("Recommended path", f.get("recommended"), "none, keep the predicted path")
    out += [f"Isolated devices: {', '.join(rr.get('isolated') or []) or '-'}", ""]
    out += ["_Recommendation only: apply changes through the normal change process._", ""]
    return out


def to_markdown(inc: dict) -> str:
    rc = inc.get("root_cause") or {}
    out = [
        f"# {inc.get('title', 'Incident')}",
        "",
        f"- ID: {inc.get('id')}",
        f"- Status: {inc.get('status')}",
        f"- Severity: {inc.get('severity')}",
        f"- Started: {inc.get('started_at')}",
        f"- Updated: {inc.get('updated_at')}",
        f"- Devices: {', '.join(inc.get('devices') or [])}",
        "",
        "## Root cause",
        "",
        f"{rc.get('summary', 'Unknown')} (confidence: {rc.get('confidence', '-')})",
        f"Evidence: {', '.join(rc.get('event_ids') or []) or '-'}",
        "",
    ]
    if inc.get("possible_causes"):
        out += ["## Possible causes", ""]
        out += [
            f"- {c.get('summary')} (evidence: {', '.join(c.get('event_ids') or [])})"
            for c in inc["possible_causes"]
        ]
        out.append("")
    out += [
        "## Impact",
        "",
        "| Device | Interface | Peer | What | Recovered |",
        "|---|---|---|---|---|",
    ]
    for i in inc.get("impact") or []:
        cells = (i.get("device"), i.get("interface"), i.get("peer"), i.get("what"))
        out.append(
            "| "
            + " | ".join(_cell(c) for c in cells)
            + f" | {'yes' if i.get('recovered') else 'no'} |"
        )
    out += ["", "## Timeline", ""]
    for e in inc.get("timeline") or []:
        out.append(
            f"- {e.get('ts')} {e.get('device')} {e.get('type')} {e.get('state') or ''} "
            f"{_code(e.get('code'))} (id {e.get('id')})"
        )
        raw = str(e.get("raw") or "").replace("```", "` ` `")
        out += ["", "  ```", *(f"  {r}" for r in raw.splitlines()), "  ```", ""]
    if inc.get("reroute"):
        out += _reroute_md(inc["reroute"])
    out += ["## Notes", "", inc.get("notes") or "-", "", "## Resolution", ""]
    out += [inc.get("resolution") or "-", ""]
    ai = inc.get("analysis")
    if ai:
        out += [
            "## AI analysis",
            "",
            f"_Generated by {ai.get('model', 'local model')} at {ai.get('created_at', '-')}._",
            "",
            ai.get("summary", ""),
            "",
            f"**Root cause:** {ai.get('root_cause', '')}",
            "",
            f"**Impact:** {ai.get('impact', '')}",
            "",
            f"Sources: {', '.join(ai.get('sources') or []) or '-'}",
            "",
        ]
    return "\n".join(out)
