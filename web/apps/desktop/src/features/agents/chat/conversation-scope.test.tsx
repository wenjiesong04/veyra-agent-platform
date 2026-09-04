import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ConversationScopePicker } from "./conversation-scope";

const alpha: ProjectSummaryResponse = {
  schema_version: "1.0",
  project_id: "project-1",
  root_path: "/tmp/veyra-agent-platform",
  name: "New Agent",
  description: "",
  pinned: false,
  pinned_at: null,
  indexed_at: "2026-08-28T00:00:00Z",
  manifest_hash: "hash",
  default_agent_id: null,
  agent_count: 0,
  agents: [],
};

const slens: ProjectSummaryResponse = {
  ...alpha,
  project_id: "project-2",
  root_path: "/tmp/SLens",
  name: "SLens",
};

describe("ConversationScopePicker", () => {
  afterEach(cleanup);

  it("filters projects and keeps create / leave actions", async () => {
    const onSelect = vi.fn();
    const onCreateProject = vi.fn();
    render(
      <ConversationScopePicker
        locale="en"
        current={{ kind: "project", projectId: "project-1", name: "New Agent" }}
        projects={[alpha, slens]}
        onSelect={onSelect}
        onCreateProject={onCreateProject}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Choose project" }));
    expect(screen.getByRole("option", { name: /New Agent/ })).toHaveAttribute("aria-selected", "true");
    await user.type(screen.getByRole("searchbox", { name: "Search projects" }), "slens");
    expect(screen.queryByRole("option", { name: /New Agent/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /SLens/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New project" }));
    expect(onCreateProject).toHaveBeenCalledTimes(1);
  });
});
