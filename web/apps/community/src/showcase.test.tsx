import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShowcaseApp } from "./showcase";
import { CommunitySite } from "./site";

const homepageTitle = /Describe a task\.\s*Build your Agent\./;
const originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollTo");
let scrollTargets: string[];
let sectionPositions: Record<string, number>;

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/?preview=studio&lang=en#home");
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("matchMedia", vi.fn((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })));
  scrollTargets = [];
  sectionPositions = { demo: 600, product: 1200, safety: 2800, docs: 3500 };
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const top = sectionPositions[this.id] ?? 0;
    return { x: 0, y: top, top, right: 1280, bottom: top + 800, left: 0, width: 1280, height: 800, toJSON: () => ({}) };
  });
  Object.defineProperties(HTMLElement.prototype, {
    scrollIntoView: { configurable: true, value: vi.fn(function (this: HTMLElement) { scrollTargets.push(this.id); }) },
    scrollTo: { configurable: true, value: vi.fn() },
  });
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value: vi.fn(function (this: HTMLDialogElement) { this.open = true; }) },
    close: { configurable: true, value: vi.fn(function (this: HTMLDialogElement) { this.open = false; }) },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScrollIntoView);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  if (originalScrollTo) Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
  window.history.replaceState(null, "", "/#home");
});

describe("Veyra showcase experience", () => {
  it("uses the same redesigned homepage for normal and former preview URLs", async () => {
    window.history.replaceState({ navigation: "preserved" }, "", "/?preview=studio&lang=en&source=review#safety");
    const view = render(<CommunitySite />);
    expect(await screen.findByRole("heading", { level: 1, name: homepageTitle })).toBeInTheDocument();
    expect(screen.getByText("Veyra / AI studio")).toBeInTheDocument();
    expect(screen.queryByText("Website design preview")).not.toBeInTheDocument();
    expect(window.location.search).toBe("?lang=en&source=review");
    expect(window.location.hash).toBe("#safety");
    expect(window.history.state).toEqual({ navigation: "preserved" });
    view.unmount();
    window.history.replaceState(null, "", "/#home");
    render(<CommunitySite />);
    expect(screen.getByRole("heading", { level: 1, name: homepageTitle })).toBeInTheDocument();
    expect(screen.getByText("Veyra / AI studio")).toBeInTheDocument();
  });

  it("has real documentation links and no unsupported installer offer", async () => {
    render(<ShowcaseApp />);
    expect(await screen.findByRole("heading", { level: 1, name: homepageTitle })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Project documentation/ })).toHaveAttribute("href", "#/docs/get-started");
    expect(screen.getByRole("link", { name: /Project documentation/ })).not.toHaveAttribute("target");
    expect(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Docs" })).toHaveAttribute("href", "#/docs");
    expect(screen.getByRole("link", { name: /Desktop build guide/ })).toHaveAttribute("href", "https://github.com/wenjiesong04/veyra-agent-platform/blob/codex/agent-platform/docs/desktop_packaging.md");
    expect(screen.getByText(/Public installers have not passed release acceptance/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /download (?:app|installer|desktop)/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download gift packaging video" })).toHaveAttribute("href", "/showcase/veyra-gift-tour.mp4");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("supports manual and keyboard scene selection without a model call", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    expect(screen.getByRole("tab", { name: "Brief" })).toHaveAttribute("aria-selected", "true");
    const edit = screen.getByRole("tab", { name: "Studio" });
    expect(edit).toHaveAttribute("aria-selected", "false");
    await user.click(edit);
    expect(edit).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Studio" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Brief" }));
    expect(screen.getByRole("tabpanel", { name: "Brief" })).toBeInTheDocument();
    await user.keyboard("{ArrowRight}{End}");
    expect(screen.getByRole("tab", { name: "Output" })).toHaveFocus();
    expect(screen.getByRole("tabpanel", { name: "Output" })).toBeInTheDocument();
    await user.keyboard("{Home}{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Output" })).toHaveAttribute("aria-selected", "true");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows the original brief and actual design candidate with their review boundaries", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    await user.click(screen.getByRole("tab", { name: "Brief" }));
    const brief = screen.getByRole("tabpanel", { name: "Brief" });
    expect(within(brief).getByText("Original brief · Translated excerpts")).toBeInTheDocument();
    expect(brief.querySelector("blockquote")).toHaveTextContent("Build a gift-packaging design Agent.");
    expect(brief.querySelector("blockquote")).toHaveTextContent(/recipient, occasion, budget, and preferred style/);
    expect(brief.querySelector("blockquote")).toHaveTextContent(/After confirmation, generate the packaging plan and visual/);
    for (const label of ["Inputs", "Deliverables", "Boundaries"]) expect(within(brief).getByText(label)).toBeInTheDocument();
    expect(within(brief).getByText("This case")).toBeInTheDocument();
    expect(within(brief).getByText("Christmas gifting")).toBeInTheDocument();
    expect(within(brief).getByText(/Ask about unknown dimensions/)).toBeInTheDocument();
    expect(within(brief).getByRole("img", { name: /Case input/ })).toHaveAttribute("src", "/showcase/gift-input.jpg");

    await user.click(screen.getByRole("tab", { name: "Output" }));
    const output = screen.getByRole("tabpanel", { name: "Output" });
    expect(within(output).getByRole("img", { name: /actual generated Christmas gift-box candidate/ })).toHaveAttribute("src", "/showcase/gift-output.jpg");
    expect(within(output).getByText("Christmas red, ivory, and gold")).toBeInTheDocument();
    expect(within(output).getByText("Pulp box, velvet ribbon, and divided insert")).toBeInTheDocument();
    const evidence = output.querySelector("details");
    expect(evidence).not.toHaveAttribute("open");
    await user.click(within(output).getByText("What has been verified?"));
    expect(evidence).toHaveAttribute("open");
    expect(within(output).getByText(/Unverified means an artifact exists without an independent acceptance conclusion/)).toBeVisible();
    expect(within(output).getByText(/while the parent Workflow failed/)).toBeVisible();
    await user.click(within(output).getByRole("button", { name: "View the original run screen" }));
    expect(within(screen.getByRole("dialog", { name: "Enlarge product image" })).getByRole("img")).toHaveAttribute("src", "/showcase/gift-runtime.png");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps approval local, allows rejection and restarts the example", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("status")).toHaveTextContent("Rejected. Example stopped.");
    expect(screen.getByRole("button", { name: "Start again" })).toHaveFocus();
    expect(screen.getByText(/This example has not written a file/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start again" }));
    expect(screen.getByRole("button", { name: "Approve" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("status")).toHaveTextContent("Example action approved");
    expect(screen.getByRole("button", { name: "Start again" })).toHaveFocus();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("opens a native image dialog and closes it explicitly", async () => {
    const user = userEvent.setup();
    render(<ShowcaseApp />);
    await user.click(screen.getAllByRole("button", { name: "Enlarge product image" })[0]);
    const dialog = screen.getByRole("dialog", { name: "Enlarge product image" });
    expect(within(dialog).getByRole("img")).toHaveAttribute("src", "/showcase/gift-input.jpg");
    await user.click(within(dialog).getByRole("button", { name: "Close product image" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("supports Chinese, theme and mobile menu without affecting APIs", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/?preview=studio&lang=zh#home");
    render(<ShowcaseApp />);
    expect(await screen.findByText("Veyra / AI 工作室")).toBeInTheDocument();
    await user.click(screen.getByLabelText("打开导航"));
    expect(screen.getByLabelText("关闭导航")).toHaveAttribute("aria-expanded", "true");
    await user.click(within(screen.getByRole("navigation", { name: "主导航" })).getByRole("link", { name: "由你掌控" }));
    expect(screen.getByLabelText("打开导航")).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByLabelText("打开导航"));
    await user.keyboard("{Escape}");
    expect(screen.getByLabelText("打开导航")).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("button", { name: "切换到深色" }));
    await waitFor(() => expect(document.querySelector(".showcase")).toHaveAttribute("data-dark", "true"));
    await user.click(screen.getByRole("button", { name: "切换到英文" }));
    expect(await screen.findByText("Veyra / AI studio")).toBeInTheDocument();
    expect(new URLSearchParams(location.search).get("lang")).toBe("en");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses the existing shared language and theme preferences", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/#home");
    localStorage.setItem("veyra.language", "zh");
    localStorage.setItem("veyra.theme", "system");
    render(<ShowcaseApp />);
    expect(screen.getByText("Veyra / AI 工作室")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "切换到英文" }));
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(localStorage.getItem("veyra.language")).toBe("en");
    expect(localStorage.getItem("veyra.theme")).toBe("dark");
    expect(localStorage.getItem("veyra.showcase-preview.language")).toBeNull();
    expect(localStorage.getItem("veyra.showcase-preview.theme")).toBeNull();
  });

  it("keeps Community routing intact for former preview links", async () => {
    window.history.replaceState(null, "", "/?preview=studio#/community");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not_found" }), { status: 404, headers: { "Content-Type": "application/json" } })));
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(screen.queryByText("Website design preview")).not.toBeInTheDocument();
  });

  it("opens the built-in documentation without rewriting its deep link or calling an API", async () => {
    window.history.replaceState({ navigation: "retained" }, "", "/?preview=studio&lang=en&source=review#/docs/concepts");
    render(<CommunitySite />);
    expect(await screen.findByRole("heading", { level: 1, name: "Prepare your local studio." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Choose how the work should run." })).toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: homepageTitle })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/docs/concepts");
    expect(window.location.search).toBe("?lang=en&source=review");
    expect(window.history.state).toEqual({ navigation: "retained" });
    expect(document.title).toBe("Documentation · Veyra");
    expect(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Docs" })).toHaveAttribute("aria-current", "location");
    expect(within(screen.getByRole("navigation", { name: "Documentation contents" })).getByRole("link", { name: /Agents and Workflows/ })).toHaveAttribute("aria-current", "location");
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-concepts"));
    expect(fetch).not.toHaveBeenCalled();
  });

  it("navigates from the shared header into local docs and back to the homepage", async () => {
    const user = userEvent.setup();
    render(<CommunitySite />);
    await user.click(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Docs" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Prepare your local studio." })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/docs");
    await user.click(within(screen.getByRole("navigation", { name: "Documentation contents" })).getByRole("link", { name: /Agents and Workflows/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/docs/concepts"));
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-concepts"));
    await user.click(screen.getByRole("link", { name: "Veyra" }));
    expect(await screen.findByRole("heading", { level: 1, name: homepageTitle })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Prepare your local studio." })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#home");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("repositions repeated documentation anchors without changing their URL or history state", async () => {
    const user = userEvent.setup();
    const historyState = { navigation: "repeat-anchor" };
    window.history.replaceState(historyState, "", "/?lang=en&source=review#/docs/concepts");
    render(<CommunitySite />);
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-concepts"));
    scrollTargets.length = 0;

    await user.click(within(screen.getByRole("navigation", { name: "Documentation contents" })).getByRole("link", { name: /Agents and Workflows/ }));
    expect(scrollTargets).toContain("showcase-docs-concepts");
    expect(window.location.hash).toBe("#/docs/concepts");
    expect(window.location.search).toBe("?lang=en&source=review");
    expect(window.history.state).toEqual(historyState);

    const oldURL = window.location.href;
    window.history.replaceState(historyState, "", "/?lang=en&source=review#/docs");
    fireEvent(window, new HashChangeEvent("hashchange", { oldURL, newURL: window.location.href }));
    await waitFor(() => expect(HTMLElement.prototype.scrollTo).toHaveBeenCalled());
    vi.mocked(HTMLElement.prototype.scrollTo).mockClear();
    await user.click(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Docs" }));
    expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }));
    expect(window.location.hash).toBe("#/docs");
    expect(window.location.search).toBe("?lang=en&source=review");
    expect(window.history.state).toEqual(historyState);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("follows back and forward-style hashchange transitions between home and documentation sections", async () => {
    render(<CommunitySite />);
    function hashChange(hash: string) {
      const oldURL = window.location.href;
      window.history.replaceState(window.history.state, "", `/?lang=en${hash}`);
      fireEvent(window, new HashChangeEvent("hashchange", { oldURL, newURL: window.location.href }));
    }
    hashChange("#/docs");
    expect(screen.getByRole("heading", { level: 1, name: "Prepare your local studio." })).toBeInTheDocument();
    hashChange("#/docs/acceptance");
    expect(within(screen.getByRole("navigation", { name: "Documentation contents" })).getByRole("link", { name: /Results and acceptance/ })).toHaveAttribute("aria-current", "location");
    await waitFor(() => expect(scrollTargets).toContain("showcase-docs-acceptance"));
    hashChange("#/docs");
    expect(screen.getByRole("heading", { level: 1, name: "Prepare your local studio." })).toBeInTheDocument();
    hashChange("#home");
    expect(screen.getByRole("heading", { level: 1, name: homepageTitle })).toBeInTheDocument();
    hashChange("#/docs/acceptance");
    expect(screen.getByRole("heading", { level: 1, name: "Prepare your local studio." })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/docs/acceptance");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("tracks the current section without adding a reading progress bar", async () => {
    render(<ShowcaseApp />);
    const root = document.querySelector(".showcase") as HTMLElement;
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(screen.queryByRole("progressbar", { name: "Page reading progress" })).not.toBeInTheDocument();
    Object.defineProperties(root, {
      scrollHeight: { configurable: true, value: 4000 },
      clientHeight: { configurable: true, value: 800 },
      scrollTop: { configurable: true, writable: true, value: 800 },
    });
    sectionPositions = { demo: 100, product: 700, safety: 1400, docs: 2000 };
    fireEvent.scroll(root);
    await waitFor(() => expect(within(navigation).getByRole("link", { name: "Demo" })).toHaveAttribute("aria-current", "location"));
    expect(within(navigation).getByRole("link", { name: "Demo" })).toHaveAttribute("aria-current", "location");

    root.scrollTop = 1600;
    sectionPositions = { demo: -1000, product: 80, safety: 1100, docs: 1800 };
    fireEvent.scroll(root);
    await waitFor(() => expect(within(navigation).getByRole("link", { name: "Product" })).toHaveAttribute("aria-current", "location"));
    expect(within(navigation).getByRole("link", { name: "Product" })).toHaveAttribute("aria-current", "location");
    expect(within(navigation).getByRole("link", { name: "Demo" })).not.toHaveAttribute("aria-current");

    root.scrollTop = 2400;
    sectionPositions = { demo: -1500, product: -800, safety: -20, docs: 900 };
    fireEvent.scroll(root);
    await waitFor(() => expect(within(navigation).getByRole("link", { name: "Control" })).toHaveAttribute("aria-current", "location"));
    expect(within(navigation).getByRole("link", { name: "Control" })).toHaveAttribute("aria-current", "location");

    root.scrollTop = 3200;
    sectionPositions = { demo: -2000, product: -1600, safety: -900, docs: 100 };
    fireEvent.scroll(root);
    await waitFor(() => expect(within(navigation).getByRole("link", { name: "Docs" })).toHaveAttribute("aria-current", "location"));
    expect(within(navigation).getByRole("link", { name: "Docs" })).toHaveAttribute("aria-current", "location");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("restores page metadata when leaving the showcase", () => {
    document.title = "Veyra Community";
    document.documentElement.lang = "zh-CN";
    const view = render(<ShowcaseApp />);
    expect(document.title).toBe("Veyra · Your AI studio");
    view.unmount();
    expect(document.title).toBe("Veyra Community");
    expect(document.documentElement.lang).toBe("zh-CN");
  });
});
