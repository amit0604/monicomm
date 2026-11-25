"""Group abnormal NetEvents into incidents with a rule-based root cause and impact.

Incidents are the JSON dicts from plans/incident-analyzer/plan.md "Contracts". Every derived field
(root cause, impact, severity, title, status) is recomputed from the timeline, so load() needs
nothing else. Pure Python: no I/O, no logging.
"""

import uuid
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.modules.investigator.events import STATEFUL, NetEvent
from app.modules.investigator.topology import Topology, ifkey

FLAP_COUNT = 3  # link downs on one interface within the window
LOGIN_COUNT, LOGIN_WINDOW_S = 5, 300  # failed logins on one device
MAX_TIMELINE = 500  # ponytail: later events are dropped once full; trim oldest context if needed
MAX_OPEN = 1000  # incidents kept in memory; the oldest by last event is forgotten
MAX_RECENT = 10_000
HOLD_S = 5  # IOS shutdown: LINEPROTO down may arrive just before its "administratively down" line
ADJACENCY = {"bgp", "ospf", "isis"}
CAUSE_TYPES = {"link", "hw_env", "cluster_failover"}
LABEL = {
    "bgp": "BGP session",
    "ospf": "OSPF adjacency",
    "isis": "IS-IS adjacency",
    "vpn": "VPN tunnel",
    "cluster_failover": "Cluster failover",
    "hw_env": "Hardware/environment alarm",
    "stp_change": "Spanning-tree topology change",
    "config_change": "Config change",
    "login_failed": "Failed login",
    "other": "Event",
}


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row(ev: NetEvent, abnormal: bool) -> dict:
    return asdict(ev) | {"ts": _iso(ev.ts), "abnormal": abnormal}


def _key(e: dict) -> tuple:
    if e["type"] == "link":
        return ("link", e["device"], ifkey(e["interface"]))
    if e["type"] in STATEFUL:
        return (e["type"], e["device"], e["peer"])
    if e["type"] == "login_failed":
        return ("login_failed", e["device"], None)
    return (e["type"], e["device"], e["interface"])


def _what(e: dict) -> str:
    if e["type"] == "link":
        return f"Interface {e['interface'] or '?'} down"
    if e["type"] in STATEFUL:
        return LABEL[e["type"]] + (f" to {e['peer']}" if e["peer"] else "") + " down"
    where = f" on {e['interface']}" if e["interface"] else ""
    return LABEL.get(e["type"], "Event") + where + (f" ({e['code']})" if e["code"] else "")


def _lineproto_down(e: NetEvent) -> bool:
    return e.type == "link" and e.state == "down" and "LINEPROTO" in (e.code or "")


class Correlator:
    def __init__(self, window_s: int = 120, topology: Topology | None = None) -> None:
        self.window_s = window_s
        self.topology = topology or Topology()
        self._open: dict[str, dict] = {}
        self._recent: deque[NetEvent] = deque(maxlen=MAX_RECENT)  # all events, window only
        self._held: list[NetEvent] = []  # LINEPROTO downs waiting HOLD_S for an admin-down line

    def load(self, incidents: list[dict]) -> None:
        for inc in incidents:
            if inc.get("status") == "closed":
                self._open.pop(inc.get("id"), None)
            else:
                self._open[inc["id"]] = inc

    def feed(self, ev: NetEvent) -> list[dict]:
        self._recent.append(ev)
        horizon = ev.ts - timedelta(seconds=max(self.window_s, LOGIN_WINDOW_S))
        while self._recent[0].ts < horizon:
            self._recent.popleft()
        changed = {i["id"]: i for i in self.flush(ev.ts)}
        if _lineproto_down(ev):
            self._held.append(ev)
        else:
            changed |= {i["id"]: i for i in self._process(ev)}
        return list(changed.values())

    def flush(self, now: datetime) -> list[dict]:
        """Act on held LINEPROTO downs older than HOLD_S. feed() calls it; call it when idle too."""
        due = [e for e in self._held if (now - e.ts).total_seconds() >= HOLD_S]
        self._held = [e for e in self._held if e not in due]
        changed: dict[str, dict] = {}
        for e in due:
            if not self._superseded(e):
                changed |= {i["id"]: i for i in self._process(e)}
        return list(changed.values())

    def _superseded(self, ev: NetEvent) -> bool:
        """Same port: an admin-down line within window_s before or HOLD_S after, or already up."""
        for e in self._recent:
            if (
                e.type != "link"
                or e.device != ev.device
                or ifkey(e.interface) != ifkey(ev.interface)
            ):
                continue
            delta = (e.ts - ev.ts).total_seconds()
            admin = e.state == "down" and not e.abnormal and -self.window_s <= delta <= HOLD_S
            if admin or (e.state == "up" and delta >= 0):
                return True
        return False

    def _process(self, ev: NetEvent) -> list[dict]:
        if ev.state == "up":
            return self._recover(ev)
        members = self._window_rule(ev)
        if not (ev.abnormal or members):
            return []
        inc = self._match(ev) or self._new()
        for e in members or [ev]:
            self._add(inc, e, True)
        self._pull_context(inc)
        self._refresh(inc)
        self._open[inc["id"]] = inc
        if len(self._open) > MAX_OPEN:
            oldest = min(self._open.values(), key=lambda i: _dt(i["updated_at"]))
            del self._open[oldest["id"]]
        return [inc]

    def _window_rule(self, ev: NetEvent) -> list[NetEvent]:
        """Events that are abnormal together: interface flapping or a failed-login burst."""
        if ev.type == "link" and ev.state == "down":
            limit, count = self.window_s, FLAP_COUNT
        elif ev.type == "login_failed":
            limit, count = LOGIN_WINDOW_S, LOGIN_COUNT
        else:
            return []
        hits = [
            e
            for e in self._recent
            if (e.device, e.type, e.state) == (ev.device, ev.type, ev.state)
            and ifkey(e.interface) == ifkey(ev.interface)
            and abs((ev.ts - e.ts).total_seconds()) <= limit
            and not _lineproto_down(e)  # IOS logs LINK + LINEPROTO per flap: count once
        ]
        return hits if len(hits) >= count else []

    def _match(self, ev: NetEvent) -> dict | None:
        near = self.topology.neighbors(ev.device) | {ev.device}
        best = None
        for inc in self._open.values():
            last = _dt(inc["updated_at"])
            if (
                inc["status"] != "closed"
                and abs((ev.ts - last).total_seconds()) <= self.window_s
                and near & set(inc["devices"])
                and (best is None or last > _dt(best["updated_at"]))
            ):
                best = inc
        return best

    def _new(self) -> dict:
        return {
            "id": uuid.uuid4().hex[:12],
            "status": "open",
            "severity": "warning",
            "title": "",
            "started_at": "",
            "updated_at": "",
            "devices": [],
            "root_cause": None,
            "possible_causes": [],
            "impact": [],
            "timeline": [],
            "notes": "",
            "resolution": "",
            "analysis": None,
        }

    def _add(self, inc: dict, ev: NetEvent, abnormal: bool) -> None:
        for row in inc["timeline"]:
            if row["id"] == ev.id:
                row["abnormal"] = row["abnormal"] or abnormal
                return
        if len(inc["timeline"]) < MAX_TIMELINE:
            inc["timeline"].append(_row(ev, abnormal))

    def _pull_context(self, inc: dict) -> None:
        """Normal events on incident devices in the window before the first abnormal one."""
        devices = {r["device"] for r in inc["timeline"]}
        first = min(_dt(r["ts"]) for r in inc["timeline"] if r["abnormal"])
        for e in self._recent:
            if (
                not e.abnormal
                and e.state != "up"
                and e.type not in ("other", "login_failed")
                and e.device in devices
                and first - timedelta(seconds=self.window_s) <= e.ts <= first
            ):
                self._add(inc, e, False)

    def _recover(self, ev: NetEvent) -> list[dict]:
        key, changed = _key(_row(ev, False)), []
        for inc in self._open.values():
            tl = inc["timeline"]
            if inc["status"] == "closed" or any(r["id"] == ev.id for r in tl):
                continue
            if any(r["abnormal"] and r["state"] == "down" and _key(r) == key for r in tl):
                self._add(inc, ev, False)
                self._refresh(inc)
                changed.append(inc)
        return changed

    def _refresh(self, inc: dict) -> None:
        tl = inc["timeline"]
        tl.sort(key=lambda r: _dt(r["ts"]))
        ab = [r for r in tl if r["abnormal"]]
        devices = sorted({r["device"] for r in tl})
        impact = self._impact(tl)
        root, title = self._root_cause(ab)
        if len(devices) > 1 and not title.startswith("Link down"):
            title += f" (+{len(devices) - 1} more devices)"
        root_ts = _dt(next(r["ts"] for r in tl if r["id"] == root["event_ids"][0]))
        inc.update(
            severity="critical" if any(self._critical(r) for r in ab) else "warning",
            title=title,
            started_at=ab[0]["ts"],
            updated_at=tl[-1]["ts"],
            devices=devices,
            root_cause=root,
            possible_causes=[
                {
                    "summary": f"{'Config change' if r['type'] == 'config_change' else _what(r)}"
                    f" on {r['device']} {int((root_ts - _dt(r['ts'])).total_seconds())} s before",
                    "event_ids": [r["id"]],
                }
                for r in tl
                if not r["abnormal"]
                and r["state"] != "up"
                and timedelta(0) <= root_ts - _dt(r["ts"]) <= timedelta(seconds=self.window_s)
            ],
            impact=impact,
            status="recovered" if impact and all(i["recovered"] for i in impact) else "open",
        )

    @staticmethod
    def _critical(e: dict) -> bool:
        return (
            (e["type"] in STATEFUL and e["state"] == "down")
            or e["type"] == "cluster_failover"
            or (e["type"] == "hw_env" and e["severity"] in ("emerg", "alert", "crit"))
        )

    @staticmethod
    def _impact(tl: list[dict]) -> list[dict]:
        items: dict[tuple, dict] = {}
        downs: dict[tuple, list[str]] = {}
        for e in tl:
            key = _key(e)
            if e["state"] == "up":
                if key in items:
                    items[key]["recovered"] = True
                    items[key]["event_ids"].append(e["id"])
                continue
            if not e["abnormal"]:
                continue  # context: a possible cause, not impact
            item = items.setdefault(
                key,
                {
                    "device": e["device"],
                    "interface": e["interface"],
                    "peer": e["peer"],
                    "what": _what(e),
                    "recovered": False,
                    "event_ids": [],
                },
            )
            item["event_ids"].append(e["id"])
            item["recovered"] = False
            if e["type"] == "link" and "LINEPROTO" not in (e["code"] or ""):  # once per flap
                downs.setdefault(key, []).append(e["id"])
            if e["type"] == "login_failed":
                item["what"] = f"{len(item['event_ids'])} failed logins"
        for key, ids in downs.items():
            if len(ids) >= FLAP_COUNT:
                link = items[key]
                items[("flap", *key)] = link | {
                    "what": f"Interface {link['interface']} flapping ({len(ids)} times)",
                    "event_ids": ids,
                }
        return list(items.values())

    def _root_cause(self, ab: list[dict]) -> tuple[dict, str]:
        links = [e for e in ab if e["type"] == "link" and e["state"] == "down"]
        for a in links:
            far = self.topology.link(a["device"], a["interface"])
            for b in links if far else []:
                if b["device"] == far[0] and (
                    far[1] is None or ifkey(b["interface"]) == ifkey(far[1])
                ):
                    ends = f"{a['device']} {a['interface']} and {b['device']} {b['interface']}"
                    return (
                        {
                            "summary": f"Link failure between {ends}",
                            "event_ids": [a["id"], b["id"]],
                            "confidence": "high",
                        },
                        f"Link down: {ends.replace(' and ', ' <-> ')}",
                    )
        for c in ab:
            if c["type"] not in CAUSE_TYPES:
                continue
            near = self.topology.neighbors(c["device"]) | {c["device"]}
            if any(
                e["type"] in ADJACENCY
                and e["state"] == "down"
                and e["device"] in near
                and _dt(e["ts"]) >= _dt(c["ts"])
                for e in ab
            ):
                return (
                    {
                        "summary": f"{_what(c)} on {c['device']}, then routing adjacencies dropped",
                        "event_ids": [c["id"]],
                        "confidence": "high" if c["type"] == "link" else "medium",
                    },
                    f"{_what(c)} on {c['device']}",
                )
        c = ab[0]
        summary = f"{_what(c)} on {c['device']}"
        return {"summary": summary, "event_ids": [c["id"]], "confidence": "low"}, summary
