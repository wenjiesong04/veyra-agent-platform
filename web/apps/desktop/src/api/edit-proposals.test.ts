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
    { impact: { ...editProposal().impact, runs_started: true } }, { validation: { ...editProposal().validation, valid: false } },
  ])("rejects malformed review safety fields: %j", async (override) => {
    const client = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response({ ...editProposal(), ...override })) });
    await expect(client.commandEditProposal("p", "proposal-1", { command: "apply", confirm: true })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("preserves typed conflicts without retrying a mutation", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", code: "draft_conflict", message: "Dependencies changed" }, 409));
    const client = new LocalApiClient({ fetcher });
    await expect(client.commandEditProposal("p", "proposal-1", { command: "undo", confirm: true })).rejects.toMatchObject({ status: 409, code: "draft_conflict" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
