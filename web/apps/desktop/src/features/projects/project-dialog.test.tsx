import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { ProjectWorkspaceProvider } from "../../api/project-workspace";
import { ProjectDialog } from "./project-dialog";

afterEach(cleanup);

describe("ProjectDialog model API guidance", () => {
  it.each(["zh", "en"] as const)("explains model API setup in ordinary %s without requesting a key", async (locale) => {
    window.localStorage.setItem("veyra.language", locale);
    const createProject = vi.fn();
    const api = { listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }), createProject } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><ProjectDialog mode="create" onClose={vi.fn()} /></ProjectWorkspaceProvider></ThemeProvider>);
    const name = await screen.findByRole("textbox", { name: locale === "zh" ? "项目名称" : "Project name" });
    expect(name).toHaveFocus();
    expect(screen.getByText(locale === "zh" ? /先创建项目，再用对话描述要做的事/ : /Create the Project, then describe your task in chat/)).toBeInTheDocument();
    expect(screen.queryByText(/Runtime Provider|Provider Credentials|Runtime Binding|Builder/)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /API Key|密钥/ })).not.toBeInTheDocument();
    expect(createProject).not.toHaveBeenCalled();
  });
});
