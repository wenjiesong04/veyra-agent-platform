import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FolderKanban } from "lucide-react";
import { parseDesktopRoute, projectRoutePaths } from "@veyra/api-contracts";
import { ApplicationShell, ThemeProvider } from "@veyra/ui";
import { DesktopApp } from "./app";

function setViewport(isMobile: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({ matches: isMobile && query.includes("max-width"), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "#/projects";
  setViewport(false);
});

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("desktop workspace", () => {
  it("renders the Projects surface and complete top-level navigation", async () => {
    const user = userEvent.setup();
    render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Make work repeatable." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Components" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Files" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Monitor" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Factory" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Sign in or register" })).toHaveAttribute("href", "#/account");
    expect(screen.getByRole("menuitem", { name: "Settings" })).toHaveAttribute("href", "#/settings");
    expect(screen.queryByRole("menuitem", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("shows account controls and invokes sign out only for an authenticated account", async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();
    render(
      <ThemeProvider>
        <ApplicationShell
          brand={{ name: "Veyra", subtitle: "Agent Platform" }}
          navigation={[{ label: "Build", items: [{ href: "#/projects", label: "Projects", icon: FolderKanban }] }]}
          activeHref="#/projects"
          eyebrow="Workspace"
          title="Projects"
          account={{ displayName: "Ada", authenticated: true, accountHref: "#/account", settingsHref: "#/settings", onSignOut }}
        >
          <div>Workspace content</div>
        </ApplicationShell>
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Account" })).toHaveAttribute("href", "#/account");
    expect(screen.getByRole("menuitem", { name: "Settings" })).toHaveAttribute("href", "#/settings");
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
  });

  it("links the local guest account page to Community sign in", () => {
    window.location.hash = "#/account";
    render(<DesktopApp />);
    expect(screen.getByRole("link", { name: "Connect account" })).toHaveAttribute("href", "http://127.0.0.1:5174/#/login");
    expect(screen.getByText("Guest mode")).toBeInTheDocument();
  });

  it("uses Project-first links for project rows and Agent cards", () => {
    render(<DesktopApp />);
    expect(screen.getByRole("link", { name: /Signal Review/ })).toHaveAttribute("href", projectRoutePaths.project("signal-review"));
    expect(screen.getByRole("link", { name: /Review Companion/ })).toHaveAttribute("href", projectRoutePaths.agentDesign("signal-review", "reviewer"));
  });

  it("keeps the second Project Factory and header action inside its Project boundary", async () => {
    const user = userEvent.setup();
    window.location.hash = projectRoutePaths.factory("release-room");
    render(<DesktopApp />);
    expect(screen.getByRole("link", { name: "Create agent" })).toHaveAttribute("href", projectRoutePaths.factory("release-room"));
    await user.click(screen.getByRole("button", { name: "Generate draft" }));
    await waitFor(() => expect(screen.getByText("Release Check")).toBeInTheDocument());
    const openStudio = screen.getByRole("link", { name: "Open Studio" });
    expect(openStudio).toHaveAttribute("href", projectRoutePaths.agentDesign("release-room", "release-check"));
    await user.click(openStudio);
    expect(await screen.findByRole("heading", { name: "Release Check" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run" })).toHaveAttribute("href", projectRoutePaths.agentRun("release-room", "release-check"));
  });

  it("renders nested Project, Factory, Design, Run, list, detail, and version routes", () => {
    window.location.hash = projectRoutePaths.project("signal-review");
    const { unmount } = render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Signal Review" })).toBeInTheDocument();
    unmount();

    window.location.hash = projectRoutePaths.factory("signal-review");
    const factory = render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Give the Factory a job to shape." })).toBeInTheDocument();
    factory.unmount();

    window.location.hash = projectRoutePaths.agentDesign("signal-review", "reviewer");
    const design = render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Review Companion" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run" })).toHaveAttribute("href", projectRoutePaths.agentRun("signal-review", "reviewer"));
    design.unmount();

    window.location.hash = projectRoutePaths.agent("signal-review", "reviewer");
    const detail = render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Review Companion" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open version detail" })).toHaveAttribute("href", projectRoutePaths.agentVersion("signal-review", "reviewer", "v0.4"));
    detail.unmount();

    window.location.hash = projectRoutePaths.agentVersion("signal-review", "reviewer", "v0.4");
    const version = render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: /Review Companion v0.4/ })).toBeInTheDocument();
    version.unmount();

    window.location.hash = projectRoutePaths.agentRun("signal-review", "reviewer");
    render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Review Companion" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ready to run" })).toBeInTheDocument();
  });

  it("renders explicit NotFound for unknown and swallowed subpaths", () => {
    window.location.hash = "#/community/unknown/path";
    render(<DesktopApp />);
    expect(screen.getByText("That workspace route is not available.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Community" })).toBeInTheDocument();
  });

  it("persists light/dark/system theme choices", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("veyra.theme", "dark");
    window.location.hash = "#/settings";
    render(<DesktopApp />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    await user.click(screen.getByRole("button", { name: "System" }));
    await waitFor(() => expect(window.localStorage.getItem("veyra.theme")).toBe("system"));
    expect(document.documentElement.dataset.theme).toBe("system");
  });

  it("exposes collapsed navigation names and expanded state", async () => {
    const user = userEvent.setup();
    render(<DesktopApp />);
    const collapse = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    expect(collapse).toHaveAttribute("aria-controls", "primary-navigation");
    await user.click(collapse);
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("title", "Projects");
  });

  it("closes the mobile sidebar with Escape and restores focus", async () => {
    const user = userEvent.setup();
    setViewport(true);
    render(<DesktopApp />);
    const menu = screen.getByRole("button", { name: "Open navigation" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-controls", "primary-navigation");
    expect(screen.getByRole("complementary", { hidden: true })).toHaveAttribute("aria-hidden", "true");
    await user.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("complementary", { hidden: true })).not.toHaveAttribute("aria-hidden");
    await user.keyboard("{Escape}");
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("complementary", { hidden: true })).toHaveAttribute("aria-hidden", "true");
    expect(menu).toHaveFocus();
  });

  it("renders without making API requests", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("API unavailable"));
    render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Make work repeatable." })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("desktop route parser", () => {
  it("covers the typed route matrix without redirecting unknown paths", () => {
    expect(parseDesktopRoute("#/projects").kind).toBe("projects");
    expect(parseDesktopRoute(projectRoutePaths.project("p")).kind).toBe("project");
    expect(parseDesktopRoute(projectRoutePaths.agents("p")).kind).toBe("project-agents");
    expect(parseDesktopRoute(projectRoutePaths.agent("p", "a")).kind).toBe("agent-detail");
    expect(parseDesktopRoute(projectRoutePaths.agentVersion("p", "a", "v1")).kind).toBe("agent-version");
    expect(parseDesktopRoute(projectRoutePaths.factory("p")).kind).toBe("factory");
    expect(parseDesktopRoute(projectRoutePaths.agentDesign("p", "a")).kind).toBe("agent-design");
    expect(parseDesktopRoute(projectRoutePaths.agentRun("p", "a")).kind).toBe("agent-run");
    expect(parseDesktopRoute("#/components").kind).toBe("components");
    expect(parseDesktopRoute("#/components/c").kind).toBe("component");
    expect(parseDesktopRoute("#/files").kind).toBe("files");
    expect(parseDesktopRoute("#/files/f").kind).toBe("file");
    expect(parseDesktopRoute("#/community").kind).toBe("community");
    expect(parseDesktopRoute("#/community/o/s").kind).toBe("community-entry");
    expect(parseDesktopRoute("#/community/o/s/versions/v1").kind).toBe("community-version");
    expect(parseDesktopRoute("#/community/o/s/unknown/v1").kind).toBe("not-found");
    expect(parseDesktopRoute("#/nowhere").kind).toBe("not-found");
  });
});
