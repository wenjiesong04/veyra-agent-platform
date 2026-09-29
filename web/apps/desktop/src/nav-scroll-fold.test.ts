import { describe, expect, it } from "vitest";
import {
  emptyNavScrollFolds,
  planNavScrollFold,
  stickyOffsetsForSections,
  type NavScrollFoldInput,
} from "@veyra/ui";

function snapshot(
  section: "pinned" | "projects" | "recent",
  overrides: Partial<NavScrollFoldInput["sections"][number]> = {},
): NavScrollFoldInput["sections"][number] {
  const stickyTop = section === "pinned" ? 0 : section === "projects" ? 38 : 77;
  const headerHeight = section === "pinned" ? 38 : 39;
  return {
    section,
    stickyTop,
    headerHeight,
    bodyHeight: 200,
    bodyBottom: stickyTop + headerHeight + 200,
    ...overrides,
  };
}

const sectionsAtTop = [
  snapshot("pinned"),
  snapshot("projects", { bodyBottom: 477 }),
  snapshot("recent", { bodyHeight: 400, bodyBottom: 916 }),
];

function plan(overrides: Partial<NavScrollFoldInput> = {}) {
  return planNavScrollFold({
    scrollTop: 0,
    direction: "none",
    sections: sectionsAtTop,
    manualCollapsed: emptyNavScrollFolds(),
    autoCollapsed: emptyNavScrollFolds(),
    allowExpand: false,
    ...overrides,
  });
}

describe("planNavScrollFold", () => {
  it("only reserves sticky slots for section groups that are rendered", () => {
    expect(stickyOffsetsForSections(["pinned", "projects", "recent"])).toEqual({ pinned: 0, projects: 38, recent: 77 });
    expect(stickyOffsetsForSections(["projects", "recent"])).toEqual({ pinned: 0, projects: 0, recent: 39 });
    expect(stickyOffsetsForSections(["recent"])).toEqual({ pinned: 0, projects: 0, recent: 0 });
  });

  it("does not toggle at rest while every body is still in view", () => {
    expect(plan({ direction: "down", scrollTop: 8 })).toMatchObject({ action: null, section: null });
    expect(plan({ direction: "up", scrollTop: 0, allowExpand: true })).toMatchObject({ action: null, section: null });
  });

  it("collapses the upper section only after its body has crossed the sticky header plus threshold", () => {
    const pinnedCovered = [
      snapshot("pinned", { bodyBottom: 50, bodyHeight: 200 }),
      snapshot("projects", { bodyBottom: 277 }),
      snapshot("recent", { bodyHeight: 400, bodyBottom: 716 }),
    ];
    expect(plan({ direction: "down", scrollTop: 180, sections: pinnedCovered })).toMatchObject({
      action: "collapse",
      section: "pinned",
      autoCollapsed: { pinned: true, projects: false, recent: false },
    });

    const pinnedStillVisible = [
      snapshot("pinned", { bodyBottom: 51, bodyHeight: 200 }),
      snapshot("projects", { bodyBottom: 278 }),
      snapshot("recent", { bodyHeight: 400, bodyBottom: 717 }),
    ];
    expect(plan({ direction: "down", scrollTop: 180, sections: pinnedStillVisible }).action).toBeNull();
  });

  it("does not collapse the next section just because the previous header is already stacked", () => {
    const viewingProjects = [
      snapshot("pinned", { bodyBottom: 38, bodyHeight: 0 }),
      snapshot("projects", { bodyBottom: 277, bodyHeight: 200 }),
      snapshot("recent", { bodyHeight: 400, bodyBottom: 716 }),
    ];
    expect(
      plan({
        direction: "down",
        scrollTop: 12,
        sections: viewingProjects,
        autoCollapsed: { pinned: true, projects: false, recent: false },
      }),
    ).toMatchObject({ action: null, autoCollapsed: { pinned: true, projects: false, recent: false } });
  });

  it("collapses projects once their body has gone under the stacked headers", () => {
    const viewingRecent = [
      snapshot("pinned", { bodyBottom: 38, bodyHeight: 0 }),
      snapshot("projects", { bodyBottom: 88, bodyHeight: 200 }),
      snapshot("recent", { bodyHeight: 400, bodyBottom: 527 }),
    ];
    expect(
      plan({
        direction: "down",
        scrollTop: 240,
        sections: viewingRecent,
        autoCollapsed: { pinned: true, projects: false, recent: false },
      }),
    ).toMatchObject({
      action: "collapse",
      section: "projects",
      autoCollapsed: { pinned: true, projects: true, recent: false },
    });
  });

  it("never auto-collapses the last section", () => {
    const recentCovered = [
      snapshot("pinned", { bodyBottom: 38, bodyHeight: 0 }),
      snapshot("projects", { bodyBottom: 77, bodyHeight: 0 }),
      snapshot("recent", { bodyBottom: 90, bodyHeight: 400 }),
    ];
    expect(
      plan({
        direction: "down",
        scrollTop: 400,
        sections: recentCovered,
        autoCollapsed: { pinned: true, projects: true, recent: false },
      }),
    ).toMatchObject({ action: null, autoCollapsed: { pinned: true, projects: true, recent: false } });
  });

  it("expands the most recently folded section when scrolling up near the top", () => {
    expect(
      plan({
        direction: "up",
        scrollTop: 24,
        allowExpand: true,
        autoCollapsed: { pinned: true, projects: true, recent: false },
      }),
    ).toMatchObject({
      action: "expand",
      section: "projects",
      autoCollapsed: { pinned: true, projects: false, recent: false },
    });
  });

  it("does not expand on the same upward pass after the first section has already been opened", () => {
    expect(
      plan({
        direction: "up",
        scrollTop: 18,
        allowExpand: false,
        autoCollapsed: { pinned: true, projects: false, recent: false },
      }),
    ).toMatchObject({ action: null, autoCollapsed: { pinned: true, projects: false, recent: false } });
  });

  it("opens the remaining folded section when the user keeps scrolling up at the top", () => {
    expect(
      plan({
        direction: "up",
        scrollTop: 0,
        allowExpand: false,
        atTopWheelUp: true,
        autoCollapsed: { pinned: true, projects: false, recent: false },
      }),
    ).toMatchObject({
      action: "expand",
      section: "pinned",
      autoCollapsed: { pinned: false, projects: false, recent: false },
    });
  });

  it("ignores scroll-driven expand/collapse for a manually folded section", () => {
    const pinnedCovered = [
      snapshot("pinned", { bodyBottom: 20, bodyHeight: 200 }),
      snapshot("projects", { bodyBottom: 277 }),
      snapshot("recent", { bodyHeight: 400, bodyBottom: 716 }),
    ];
    expect(
      plan({
        direction: "down",
        scrollTop: 180,
        sections: pinnedCovered,
        manualCollapsed: { pinned: true, projects: false, recent: false },
      }),
    ).toMatchObject({ action: null });

    expect(
      plan({
        direction: "up",
        scrollTop: 0,
        allowExpand: true,
        atTopWheelUp: true,
        manualCollapsed: { pinned: true, projects: false, recent: false },
        autoCollapsed: { pinned: false, projects: false, recent: false },
      }),
    ).toMatchObject({ action: null, autoCollapsed: { pinned: false, projects: false, recent: false } });
  });
});
