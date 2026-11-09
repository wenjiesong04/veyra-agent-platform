import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { BuilderWorkspaceDock } from "./BuilderWorkspaceDock";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function canvasContext(): CanvasRenderingContext2D {
  return {
    setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(),
    fill: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(),
  } as unknown as CanvasRenderingContext2D;
}

describe("BuilderWorkspaceDock", () => {
  it("stops animation frames when a running workbench becomes static", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext());
    const schedule = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(7);
    const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const dock = (live: boolean) => (
      <ThemeProvider storageKey="builder-dock-animation">
        <BuilderWorkspaceDock locale="en" live={live} tab="workbench" onTabChange={() => undefined} expanded={false} onToggleExpand={() => undefined} onClose={() => undefined} workbench={<p>Plan</p>} test={null} />
      </ThemeProvider>
    );
    const { rerender } = render(dock(true));
    expect(schedule).toHaveBeenCalledTimes(1);
    schedule.mockClear();
    rerender(dock(false));
    expect(cancel).toHaveBeenCalledWith(7);
    expect(schedule).not.toHaveBeenCalled();
    expect(document.querySelector(".builder-workspace-dock")).not.toHaveClass("is-live");
  });

  it("renders a static workbench when the system requests reduced motion", () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    const context = canvasContext();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
    const schedule = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(7);
    render(
      <ThemeProvider storageKey="builder-dock-reduced-motion">
        <BuilderWorkspaceDock locale="en" live tab="workbench" onTabChange={() => undefined} expanded={false} onToggleExpand={() => undefined} onClose={() => undefined} workbench={<p>Plan</p>} test={null} />
      </ThemeProvider>,
    );
    expect(context.clearRect).toHaveBeenCalled();
    expect(schedule).not.toHaveBeenCalled();
  });

  it("switches Workbench and Test pages without mounting Test until selected", () => {
    const { rerender } = render(
      <ThemeProvider storageKey="builder-dock-test">
        <BuilderWorkspaceDock
          locale="en"
          live
          tab="workbench"
          onTabChange={() => undefined}
          expanded={false}
          onToggleExpand={() => undefined}
          onClose={() => undefined}
          workbench={<p>Assembly body</p>}
          test={<p>Test body</p>}
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Test" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("Assembly body")).toBeInTheDocument();
    expect(screen.queryByText("Test body")).not.toBeInTheDocument();
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Full screen" })).toBeInTheDocument();
    expect(document.querySelector(".builder-workspace-head-spacer")).not.toBeInTheDocument();
    expect(document.querySelector(".builder-live-field")).toBeInTheDocument();
    expect(document.querySelector(".builder-workspace-dock")?.firstElementChild).toHaveClass("builder-workspace-head");
    expect(document.querySelector(".builder-workspace-head .builder-workspace-tabs")).toBeInTheDocument();

    rerender(
      <ThemeProvider storageKey="builder-dock-test">
        <BuilderWorkspaceDock
          locale="en"
          live={false}
          tab="test"
          onTabChange={() => undefined}
          expanded
          onToggleExpand={() => undefined}
          onClose={() => undefined}
          workbench={<p>Assembly body</p>}
          test={<p>Test body</p>}
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("tab", { name: "Test" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Test body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exit full screen" })).toBeInTheDocument();
    expect(document.querySelector(".builder-workspace-dock")).toHaveClass("is-expanded");
  });

  it("asks the parent to fill and restore the chat page from the in-flow chrome", () => {
    const onToggleExpand = vi.fn();
    const onClose = vi.fn();
    render(
      <ThemeProvider storageKey="builder-dock-test">
        <BuilderWorkspaceDock
          locale="zh"
          live={false}
          tab="workbench"
          onTabChange={() => undefined}
          expanded={false}
          onToggleExpand={onToggleExpand}
          onClose={onClose}
          workbench={<p>工作台内容</p>}
          test={null}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "全屏" }));
    expect(onToggleExpand).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "关闭工作台" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("notifies the parent when a tab is clicked", () => {
    const onTabChange = vi.fn();
    render(
      <ThemeProvider storageKey="builder-dock-test">
        <BuilderWorkspaceDock
          locale="zh"
          live={false}
          tab="workbench"
          onTabChange={onTabChange}
          expanded={false}
          onToggleExpand={() => undefined}
          onClose={() => undefined}
          workbench={<p>工作台内容</p>}
          test={null}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("tab", { name: "测试" }));
    expect(onTabChange).toHaveBeenCalledWith("test");
  });
});
