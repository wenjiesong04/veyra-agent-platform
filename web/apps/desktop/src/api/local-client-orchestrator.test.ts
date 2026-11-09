import { describe, expect, it, vi } from "vitest";
import { LocalApiClient } from "./local-client";

function work(overrides = {}) {
  return {
    schema_version: "1.0", work_item_id: "work-1", project_id: "project-1",
    title: "Pinned work", description: "", agent_id: "agent-1",
    agent_version_id: "version-1", agent_source_hash: "a".repeat(64), binding_required: false,
    depends_on: [], inputs: { request: "facts" }, status: "failed", run_id: "run-1",
    attempt_number: 1, created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z",
    attempts: [{ attempt_id: "attempt-1", attempt_number: 1, operation: "retry", previous_run_id: "run-0", run_id: "run-1", error_code: "runtime_timeout", status: "failed", failure_class: "provider", claimed_at: "2026-10-16T00:00:00Z", started_at: null, finished_at: null, created_at: "2026-10-16T00:00:00Z" }],
    ...overrides,
  };
}

function response(payload: unknown) {
  return new Response(JSON.stringify(payload), { headers: { "Content-Type": "application/json" } });
}

describe("LocalApiClient managed execution", () => {
  it.each(["dispatchWorkItem", "retryWorkItem"] as const)("%s preserves the caller operation key, nonce, pin and lineage", async (action) => {
    const fetcher = vi.fn().mockImplementation(async () => response(work()));
    const client = new LocalApiClient({ fetcher });
    const key = "01990000-0000-7000-8000-000000000001";
    for (let i = 0; i < 2; i += 1) {
      const result = await client[action]("work-1", { idempotencyKey: key, expectedAttemptNumber: 1 });
      expect(result).toMatchObject({ agent_version_id: "version-1", agent_source_hash: "a".repeat(64), binding_required: false, attempts: [{ operation: "retry", previous_run_id: "run-0", error_code: "runtime_timeout" }] });
    }
    for (const [url, init] of fetcher.mock.calls) {
      expect(url).toBe(`/api/v1/work-items/work-1/${action === "dispatchWorkItem" ? "dispatch" : "retry"}`);
      expect(new Headers(init.headers).get("Idempotency-Key")).toBe(key);
      expect(JSON.parse(init.body)).toEqual({ expected_attempt_number: 1 });
    }
  });

  it("sends an explicitly selected committed version on creation and legacy binding", async () => {
    const fetcher = vi.fn().mockImplementation(async () => response(work()));
    const client = new LocalApiClient({ fetcher });
    await client.createWorkItem("project-1", { title: "Pinned", agent_id: "agent-1", agent_version_id: "version-1" });
    await client.updateWorkItem("work-1", { agent_version_id: "version-2" });
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({ agent_version_id: "version-1" });
    expect(fetcher.mock.calls[1][0]).toBe("/api/v1/work-items/work-1");
    expect(fetcher.mock.calls[1][1].method).toBe("PATCH");
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ agent_version_id: "version-2" });
  });

  it("keeps cancelling and treats absent legacy pins as unbound without inventing a version", async () => {
    const old = work({ status: "cancelling" });
    delete (old as Partial<typeof old>).agent_version_id;
    delete (old as Partial<typeof old>).agent_source_hash;
    delete (old as Partial<typeof old>).binding_required;
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", project_id: "project-1", counts: {}, work_items: [old] }));
    const client = new LocalApiClient({ fetcher });
    const listed = await client.listWorkItems("project-1");
    expect(listed.work_items[0]).toMatchObject({ status: "cancelling", agent_version_id: null, agent_source_hash: null, binding_required: true });
  });
});
