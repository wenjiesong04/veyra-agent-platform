import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PaneResizeHandle } from "@veyra/ui";
import { CanvasEditToolbar } from "./canvas-tools";
import { STUDIO_CANVAS_TOOLS_SLOT_ID } from "./studio-run-dock";
import { clampStudioPane, crowdCompactStudioChrome, exclusiveStudioPatch, fluidRunHeight, readStudioChrome, studioStageStyle, STUDIO_CHROME_STORAGE_KEY, STUDIO_PANE_LIMITS } from "./studio-chrome";

const studioCss = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "studio.css"), "utf8");

afterEach(() => {
  cleanup();
  window.localStorage.removeItem(STUDIO_CHROME_STORAGE_KEY);
  document.getElementById(STUDIO_CANVAS_TOOLS_SLOT_ID)?.remove();
});

describe("studio canvas overlay layout", () => {
  it("pins the run dock in the canvas well without covering or being covered", () => {
    expect(studioCss).not.toMatch(/inspector-collapsed\)\) \.react-flow__minimap/);
    expect(studioCss).not.toMatch(/:has\(\.studio-layout\.inspector-collapsed\) \.studio-run-dock/);
    expect(studioCss).not.toMatch(/:has\(\.studio-layout\.palette-collapsed\) \.studio-run-dock/);
    expect(studioCss).toMatch(/--studio-run-height:\s*clamp\(12\.5rem,\s*28%,\s*18rem\)/);
    expect(studioCss).toMatch(/--studio-run-max-width:\s*min\(40rem,\s*100%\)/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.canvas-panel \{[\s\S]*?inset: 0;/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-dock \{[\s\S]*?right: calc\(var\(--studio-overlay-inset\) \+ var\(--studio-inspector-width\) \+ var\(--studio-run-gap\)\);/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-dock \{[\s\S]*?left: calc\(var\(--studio-overlay-inset\) \+ var\(--studio-rail-width\) \+ var\(--studio-run-gap\)\);/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-dock \{[\s\S]*?pointer-events: none;/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-rail \{[\s\S]*?bottom: var\(--studio-overlay-inset\);/);
    expect(studioCss).not.toMatch(/\.studio-stage\.is-canvas \.inspector-panel \{[^}]*--studio-bottom-reserve/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-panel \{[\s\S]*?max-width: var\(--studio-run-max-width\);/);
  });

  it("keeps compact canvas chrome from stacking every overlay at once", () => {
    expect(studioCss).toMatch(/@media \(max-width: 960px\) \{[\s\S]*?--studio-sheet-width:/);
    expect(studioCss).toMatch(/@media \(max-width: 960px\) \{[\s\S]*?\.studio-stage\.is-canvas \.studio-run-dock \{[\s\S]*?left: calc\(var\(--studio-overlay-inset\) \+ var\(--studio-rail-collapsed\) \+ var\(--studio-run-gap\)\);/);
    expect(studioCss).toMatch(/@media \(max-width: 960px\) \{[\s\S]*?:has\(\.studio-layout:not\(\.inspector-collapsed\)\) \.studio-run-dock/);
    expect(studioCss).toMatch(/@media \(max-width: 960px\) \{[\s\S]*?\.pane-resize-handle \{[\s\S]*?display: none;/);
    expect(studioCss).not.toMatch(/@media \(max-width: 540px\) \{[\s\S]*?flex-direction: column;/);
    expect(studioCss).toMatch(/\.studio-body > \.studio-notice \{[\s\S]*?z-index: 12;/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-dock:has\(\.canvas-edit-toolbar\):not\(:has\(\.studio-run-panel\.is-collapsed\)\) \.studio-run-shelf \{[\s\S]*?z-index: 4;/);
    expect(studioCss).not.toMatch(/margin-top: -10px;/);
  });

  it("keeps the inspector and run dock above the canvas as separate overlays", () => {
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.canvas-panel \{[\s\S]*?z-index: 1;/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-rail \{[\s\S]*?z-index: 8;/);
    expect(studioCss).toMatch(/\.studio-stage\.is-canvas \.studio-run-dock \{[\s\S]*?z-index: 8;/);
    expect(studioCss).toMatch(/\.inspector-fields input,[\s\S]*?\.inspector-fields select,[\s\S]*?min-width: 0;/);
  });
});

describe("canvas edit toolbar", () => {
  it("does not offer a duplicate action", () => {
    const slot = document.createElement("div");
    slot.id = STUDIO_CANVAS_TOOLS_SLOT_ID;
    document.body.appendChild(slot);
    const noop = () => undefined;
    render(
      <CanvasEditToolbar
        locale="zh"
        canUndo={false}
        canRedo={false}
        canCopy
        canPaste={false}
        canDelete={false}
        boxSelect={false}
        onUndo={noop}
        onRedo={noop}
        onCopy={noop}
        onPaste={noop}
        onDelete={noop}
        onToggleBoxSelect={noop}
      />,
    );
    expect(screen.queryByRole("button", { name: "复制一份" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "粘贴" })).toBeInTheDocument();
  });
});

describe("studio chrome pane sizes", () => {
  it("clamps palette and run sizes into the stored range", () => {
    expect(clampStudioPane("paletteWidth", 10)).toBe(STUDIO_PANE_LIMITS.paletteWidth.min);
    expect(clampStudioPane("paletteWidth", 999)).toBe(STUDIO_PANE_LIMITS.paletteWidth.max);
    expect(clampStudioPane("runHeight", 10, 800)).toBe(STUDIO_PANE_LIMITS.runHeight.min);
    expect(clampStudioPane("runHeight", 999, 800)).toBe(400);
    expect(fluidRunHeight(800)).toBe(224);
  });

  it("leaves run height to CSS until the user resizes it", () => {
    const fluid = studioStageStyle({
      paletteCollapsed: false,
      inspectorCollapsed: false,
      runCollapsed: false,
      paletteWidth: 228,
      inspectorWidth: 300,
      runHeight: 0,
    });
    expect(fluid).not.toHaveProperty("--studio-run-height");
    expect(fluid["--studio-rail-width"]).toBe("228px");
    expect(studioStageStyle({
      paletteCollapsed: false,
      inspectorCollapsed: false,
      runCollapsed: false,
      paletteWidth: 228,
      inspectorWidth: 300,
      runHeight: 210,
    })["--studio-run-height"]).toBe("210px");
    expect(studioStageStyle({
      paletteCollapsed: true,
      inspectorCollapsed: true,
      runCollapsed: true,
      paletteWidth: 228,
      inspectorWidth: 300,
      runHeight: 0,
    }, true)).not.toHaveProperty("--studio-rail-width");
  });

  it("opens only one compact overlay at a time and crowds both rails closed", () => {
    expect(exclusiveStudioPatch({ inspectorCollapsed: false }, true)).toMatchObject({
      inspectorCollapsed: false,
      paletteCollapsed: true,
      runCollapsed: true,
    });
    expect(exclusiveStudioPatch({ paletteCollapsed: false }, true)).toMatchObject({
      paletteCollapsed: false,
      inspectorCollapsed: true,
      runCollapsed: true,
    });
    expect(exclusiveStudioPatch({ runCollapsed: false }, true)).toMatchObject({
      runCollapsed: false,
      inspectorCollapsed: true,
      paletteCollapsed: true,
    });
    expect(exclusiveStudioPatch({ inspectorCollapsed: false }, false)).toEqual({ inspectorCollapsed: false });
    expect(crowdCompactStudioChrome({
      paletteCollapsed: false,
      inspectorCollapsed: false,
      runCollapsed: false,
      paletteWidth: 228,
      inspectorWidth: 300,
      runHeight: 0,
    }, true)).toMatchObject({
      paletteCollapsed: true,
      inspectorCollapsed: true,
      runCollapsed: true,
    });
    expect(crowdCompactStudioChrome({
      paletteCollapsed: true,
      inspectorCollapsed: false,
      runCollapsed: true,
      paletteWidth: 228,
      inspectorWidth: 300,
      runHeight: 0,
    }, true).inspectorCollapsed).toBe(false);
  });

  it("ignores stored pane sizes so a refresh returns to the defaults", () => {
    window.localStorage.setItem(STUDIO_CHROME_STORAGE_KEY, JSON.stringify({
      paletteCollapsed: true,
      inspectorCollapsed: false,
      runCollapsed: false,
      paletteWidth: 300,
      inspectorWidth: 240,
      runHeight: 200,
    }));
    expect(readStudioChrome()).toMatchObject({
      paletteCollapsed: true,
      paletteWidth: STUDIO_PANE_LIMITS.paletteWidth.default,
      inspectorWidth: STUDIO_PANE_LIMITS.inspectorWidth.default,
      runHeight: STUDIO_PANE_LIMITS.runHeight.default,
    });
    window.localStorage.setItem(STUDIO_CHROME_STORAGE_KEY, "{not-json");
    expect(readStudioChrome()).toMatchObject({
      paletteCollapsed: false,
      paletteWidth: STUDIO_PANE_LIMITS.paletteWidth.default,
    });
  });
});

describe("PaneResizeHandle", () => {
  it("updates the value from arrow keys", () => {
    const onChange = vi.fn();
    render(
      <div style={{ position: "relative", height: 80 }}>
        <PaneResizeHandle label="Resize catalog" edge="right" value={228} min={180} max={420} onChange={onChange} />
      </div>,
    );
    const handle = screen.getByRole("separator", { name: "Resize catalog" });
    expect(handle).toHaveAttribute("aria-valuenow", "228");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith(236);
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith(220);
    fireEvent.keyDown(handle, { key: "Home" });
    expect(onChange).toHaveBeenCalledWith(180);
  });
});
