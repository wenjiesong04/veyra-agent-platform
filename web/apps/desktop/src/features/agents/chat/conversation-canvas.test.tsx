import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, AgentSource, JsonObject } from "@veyra/api-contracts";
import type { LiveRunSession } from "../../studio/live-run";
import { ConversationCanvasPanel } from "./conversation-canvas";
import type { ConversationCanvasKind } from "./canvas-artifact";
import "./conversation.css";

const source: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow",
  agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "",
  inputs: { request: "string" }, outputs: { result: "string" },
  nodes: [
    { id: "start", component_type: "Start" },
    { id: "model", component_type: "Agent", model_ref: "model.primary" },
    { id: "output", component_type: "Output", output_name: "result" },
  ],
  transitions: [{ from: "start", port: "next", to: "model" }, { from: "model", port: "next", to: "output" }],
  extensions: { veyra: { runtime_profile: "guarded-local", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 80 }, model: { x: 240, y: 80 }, output: { x: 480, y: 80 } } },
  lock: {},
};

function panel(kind: ConversationCanvasKind, result: JsonObject) {
  const run: AgentRunResponse = {
    schema_version: "1.0", run_id: "run-1", project_id: "project-1", agent_id: source.agent_id,
    version_id: "version-1", status: "unverified", result, error: null,
    created_at: "2026-10-18T00:00:00Z", finished_at: "2026-10-18T00:00:01Z",
  };
  const live: LiveRunSession = {
    run, error: "", busy: false, start: vi.fn(), sendCommand: vi.fn(), restore: vi.fn(), clear: vi.fn(),
  };
  return render(<ConversationCanvasPanel spec={{ kind, title: `${kind} content` }} source={source} catalog={[]} live={live} locale="en" onClose={vi.fn()} />);
}

afterEach(cleanup);

describe("conversation result carriers", () => {
  it("opens the full safe document instead of an execution graph", () => {
    const document = `## Known facts\n${"Original fact and citation.\n".repeat(40)}<script>not executable</script>`;
    const result = { result: document };
    const before = JSON.stringify(result);
    const { container } = panel("document", result);
    expect(screen.getByRole("heading", { name: "Known facts", level: 2 })).toBeInTheDocument();
    const reader = container.querySelector(".runtime-reading-markdown");
    expect(reader?.textContent?.match(/Original fact and citation\./g)).toHaveLength(40);
    expect(reader).toHaveTextContent("<script>not executable</script>");
    expect(container.querySelector(".agent-convo-flow")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector(".runtime-output-reading")).not.toBeNull();
    expect(JSON.stringify(result)).toBe(before);
  });

  it("keeps every field beside a table rather than extracting only the first array", () => {
    const result = { summary: "All differences retained", total: 60.1, differences: [{ order: "O002", amount: 0.1 }, { order: "O003", amount: 30 }] };
    const before = JSON.stringify(result);
    const { container } = panel("table", result);
    expect(screen.getByText("All differences retained")).toBeInTheDocument();
    expect(screen.getByText("60.1")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Output items" })).toBeInTheDocument();
    expect(screen.getByText("O002")).toBeInTheDocument();
    expect(screen.getByText("O003")).toBeInTheDocument();
    expect(container.querySelector(".agent-convo-flow")).toBeNull();
    expect(JSON.stringify(result)).toBe(before);
  });

  it("uses the existing reader for structured results without raw JSON or a graph", () => {
    const { container } = panel("result", { summary: "Reviewed result", findings: ["Missing approver", "Conflicting dates"] });
    expect(screen.getByText("Reviewed result")).toBeInTheDocument();
    expect(screen.getByText("Conflicting dates")).toBeInTheDocument();
    expect(container.querySelector(".agent-convo-flow")).toBeNull();
    expect(container.querySelector("pre")).toBeNull();
  });

  it("keeps image artifacts in their existing card instead of adding a graph", () => {
    const { container } = panel("result", { picture: { kind: "artifact", artifact_id: "image-1", media_type: "image/png", filename: "front.png" } });
    expect(screen.getByText("front.png").closest(".runtime-artifact-card")).not.toBeNull();
    expect(container.querySelector(".agent-convo-flow")).toBeNull();
  });

  it("retains an explicit diagram carrier and contains its wide geometry in its own scroll area", () => {
    const { container } = panel("run", { result: "Not a document carrier" });
    expect(container.querySelectorAll(".agent-convo-flow-node")).toHaveLength(3);
    expect(screen.getByRole("region", { name: "Execution diagram" })).toHaveClass("agent-convo-flow-scroll");
    expect(container.querySelector(".agent-convo-flow")?.parentElement).toHaveClass("agent-convo-flow-scroll");
    expect(container.querySelector(".runtime-output-reading")).toBeNull();
  });

  it("constrains document layout to one shrinkable track with a safe wrapping reader", () => {
    const { container } = panel("document", { result: "very-long-unbroken-token".repeat(100) });
    const body = screen.getByRole("region", { name: "document content" });
    expect(body).toHaveAttribute("tabindex", "0");
    expect(getComputedStyle(body).gridTemplateColumns).toBe("minmax(0, 1fr)");
    expect(getComputedStyle(body).minWidth).toBe("0");
    expect(getComputedStyle(body).overflow).toBe("auto");
    expect(getComputedStyle(container.querySelector(".agent-convo-document")!).overflowWrap).toBe("anywhere");
  });
});
