import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderConversationOperation } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { BuilderActivityBlock } from "./BuilderActivityBlock";

afterEach(() => cleanup());

function operation(overrides: Partial<BuilderConversationOperation> = {}): BuilderConversationOperation {
  return {
    operation_id: "op-1",
    conversation_id: "conv-1",
    kind: "create_agent",
    target_kind: "agent",
    status: "in_progress",
    retry_of: null,
    error_code: null,
    proposal_id: null,
    run_id: null,
    factory_session_id: "session-1",
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:18Z",
    diagnostic: {},
    has_request: true,
    events: [],
    ...overrides,
  };
}

describe("BuilderActivityBlock", () => {
  it("collapses completed operations and hides failure retry", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "succeeded",
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.proposal.ready", label: "Preparing review", summary: "", facts: {}, created_at: "2026-09-18T00:00:10Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:18Z" },
            ],
          })}
          locale="zh"
          onRetry={() => undefined}
        />
      </ThemeProvider>,
    );
    const toggle = screen.getByRole("button", { name: /构建 Agent · 已完成/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("18s")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(screen.queryByText("理解需求")).not.toBeInTheDocument();
  });

  it("keeps a running operation expanded on the current server stage", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { intent: "create", create_kind: "agent" }, created_at: "2026-09-18T00:00:01Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.semantic_plan.started", label: "Planning Agent", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button", { name: /正在构建 Agent/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("生成方案").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  });

  it("shows Rate limited on the planning step with an operation retry", () => {
    const onRetry = vi.fn();
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "failed",
            error_code: "factory_rate_limited",
            diagnostic: { http_status: "429", error_code: "factory_rate_limited" },
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { intent: "create", create_kind: "agent" }, created_at: "2026-09-18T00:00:01Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.failed", label: "Failed", summary: "Factory model service is rate limited", facts: { http_status: "429" }, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="zh"
          onRetry={onRetry}
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button", { name: /构建 Agent · 失败/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Rate limited")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  });
});
