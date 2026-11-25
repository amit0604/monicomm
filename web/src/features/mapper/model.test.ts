import { describe, expect, it } from "vitest";
import type { Topology } from "./api";
import { countBy, neighbors, roots, shortPort, visibleLinks } from "./model";
import { TOPOLOGY } from "./testData";

describe("mapper model", () => {
  it("shortens port names the way the CLI shows them", () => {
    expect(shortPort("GigabitEthernet1/0/1")).toBe("Gi1/0/1");
    expect(shortPort("TenGigabitEthernet1/1/1")).toBe("Te1/1/1");
    expect(shortPort("Dot11Radio1")).toBe("Radio1");
    expect(shortPort("ge-0/0/3")).toBe("ge-0/0/3");
    expect(shortPort("eth0")).toBe("eth0");
  });

  it("filters links by medium and status", () => {
    const all = new Set(["fiber", "copper", "wireless", "wan"] as const);
    expect(visibleLinks(TOPOLOGY, { mediums: all, status: "" })).toHaveLength(3);
    expect(
      visibleLinks(TOPOLOGY, { mediums: new Set(["copper"] as const), status: "" }).map(
        (l) => l.medium,
      ),
    ).toEqual(["copper"]);
    expect(visibleLinks(TOPOLOGY, { mediums: all, status: "down" }).map((l) => l.status)).toEqual([
      "down",
    ]);
  });

  it("lists a device's links from its own side", () => {
    const mine = neighbors(TOPOLOGY, "sw");
    expect(mine.map((n) => [n.port, n.other?.name, n.otherPort])).toEqual([
      ["GigabitEthernet1/0/1", "rtr-1", "ge-0/0/0"],
      ["GigabitEthernet1/0/2", "srv-1", "eth0"],
    ]);
    expect(neighbors(TOPOLOGY, "lonely")).toEqual([]);
  });

  it("roots the drawing at the routers and counts statuses", () => {
    expect(roots(TOPOLOGY)).toEqual(["rtr"]);
    expect(countBy(TOPOLOGY.links.map((l) => l.status))).toEqual({ up: 1, down: 1, degraded: 1 });
    expect(roots({ ...TOPOLOGY, nodes: [] } as Topology)).toEqual([]);
  });
});
