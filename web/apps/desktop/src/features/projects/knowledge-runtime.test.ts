import { describe, expect, it, vi } from "vitest";
import type { AgentSource, ProjectKnowledgeRecord } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { bindKnowledgeToAgent } from "./knowledge-runtime";

const source: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "reviewer",
  name: "Reviewer",
  description: "",
  inputs: { request: "string" },
  outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "out", component_type: "Output", output_name: "result" },
  ],
  transitions: [{ from: "start", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, out: { x: 200, y: 0 } } },
  lock: {},
};

const knowledge: ProjectKnowledgeRecord = {
  knowledge_id: "knowledge-1",
  slug: "brand",
  name: "Brand",
  description: "",
  version: "1.0.0",
  source_path: "knowledge/brand/document.md",
  source_file_hash: "b".repeat(64),
};

describe("bindKnowledgeToAgent", () => {
  it("writes an explicit versioned Knowledge binding and lock", async () => {
    const saveDraft = vi.fn().mockResolvedValue({ source });
    const api = {
      getDraft: vi.fn().mockResolvedValue({ source, revision: 3, etag: "etag-3" }),
      saveDraft,
    } as unknown as LocalProjectApi;

    await bindKnowledgeToAgent(api, "project-1", "agent-1", knowledge);

    const request = saveDraft.mock.calls[0]?.[2] as { source: AgentSource; expected_revision: number };
    expect(request.expected_revision).toBe(3);
    expect(request.source.extensions.veyra.knowledge_refs).toEqual(["knowledge-1@1.0.0"]);
    expect(request.source.lock).toEqual({ "knowledge-1@1.0.0": "b".repeat(64) });
    expect(request.source.ui.bindings?.knowledge_knowledge1).toMatchObject({ kind: "knowledge", reference: "knowledge-1@1.0.0" });
    expect(saveDraft.mock.calls[0]?.[3]).toEqual({ etag: "etag-3" });
  });
});
