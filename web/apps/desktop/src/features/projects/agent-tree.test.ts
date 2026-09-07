import { describe, expect, it } from "vitest";
import { agentAncestryPath, agentTree, layoutAgentGraph, parseProjectFileId, projectFileId } from "./agent-tree";

function agent(id: string, slug: string, parent?: string) {
  return {
    agent_id: id,
    slug,
    name: slug,
    source_path: `agents/${slug}/agent.vagent.yaml`,
    ...(parent ? { parent_agent_id: parent } : {}),
  };
}

describe("agentTree", () => {
  it("builds a recursive forest and treats a missing parent as a root", () => {
    const tree = agentTree([
      agent("child", "child", "parent"),
      agent("grand", "grand", "child"),
      agent("parent", "parent"),
      agent("orphan", "orphan", "missing"),
    ]);
    expect(tree.map((node) => node.slug)).toEqual(["orphan", "parent"]);
    expect(tree[1]?.children[0]?.slug).toBe("child");
    expect(tree[1]?.children[0]?.children[0]?.slug).toBe("grand");
  });

  it("keeps a pinned root first among siblings", () => {
    const tree = agentTree([
      { ...agent("alpha", "alpha"), pinned: false },
      { ...agent("zeta", "zeta"), pinned: true },
    ]);
    expect(tree.map((node) => node.slug)).toEqual(["zeta", "alpha"]);
  });
});

describe("agentAncestryPath", () => {
  it("returns root-to-target ancestry for nested agents", () => {
    const agents = [
      agent("parent", "parent"),
      agent("child", "child", "parent"),
      agent("grand", "grand", "child"),
    ];
    expect(agentAncestryPath(agents, "grand").map((item) => item.slug)).toEqual(["parent", "child", "grand"]);
    expect(agentAncestryPath(agents, "missing")).toEqual([]);
  });
});

describe("layoutAgentGraph", () => {
  it("places a parent above its children", () => {
    const layout = layoutAgentGraph([
      agent("parent", "parent"),
      agent("left", "left", "parent"),
      agent("right", "right", "parent"),
    ]);
    const parent = layout.nodes.find((node) => node.agent.slug === "parent");
    const left = layout.nodes.find((node) => node.agent.slug === "left");
    const right = layout.nodes.find((node) => node.agent.slug === "right");
    expect(parent?.y).toBe(0);
    expect(left?.y).toBeGreaterThan(parent?.y ?? 0);
    expect(right?.y).toBe(left?.y);
    expect(layout.edges).toHaveLength(2);
  });
});

describe("project file ids", () => {
  it("round-trips a Project-relative path", () => {
    const id = projectFileId("project-1", "agents/reviewer/agent.vagent.yaml");
    expect(parseProjectFileId(id)).toEqual({
      projectId: "project-1",
      path: "agents/reviewer/agent.vagent.yaml",
    });
  });
});
