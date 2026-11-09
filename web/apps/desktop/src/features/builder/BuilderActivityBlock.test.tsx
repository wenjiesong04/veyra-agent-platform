import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderConversationOperation, BuilderHarnessReceipt, FactorySession } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { BuilderActivityBlock } from "./BuilderActivityBlock";

afterEach(() => { cleanup(); vi.useRealTimers(); });

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
  it("keeps total elapsed time increasing when a repair restarts a stage", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T00:05:00Z"));
    const first = operation({
      events: [{ event_id: "stage1", operation_id: "op-1", sequence: 0, kind: "builder.specification.started", label: "Planning", summary: "", facts: {}, created_at: "2026-09-18T00:04:45Z" }],
      receipts: [receipt(), receipt({ receipt_id: "r2", sequence: 1 })],
    });
    const view = render(<ThemeProvider><BuilderActivityBlock operation={first} locale="zh" /></ThemeProvider>);
    expect(screen.getByText("总耗时 5:00 · 2 次模型请求")).toBeInTheDocument();
    const repaired = { ...first, events: [...first.events, { ...first.events[0], event_id: "stage2", sequence: 1, created_at: "2026-09-18T00:04:59Z" }], receipts: [...first.receipts, receipt({ receipt_id: "r3", sequence: 2 })] };
    view.rerender(<ThemeProvider><BuilderActivityBlock operation={repaired} locale="zh" /></ThemeProvider>);
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByText("总耗时 5:02 · 3 次模型请求")).toBeInTheDocument();
  });
  it.each(["factory_quota_exhausted", "factory_rate_limited"])("keeps %s historical quota evidence and offers only a manual retained-plan recovery", (code) => {
    const onRetry = vi.fn();
    const onContinueReview = vi.fn();
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: code, diagnostic: { http_status: "429", provider_error_type: "exceeded_current_quota_error" } })} locale="zh" onRetry={onRetry} onContinueReview={onContinueReview} /></ThemeProvider>);
    expect(screen.getByText("服务商账户余额或配额不可用，请检查账户后再继续")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "继续检查保留方案" })).not.toBeInTheDocument();
    expect(onContinueReview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "账户恢复后继续检查" }));
    expect(onContinueReview).toHaveBeenCalledTimes(1);
    expect(onRetry).not.toHaveBeenCalled();
    expect(screen.getByText("服务商账户余额或配额不可用，请检查账户后再继续")).toBeInTheDocument();
    expect(screen.queryByText("服务商暂时限流")).not.toBeInTheDocument();
  });
  it.each(["create_agent", "create_workflow"] as const)("offers an explicit retained-plan check next to Retry for failed %s", (kind) => {
    const onRetry = vi.fn();
    const onContinueReview = vi.fn();
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ kind, status: "failed", error_code: "factory_generation_blocked" })} locale="zh" onRetry={onRetry} onContinueReview={onContinueReview} /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "继续检查保留方案" }));
    expect(onContinueReview).toHaveBeenCalledTimes(1);
    expect(onRetry).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onContinueReview).toHaveBeenCalledTimes(1);
  });

  it("does not offer model regeneration while a reviewed proposal can continue applying", () => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: "resource_unbound", proposal_id: "proposal-1", diagnostic: { stage: "agent_creation_apply" } })} factorySession={{ session_id: "session-1", state: "review" } as FactorySession} locale="en" onRetry={vi.fn()} onContinueReview={vi.fn()} /></ThemeProvider>);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check retained plan" })).not.toBeInTheDocument();
  });

  it.each<Partial<BuilderConversationOperation>>([
    { kind: "edit" as const },
    { kind: "test_agent" as const },
    { factory_session_id: null },
    { status: "in_progress" as const },
    { status: "waiting" as const },
    { diagnostic: { blocked_reason: "unsupported_shape" } },
    { diagnostic: { resolution_status: "unsupported" } },
  ])("does not offer a retained-plan check for an ineligible operation %j", (overrides) => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: "factory_generation_blocked", ...overrides })} locale="en" onRetry={vi.fn()} onContinueReview={vi.fn()} /></ThemeProvider>);
    expect(screen.queryByRole("button", { name: "Check retained plan" })).not.toBeInTheDocument();
  });
  it("shows a specific failure and model cost evidence without expanding details", () => {
    const cause = "The plan needs saved project state but has no executable state contract.";
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: "factory_generation_blocked", diagnostic: { validation_code: "persistent_state_not_represented", validation_summary: cause }, receipts: [receipt(), receipt({ receipt_id: "r2", sequence: 1 })] })} locale="en" /></ThemeProvider>);
    expect(screen.getByText(cause)).toBeInTheDocument();
    expect(screen.getByText(/2 model requests/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build Agent · generation failed" })).toHaveAttribute("aria-expanded", "false");
  });
  it("shows the complete review feedback and keeps a successful model request distinct from the failed build", () => {
    const feedback = `No executable repair and recheck path. ${"The failed check currently routes directly to output. ".repeat(8)}\nCheck the final design and revise it before publishing.`;
    render(<ThemeProvider><BuilderActivityBlock operation={operation({
      status: "failed", error_code: "factory_generation_blocked",
      diagnostic: { stage: "coverage_review", validation_code: "coverage_review_incomplete", validation_summary: "Review found an executable repair gap." },
      generation_feedback: [feedback, "Budget and dimensions are only written in instructions.\nCheck dimensions and total cost."],
      receipts: [receipt({ output_contract: "TaskCoverageV1" })],
    })} locale="en" /></ThemeProvider>);
    expect(screen.getByText("Review found an executable repair gap.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Build Agent · generation failed" }));
    expect(screen.getByText("Plan review").closest("li")).toHaveAttribute("data-state", "failed");
    fireEvent.click(screen.getByRole("button", { name: "Build details" }));
    expect(screen.getByText("Requirement coverage review")).toBeInTheDocument();
    expect(screen.getByText("Review feedback 1").nextElementSibling?.textContent).toBe(feedback);
    expect(screen.getByText("Review feedback 2").nextElementSibling?.textContent).toBe("Budget and dimensions are only written in instructions.\nCheck dimensions and total cost.");
    expect(screen.getByText("Success")).toBeInTheDocument();
  });
  it("keeps an unsupported task distinct from a retryable generator check failure", () => {
    const onRetry = vi.fn();
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: "factory_generation_blocked", diagnostic: { blocked_reason: "unsupported_shape" } })} locale="en" onRetry={onRetry} /></ThemeProvider>);
    expect(screen.getByText("Task support limitation")).toBeInTheDocument();
    expect(screen.getByText(/This task is not fully supported yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Build Agent · generation failed" }));
    fireEvent.click(screen.getByRole("button", { name: "Build details" }));
    expect(screen.getByText(/Review Project resources for available capabilities/)).toBeInTheDocument();
    expect(onRetry).not.toHaveBeenCalled();
  });

  it.each(["succeeded", "failed"] as const)("labels a %s but blocked generation truthfully and stops its stale plan stage", (status) => {
    const onRetry = vi.fn();
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status,
            error_code: status === "failed" ? "factory_generation_blocked" : null,
            diagnostic: status === "failed" ? { validation_kind: "task_io_invalid", validation_issue: "$.outputs[0]: required: name" } : {},
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.semantic_plan.started", label: "Planning", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: status === "failed" ? "builder.operation.failed" : "builder.operation.completed", label: "Ended", summary: "", facts: {}, created_at: "2026-09-18T00:00:18Z" },
            ],
          })}
          factorySession={status === "succeeded" ? { blocked_reason: "Invalid output mapping" } as FactorySession : null}
          locale="zh"
          onRetry={onRetry}
        />
      </ThemeProvider>,
    );
    const toggle = screen.getByRole("button", { name: "构建 Agent · 生成失败" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("生成失败")).toBeInTheDocument();
    expect(screen.getByText(/原始需求已保留，可以重试或展开构建详情/)).toBeInTheDocument();
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText("整理规格").closest("li")).toHaveAttribute("data-state", "failed");
    expect(screen.queryByText("验证通过")).not.toBeInTheDocument();
    expect(document.querySelector(".builder-activity-pulse")).toBeNull();
    if (status === "failed") {
      fireEvent.click(screen.getByRole("button", { name: "构建详情" }));
      expect(screen.getByText("生成的输入或输出定义存在错误，自动修复未完成。")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "技术详情" }));
      expect(screen.getByText("$.outputs[0]: required: name")).toBeInTheDocument();
    }
    expect(onRetry).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a compilation failure at compilation rather than task planning", () => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", error_code: "factory_generation_blocked", diagnostic: { blocked_reason: "compose_failed" }, events: [
      { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.specification.completed", label: "Ended", summary: "", facts: { target_kind: "blocked", blocked_reason: "compose_failed" }, created_at: "2026-09-18T00:00:18Z" },
    ] })} locale="zh" /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "构建 Agent · 生成失败" }));
    expect(screen.getByText("编译").closest("li")).toHaveAttribute("data-state", "failed");
    expect(screen.getByText("整理规格").closest("li")).toHaveAttribute("data-state", "done");
  });

  it("does not pulse an unfinished stage after a terminal failure", () => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "failed", events: [
      { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.compile.started", label: "Compiling", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
    ] })} locale="zh" /></ThemeProvider>);
    fireEvent.click(screen.getByRole("button", { name: "构建 Agent · 失败" }));
    expect(document.querySelector(".builder-activity-pulse")).toBeNull();
  });

  it("keeps a historical blocked operation blocked without its previous Factory session", () => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({ status: "succeeded", events: [
      { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.semantic_plan.started", label: "Planning", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
      { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.specification.completed", label: "Resolved", summary: "", facts: { target_kind: "blocked", blocked_reason: "State requirement cannot be represented" }, created_at: "2026-09-18T00:00:18Z" },
      { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.operation.completed", label: "Ended", summary: "", facts: {}, created_at: "2026-09-18T00:00:18Z" },
    ] })} locale="zh" /></ThemeProvider>);
    expect(screen.getByRole("button", { name: "构建 Agent · 生成失败" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
    expect(document.querySelector(".builder-activity-pulse")).toBeNull();
  });

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
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
    expect(screen.queryByText("理解需求")).not.toBeInTheDocument();
  });

  it("labels an unsupported create as not created rather than a completed build", () => {
    render(<ThemeProvider><BuilderActivityBlock operation={operation({
      kind: "create_workflow",
      target_kind: "workflow",
      status: "succeeded",
      events: [
        { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { status: "unsupported", create_kind: "workflow" }, created_at: "2026-09-18T00:00:01Z" },
        { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
      ],
    })} locale="zh" /></ThemeProvider>);
    const toggle = screen.getByRole("button", { name: "构建 Workflow · 未创建" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByText("未生成方案")).toBeInTheDocument();
    expect(screen.queryByText("验证通过")).not.toBeInTheDocument();
  });

  it("keeps a running operation expanded on the current server stage", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.intent.resolved", label: "Understanding request", summary: "", facts: { intent: "create", create_kind: "agent" }, created_at: "2026-09-18T00:00:01Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.specification.started", label: "Specifying Agent", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button", { name: /正在构建 Agent/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("整理规格").length).toBeGreaterThan(0);
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
    expect(screen.getByText("服务商暂时限流")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  });

  it("uses the event span for duration instead of a drifted operation clock", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            status: "succeeded",
            created_at: "2026-09-18T00:00:00Z",
            updated_at: "2026-09-18T14:11:52Z",
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:18Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    expect(screen.getByText("18s")).toBeInTheDocument();
    expect(screen.queryByText(/50912s|14h/)).not.toBeInTheDocument();
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
    expect(screen.getAllByText("服务商暂时限流").length).toBeGreaterThan(0);
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

  it("renders a Test Agent activity from Runtime observation without harness receipts", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            kind: "test_agent",
            status: "succeeded",
            run_id: "run-1",
            receipts: [],
            run_observation: {
              run_id: "run-1",
              agent_id: "agent-1",
              version_id: "version-1",
              status: "unverified",
              runtime_model_id: "translator-model",
              runtime_model_source: "agent",
              output_summary: "你好，世界",
              failure_code: null,
              failed_node: null,
              tool_failure: null,
              knowledge_failure: null,
              approval_required: false,
              duration_ms: 40,
              evidence_count: 1,
              classification: "none",
              explanation: "测试成功。",
              repair_proposal_id: null,
              repair_code: null,
              next_action: null,
            },
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.operation.started", label: "Started", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.test_run.started", label: "Testing Agent", summary: "", facts: { runtime_model_id: "translator-model" }, created_at: "2026-09-18T00:00:01Z" },
              { event_id: "e3", operation_id: "op-1", sequence: 2, kind: "builder.test_run.completed", label: "Test succeeded", summary: "", facts: { run_id: "run-1" }, created_at: "2026-09-18T00:00:02Z" },
              { event_id: "e4", operation_id: "op-1", sequence: 3, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-18T00:00:02Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    const toggle = screen.getByRole("button", { name: /测试 Agent · 完成/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByText("你好，世界")).toBeInTheDocument();
    expect(screen.getByText("translator-model")).toBeInTheDocument();
    expect(screen.queryByText("Kimi K3")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /构建详情/ })).not.toBeInTheDocument();
  });

  it("keeps waiting approval expanded and does not treat it as failure", () => {
    render(
      <ThemeProvider>
        <BuilderActivityBlock
          operation={operation({
            kind: "test_agent",
            status: "waiting",
            run_id: "run-wait",
            run_observation: {
              run_id: "run-wait",
              agent_id: "agent-1",
              version_id: "version-1",
              status: "waiting",
              runtime_model_id: "kimi-k3",
              runtime_model_source: "host",
              output_summary: null,
              failure_code: null,
              failed_node: null,
              tool_failure: null,
              knowledge_failure: null,
              approval_required: true,
              duration_ms: null,
              evidence_count: 0,
              classification: "none",
              explanation: "等待人工批准。",
              repair_proposal_id: null,
              repair_code: null,
              next_action: "approve_or_reject",
            },
            events: [
              { event_id: "e1", operation_id: "op-1", sequence: 0, kind: "builder.test_run.started", label: "Testing Agent", summary: "", facts: {}, created_at: "2026-09-18T00:00:00Z" },
              { event_id: "e2", operation_id: "op-1", sequence: 1, kind: "builder.test_run.waiting_approval", label: "Waiting for approval", summary: "", facts: {}, created_at: "2026-09-18T00:00:01Z" },
            ],
          })}
          locale="zh"
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button", { name: /测试 Agent · 等待批准/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("等待批准").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  });
});
