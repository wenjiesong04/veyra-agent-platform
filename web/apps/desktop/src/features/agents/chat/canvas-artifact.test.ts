import { describe, expect, it } from "vitest";
import type { AgentRunResponse, AgentSource } from "@veyra/api-contracts";
import { assistantPreview, conversationCanvas, isDocumentResult, isMediaResult, isStructuredResult, scalarResultText, tableRows, workingCaption } from "./canvas-artifact";

const source: AgentSource = {
  schema_version: "1.0",
  agentspec_version: "26.1",
  component_type: "Flow",
  agent_id: "agent-1",
  slug: "reviewer",
  name: "Reviewer",
  description: "",
  inputs: { request: "string" },
  outputs: { answer: "string" },
  nodes: [],
  transitions: [],
  extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: true, checks: [] } } },
  ui: { positions: {} },
  lock: {},
};

const run: AgentRunResponse = {
  schema_version: "1.0",
  run_id: "run-1",
  project_id: "project-1",
  agent_id: "agent-1",
  version_id: "version-1",
  status: "verified",
  result: { answer: "Reviewed" },
  error: null,
  created_at: "2026-08-28T00:00:00Z",
  finished_at: "2026-08-28T00:00:01Z",
};

describe("conversation canvas policy", () => {
  it("keeps a short scalar reply in the transcript instead of opening a canvas", () => {
    expect(scalarResultText(run.result)).toBe("Reviewed");
    expect(conversationCanvas({ locale: "en", source, run })).toBeNull();
    expect(assistantPreview(run.result, null, "en")).toEqual({ text: "Reviewed", openedInCanvas: false });
  });

  it("opens a run canvas while a multi-node Agent is executing", () => {
    const graph = {
      ...source,
      nodes: [
        { id: "start", component_type: "Start" as const },
        { id: "approve", component_type: "HumanApproval" as const, prompt: "Write notes.txt?" },
        { id: "output", component_type: "Output" as const, output_name: "answer" },
      ],
    };
    const waiting = { ...run, status: "waiting" as const, result: null, finished_at: null, events: [{ schema_version: "1.0" as const, event_id: "event-1", run_id: "run-1", sequence: 1, kind: "approval.requested" as const, node_id: "approve", payload: { prompt: "Write notes.txt?" }, timestamp: "2026-08-28T00:00:02Z" }] };
    expect(conversationCanvas({ locale: "en", source: graph, run: waiting })).toEqual({ kind: "run", title: "Run canvas" });
    expect(workingCaption(waiting, "en")).toBe("Waiting for approval…");
  });

  it("opens a table canvas for arrays of objects and a result canvas for multi-field objects", () => {
    expect(tableRows({ rows: [{ name: "A", value: 1 }, { name: "B", value: 2 }] })).toHaveLength(2);
    expect(isStructuredResult({ answer: "ok" })).toBe(false);
    expect(isStructuredResult({ title: "Brief", score: 4, notes: ["a"] })).toBe(true);
    expect(conversationCanvas({ locale: "zh", source, run: { ...run, result: { rows: [{ name: "A" }, { name: "B" }] } } })).toEqual({ kind: "table", title: "数据表" });
    expect(conversationCanvas({ locale: "en", source, run: { ...run, result: { title: "Brief", score: 4 } } })).toEqual({ kind: "result", title: "Result canvas" });
    expect(assistantPreview({ title: "Brief", score: 4 }, { kind: "result", title: "Result canvas" }, "en").openedInCanvas).toBe(true);
  });

  it("keeps image and file artifacts in the transcript instead of a JSON canvas", () => {
    const picture = { kind: "artifact" as const, artifact_id: "art_out", media_type: "image/png", filename: "pack.png" };
    expect(isMediaResult({ picture })).toBe(true);
    expect(isStructuredResult({ picture })).toBe(false);
    expect(conversationCanvas({ locale: "en", source, run: { ...run, result: { picture } } })).toBeNull();
    expect(assistantPreview({ picture }, null, "en")).toEqual({ text: null, openedInCanvas: false });
  });

  it("treats long markdown as a document canvas", () => {
    const document = `${"#" }# Review\n\n${"word ".repeat(200)}`;
    expect(isDocumentResult({ answer: document })).toBe(true);
    expect(conversationCanvas({ locale: "en", source, run: { ...run, result: { answer: document } } })?.kind).toBe("document");
  });
});
