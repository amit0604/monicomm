"""Failure rerouting: predicted path (lowest estimated cost) + recommended path (lowest peak load).

Pure, no I/O. Input is the LLDP graph from `Topology.edges()`; see
plans/incident-analyzer/reroute-plan.md for the contract. Recommendation only: nothing here
touches a device.
"""

import heapq
from collections.abc import Callable
from datetime import UTC, datetime
from itertools import combinations

from app.modules.investigator.topology import Topology, ifkey

UNKNOWN_COST = 65535  # OSPF max metric: a link of unknown speed is a last resort
MAX_DEVICE_PAIRS = 10
_RANK = {"ok": 0, "unknown": 1, "warning": 2, "critical": 3}

Step = tuple[str, str, int]  # (from node, to node, edge index)


def compute(
    topology: Topology,
    failed_links: list[tuple[str, str | None]],
    failed_devices: list[str],
    ref_bw_mbps: float,
    util_warn: float,
    now: datetime,
) -> dict | None:
    edges = topology.edges()
    costs = [
        max(1, round(ref_bw_mbps / e["speed_mbps"])) if e["speed_mbps"] else UNKNOWN_COST
        for e in edges
    ]
    nodes = {e[end] for e in edges for end in ("a", "b")}
    down_edges = {
        i for dev, ifname in failed_links if (i := _find(topology, edges, dev, ifname)) is not None
    }
    down_nodes = {d for d in failed_devices if d in nodes}
    if not down_edges and not down_nodes:
        return None

    full = _adjacency(edges, set(), set())
    alive = _adjacency(edges, down_edges, down_nodes)
    flows = []
    for i in sorted(down_edges):
        e = edges[i]
        reason = f"Link {e['a']} {e['a_if'] or '?'} <-> {e['b']} {e['b_if'] or '?'} down"
        before = [(e["a"], e["b"], i)]
        flows.append(
            _flow(edges, costs, alive, e["a"], e["b"], e["load_bps"], reason, before, util_warn)
        )
    for dev in sorted(down_nodes):
        neighbors = sorted({n for n, _ in full[dev]} - down_nodes)
        # ponytail: first 10 neighbor pairs only; no flow data says which pairs matter
        for src, dst in list(combinations(neighbors, 2))[:MAX_DEVICE_PAIRS]:
            through = _dijkstra(
                full, costs, src, dst, lambda j, d=dev: d in (edges[j]["a"], edges[j]["b"])
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


def _find(topology: Topology, edges: list[dict], device: str, interface: str | None) -> int | None:
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


def _adjacency(edges: list[dict], down_edges: set[int], down_nodes: set[str]) -> dict:
    adj: dict[str, list[tuple[str, int]]] = {}
    for i, e in enumerate(edges):
        a, b = e["a"], e["b"]
        for n in (a, b):
            if n not in down_nodes:
                adj.setdefault(n, [])
        if i in down_edges or a in down_nodes or b in down_nodes:
            continue
        adj[a].append((b, i))
        adj[b].append((a, i))
    return adj


def _dijkstra(
    adj: dict,
    costs: list[int],
    src: str,
    dst: str,
    allowed: Callable[[int], bool] = lambda _: True,
) -> tuple[int, list[Step]] | None:
    heap: list[tuple[int, str, list[Step]]] = [(0, src, [])]
    done: set[str] = set()
    while heap:
        cost, node, path = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node == dst:
            return cost, path
        for nxt, i in adj.get(node, []):
            if nxt not in done and allowed(i):
                heapq.heappush(heap, (cost + costs[i], nxt, [*path, (node, nxt, i)]))
    return None


def _util(edge: dict, moved: float | None) -> float | None:
    speed, load = edge["speed_mbps"], edge["load_bps"]
    if speed is None or load is None or moved is None:
        return None  # PROJECT.md 2.3: what we can't see is unknown, not safe
    return round((load + moved) / (speed * 1e6), 4)


def _status(util: float | None, warn: float) -> str:
    if util is None:
        return "unknown"
    return "critical" if util >= 1.0 else "warning" if util >= warn else "ok"


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
                "status": _status(util, warn),
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
    found = _dijkstra(alive, costs, src, dst)
    predicted = _path(edges, costs, found[1], moved, warn) if found else None
    recommended = None
    if predicted and predicted["status"] in ("warning", "critical"):
        # bottleneck search: lowest threshold that still connects, then cheapest path under it
        # ponytail: one Dijkstra per distinct utilization, fine for hundreds of links
        utils = {i: u for i, e in enumerate(edges) if (u := _util(e, moved)) is not None}
        for limit in sorted(set(utils.values())):
            if limit >= predicted["max_util"]:
                break
            if hit := _dijkstra(alive, costs, src, dst, lambda i, t=limit: utils.get(i, 2e9) <= t):
                recommended = _path(edges, costs, hit[1], moved, warn)
                recommended["why"] = _why(predicted, recommended, warn)
                break
    return {
        "from": src,
        "to": dst,
        "load_bps": moved,
        "reason": reason,
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


def _components(adj: dict) -> list[set[str]]:
    seen: set[str] = set()
    out = []
    for start in sorted(adj):
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n not in comp:
                comp.add(n)
                stack.extend(m for m, _ in adj[n])
        seen |= comp
        out.append(comp)
    return out


def _isolated(full: dict, alive: dict, down_nodes: set[str]) -> list[str]:
    after = _components(alive)
    if not after:
        return []
    main = min(after, key=lambda c: (-len(c), sorted(c)))
    before = next(c for c in _components(full) if main <= c)
    return sorted(before - main - down_nodes)
