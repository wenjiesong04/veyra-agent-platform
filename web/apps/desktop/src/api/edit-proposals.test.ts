import { describe, expect, it, vi } from "vitest";
import { editProposal } from "../test/edit-proposals";
import { LocalApiClient } from "./local-client";

const response = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });

describe("Edit proposal wire contract", () => {
  it("sends natural-language context and rejects a resolved edit without a baseline", async () => {
    const payload = { schema_version: "1.0", intent: "edit", create_kind: null, status: "resolved", message: "Will edit Review", instruction: "Add quality check", plan: ["Add verifier"], targets: [{ kind: "agent", target_id: "a", name: "Review", revision: 1, etag: '"e"' }] };
    const fetcher = vi.fn().mockResolvedValueOnce(response(payload)).mockResolvedValueOnce(response({ ...payload, targets: [{ kind: "agent", target_id: "a", name: "Review" }] }));
    const client = new LocalApiClient({ fetcher });
    const request = { content: "Add quality check to Review", history: [], focus: null, locale: "en" as const };
    await expect(client.resolveBuilderIntent("p /1", request)).resolves.toEqual(payload);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/projects/p%20%2F1/builder/resolve");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(request);
    await expect(client.resolveBuilderIntent("p /1", request)).rejects.toMatchObject({ code: "invalid_response" });
  });
  it.each(["agent", "workflow"] as const)("parses %s proposals and sends exact revision, ETag and explicit commands", async (kind) => {
    const proposal = editProposal(kind);
    const fetcher = vi.fn().mockResolvedValueOnce(response({ schema_version: "1.0", proposals: [proposal] }))
      .mockResolvedValueOnce(response(proposal, 201)).mockImplementation(async () => response({ ...proposal, state: "applied", applied_revision: 2 }));
    const client = new LocalApiClient({ fetcher });
    await expect(client.listEditProposals("project /1", kind, "target /1")).resolves.toEqual({ schema_version: "1.0", proposals: [proposal] });
    const request = { target_kind: kind, target_id: proposal.target_id, instruction: proposal.instruction, expected_revision: 1, expected_etag: proposal.base_etag };
    await expect(client.createEditProposal("project /1", request)).resolves.toEqual(proposal);
    for (const command of ["apply", "reject", "undo"] as const) await client.commandEditProposal("project /1", "proposal /1", { command, confirm: true });
    expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/projects/project%20%2F1/edit-proposals?target_kind=${kind}&target_id=target+%2F1`);
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual(request);
    for (const [index, command] of ["apply", "reject", "undo"].entries()) {
      expect(fetcher.mock.calls[index + 2][0]).toBe("/api/v1/projects/project%20%2F1/edit-proposals/proposal%20%2F1/commands");
      expect(JSON.parse(fetcher.mock.calls[index + 2][1].body)).toEqual({ command, confirm: true });
    }
  });

  it.each([
    { state: "executed" }, { stale: "false" }, { candidate_source: { ...editProposal().candidate_source, agent_id: "another-agent" } },
    { impact: { ...editProposal().impact, runs_started: true } }, { validation: { ...editProposal().validation, valid: "false" } },
  ])("rejects malformed review safety fields: %j", async (override) => {
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response({ ...editProposal(), ...override })) });
    await expect(client.commandEditProposal("p", "proposal-1", { command: "apply", confirm: true })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("parses a server-resolved Knowledge binding plan with honest readiness", async () => {
    const plan = {
      reference: "01a0ae99-45da-755f-862f-f78823dcf760@1.0.0",
      name: "毕业论文",
      source_file_hash: "a".repeat(64),
      index_status: "not_indexed",
      chunk_count: null,
      failure_reason: null,
      runnable: false,
      required_action: "build_index",
    };
    const proposal = { ...editProposal("agent"), knowledge_binding: plan };
    const fetcher = vi.fn().mockResolvedValue(response(proposal, 201));
    const client = new LocalApiClient({ fetcher });
    const request = { agent_id: proposal.target_id, instruction: "使用毕业论文资料。", expected_revision: 1, expected_etag: proposal.base_etag };
    const parsed = await client.createKnowledgeBindingProposal("project /1", request);
    expect(parsed.knowledge_binding).toEqual({ ...plan, chunk_count: undefined, index_status: "not_indexed", required_action: "build_index" });
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/projects/project%20%2F1/edit-proposals/knowledge-binding");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(request);
  });

  it.each([
    { index_status: "indexed", runnable: false, required_action: null },
    { index_status: "not_indexed", runnable: true, required_action: null },
    { index_status: "unknown", runnable: false, required_action: "build_index" },
    { index_status: "stale", runnable: false, required_action: "auto_rebuild" },
  ])("rejects a Knowledge binding plan whose readiness contradicts itself: %j", async (plan) => {
    const proposal = { ...editProposal("agent"), knowledge_binding: { reference: "01a0ae99-45da-755f-862f-f78823dcf760@1.0.0", name: "毕业论文", source_file_hash: "a".repeat(64), failure_reason: null, ...plan } };
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(proposal, 201)) });
    await expect(client.createKnowledgeBindingProposal("p", { agent_id: "a", instruction: "x", expected_revision: 1, expected_etag: '"e"' })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("surfaces an ambiguous Knowledge mention as a typed clarification, not a guess", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", code: "knowledge_mention_ambiguous", message: "No single Project Knowledge document matched this request.", details: { candidates: "毕业论文 (id@1.0.0), 毕业论文-旧版 (id2@1.0.0)" } }, 422));
    const client = new LocalApiClient({ fetcher });
    await expect(client.createKnowledgeBindingProposal("p", { agent_id: "a", instruction: "使用毕业论文资料。", expected_revision: 1, expected_etag: '"e"' }))
      .rejects.toMatchObject({ status: 422, code: "knowledge_mention_ambiguous" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("parses a Project-pinned Resource plan and sends the deterministic endpoint", async () => {
    const plan = {
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      bound_content_hash: "a".repeat(64),
      catalog_content_hash: "a".repeat(64),
      binding_status: "current",
      readiness: "ready",
      availability: "ready",
      runtime_status: "supported",
      required_permissions: {
        network_hosts: [],
        tools: ["veyra.tool.filesystem.read"],
        filesystem_read_roots: ["project"],
        filesystem_write_roots: [],
        shell_workspace_only: false,
      },
      blocking_reasons: [],
      project_resource_changed: false,
      automatic_upgrade: false,
    } as const;
    const proposal = { ...editProposal("agent"), resource_binding: plan };
    const fetcher = vi.fn().mockResolvedValue(response(proposal, 201));
    const client = new LocalApiClient({ fetcher });
    const request = { agent_id: proposal.target_id, instruction: "读取项目文件", expected_revision: 1, expected_etag: proposal.base_etag };
    const parsed = await client.createResourceBindingProposal("project /1", request);
    expect(parsed.resource_binding).toEqual(plan);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/projects/project%20%2F1/edit-proposals/resource-binding");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(request);
  });

  it.each([
    { binding_status: "stale", bound_content_hash: "a".repeat(64), catalog_content_hash: "a".repeat(64), readiness: "stale" },
    { binding_status: "current", bound_content_hash: "a".repeat(64), catalog_content_hash: "b".repeat(64), readiness: "ready" },
    { binding_status: "current", bound_content_hash: "a".repeat(64), catalog_content_hash: "a".repeat(64), readiness: "ready", availability: "requires_configuration" },
    { binding_status: "current", bound_content_hash: "not-a-hash", catalog_content_hash: "a".repeat(64), readiness: "ready" },
  ])("rejects a Resource binding plan that contradicts Project pin/readiness: %j", async (override) => {
    const resource_binding = Object.assign({
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      bound_content_hash: "a".repeat(64),
      catalog_content_hash: "a".repeat(64),
      binding_status: "current",
      readiness: "ready",
      availability: "ready",
      runtime_status: "supported",
      required_permissions: { network_hosts: [], tools: [], filesystem_read_roots: [], filesystem_write_roots: [], shell_workspace_only: false },
      blocking_reasons: [],
      project_resource_changed: false,
      automatic_upgrade: false,
    }, override);
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response({ ...editProposal(), resource_binding }, 201)) });
    await expect(client.createResourceBindingProposal("p", { agent_id: "a", instruction: "x", expected_revision: 1, expected_etag: '"e"' }))
      .rejects.toMatchObject({ code: "invalid_response" });
  });

  it("parses a boolean validation failure and a deterministic repair plan", async () => {
    const plan = {
      code: "lock_mismatch",
      kind: "tool",
      reference: "veyra.tool.filesystem.read@1.0.0",
      name: "Filesystem Read",
      repairable: true as const,
      automatic_upgrade: false as const,
      project_resource_changed: false as const,
      locked_hash: "b".repeat(64),
      bound_content_hash: "a".repeat(64),
      target_kind: "agent" as const,
      impact: "Align the Agent lock to the current Project pin.",
    };
    const proposal = {
      ...editProposal("agent"),
      instruction: "Repair lock_mismatch for veyra.tool.filesystem.read@1.0.0",
      validation: { ...editProposal().validation, valid: false, runtime_ready: false },
      validation_repair: plan,
    };
    const fetcher = vi.fn().mockResolvedValue(response(proposal, 201));
    const client = new LocalApiClient({ fetcher });
    const request = { agent_id: "agent-1", reference: plan.reference, code: "lock_mismatch", expected_revision: 1, expected_etag: '"etag-1"' };
    const parsed = await client.createValidationRepairProposal("project /1", request);
    expect(parsed.validation.valid).toBe(false);
    expect(parsed.validation_repair).toEqual(plan);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/projects/project%20%2F1/edit-proposals/validation-repair");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(request);
  });

  it("rejects a repair plan that claims a silent upgrade", async () => {
    const proposal = { ...editProposal(), validation_repair: { code: "lock_mismatch", kind: "tool", reference: "veyra.tool.filesystem.read@1.0.0", name: "Read", repairable: true, automatic_upgrade: true, project_resource_changed: false, target_kind: "agent", impact: "upgrade" } };
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(proposal, 201)) });
    await expect(client.createValidationRepairProposal("p", { agent_id: "a", reference: "veyra.tool.filesystem.read@1.0.0", code: "lock_mismatch", expected_revision: 1, expected_etag: '"e"' }))
      .rejects.toMatchObject({ code: "invalid_response" });
  });

  it("preserves typed conflicts without retrying a mutation", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", code: "draft_conflict", message: "Dependencies changed" }, 409));
    const client = new LocalApiClient({ fetcher });
    await expect(client.commandEditProposal("p", "proposal-1", { command: "undo", confirm: true })).rejects.toMatchObject({ status: 409, code: "draft_conflict" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
