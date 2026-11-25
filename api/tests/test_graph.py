from app.core import graph

# a - b - c, plus a slow shortcut a - c, and d on its own
EDGES = [("a", "b", "ab"), ("b", "c", "bc"), ("a", "c", "ac"), ("x", "y", "outside")]
ADJ = graph.adjacency({"a", "b", "c", "d"}, EDGES)


def test_adjacency_keeps_only_edges_inside_the_node_set():
    assert ADJ == {
        "a": [("b", "ab"), ("c", "ac")],
        "b": [("a", "ab"), ("c", "bc")],
        "c": [("b", "bc"), ("a", "ac")],
        "d": [],
    }


def test_hops_and_components():
    assert graph.hops(ADJ, {"a", "missing"}) == {"a": 0, "b": 1, "c": 1}
    assert graph.components(ADJ) == [{"a", "b", "c"}, {"d"}]


def test_shortest_path_by_hops_cost_and_filter():
    assert graph.shortest_path(ADJ, "a", "c") == (1, [("a", "c", "ac")])
    cost = {"ab": 1, "bc": 1, "ac": 10}.__getitem__
    assert graph.shortest_path(ADJ, "a", {"c"}, cost) == (2, [("a", "b", "ab"), ("b", "c", "bc")])
    assert graph.shortest_path(ADJ, "a", "c", allowed=lambda k: k != "ac")[0] == 2
    assert graph.shortest_path(ADJ, "a", "a") == (0, [])
    assert graph.shortest_path(ADJ, "a", "d") is None


def test_one_link_load_rule():
    assert [graph.util_status(u, 0.8) for u in (None, 0.5, 0.8, 0.99, 1.0, 1.4)] == [
        "unknown",
        "ok",
        "warning",
        "warning",
        "critical",
        "critical",
    ]
