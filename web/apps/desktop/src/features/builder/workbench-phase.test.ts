import { describe, expect, it } from "vitest";
import type { BuilderConversationOperation, FactorySession } from "@veyra/api-contracts";
import { workbenchPhase } from "./workbench-phase";

function operation(kinds: string[], status: BuilderConversationOperation["status"] = "in_progress"): BuilderConversationOperation {
  return {
    operation_id: "op-1",
    conversation_id: "conv-1",
    kind: "create_agent",
    target_kind: "agent",
    status,
    retry_of: null,
    error_code: null,
    proposal_id: null,
    run_id: null,
    factory_session_id: "session-1",
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:01Z",
    diagnostic: {},
    has_request: true,
    events: kinds.map((kind, sequence) => ({
      event_id: `evt-${sequence}`,
      operation_id: "op-1",
      sequence,
      kind: kind as BuilderConversationOperation["events"][number]["kind"],
      label: kind,
      summary: "",
      facts: {},
      created_at: "2026-09-18T00:00:00Z",
    })),
    receipts: [],
  };
}

const session = { state: "generating" } as FactorySession;

describe("workbenchPhase", () => {
  it("follows server events instead of a timer script", () => {
    expect(workbenchPhase(operation(["builder.operation.started", "builder.intent.started"]), session, null)).toBe("understanding");
    expect(workbenchPhase(operation(["builder.semantic_plan.started"]), session, null)).toBe("planning");
    expect(workbenchPhase(operation(["builder.compile.started"]), session, null)).toBe("compiling");
    expect(workbenchPhase(operation(["builder.validation.started"]), session, null)).toBe("validating");
    expect(workbenchPhase(operation(["builder.proposal.ready"], "waiting"), { ...session, state: "review" }, null)).toBe("review");
    expect(workbenchPhase(operation(["builder.proposal.ready"], "failed"), { ...session, state: "missing_capability" }, null)).toBe("missing");
    expect(workbenchPhase({
      ...operation(["builder.capabilities.resolved", "builder.operation.failed"], "failed"),
      error_code: "factory_missing_capability",
    }, null, null)).toBe("missing");
    expect(workbenchPhase(operation(["builder.operation.completed"], "succeeded"), { ...session, state: "completed" }, "agent-1")).toBe("completed");
  });
});
