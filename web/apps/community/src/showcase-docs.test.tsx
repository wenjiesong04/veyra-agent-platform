import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShowcaseDocs } from "./showcase-docs";
import { CommunitySite } from "./site";

const originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo");
let documentTops: Record<string, number>;
let scrollPosition: number;
let headerHeight: number;
let sidebarHeight: number;
let scrollTargets: string[];
let resizeCallbacks: ResizeObserverCallback[];

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({ source: "docs-test" }, "", "/?lang=en#/docs");
  vi.stubGlobal("fetch", vi.fn());
  documentTops = { "get-started": 500, concepts: 1700, "first-agent": 2800, acceptance: 4100 };
  scrollPosition = 0;
  headerHeight = 72;
  sidebarHeight = 60;
  scrollTargets = [];
  resizeCallbacks = [];
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resizeCallbacks.push(callback); }
    observe = vi.fn();
    disconnect = vi.fn();
  });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const id = this.id.replace("showcase-docs-", "");
    const height = this.classList.contains("showcase-header") ? headerHeight : this.classList.contains("showcase-docs-sidebar") ? sidebarHeight : 800;
    const top = this.id in documentTops ? documentTops[this.id] + 20 - scrollPosition : id in documentTops ? documentTops[id] + 20 - scrollPosition : 20;
    return { x: 0, y: top, top, bottom: top + height, left: 0, right: 1280, width: 1280, height, toJSON: () => ({}) };
  });
  Object.defineProperties(HTMLElement.prototype, {
    scrollIntoView: { configurable: true, value: vi.fn(function (this: HTMLElement) {
      scrollTargets.push(this.id);
      const id = this.id.replace("showcase-docs-", "");
      const scroller = this.closest<HTMLElement>(".showcase");
      if (!(id in documentTops) || !scroller) return;
      const docs = this.closest<HTMLElement>(".showcase-docs");
      const offset = Number.parseFloat(docs?.style.getPropertyValue("--showcase-docs-scroll-offset") || "96");
      scroller.scrollTop = documentTops[id] - offset;
      fireEvent.scroll(scroller);
    }) },
    scrollTo: { configurable: true, value: vi.fn(function (this: HTMLElement, options: ScrollToOptions) {
      if (typeof options.top === "number" && this.classList.contains("showcase")) {
        this.scrollTop = options.top;
        fireEvent.scroll(this);
      }
    }) },
  });
});

afterEach(() => {
  expect(fetch).not.toHaveBeenCalled();
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScrollIntoView);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  if (originalScrollTo) Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
  window.history.replaceState(null, "", "/#home");
});

function configureScroller() {
  const scroller = document.querySelector<HTMLElement>(".showcase")!;
  Object.defineProperties(scroller, {
    clientHeight: { configurable: true, value: 800 },
    scrollHeight: { configurable: true, value: 5200 },
    scrollTop: { configurable: true, get: () => scrollPosition, set: (value: number) => { scrollPosition = value; } },
  });
  return scroller;
}

function selectedHref(language: "en" | "zh" = "en") {
  const nav = screen.getByRole("navigation", { name: language === "en" ? "Documentation contents" : "文档目录" });
  return within(nav).getByRole("link", { current: "location" }).getAttribute("href");
}

function renderDocs() {
  render(<div className="showcase"><header className="showcase-header" /><ShowcaseDocs locale="en" /></div>);
  return configureScroller();
}

describe("Documentation scroll navigation", () => {
  it.each([
    { locale: "en" as const, nav: "Documentation contents", first: "Prepare your local studio.", back: "Back to Veyra", label: "A practical guide", title: "Project documentation", intro: "Understand Veyra, then run your first Agent. Start with one complete task and keep the way you want the work done." },
    { locale: "zh" as const, nav: "文档目录", first: "先准备本地工作室。", back: "返回产品首页", label: "使用指南", title: "项目文档", intro: "从理解 Veyra，到运行你的第一个 Agent。先走通一个小任务，再把自己的工作方法留下来。" },
  ])("starts directly with the contents and first chapter in $locale", ({ locale, nav, first, back, label, title, intro }) => {
    render(<ShowcaseDocs locale={locale} />);
    expect(screen.getByRole("navigation", { name: nav })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: first })).toBeInTheDocument();
    expect(screen.getAllByRole("heading")[0]).toHaveTextContent(first);
    expect(screen.queryByRole("link", { name: back })).not.toBeInTheDocument();
    expect(screen.queryByText(label)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: title })).not.toBeInTheDocument();
    expect(screen.queryByText(intro)).not.toBeInTheDocument();
  });

  it("highlights the section being read without changing the document route or history", async () => {
    const scroller = renderDocs();
    const push = vi.spyOn(window.history, "pushState");
    const replace = vi.spyOn(window.history, "replaceState");
    fireEvent.scroll(scroller);
    await waitFor(() => expect(selectedHref()).toBe("#/docs/get-started"));
    scroller.scrollTop = 1700;
    fireEvent.scroll(scroller);
    await waitFor(() => expect(selectedHref()).toBe("#/docs/concepts"));
    scroller.scrollTop = 4100;
    fireEvent.scroll(scroller);
    await waitFor(() => expect(selectedHref()).toBe("#/docs/acceptance"));
    expect(window.location.hash).toBe("#/docs");
    expect(window.location.search).toBe("?lang=en");
    expect(window.history.state).toEqual({ source: "docs-test" });
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("selects the last section at the page bottom even when its heading cannot reach the sticky offset", async () => {
    const scroller = renderDocs();
    documentTops.acceptance = 4900;
    scroller.scrollTop = 4400;
    fireEvent.scroll(scroller);
    await waitFor(() => expect(selectedHref()).toBe("#/docs/acceptance"));
  });

  it("recalculates the reading offset when a compact sticky directory or its height changes", async () => {
    const scroller = renderDocs();
    scroller.scrollTop = 1580;
    fireEvent.scroll(scroller);
    await waitFor(() => expect(selectedHref()).toBe("#/docs/get-started"));
    const docs = document.querySelector<HTMLElement>(".showcase-docs")!;
    headerHeight = 64;
    docs.style.setProperty("--showcase-docs-inline-nav", "1");
    fireEvent.resize(window);
    await waitFor(() => expect(docs.style.getPropertyValue("--showcase-docs-scroll-offset")).toBe("148px"));
    expect(selectedHref()).toBe("#/docs/concepts");
    sidebarHeight = 80;
    act(() => { resizeCallbacks[0]([], {} as ResizeObserver); });
    await waitFor(() => expect(docs.style.getPropertyValue("--showcase-docs-scroll-offset")).toBe("168px"));
  });

  it("keeps deep links, directory clicks, hash history transitions, and language changes positioned", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/?lang=en#/docs/concepts");
    render(<CommunitySite />);
    configureScroller();
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-concepts"));
    await waitFor(() => expect(selectedHref()).toBe("#/docs/concepts"));
    await user.click(within(screen.getByRole("navigation", { name: "Documentation contents" })).getByRole("link", { name: /Your first task/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/docs/first-agent"));
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-first-agent"));
    await waitFor(() => expect(selectedHref()).toBe("#/docs/first-agent"));

    function historyHash(hash: string) {
      const oldURL = window.location.href;
      const url = new URL(oldURL);
      url.hash = hash;
      window.history.replaceState(window.history.state, "", url);
      fireEvent(window, new HashChangeEvent("hashchange", { oldURL, newURL: url.href }));
    }
    historyHash("#/docs/concepts");
    await waitFor(() => expect(selectedHref()).toBe("#/docs/concepts"));
    historyHash("#/docs/first-agent");
    await waitFor(() => expect(selectedHref()).toBe("#/docs/first-agent"));
    scrollTargets.length = 0;
    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-first-agent"));
    expect(selectedHref("zh")).toBe("#/docs/first-agent");
  });
});
