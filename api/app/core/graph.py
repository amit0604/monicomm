"""Network graph helpers shared by the Analyzer (planned change) and the Investigator (failure).

Pure, no I/O. A graph is an adjacency map: node -> [(neighbor, edge key)], where the edge key is
whatever the caller uses to name a link (a link id, an edge index).
"""

import heapq
from collections import deque
from collections.abc import Callable, Hashable, Iterable

Adjacency = dict[str, list[tuple[str, Hashable]]]
Step = tuple[str, str, Hashable]  # (from node, to node, edge key)


def adjacency(nodes: Iterable[str], edges: Iterable[tuple[str, str, Hashable]]) -> Adjacency:
    """Undirected graph of `nodes`; an edge (a, b, key) counts only if both ends are in `nodes`."""
    adj: Adjacency = {n: [] for n in nodes}
    for a, b, key in edges:
        if a in adj and b in adj:
            adj[a].append((b, key))
            adj[b].append((a, key))
    return adj


def hops(adj: Adjacency, sources: Iterable[str]) -> dict[str, int]:
    """Hop distance to the nearest source, for every node that can reach one."""
    dist = {s: 0 for s in sources if s in adj}
    queue = deque(dist)
    while queue:
        cur = queue.popleft()
        for nxt, _ in adj[cur]:
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)
    return dist


def shortest_path(
    adj: Adjacency,
    src: str,
    targets: str | set[str],
    cost: Callable[[Hashable], int] = lambda _: 1,
    allowed: Callable[[Hashable], bool] = lambda _: True,
) -> tuple[int, list[Step]] | None:
    """Cheapest path from `src` to the nearest target (Dijkstra; ties go to the lower node name).

    `cost` and `allowed` take an edge key. Default cost 1 = fewest hops. None = no path.
    """
    goal = {targets} if isinstance(targets, str) else targets
    heap: list[tuple[int, str, list[Step]]] = [(0, src, [])]
    done: set[str] = set()
    while heap:
        total, node, path = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node in goal:
            return total, path
        for nxt, key in adj.get(node, []):
            if nxt not in done and allowed(key):
                heapq.heappush(heap, (total + cost(key), nxt, [*path, (node, nxt, key)]))
    return None


def components(adj: Adjacency) -> list[set[str]]:
    """Connected pieces of the graph, in order of their lowest node name."""
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


def util_status(util: float | None, warn: float) -> str:
    """One rule for link load everywhere: `util` is a fraction (1.0 = full), `warn` the threshold.

    Unknown load is "unknown", never safe (PROJECT.md 2.3).
    """
    if util is None:
        return "unknown"
    return "critical" if util >= 1.0 else "warning" if util >= warn else "ok"
