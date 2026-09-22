import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  BuilderConversationOperation,
  BuilderConversationSnapshot,
  CustomComponentProposal,
} from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { BuilderComponentProposal } from "./BuilderComponentProposal";

afterEach(() => cleanup());

function operation(
  overrides: Partial<BuilderConversationOperation> = {},
): BuilderConversationOperation {
  return {
    operation_id: "operation-1",
    conversation_id: "conversation-1",
    kind: "create_component",
    target_kind: null,
    status: "waiting",
    retry_of: null,
    error_code: null,
    proposal_id: "proposal-1",
    run_id: null,
    factory_session_id: null,
    created_at: "2026-09-22T00:00:00Z",
    updated_at: "2026-09-22T00:00:00Z",
    diagnostic: {},
    has_request: true,
    events: [],
    receipts: [],
    ...overrides,
  };
}

function proposal(overrides: Partial<CustomComponentProposal> = {}): CustomComponentProposal {
  return {
    schema_version: "1.0",
    proposal_id: "proposal-1",
    proposal_kind: "create_custom_component",
    project_id: "project-1",
    target_kind: "custom_component",
    target_id: "component-1",
    instruction: "Create a reusable text normalization capability",
    created_at: "2026-09-22T00:00:00Z",
    component_plan: {
      component_id: "component-1",
      display_name: "Text normalization",
      description: "Normalize input text.",
      capability_requirement: "Normalize text",
      agent_step: "Normalize the input before summarizing.",
      inputs: { text: { type: "string" } },
      outputs: { normalized: { type: "string" } },
      implementation: { kind: "model_recipe", instruction: "Normalize text." },
      dependencies: [{ reference: "veyra.skill.text@1.0.0", content_hash: "a".repeat(64) }],
      required_permissions: {
        network_hosts: [],
        tools: [],
        filesystem_read_roots: [],
        filesystem_write_roots: [],
        shell_workspace_only: false,
      },
      readiness_expectation: "ready",
    },
    continuation: "agent",
    conversation_id: "conversation-1",
    operation_id: "operation-1",
    factory_session_id: "factory-1",
    changes: [],
    permission_changes: [],
    impact: {
      target_kind: "custom_component",
      target_id: "component-1",
      scope: "project_resource",
      immutable_versions_changed: false,
      runs_started: false,
      creates_component: true,
    },
    validation: { valid: true, readiness_expectation: "ready", dependencies: [] },
    state: "review",
    stale: false,
    created_component: null,
    ...overrides,
  };
}

describe("BuilderComponentProposal", () => {
  it("shows the review and publishes only after explicit confirmation", async () => {
    const snapshot = { schema_version: "1.0" } as BuilderConversationSnapshot;
    const getProposal = vi.fn().mockResolvedValue(proposal());
    const command = vi.fn().mockResolvedValue(snapshot);
    const onSnapshot = vi.fn();
    const api = {
      getBuilderComponentProposal: getProposal,
      commandBuilderComponentProposal: command,
    } as unknown as LocalProjectApi;

    render(
      <BuilderComponentProposal
        api={api}
        projectId="project-1"
        conversationId="conversation-1"
        operation={operation()}
        locale="zh"
        onSnapshot={onSnapshot}
      />,
    );

    expect(await screen.findByText("Text normalization")).toBeInTheDocument();
    expect(screen.getByText(/Agent 不会在此操作中创建/)).toBeInTheDocument();
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认创建并发布组件" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "project-1",
        "conversation-1",
        "operation-1",
        "proposal-1",
        { command: "apply", confirm: true, locale: "zh" },
      ),
    );
    expect(onSnapshot).toHaveBeenCalledWith(snapshot);
  });

  it("does not allow a stale proposal to be confirmed", async () => {
    const command = vi.fn();
    const api = {
      getBuilderComponentProposal: vi.fn().mockResolvedValue(
        proposal({ stale: true }),
      ),
      commandBuilderComponentProposal: command,
    } as unknown as LocalProjectApi;

    render(
      <BuilderComponentProposal
        api={api}
        projectId="project-1"
        conversationId="conversation-1"
        operation={operation()}
        locale="en"
        onSnapshot={() => undefined}
      />,
    );

    expect(await screen.findByText(/Generate a new proposal/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm and publish Component" })).toBeDisabled();
    expect(command).not.toHaveBeenCalled();
  });

  it("records an explicit rejection without applying the proposal", async () => {
    const command = vi.fn().mockResolvedValue({ schema_version: "1.0" });
    const api = {
      getBuilderComponentProposal: vi.fn().mockResolvedValue(proposal()),
      commandBuilderComponentProposal: command,
    } as unknown as LocalProjectApi;

    render(
      <BuilderComponentProposal
        api={api}
        projectId="project-1"
        conversationId="conversation-1"
        operation={operation()}
        locale="en"
        onSnapshot={() => undefined}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Reject, create nothing" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "project-1",
        "conversation-1",
        "operation-1",
        "proposal-1",
        { command: "reject", confirm: true, locale: "en" },
      ),
    );
  });
});
