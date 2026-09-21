import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { BuilderWorkspaceDock } from "./BuilderWorkspaceDock";

afterEach(() => cleanup());

describe("BuilderWorkspaceDock", () => {
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
