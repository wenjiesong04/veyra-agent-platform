import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import type { CommunityApi } from "@veyra/connected-account";
import type { CommunityRegistryEntry, ExportResponse, ProjectSummaryResponse, ValidateResponse } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { CommunityPublishPanel } from "./community-publish-panel";

afterEach(() => cleanup());

function exportResponse(overrides: { secretRefs?: string[]; description?: string } = {}): ExportResponse {
  return {
    schema_version: "1.0",
    agent_id: "agent-1",
    source: {
      schema_version: "1.0",
      agentspec_version: "26.1",
      component_type: "Flow",
      agent_id: "agent-1",
      slug: "meeting-summary",
      name: "Meeting Summary",
      description: overrides.description ?? "Summarize a meeting.",
      inputs: {},
      outputs: {},
      nodes: [],
      transitions: [],
      extensions: { veyra: { runtime_profile: "veyra-runtime-profile/1", secret_refs: overrides.secretRefs ?? [], permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false }, verification: { required: false, checks: [] } } },
      ui: { positions: {} },
      lock: {},
    },
    source_text: "Original local YAML comments are not part of a Community package.",
    file_hash: "raw-file-hash",
    community_package: {
      source_text: "{\"schema_version\":\"1.0\",\"name\":\"Meeting Summary\"}\n",
      file_hash: "community-file-hash",
      source_hash: "source-hash",
      behavior_hash: "behavior-hash",
      lock_hash: "lock-hash",
      dependencies: ["veyra.tool.filesystem.read@1.0.0"],
      version: "1.2.0",
      slug: "meeting-summary",
      name: "Meeting Summary",
      description: "Summarize a meeting.",
    },
  } as ExportResponse;
}

function renderPanel(args: { secretRefs?: string[]; description?: string } = {}) {
  const publish = vi.fn().mockResolvedValue({ schema_version: "community.registry.v1", status: "published" } as CommunityRegistryEntry);
  const exported = exportResponse(args);
  const localApi = {
    exportAgent: vi.fn().mockResolvedValue(exported),
    validate: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      valid: true,
      source_hash: exported.community_package.source_hash,
      behavior_hash: exported.community_package.behavior_hash,
      lock_hash: exported.community_package.lock_hash,
      file_hash: "draft-file-hash",
      runtime_ready: true,
      runtime_ready_scope: "agent_dependencies",
      dependencies: [{ reference: "veyra.tool.filesystem.read@1.0.0", status: "ready", detail: "Pinned in this Project" }],
    } as unknown as ValidateResponse),
  } as unknown as LocalProjectApi;
  const communityApi = { publishRegistryAgent: publish } as unknown as CommunityApi;
  const onPublished = vi.fn();
  render(<ThemeProvider><CommunityPublishPanel
    projects={[{ project_id: "project-1", name: "Project", agents: [{ agent_id: "agent-1", name: "Meeting Summary", slug: "meeting-summary" }] } as ProjectSummaryResponse]}
    localApi={localApi}
    communityApi={communityApi}
    onPublished={onPublished}
  /></ThemeProvider>);
  return { publish, onPublished };
}

describe("Community publish review boundary", () => {
  it("keeps publication local until explicit confirmation and uploads the canonical source", async () => {
    const user = userEvent.setup();
    const { publish, onPublished } = renderPanel();

    await user.click(screen.getByRole("button", { name: "Review publication" }));
    expect(await screen.findByText("Publication preview (not uploaded)")).toBeInTheDocument();
    expect(screen.getByText("source-hash")).toBeInTheDocument();
    expect(publish).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirm publication" }));
    expect(publish).toHaveBeenCalledTimes(1);
    const file = publish.mock.calls[0]?.[0];
    expect(file).toBeInstanceOf(File);
    expect(file?.name).toBe("meeting-summary.vagent.yaml");
    expect(onPublished).toHaveBeenCalledTimes(1);
  });

  it("disables upload when the source declares host Secret references", async () => {
    const user = userEvent.setup();
    const { publish } = renderPanel({ secretRefs: ["OPENAI_API_KEY"] });

    await user.click(screen.getByRole("button", { name: "Review publication" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Host Secret references");
    expect(screen.getByRole("button", { name: "Confirm publication" })).toBeDisabled();
    expect(publish).not.toHaveBeenCalled();
  });

  it("disables upload when the Agent source contains a machine path", async () => {
    const user = userEvent.setup();
    const { publish } = renderPanel({ description: "Read /Users/alice/private/research" });

    await user.click(screen.getByRole("button", { name: "Review publication" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Absolute, sensitive, or traversing path");
    expect(screen.getByRole("button", { name: "Confirm publication" })).toBeDisabled();
    expect(publish).not.toHaveBeenCalled();
  });
});
