import { describe, expect, it, vi } from "vitest";
import { LocalApiClient } from "./local-client";

describe("Knowledge remove wire", () => {
  it("preserves typed conflict and usage evidence from DELETE", async () => {
    const details = { knowledge_id: "knowledge-1", reason: "Retained binding", kind: "agent_version", agent_id: "agent-1", version_id: "version-1" };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema_version: "1.0", code: "knowledge_in_use", message: "Knowledge is still used", details }), { status: 409 }));
    const api = new LocalApiClient({ fetcher });
    await expect(api.deleteKnowledge("project-1", "knowledge-1")).rejects.toMatchObject({ status: 409, code: "knowledge_in_use", details });
    expect(fetcher).toHaveBeenCalledWith("/api/v1/projects/project-1/knowledge/knowledge-1", expect.objectContaining({ method: "DELETE" }));
  });
});
