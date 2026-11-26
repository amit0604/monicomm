"""Change impact simulation: pure, no I/O (plans/change-impact/plan.md, Phase 1).

Removes a link or node from a copy of the topology, then answers: who loses the path to core,
where does the removed link's traffic go and how full does that make it, what became a single
point of failure, how risky is it, when is the quietest hour, and how to roll back.
"""

import secrets
from datetime import UTC, datetime

from app.core import graph
from app.core.snmp_names import ifkey
from app.modules.analyzer.models import (
    Affected,
    Change,
    Link,
    LinkLoad,
    Report,
    Reroute,
    Spof,
    Topology,
    UnknownTarget,
    Window,
)


def _label(link: Link) -> str:
    return f"{link.a.device} {link.a.interface} ↔ {link.b.device} {link.b.interface}"


def _graph(nodes: set[str], links: list[Link]) -> graph.Adjacency:
    return graph.adjacency(nodes, ((x.a.device, x.b.device, x.id) for x in links))


def _hops(nodes: set[str], links: list[Link], cores: set[str]) -> dict[str, int]:
    """Hop distance to the nearest core node, for every node that has a path to core."""
    return graph.hops(_graph(nodes, links), cores)


def _reach(nodes: set[str], links: list[Link], cores: set[str]) -> set[str]:
    return set(_hops(nodes, links, cores))


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'s' * (count != 1)}"


def _path(nodes: set[str], links: list[Link], src: str, dst: set[str]) -> list[str]:
    """Link ids of the shortest path (by hops) from src to the nearest node in dst."""
    found = graph.shortest_path(_graph(nodes, links), src, dst)
    return [link_id for _, _, link_id in found[1]] if found else []


def _new_spofs(before, after, cores: set[str], by_id: dict[str, Link]) -> list[Spof]:
    # ponytail: brute force, O(V*(V+E)). Tarjan bridges/articulation points is the upgrade
    # when topologies get large.
    (b_nodes, b_links), (a_nodes, a_links) = before, after
    base = _reach(a_nodes, a_links, cores)
    out = []
    for node in sorted(a_nodes):
        lost = base - {node} - _reach(a_nodes - {node}, a_links, cores)
        cut_before = b_nodes - {node} - _reach(b_nodes - {node}, b_links, cores)
        if lost - cut_before:
            out.append(Spof(kind="node", id=node, label=node))
    for link in a_links:
        lost = base - _reach(a_nodes, [x for x in a_links if x.id != link.id], cores)
        cut_before = b_nodes - _reach(b_nodes, [x for x in b_links if x.id != link.id], cores)
        if lost - cut_before:
            out.append(Spof(kind="link", id=link.id, label=_label(by_id[link.id])))
    return out


def _rollback(dev: str, ifname: str | None, vendor: str | None) -> str:
    if ifname is None:
        return (
            f"Power {dev} back on / roll back the replacement and confirm all links come back up."
        )
    if vendor == "Cisco":
        how = f"Cisco: interface {ifname}, then no shutdown"
    elif vendor == "Juniper":
        how = f"Juniper: delete interfaces {ifname} disable, then commit"
    else:
        how = "bring the port administratively up"
    return f"Re-enable {ifname} on {dev} ({how}) and confirm the link comes back up."


def _spof_text(spofs: list[Spof]) -> str:
    """'4 new single points of failure (DEMO-core-sw-02, 1 more device and 2 links)'."""
    if not spofs:
        return "no new single points of failure"
    nodes = [s.id for s in spofs if s.kind == "node"]
    parts = nodes[:1]  # one name keeps the sentence short; the full list is in new_spofs
    if len(nodes) > 1:
        parts.append(_n(len(nodes) - 1, "more device"))
    n_links = len(spofs) - len(nodes)
    if n_links:
        parts.append(_n(n_links, "link"))
    names = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    plural = "s" * (len(spofs) > 1)
    return f"{len(spofs)} new single point{plural} of failure ({names})"


def simulate(topo: Topology, change: Change, util_warn: float = 0.8) -> Report:
    """`util_warn` = MONICOMM_LINK_UTIL_WARN (0.8 = 80 %); 100 % or more is critical."""
    nodes = {n.id: n for n in topo.nodes}
    by_id = {link.id: link for link in topo.links}
    node = nodes.get(change.device)
    if node is None:
        raise UnknownTarget(f"unknown device: {change.device}")
    unknowns: list[str] = []
    warnings: list[str] = []

    # Apply the change to a copy of the graph.
    ifname = None
    if change.kind == "interface_down":
        # Short and long names match ("Gi1/0/2" = "GigabitEthernet1/0/2"); report the node's own.
        key = ifkey(change.interface)
        ifname = next((i for i in node.interfaces if ifkey(i) == key), None)
        if ifname is None:
            raise UnknownTarget(f"unknown interface on {change.device}: {change.interface}")
        removed = [
            x
            for x in topo.links
            if any(e.device == node.id and ifkey(e.interface) == key for e in (x.a, x.b))
        ]
        if not removed:
            unknowns.append(
                f"No neighbor link known on {change.device} {ifname}; "
                "what is behind it is unknown."
            )
        a_nodes = set(nodes)
        title = f"Shut {ifname} on {change.device}"
    else:
        removed = [x for x in topo.links if change.device in (x.a.device, x.b.device)]
        a_nodes = set(nodes) - {change.device}
        title = f"Take {change.device} down (reboot / replace)"
    gone = {x.id for x in removed}
    a_links = [x for x in topo.links if x.id not in gone]
    b_nodes, b_links = set(nodes), list(topo.links)

    # Reachability to core, before vs after (only losses caused by this change count).
    cores = {n.id for n in topo.nodes if n.role == "core"}
    if not cores:
        unknowns.append("no core device known: reachability can't be judged")
    elif not cores & a_nodes:
        warnings.append("No core device remains: everything is unreachable.")
    if node.role == "core":
        warnings.append(f"{change.device} is a core device.")
    hops_before = _hops(b_nodes, b_links, cores)
    reach_before = set(hops_before)
    reach_after = _reach(a_nodes, a_links, cores)
    affected: list[Affected] = []
    down = [node] if change.kind == "device_down" else []
    for n in down + [nodes[x] for x in sorted((reach_before & a_nodes) - reach_after)]:
        if n in down:
            detail, status = "taken down by this change", "warning"
        else:
            detail, status = "loses connectivity to core", "critical"
        affected.append(Affected(kind="node", id=n.id, label=n.id, detail=detail, status=status))
        if n.endpoints:
            label = f"{n.endpoints} hosts behind {n.id}"
            detail = "lose connectivity to core"
            affected.append(
                Affected(kind="endpoints", id=n.id, label=label, detail=detail, status="critical")
            )
        for svc in n.services:
            affected.append(
                Affected(
                    kind="service",
                    id=f"{svc}@{n.id}",
                    label=f"{svc} on {n.id}",
                    detail="service unreachable",
                    status="critical",
                )
            )

    # Reroute: the removed link's load moves from its end farther from core (before the change;
    # tie -> b) along the shortest remaining path to the nearest core.
    # ponytail: traffic assumed to head to core; real flow destinations need NetFlow
    extra: dict[str, float] = {}  # known load added per link
    partly_unknown: set[str] = set()  # links that also got load we can't size
    final: dict[str, LinkLoad] = {}
    reroutes: list[Reroute] = []
    far = float("inf")
    for link in removed:
        if change.kind == "device_down":
            src = link.b.device if link.a.device == change.device else link.a.device
        else:
            a_hops, b_hops = (hops_before.get(e.device, far) for e in (link.a, link.b))
            src = link.a.device if a_hops > b_hops else link.b.device
        if src not in reach_after or src in cores:
            continue
        via = _path(a_nodes, a_links, src, cores)
        load = None
        if link.util_pct is None or not link.capacity_mbps:
            unknowns.append(f"utilization of {link.id} ({_label(link)}) not polled")
        else:
            load = round(link.util_pct / 100 * link.capacity_mbps, 1)
        after = []
        for lid in via:
            alt = by_id[lid]
            util_after = None
            if alt.util_pct is None or not alt.capacity_mbps:
                unknowns.append(f"utilization of {lid} ({_label(alt)}) not polled")
                partly_unknown.add(lid)
            else:
                if load is None:
                    partly_unknown.add(lid)
                else:
                    extra[lid] = extra.get(lid, 0.0) + load
                util_after = round(alt.util_pct + extra.get(lid, 0.0) / alt.capacity_mbps * 100, 1)
            final[lid] = LinkLoad(
                link=lid, label=_label(alt), util_before=alt.util_pct, util_after=util_after
            )
            after.append(final[lid])
        reroutes.append(Reroute(link=link.id, via=via, load_mbps=load, after=after))

    over_warn = over_100 = 0
    for la in final.values():  # known load only grows, so the last value per link is the total
        unsure = la.link in partly_unknown
        status = graph.util_status(
            None if la.util_after is None else la.util_after / 100, util_warn
        )
        if status in ("warning", "critical"):
            detail = f"{la.util_before}% → {la.util_after}% after reroute"
            detail += " plus load of unknown size" if unsure else ""
            over_warn += 1
            over_100 += status == "critical"
        elif unsure:
            status, detail = "neutral", "utilization after reroute unknown"
        else:
            continue
        affected.append(
            Affected(kind="link", id=la.link, label=la.label, detail=detail, status=status)
        )
    for lid in sorted(partly_unknown):
        unknowns.append(f"load moved onto {lid} is partly unknown")

    new_spofs = _new_spofs((b_nodes, b_links), (a_nodes, a_links), cores, by_id)

    # Quietest hour over every link this change touches.
    touched = [by_id[x] for x in dict.fromkeys([*gone, *final])]
    window_links = [x for x in touched if x.hourly_util_pct]
    unknowns += [f"no traffic history for {x.id}" for x in touched if not x.hourly_util_pct]
    window = None
    if window_links:
        means = [
            sum(x.hourly_util_pct[h] for x in window_links) / len(window_links) for h in range(24)
        ]
        h = means.index(min(means))
        window = Window(start_hour=h, end_hour=(h + 1) % 24, avg_util_pct=round(means[h], 1))
    else:
        unknowns.append("no hourly utilization history for the affected links")

    def has(kind: str) -> bool:
        return any(a.kind == kind and a.status == "critical" for a in affected)

    if has("node") or has("service") or over_100:
        risk = "high"
    elif has("endpoints") or over_warn or new_spofs or unknowns:
        risk = "medium"
    else:
        risk = "low"

    n_lost = sum(a.kind == "node" and a.status == "critical" for a in affected)
    hosts = sum(nodes[a.id].endpoints for a in affected if a.kind == "endpoints")
    summary = (
        f"{_n(n_lost, 'device')} and {_n(hosts, 'host')} cut off from core; "
        f"{_n(len(reroutes), 'link')} rerouted ({over_warn} at {util_warn * 100:g}% or more); "
        f"{_spof_text(new_spofs)}."
    )
    now = datetime.now(UTC)
    return Report(
        id=f"imp-{now:%Y%m%d}-{secrets.token_hex(3)}",
        created_at=now,
        source=topo.source,
        data_as_of=topo.as_of,
        change=change,
        title=title,
        risk=risk,
        summary=summary,
        affected=affected,
        reroutes=reroutes,
        new_spofs=new_spofs,
        maintenance_window=window,
        rollback=_rollback(change.device, ifname, node.vendor),
        warnings=warnings,
        unknowns=list(dict.fromkeys(unknowns)),
        data_used=[
            f"{topo.source} topology as of {topo.as_of.isoformat()}",
            f"{len(topo.nodes)} nodes, {len(topo.links)} links",
        ],
    )
