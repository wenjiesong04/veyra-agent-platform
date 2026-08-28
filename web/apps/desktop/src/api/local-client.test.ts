import { describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { LocalApiClient } from "./local-client";

function summary(overrides: Partial<ProjectSummaryResponse> = {}) {
  return {
    schema_version: "1.0",
    project_id: "project-1",
    root_path: "/tmp/project-1",
    name: "Project One",
    description: "",
    pinned: false,
    pinned_at: null,
    indexed_at: "2026-08-28T00:00:00Z",
    manifest_hash: "manifest-hash",
    agents: [],
    ...overrides,
  } satisfies ProjectSummaryResponse;
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LocalApiClient Project requests", () => {
  it("lists and validates real Project summaries", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", projects: [summary({ agents: [{ agent_id: "agent-1", slug: "reviewer", source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" }] })] }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjects()).resolves.toEqual({ schema_version: "1.0", projects: [summary({ agents: [{ agent_id: "agent-1", slug: "reviewer", source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "file-hash" }] })] });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/projects", expect.objectContaining({ method: "GET", credentials: "include" }));
  });

  it("sends a create name and description while opening continues to send an existing root path", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(summary({ project_id: "created", name: "Created" }), 201))
      .mockResolvedValueOnce(response(summary({ project_id: "opened", name: "Opened" })));
    const client = new LocalApiClient({ fetcher });

    await client.createProject({ name: "Created", description: "A created Project" });
    await client.openProject({ root_path: "/tmp/existing" });

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ name: "Created", description: "A created Project" });
    expect(fetcher.mock.calls[1]?.[0]).toBe("/api/v1/projects/open");
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({ root_path: "/tmp/existing" });
  });

  it("uses the deliberate desktop intent header for the native directory picker", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected" }));
    const client = new LocalApiClient({ fetcher });

    await expect(client.selectDirectory()).resolves.toEqual({ schema_version: "1.0", status: "selected", root_path: "/tmp/selected" });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/system/select-directory", expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "X-Veyra-Desktop-Intent": "select-directory" }),
    }));
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({});
  });

  it("surfaces typed sidecar errors instead of falling back to fixture data", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", code: "project_unavailable", message: "Project root cannot be read", request_id: "request-1" }, 503));
    const client = new LocalApiClient({ fetcher });

    await expect(client.listProjects()).rejects.toMatchObject({
      status: 503,
      code: "project_unavailable",
      requestId: "request-1",
      message: "Project root cannot be read",
    });
  });
});
