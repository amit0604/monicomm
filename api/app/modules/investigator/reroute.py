"""Failure rerouting: predicted path (lowest estimated cost) + recommended path (lowest peak load).

Pure, no I/O. Input is the LLDP graph from `Topology.edges()`; see
plans/incident-analyzer/reroute-plan.md for the contract. Recommendation only: nothing here
touches a device.
"""

from datetime import UTC, datetime
from itertools import combinations

from app.core import graph
from app.core.snmp_names import IFINDEX, ifkey
from app.modules.investigator.topology import Topology

UNKNOWN_COST = 65535  # OSPF max metric: a link of unknown speed is a last resort
MAX_DEVICE_PAIRS = 10
_RANK = {"ok": 0, "unknown": 1, "warning": 2, "critical": 3}

Step = graph.Step  # edge key = index into Topology.edges()
Link = tuple[str, str | None]  # (device, interface) as the failure event names it


def compute(
    topology: Topology,
    failed_links: list[Link],
    failed_devices: list[str],
    ref_bw_mbps: float,
    util_warn: float,
    now: datetime,
    *,
    edges: list[dict] | None = None,
    moved_loads: dict[Link, float] | None = None,
) -> dict | None:
    """`edges` = a precomputed `topology.edges()`; `moved_loads` = load remembered per failed
    link from the first computation (the dead link's own rate drops to 0 on the next poll)."""
    if edges is None:
        edges = topology.edges()
    moved_loads = moved_loads or {}
    costs = [
        max(1, round(ref_bw_mbps / e["speed_mbps"])) if e["speed_mbps"] else UNKNOWN_COST
        for e in edges
    ]
    nodes = {e[end] for e in edges for end in ("a", "b")}
    hits: dict[int, list[Link]] = {}
    for dev, ifname in failed_links:
        if (i := _find(topology, edges, dev, ifname)) is not None:
            hits.setdefault(i, []).append((dev, ifname))
    # a phantom LLDP duplicate shares the dead port: it can't carry the reroute either
    dead_ends = set().union(*(_ends(edges[i]) for i in hits))
    down_edges = set(hits) | {j for j, e in enumerate(edges) if _ends(e) & dead_ends}
    down_nodes = {d for d in failed_devices if d in nodes}
    if not down_edges and not down_nodes:
        return None

    full = _adjacency(edges, set(), set())
    alive = _adjacency(edges, down_edges, down_nodes)
    flows = []
    for i in sorted(hits):
        e = edges[i]
        reason = f"Link {e['a']} {e['a_if'] or '?'} <-> {e['b']} {e['b_if'] or '?'} down"
        before = [(e["a"], e["b"], i)]
        known = [moved_loads[k] for k in hits[i] if k in moved_loads]
        # a rate of exactly 0 on a failed link is the post-failure poll, not the moved load
        moved = known[0] if known else (e["load_bps"] or None)
        dev, ifname = hits[i][0]
        flow = _flow(edges, costs, alive, e["a"], e["b"], moved, reason, before, util_warn)
        flows.append(flow | {"failed": {"device": dev, "interface": ifname}})
    for dev in sorted(down_nodes):
        neighbors = sorted({n for n, _ in full[dev]} - down_nodes)
        # ponytail: first 10 neighbor pairs only; no flow data says which pairs matter
        for src, dst in list(combinations(neighbors, 2))[:MAX_DEVICE_PAIRS]:
            through = graph.shortest_path(
                full,
                src,
                dst,
                costs.__getitem__,
                lambda j, d=dev: d in (edges[j]["a"], edges[j]["b"]),
            )
            before = through[1] if through else []
            flows.append(
                _flow(edges, costs, alive, src, dst, None, f"Device {dev} down", before, util_warn)
            )

    assumptions = [
        f"Link costs estimated from interface speed (reference {ref_bw_mbps:g} Mbps); "
        "configured OSPF costs are not known",
        "One path per flow; equal-cost multipath (ECMP) is ignored",
        "The LLDP neighbor graph is taken as the routed graph "
        "(no L2-only hops, tunnels or policy routing)",
    ]
    if down_edges:
        assumptions.append("Moved load = last measured rate on the failed link")
    if down_nodes:
        assumptions.append("Load between the failed device's neighbors is unknown (no flow data)")
    # ponytail: each flow is checked alone; loads of several simultaneous failures don't stack
    return {
        "computed_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "assumptions": assumptions,
        "flows": flows,
        "isolated": _isolated(full, alive, down_nodes),
    }


def _ends(edge: dict) -> set[tuple[str, str]]:
    """(device, ifIndex) of the ends with a known ifIndex (a name-only end may be parallel)."""
    return {(edge[n], edge[f"{n}_port"]) for n in ("a", "b") if edge[f"{n}_port"] is not None}


def _find(topology: Topology, edges: list[dict], device: str, interface: str | None) -> int | None:
    if m := IFINDEX.match(interface or ""):  # exact port, even among parallel links
        for i, e in enumerate(edges):
            if (device, m[1]) in ((e["a"], e["a_port"]), (e["b"], e["b_port"])):
                return i
    hit = topology.link(device, interface)
    if not hit:
        return None
    far, far_if = hit
    pair = [i for i, e in enumerate(edges) if {e["a"], e["b"]} == {device, far}]
    for i in pair:
        e = edges[i]
        near_if, other_if = (e["a_if"], e["b_if"]) if e["a"] == device else (e["b_if"], e["a_if"])
        if ifkey(near_if) == ifkey(interface) or (far_if and ifkey(other_if) == ifkey(far_if)):
            return i
    return pair[0] if len(pair) == 1 else None  # e.g. "ifIndex 24" on a single link


def _adjacency(edges: list[dict], down_edges: set[int], down_nodes: set[str]) -> graph.Adjacency:
    nodes = {e[n] for e in edges for n in ("a", "b")} - down_nodes
    alive = ((e["a"], e["b"], i) for i, e in enumerate(edges) if i not in down_edges)
    return graph.adjacency(nodes, alive)


def _util(edge: dict, moved: float | None) -> float | None:
    speed, load = edge["speed_mbps"], edge["load_bps"]
    if speed is None or load is None or moved is None:
        return None  # PROJECT.md 2.3: what we can't see is unknown, not safe
    return round((load + moved) / (speed * 1e6), 4)


def _path(edges: list[dict], costs: list[int], steps: list[Step], moved, warn: float) -> dict:
    hops = []
    for frm, to, i in steps:
        e = edges[i]
        forward = e["a"] == frm
        util = _util(e, moved)
        hops.append(
            {
                "from": frm,
                "from_if": e["a_if"] if forward else e["b_if"],
                "to": to,
                "to_if": e["b_if"] if forward else e["a_if"],
                "speed_mbps": e["speed_mbps"],
                "load_bps": e["load_bps"],
                "util_after": util,
                "status": graph.util_status(util, warn),
            }
        )
    utils = [h["util_after"] for h in hops if h["util_after"] is not None]
    return {
        "hops": hops,
        "cost": sum(costs[i] for _, _, i in steps),
        "max_util": max(utils, default=None),
        "status": max((h["status"] for h in hops), key=_RANK.__getitem__, default="unknown"),
    }


def _flow(edges, costs, alive, src, dst, moved, reason, before, warn) -> dict:
    found = graph.shortest_path(alive, src, dst, costs.__getitem__)
    predicted = _path(edges, costs, found[1], moved, warn) if found else None
    recommended = None
    if predicted and predicted["status"] in ("warning", "critical"):
        # bottleneck search: lowest ceiling that still connects (connectivity only grows with
        # the ceiling, so binary search), then the cheapest path under it
        utils = {i: u for i, e in enumerate(edges) if (u := _util(e, moved)) is not None}
        limits = sorted({u for u in utils.values() if u < predicted["max_util"]})
        lo, hi, best = 0, len(limits) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            t = limits[mid]
            if hit := graph.shortest_path(
                alive, src, dst, costs.__getitem__, lambda i, t=t: utils.get(i, 2e9) <= t
            ):
                best, hi = hit, mid - 1
            else:
                lo = mid + 1
        if best:
            recommended = _path(edges, costs, best[1], moved, warn)
            recommended["why"] = _why(predicted, recommended, warn)
    return {
        "from": src,
        "to": dst,
        "load_bps": moved,
        "reason": reason,
        "failed": None,
        "before": {"hops": _path(edges, costs, before, 0.0, warn)["hops"]},
        "predicted": predicted,
        "recommended": recommended,
    }


def _why(predicted: dict, recommended: dict, warn: float) -> str:
    worst = max(
        (h for h in predicted["hops"] if h["util_after"] is not None),
        key=lambda h: h["util_after"],
    )
    text = (
        f"The predicted path would run {worst['from']} -> {worst['to']} at "
        f"{_pct(worst['util_after'])}; this path keeps every link at "
        f"{_pct(recommended['max_util'])} or less"
    )
    if recommended["status"] == "ok":
        text += f" (under the {_pct(warn)} warning level)"
    return f"{text}, at estimated cost {recommended['cost']} instead of {predicted['cost']}"


def _pct(util: float) -> str:
    return f"{util * 100:.0f} %"


def _isolated(full: dict, alive: dict, down_nodes: set[str]) -> list[str]:
    """Per LLDP island: everything cut off from its largest surviving piece."""
    after = graph.components(alive)
    out: set[str] = set()
    for before in graph.components(full):
        if pieces := [c for c in after if c <= before]:
            main = min(pieces, key=lambda c: (-len(c), sorted(c)))
            out |= before - main - down_nodes
    return sorted(out)
