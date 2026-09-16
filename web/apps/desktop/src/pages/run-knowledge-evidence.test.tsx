import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import type { AgentRunResponse, KnowledgeRetrievalHit } from "@veyra/api-contracts";
import { LocalApiClient } from "../api/local-client";
import { RunDetail } from "../features/runs/RunDetail";
import { knowledgeEvidence } from "../features/runs/knowledge-evidence";

const identity = { projectId: "project-1", agentId: "agent-1", runId: "historical-1" };
const reference = "01900000-0000-7000-8000-000000000001@1.0.0";
const hit: KnowledgeRetrievalHit = { reference, source_file_hash: "a".repeat(64), chunk_id: "b".repeat(64), chunk_index: 0, line_start: 2, line_end: 4, rank: 1, score: 8 };
const run: AgentRunResponse = {
  schema_version: "1.0", project_id: identity.projectId, agent_id: identity.agentId, run_id: identity.runId,
  version_id: "original-version", status: "unverified", result: { answer: "Original answer without inline markers" }, error: null,
  created_at: "2026-09-15T10:00:00Z", finished_at: "2026-09-15T10:00:01Z",
  events: [{ schema_version: "1.0", event_id: "retrieval-1", run_id: identity.runId, sequence: 1, kind: "tool.completed", node_id: "model", timestamp: "2026-09-15T10:00:01Z", payload: {
    tool_reference: "knowledge.context", query_hash: "d".repeat(64), hit_count: 3,
    receipts: [hit, { ...hit, reference: "01900000-0000-7000-8000-000000000002@1.0.0", chunk_id: "c".repeat(64), rank: 2, score: 5 }, { ...hit, chunk_id: "e".repeat(64), chunk_index: 1, line_start: 8, line_end: 9, rank: 3, score: 2 }],
  } }],
};
const excerpt = { schema_version: "1.0", project_id: identity.projectId, reference, source_file_hash: hit.source_file_hash, chunk_id: hit.chunk_id, line_start: 2, line_end: 4, text: "Original source excerpt\nreal context\nlast line" };

function setup(detail = run, preview: unknown = excerpt, status = 200) {
  const fetcher = vi.fn().mockImplementation(async (url: string) => new Response(JSON.stringify(url.includes("/chunks/") ? preview : detail), { status: url.includes("/chunks/") ? status : 200 }));
  const api = new LocalApiClient({ fetcher });
  const mount = () => render(<ThemeProvider><RunDetail api={api} {...identity} locale="en" /></ThemeProvider>);
  return { api, fetcher, mount };
}
afterEach(cleanup);

describe("Run Detail Knowledge evidence", () => {
  it("preserves wire identity, global hit order and locator, expands only on request, and reloads the exact historical run", async () => {
    const { api, fetcher, mount } = setup();
    const loaded = await api.getAgentRun(identity.projectId, identity.agentId, identity.runId);
    expect(loaded.events).toEqual(run.events);
    let view = mount();
    for (let attempt = 0; attempt < 2; attempt++) {
      const panel = await screen.findByRole("region", { name: "Knowledge Evidence" });
      const rows = within(panel).getAllByRole("listitem");
      expect(rows).toHaveLength(3);
      expect(rows.map((row) => row.textContent?.match(/Rank \d/)?.[0])).toEqual(["Rank 1", "Rank 2", "Rank 3"]);
      expect(within(rows[0]).getByText(/Lines 2–4 · Rank 1 · Score 8/)).toBeInTheDocument();
      expect(within(rows[2]).getByText(/Lines 8–9/)).toBeInTheDocument();
      expect(within(rows[0]).getByRole("link", { name: reference })).toHaveAttribute("href", "#/projects/project-1/knowledge/01900000-0000-7000-8000-000000000001");
      expect(within(rows[0]).getByText("aaaaaaaaaaaa")).toHaveAttribute("title", hit.source_file_hash);
      expect(within(panel).getByText("dddddddddddd")).toHaveAttribute("title", "d".repeat(64));
      expect(screen.queryByText(/Original source excerpt/)).not.toBeInTheDocument();
      if (attempt === 0) { view.unmount(); view = mount(); }
    }
    expect(fetcher.mock.calls.every(([url]) => url === "/api/v1/projects/project-1/agents/agent-1/runs/historical-1")).toBe(true);
    await userEvent.setup().click(within(await screen.findByRole("region", { name: "Knowledge Evidence" })).getAllByRole("button", { name: "Expand excerpt" })[0]);
    expect(await screen.findByText(/Original source excerpt/)).toBeInTheDocument();
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe(`/api/v1/projects/project-1/knowledge/${reference.split("@")[0]}/chunks/${hit.chunk_id}?source_file_hash=${hit.source_file_hash}`);
    await userEvent.setup().click(screen.getByRole("button", { name: "Collapse excerpt" }));
    expect(screen.queryByText(/Original source excerpt/)).not.toBeInTheDocument();
    expect(screen.getByText(/Original answer without inline markers/)).toBeInTheDocument();
  });

  it("shows empty retrieval rather than a fake citation", async () => {
    const empty = { ...run, events: [{ ...run.events![0], payload: { tool_reference: "knowledge.context", query_hash: "d".repeat(64), hit_count: 0, receipts: [] } }] };
    setup(empty).mount();
    const panel = await screen.findByRole("region", { name: "Knowledge Evidence" });
    expect(within(panel).getByText("No relevant Knowledge chunks retrieved.")).toBeInTheDocument();
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it.each(["knowledge_source_mismatch", "knowledge_index_stale", "knowledge_source_missing", "knowledge_index_invalid"])("keeps persisted identity when preview returns %s", async (code) => {
    const { mount } = setup(run, { code, message: "not shown: internal failure" }, 422);
    mount();
    const panel = await screen.findByRole("region", { name: "Knowledge Evidence" });
    await userEvent.setup().click(within(panel).getAllByRole("button", { name: "Expand excerpt" })[0]);
    expect(await screen.findByRole("status")).toHaveTextContent(code.includes("mismatch") || code.includes("stale") ? "Historical source changed" : "Historical source unavailable");
    expect(within(panel).getAllByRole("link", { name: reference })).toHaveLength(2);
    expect(within(panel).getByText(/Lines 2–4 · Rank 1 · Score 8/)).toBeInTheDocument();
    expect(screen.queryByText(/internal failure/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Original source excerpt/)).not.toBeInTheDocument();
  });

  it.each([{ source_file_hash: "f".repeat(64) }, { project_id: "other-project" }, { chunk_id: "f".repeat(64) }, { line_end: 8 }, { reference: reference.replace("1.0.0", "2.0.0") }, { text: "x".repeat(2001) }])("rejects excerpt response mismatch %j without changing evidence", async (mismatch) => {
    setup(run, { ...excerpt, ...mismatch }).mount();
    const panel = await screen.findByRole("region", { name: "Knowledge Evidence" });
    await userEvent.setup().click(within(panel).getAllByRole("button", { name: "Expand excerpt" })[0]);
    expect(await screen.findByRole("status")).toHaveTextContent("Historical source unavailable");
    expect(within(panel).getAllByText("aaaaaaaaaaaa")).toHaveLength(3);
    expect(screen.queryByText(/Original source excerpt/)).not.toBeInTheDocument();
  });

  it.each(["knowledge_not_indexed", "knowledge_index_stale", "knowledge_source_missing", "knowledge_index_invalid"])("retains typed Run failure %s without successful retrieval evidence", async (code) => {
    setup({ ...run, status: "failed", error: { code, message: "Knowledge retrieval failed before model" }, events: [] }).mount();
    expect(await screen.findByText(code)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Knowledge Evidence" })).not.toBeInTheDocument();
  });

  it("does not reinterpret legacy whole-document receipts or failed events as chunk retrieval", () => {
    const event = run.events![0];
    expect(knowledgeEvidence({ ...event, kind: "tool.failed" })).toBeNull();
    expect(knowledgeEvidence({ ...event, payload: { tool_reference: "knowledge.context", receipts: [{ reference, verified: true }] } })).toBeNull();
    expect(knowledgeEvidence({ ...event, payload: { ...event.payload, hit_count: 0 } })).toBeNull();
    expect(knowledgeEvidence(event)?.receipts).toEqual(event.payload.receipts);
  });
});
