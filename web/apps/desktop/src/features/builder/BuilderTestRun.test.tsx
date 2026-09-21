import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BuilderConversationOperation, BuilderConversationSnapshot } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { editAgent, editDraft } from "../../test/edit-proposals";
import { BuilderTestRun } from "./BuilderTestRun";

afterEach(() => cleanup());

function observation(overrides: Partial<NonNullable<BuilderConversationOperation["run_observation"]>> = {}): NonNullable<BuilderConversationOperation["run_observation"]> {
  return {
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
    duration_ms: 20,
    evidence_count: 1,
    classification: "none",
    explanation: "测试成功。",
    repair_proposal_id: null,
    repair_code: null,
    next_action: null,
    ...overrides,
  };
}

function operation(overrides: Partial<BuilderConversationOperation> = {}): BuilderConversationOperation {
  return {
    operation_id: "op-test",
    conversation_id: "conv-1",
    kind: "test_agent",
    target_kind: "agent",
    status: "succeeded",
    retry_of: null,
    error_code: null,
    proposal_id: null,
    run_id: "run-1",
    factory_session_id: null,
    created_at: "2026-09-20T00:00:00Z",
    updated_at: "2026-09-20T00:00:01Z",
    diagnostic: {},
    has_request: false,
    events: [
      { event_id: "e1", operation_id: "op-test", sequence: 0, kind: "builder.test_run.started", label: "Testing Agent", summary: "", facts: {}, created_at: "2026-09-20T00:00:00Z" },
      { event_id: "e2", operation_id: "op-test", sequence: 1, kind: "builder.test_run.completed", label: "Test succeeded", summary: "", facts: {}, created_at: "2026-09-20T00:00:01Z" },
      { event_id: "e3", operation_id: "op-test", sequence: 2, kind: "builder.operation.completed", label: "Completed", summary: "", facts: {}, created_at: "2026-09-20T00:00:01Z" },
    ],
    receipts: [],
    run_observation: observation(),
    ...overrides,
  };
}

function snapshotFor(next: BuilderConversationOperation): BuilderConversationSnapshot {
  return {
    schema_version: "1.0",
    conversation: {
      conversation_id: "conv-1",
      project_id: "project-1",
      title: "Test Agent",
      status: "active",
      created_at: "2026-09-20T00:00:00Z",
      updated_at: "2026-09-20T00:00:01Z",
      last_activity_at: "2026-09-20T00:00:01Z",
      last_operation_status: next.status,
    },
    messages: [],
    operations: [next],
    resolution: null,
    factory_session: null,
  };
}

function apiFor(overrides: Partial<LocalProjectApi> = {}): LocalProjectApi {
  const source = { ...editAgent, inputs: { text: "string" } };
  return {
    getDraft: vi.fn().mockResolvedValue(editDraft(source)),
    validate: vi.fn().mockResolvedValue({ schema_version: "1.0", valid: true, source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), file_hash: "d".repeat(64), dependencies: [], dependency_summary: { total: 0, ready: 0, attention: 0 }, runtime_ready: true, runtime_ready_scope: "agent_dependencies" }),
    runtimeReadiness: vi.fn().mockResolvedValue({
      schema_version: "1.0",
      project_id: "project-1",
      agent_id: "agent-1",
      ready: true,
      profile_source: "default",
      model: { required: true, configured: true, model_id: "translator-model", model_base_url: "https://example.test", model_api_key_env: "KEY" },
      dependency_summary: { total: 0, ready: 0, attention: 0 },
      dependencies: [],
      tool_checks: [],
      checks: [],
    }),
    ...overrides,
  } as unknown as LocalProjectApi;
}

describe("BuilderTestRun", () => {
  it("starts an explicit Runtime run and shows the actual Runtime model", async () => {
    const started = operation({ status: "succeeded" });
    const startBuilderTestRun = vi.fn().mockResolvedValue(snapshotFor(started));
    const onSnapshot = vi.fn();
    render(
      <ThemeProvider>
        <BuilderTestRun api={apiFor({ startBuilderTestRun })} projectId="project-1" agentId="agent-1" conversationId="conv-1" locale="zh" onSnapshot={onSnapshot} />
      </ThemeProvider>,
    );
    fireEvent.change(await screen.findByLabelText("测试输入"), { target: { value: "Hello world" } });
    fireEvent.click(screen.getByRole("button", { name: "测试 Agent" }));
    await waitFor(() => expect(startBuilderTestRun).toHaveBeenCalledWith("project-1", "conv-1", {
      agent_id: "agent-1",
      inputs: { text: "Hello world" },
      locale: "zh",
    }));
    expect(onSnapshot).toHaveBeenCalled();
  });

  it("does not show Test Agent before the Agent is validated", async () => {
    const api = apiFor({
      validate: vi.fn().mockResolvedValue({ schema_version: "1.0", valid: false, source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), file_hash: "d".repeat(64), dependencies: [], dependency_summary: { total: 0, ready: 0, attention: 0 }, runtime_ready: false, runtime_ready_scope: "agent_dependencies" }),
      startBuilderTestRun: vi.fn(),
    });
    render(
      <ThemeProvider>
        <BuilderTestRun api={api} projectId="project-1" agentId="agent-1" conversationId="conv-1" locale="zh" onSnapshot={() => undefined} />
      </ThemeProvider>,
    );
    expect(await screen.findByText("请先完成结构验证，再测试 Agent。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "测试 Agent" })).not.toBeInTheDocument();
    expect(api.startBuilderTestRun).not.toHaveBeenCalled();
  });

  it("explains runtime_not_configured without labeling Builder Kimi as the Runtime model", async () => {
    const failed = operation({
      status: "failed",
      run_id: null,
      error_code: "runtime_not_configured",
      events: [
        { event_id: "e1", operation_id: "op-test", sequence: 0, kind: "builder.test_run.started", label: "Testing Agent", summary: "", facts: {}, created_at: "2026-09-20T00:00:00Z" },
        { event_id: "e2", operation_id: "op-test", sequence: 1, kind: "builder.test_run.failed", label: "Test failed", summary: "", facts: {}, created_at: "2026-09-20T00:00:01Z" },
      ],
      run_observation: observation({
        run_id: null,
        status: "failed",
        runtime_model_id: "",
        output_summary: null,
        failure_code: "runtime_not_configured",
        classification: "user_action",
        explanation: "Agent 结构已经有效，但还没有配置运行模型。Veyra Builder 的 Kimi 不会自动成为这个 Agent 的 Runtime。",
        next_action: "open_runtime_settings",
      }),
    });
    render(
      <ThemeProvider>
        <BuilderTestRun
          api={apiFor({
            runtimeReadiness: vi.fn().mockResolvedValue({
              schema_version: "1.0",
              project_id: "project-1",
              agent_id: "agent-1",
              ready: false,
              profile_source: "default",
              model: { required: true, configured: false, model_id: "", model_base_url: "", model_api_key_env: "" },
              dependency_summary: { total: 0, ready: 0, attention: 0 },
              dependencies: [],
              tool_checks: [],
              checks: [],
            }),
            startBuilderTestRun: vi.fn().mockResolvedValue(snapshotFor(failed)),
          })}
          projectId="project-1"
          agentId="agent-1"
          conversationId="conv-1"
          locale="zh"
          operation={failed}
          onSnapshot={() => undefined}
        />
      </ThemeProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/还没有配置运行模型/);
    expect(screen.getByRole("link", { name: "打开 Runtime 设置" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/design");
    expect(screen.getByText(/未配置/)).toBeInTheDocument();
    expect(screen.queryByText("Kimi K3")).not.toBeInTheDocument();
  });

  it("offers a repair proposal only for deterministic failures and keeps rerun explicit", async () => {
    const failed = operation({
      status: "failed",
      error_code: "tool_permission_denied",
      events: [
        { event_id: "e1", operation_id: "op-test", sequence: 0, kind: "builder.test_run.failed", label: "Test failed", summary: "", facts: {}, created_at: "2026-09-20T00:00:00Z" },
      ],
      run_observation: observation({
        status: "failed",
        output_summary: null,
        failure_code: "tool_permission_denied",
        classification: "repairable",
        explanation: "当前运行权限不允许这项操作。",
        repair_code: "permission_denied",
        next_action: "create_repair_proposal",
      }),
    });
    const proposeBuilderTestRepair = vi.fn().mockResolvedValue(snapshotFor({ ...failed, proposal_id: "proposal-1" }));
    const startBuilderTestRun = vi.fn();
    const listEditProposals = vi.fn().mockResolvedValue({ schema_version: "1.0", proposals: [] });
    render(
      <ThemeProvider>
        <BuilderTestRun
          api={apiFor({ startBuilderTestRun, proposeBuilderTestRepair, listEditProposals })}
          projectId="project-1"
          agentId="agent-1"
          conversationId="conv-1"
          locale="zh"
          operation={failed}
          onSnapshot={() => undefined}
        />
      </ThemeProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "创建修复提案" }));
    await waitFor(() => expect(proposeBuilderTestRepair).toHaveBeenCalledWith("project-1", "conv-1", "op-test", { locale: "zh" }));
    expect(startBuilderTestRun).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "再次运行" })).toBeInTheDocument();
  });

  it("does not offer repair for environment failures", async () => {
    const failed = operation({
      status: "failed",
      error_code: "runtime_rate_limited",
      run_observation: observation({
        status: "failed",
        output_summary: null,
        failure_code: "runtime_rate_limited",
        classification: "environment",
        explanation: "Agent Runtime 模型当前被限流。",
        next_action: "retry_later",
      }),
    });
    render(
      <ThemeProvider>
        <BuilderTestRun api={apiFor({ startBuilderTestRun: vi.fn() })} projectId="project-1" agentId="agent-1" conversationId="conv-1" locale="zh" operation={failed} onSnapshot={() => undefined} />
      </ThemeProvider>,
    );
    expect(await screen.findByText(/限流/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建修复提案" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看运行详情" })).toHaveAttribute("href", "#/projects/project-1/agents/agent-1/run?run_id=run-1");
  });
});
