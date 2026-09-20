import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderConversationOperation, BuilderHarnessReceipt } from "@veyra/api-contracts";
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
    receipts: [],
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

function receipt(overrides: Partial<BuilderHarnessReceipt> = {}): BuilderHarnessReceipt {
  return {
    receipt_id: "receipt-1",
    operation_id: "op-1",
    conversation_id: "conv-1",
    project_id: "project-1",
    invocation_kind: "semantic_plan",
    sequence: 2,
    status: "success",
    started_at: "2026-09-18T00:00:02Z",
    completed_at: "2026-09-18T00:00:10Z",
    harness_mode: "create_agent",
    policy_version: "builder-policy-v1",
    policy_hash: "policyhashpolicyhashpolicyhashpolicyhashpolicyhashpolicyhashpol",
    output_contract: "AgentSemanticPlanV1",
    schema_version: "1.0",
    schema_hash: "schemahashschemahashschemahashschemahashschemahashschemahashsch",
    structured_mode: "strict_json_schema",
    project_snapshot_hash: "projecthashprojecthashprojecthashprojecthashprojecthashprojectha",
    catalog_snapshot_hash: "cataloghashcataloghashcataloghashcataloghashcataloghashcatalogha",
    included_categories: ["project_agents_metadata", "catalog_capabilities", "knowledge_metadata"],
    excluded_categories: ["knowledge_contents", "project_file_contents", "secrets", "credentials"],
    history_message_count: 2,
    context_size_bytes: 1200,
    request_size_bytes: 2400,
    provider_id: "moonshot",
    model: "kimi-k3",
    endpoint_kind: "chat_completions",
    provider_profile_status: "known",
    provider_profile_source: "probe",
    schema_profile: "mfjs",
    failure_stage: null,
    error_code: null,
    safe_provider_error_type: null,
    safe_provider_error_param: null,
    provider_request_id: "cmpl-safe",
    fallback_from: null,
    fallback_to: null,
    ...overrides,
  };
}

describe("BuilderActivityBlock Build details", () => {
  it("keeps Build details collapsed and hides hashes until Technical details opens", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "succeeded",
            receipts: [receipt()],
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.proposal.ready", label: "Preparing review", summary: "", facts: {}, created_at: "2026-09-18T00:00:10Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:18Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /构建 Agent · 已完成/ }));
    const details = screen.getByRole("button", { name: /构建详情/ });
    expect(details).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Moonshot/)).not.toBeInTheDocument();
    fireEvent.click(details);
    expect(screen.getByText("Moonshot · Kimi K3")).toBeInTheDocument();
    expect(screen.getByText("AgentSemanticPlan v1")).toBeInTheDocument();
    expect(screen.getByText("Strict JSON Schema")).toBeInTheDocument();
    expect(screen.getByText(/Knowledge 正文/)).toBeInTheDocument();
    expect(screen.queryByText(receipt().policy_hash)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /技术详情/ }));
    expect(screen.getByText(/policyhashpo/)).toBeInTheDocument();
  });

  it("shows a safe failure classification and truthful fallback", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "failed",
            error_code: "factory_rate_limited",
            receipts: [
              receipt({
                receipt_id: "r-strict",
                sequence: 2,
                status: "failed",
                structured_mode: "strict_json_schema",
                failure_stage: "provider_request",
                error_code: "factory_request_invalid",
                safe_provider_error_type: "invalid_request_error",
                safe_provider_error_param: "response_format.json_schema",
              }),
              receipt({
                receipt_id: "r-object",
                sequence: 3,
                status: "failed",
                structured_mode: "json_object",
                fallback_from: "strict_json_schema",
                fallback_to: "json_object",
                failure_stage: "provider_request",
                error_code: "factory_rate_limited",
              }),
            ],
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: {}, created_at: "2026-09-18T00:00:01Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.failed", label: "Failed", summary: "Factory model service is rate limited", facts: { http_status: "429" }, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /构建 Agent · 失败/ }));
    fireEvent.click(screen.getByRole("button", { name: /构建详情/ }));
    expect(screen.getByText("Provider 请求")).toBeInTheDocument();
    expect(screen.getAllByText("Rate limited").length).toBeGreaterThan(0);
    expect(screen.getAllByText("JSON Object").length).toBeGreaterThan(0);
    expect(screen.queryByText(/choices/)).not.toBeInTheDocument();
    expect(screen.queryByText(/moonshot flavored/)).not.toBeInTheDocument();
  });

  it("does not error when a deterministic operation has no receipt", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "succeeded",
            kind: "edit",
            target_kind: "agent",
            receipts: [],
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="en"
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Build Agent · completed/ }));
    fireEvent.click(screen.getByRole("button", { name: /Build details/ }));
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.queryByText(/No receipt found/i)).not.toBeInTheDocument();
  });
});
