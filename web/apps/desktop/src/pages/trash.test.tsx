import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkspaceTrashItem } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ProjectWorkspaceProvider } from "../api/project-workspace";
import { LocalApiClientError, type LocalProjectApi } from "../api/local-client";
import { TrashPage } from "./trash";

function item(overrides: Partial<WorkspaceTrashItem> = {}): WorkspaceTrashItem {
  return {
    kind: "agent",
    id: "agent-1",
    name: "Review helper",
    project_id: "project-1",
    project_name: "Keep",
    removed_at: new Date(Date.now() - 3_600_000).toISOString(),
    expires_at: new Date(Date.now() + 30 * 86_400_000).toISOString(),
    restorable: true,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("TrashPage", () => {
  it("restores a trash item through the workspace trash API", async () => {
    const listed = [
      item(),
      item({ kind: "conversation", id: "conv-1", name: "Gift wrap", restorable: true }),
      item({ kind: "agent", id: "orphan-agent", name: "Orphan", restorable: false, project_name: null }),
    ];
    const listWorkspaceTrash = vi.fn()
      .mockResolvedValueOnce({ schema_version: "1.0", retention_days: 30, items: listed })
      .mockResolvedValue({ schema_version: "1.0", retention_days: 30, items: listed.slice(1) });
    const restoreWorkspaceTrash = vi.fn().mockResolvedValue({ schema_version: "1.0", kind: "agent", id: "agent-1", restored: true });
    const purgeWorkspaceTrash = vi.fn();
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listWorkspaceTrash,
      restoreWorkspaceTrash,
      purgeWorkspaceTrash,
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><TrashPage /></ProjectWorkspaceProvider></ThemeProvider>);
    expect(await screen.findByRole("heading", { name: "Deleted workspace objects stay recoverable for 30 days." })).toBeInTheDocument();
    expect(screen.getByText("Review helper")).toBeInTheDocument();
    expect(screen.getByText("Gift wrap")).toBeInTheDocument();
    expect(screen.getByText("Restore the parent Project first.")).toBeInTheDocument();
    expect(within(screen.getByText("Orphan").closest("article") as HTMLElement).getByRole("button", { name: "Restore" })).toBeDisabled();
    await user.click(within(screen.getByText("Review helper").closest("article") as HTMLElement).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(restoreWorkspaceTrash).toHaveBeenCalledWith("agent", "agent-1"));
    expect(await screen.findByText("Restored.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Review helper")).not.toBeInTheDocument());
    expect(screen.getByText("Gift wrap")).toBeInTheDocument();
    expect(purgeWorkspaceTrash).not.toHaveBeenCalled();
  });

  it("requires confirmation before permanently deleting a trash item", async () => {
    const listed = [item({ kind: "project", id: "project-9", name: "Old project", project_id: null, project_name: null })];
    const listWorkspaceTrash = vi.fn()
      .mockResolvedValueOnce({ schema_version: "1.0", retention_days: 30, items: listed })
      .mockResolvedValue({ schema_version: "1.0", retention_days: 30, items: [] });
    const purgeWorkspaceTrash = vi.fn().mockResolvedValue({ schema_version: "1.0", kind: "project", id: "project-9", deleted: true });
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listWorkspaceTrash,
      restoreWorkspaceTrash: vi.fn(),
      purgeWorkspaceTrash,
    } as unknown as LocalProjectApi;
    const user = userEvent.setup();
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><TrashPage /></ProjectWorkspaceProvider></ThemeProvider>);
    await user.click(await screen.findByRole("button", { name: "Delete forever" }));
    expect(purgeWorkspaceTrash).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Delete forever?" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("dialog", { name: "Delete forever?" })).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Delete forever?" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete forever" }));
    await user.click(within(screen.getByRole("dialog", { name: "Delete forever?" })).getByRole("button", { name: "Delete forever" }));
    await waitFor(() => expect(purgeWorkspaceTrash).toHaveBeenCalledWith("project", "project-9"));
    expect(await screen.findByText("Trash is empty")).toBeInTheDocument();
    expect(screen.getByText("Permanently deleted.")).toBeInTheDocument();
  });

  it("does not treat a missing trash route as an empty trash", async () => {
    const api = {
      listProjects: vi.fn().mockResolvedValue({ schema_version: "1.0", projects: [] }),
      listWorkspaceTrash: vi.fn().mockRejectedValue(new LocalApiClientError("Not Found", { status: 404, code: "http_error" })),
    } as unknown as LocalProjectApi;
    render(<ThemeProvider><ProjectWorkspaceProvider api={api}><TrashPage /></ProjectWorkspaceProvider></ThemeProvider>);
    expect(await screen.findByText("Trash could not be loaded. Check the desktop sidecar.")).toBeInTheDocument();
    expect(screen.queryByText("Trash is empty")).not.toBeInTheDocument();
  });
});
