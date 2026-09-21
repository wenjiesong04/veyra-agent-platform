import { describe, expect, it } from "vitest";
import { sortPinnedFirst, toggleSidebarResourcePin } from "./sidebar-pins";

describe("sidebar resource pins", () => {
  it("toggles an exclusive pin per kind and project", () => {
    const first = toggleSidebarResourcePin({}, "project-1", "workflow", "wf-a");
    expect(first).toEqual({ "project-1": { workflow: "wf-a" } });
    const moved = toggleSidebarResourcePin(first, "project-1", "workflow", "wf-b");
    expect(moved).toEqual({ "project-1": { workflow: "wf-b" } });
    const cleared = toggleSidebarResourcePin(moved, "project-1", "workflow", "wf-b");
    expect(cleared).toEqual({});
    const chat = toggleSidebarResourcePin({}, "project-1", "conversation", "conv-1");
    expect(chat).toEqual({ "project-1": { conversation: "conv-1" } });
  });

  it("keeps a pinned item first without reordering the rest", () => {
    const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
    expect(sortPinnedFirst(items, "c", (item) => item.id).map((item) => item.id)).toEqual(["c", "a", "b"]);
    expect(sortPinnedFirst(items, undefined, (item) => item.id).map((item) => item.id)).toEqual(["a", "b", "c"]);
  });
});
