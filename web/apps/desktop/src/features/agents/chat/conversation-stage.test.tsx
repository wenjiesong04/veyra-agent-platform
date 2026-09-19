import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import { CONVERSATION_CANVAS_STORAGE_KEY } from "./conversation-canvas-layout";
import { ConversationStage } from "./conversation-stage";

const observers: ResizeObserverCallback[] = [];

class FakeResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    observers.push(callback);
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

function renderStage() {
  return render(
    <ThemeProvider storageKey="conversation-canvas-test">
      <ConversationStage
        empty={false}
        canvasOpen
        canvas={<aside className="agent-convo-canvas" aria-label="Assembly canvas">Blueprint</aside>}
      >
        <p>Hello</p>
      </ConversationStage>
    </ThemeProvider>,
  );
}

function setStageSize(width: number, height: number) {
  const stage = document.querySelector(".agent-conversation") as HTMLElement;
  Object.defineProperty(stage, "clientWidth", { configurable: true, get: () => width });
  Object.defineProperty(stage, "clientHeight", { configurable: true, get: () => height });
  act(() => {
    observers.forEach((callback) => callback([] as unknown as ResizeObserverEntry[], {} as ResizeObserver));
  });
}

beforeEach(() => {
  observers.length = 0;
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  window.localStorage.removeItem(CONVERSATION_CANVAS_STORAGE_KEY);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.removeItem(CONVERSATION_CANVAS_STORAGE_KEY);
});

describe("ConversationStage canvas chrome", () => {
  it("shows a side panel with a width handle and collapse control", () => {
    renderStage();
    setStageSize(1100, 800);
    const stage = document.querySelector(".agent-conversation") as HTMLElement;
    expect(stage).toHaveAttribute("data-canvas-layout", "split");
    expect(screen.getByRole("separator", { name: "Resize canvas" })).toHaveAttribute("aria-valuenow", "520");
    expect(screen.getByLabelText("Assembly canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse canvas" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "Collapse canvas" }));
    expect(stage).toHaveAttribute("data-canvas-collapsed", "true");
    expect(screen.getByRole("button", { name: "Expand canvas" })).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector(".agent-convo-canvas-slot")).toHaveClass("is-collapsed");
    expect(document.querySelector(".agent-convo-canvas-slot-body")).toHaveAttribute("hidden");
    fireEvent.click(screen.getByRole("button", { name: "Expand canvas" }));
    expect(document.querySelector(".agent-convo-canvas-slot-body")).not.toHaveAttribute("hidden");
    expect(screen.getByLabelText("Assembly canvas")).toBeInTheDocument();
  });

  it("widens the panel with arrow keys and remembers the width", () => {
    renderStage();
    setStageSize(1100, 800);
    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize canvas" }), { key: "ArrowLeft" });
    expect(screen.getByRole("separator", { name: "Resize canvas" })).toHaveAttribute("aria-valuenow", "528");
    expect(JSON.parse(window.localStorage.getItem(CONVERSATION_CANVAS_STORAGE_KEY) ?? "{}")).toMatchObject({ width: 528 });
  });

  it("uses a height handle when the conversation column is narrow", () => {
    renderStage();
    setStageSize(640, 720);
    const stage = document.querySelector(".agent-conversation") as HTMLElement;
    expect(stage).toHaveAttribute("data-canvas-layout", "stack");
    expect(screen.getByRole("separator", { name: "Resize canvas height" })).toBeInTheDocument();
    expect(screen.queryByRole("separator", { name: "Resize canvas" })).not.toBeInTheDocument();
  });
});
