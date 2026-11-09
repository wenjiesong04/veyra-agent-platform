import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, EvaluationReport, EvaluationSpec, WorkflowRunResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { RunEvaluationPanel } from "./RunEvaluationPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const run: AgentRunResponse = {
  schema_version: "1.0", project_id: "project-1", agent_id: "agent-1", run_id: "run-1", version_id: "version-1", status: "unverified",
  result: { "汇总.金额": { "订单": [{ "总价": "9007199254740993.0001" }] }, total: 42, rows: ["a", "b"] }, error: null,
  created_at: "2026-10-15T00:00:00Z", finished_at: "2026-10-15T00:01:00Z", events: [],
};
const spec: EvaluationSpec = { version: "1", version_id: run.version_id, checks: [{ id: "condition-1", label: "Expected total", required: true, path: ["total"], method: "equals", expected: 42, baseline: { kind: "reference", reference: "approved.csv", revision: "v2" } }] };

function report(overrides: Partial<EvaluationReport> = {}): EvaluationReport {
  return {
    schema_version: "1.0", evaluator_version: "1", scope: "declared_checks", evaluation_id: "evaluation-1", project_id: run.project_id,
    target_kind: "agent", target_id: run.agent_id, run_id: run.run_id, version_id: run.version_id, run_status: run.status,
    source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), spec_hash: "d".repeat(64), input_hash: "e".repeat(64), input_evidence: "persisted", result_hash: "f".repeat(64),
    created_at: run.finished_at!, spec, decision: "accepted", checks: spec.checks.map((check) => ({ ...check, status: "pass", code: "baseline_match", baseline: check.baseline!, evidence: [] })), output_contract: "pass", independent_scope: "baseline_comparison_and_artifact_integrity_only", ...overrides,
  };
}

function apiWith(overrides: Partial<LocalProjectApi> = {}): LocalProjectApi {
  return {
    getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [] }),
    evaluateAgentRun: vi.fn().mockImplementation(async (_p, _a, _r, submitted) => report({ spec: submitted })),
    commandAgentRun: vi.fn(), runAgent: vi.fn(), commandWorkflowRun: vi.fn(), runWorkflow: vi.fn(), ...overrides,
  } as unknown as LocalProjectApi;
}

function mount(api: LocalProjectApi, next: AgentRunResponse | WorkflowRunResponse = run, locale: "zh" | "en" = "en") {
  return render(<ThemeProvider><RunEvaluationPanel api={api} run={next} locale={locale} /></ThemeProvider>);
}

async function condition(user = userEvent.setup()) {
  await screen.findByText("No evaluation reports yet.");
  await user.click(screen.getByRole("button", { name: "Add condition" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 1" }), JSON.stringify("total"));
  await user.type(screen.getByRole("textbox", { name: "Expected JSON 1" }), "42");
  await user.type(screen.getByRole("textbox", { name: "Baseline reference 1" }), "approved.csv");
  await user.type(screen.getByRole("textbox", { name: "Baseline revision 1" }), "v2");
  return user;
}

describe("Run result acceptance", () => {
  it("keeps nested reserved-looking and empty keys selectable without confusing whole-value selection", async () => {
    const api = apiWith();
    mount(api, { ...run, result: { result: { "$schema": { "": 1 } } } });
    const user = userEvent.setup();
    await screen.findByText("No evaluation reports yet.");
    await user.click(screen.getByRole("button", { name: "Add condition" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 1" }), JSON.stringify("result"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 2" }), JSON.stringify("$schema"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 3" }), JSON.stringify(""));
    await user.type(screen.getByRole("textbox", { name: "Expected JSON 1" }), "1");
    await user.type(screen.getByRole("textbox", { name: "Baseline reference 1" }), "answer");
    await user.type(screen.getByRole("textbox", { name: "Baseline revision 1" }), "1");
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await waitFor(() => expect(api.evaluateAgentRun).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.evaluateAgentRun!).mock.calls[0][3].checks[0].path).toEqual(["result", "$schema", ""]);
  });

  it("starts a new explicit evaluation after a known success even with unchanged conditions", async () => {
    const api = apiWith(); mount(api);
    const user = await condition();
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await screen.findByText("Selected conditions accepted");
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await waitFor(() => expect(api.evaluateAgentRun).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.evaluateAgentRun!).mock.calls;
    expect(calls[0][3]).toEqual(calls[1][3]);
    expect(calls[0][4].idempotencyKey).not.toBe(calls[1][4].idempotencyKey);
  });

  it("only reads history, never starts or approves a Run, and requires explicit expected truth", async () => {
    const api = apiWith(); mount(api);
    const user = userEvent.setup();
    await screen.findByText("No evaluation reports yet.");
    expect(api.getAgentRunEvaluations).toHaveBeenCalledExactlyOnceWith("project-1", "agent-1", "run-1");
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Add condition" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 1" }), JSON.stringify("total"));
    expect(screen.getByRole("textbox", { name: "Expected JSON 1" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "Baseline reference 1" })).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    expect(await screen.findByText("Condition 1 needs a baseline reference and revision.")).toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    for (const method of [api.commandAgentRun, api.runAgent, api.commandWorkflowRun, api.runWorkflow]) expect(method).not.toHaveBeenCalled();
  });

  it("preserves dotted Chinese keys, array segments and exact decimal text", async () => {
    const api = apiWith(); mount(api); const user = userEvent.setup();
    await screen.findByText("No evaluation reports yet.");
    await user.click(screen.getByRole("button", { name: "Add condition" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 1" }), JSON.stringify("汇总.金额"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 2" }), JSON.stringify("订单"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 3" }), JSON.stringify("0"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Output field 1 4" }), JSON.stringify("总价"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Method 1" }), "number_equals");
    await user.type(screen.getByRole("textbox", { name: "Expected decimal text 1" }), "9007199254740993.0001");
    await user.type(screen.getByRole("textbox", { name: "Baseline reference 1" }), "signed.xlsx");
    await user.type(screen.getByRole("textbox", { name: "Baseline revision 1" }), "v1");
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await waitFor(() => expect(api.evaluateAgentRun).toHaveBeenCalledTimes(1));
    const submitted = vi.mocked(api.evaluateAgentRun!).mock.calls[0];
    expect(submitted.slice(0, 3)).toEqual(["project-1", "agent-1", "run-1"]);
    expect(submitted[3]).toMatchObject({ version_id: "version-1", checks: [{ path: ["汇总.金额", "订单", "0", "总价"], method: "number_equals", expected: "9007199254740993.0001" }] });
    expect(submitted[4].idempotencyKey).toBeTruthy();
    expect(run.status).toBe("unverified");
  });

  it("suppresses double submit, preserves a stable key on unknown-result manual retry, and changes it for edited conditions", async () => {
    let reject: (cause: Error) => void = () => undefined;
    const pending = new Promise<EvaluationReport>((_resolve, fail) => { reject = fail; });
    const evaluateAgentRun = vi.fn().mockReturnValueOnce(pending).mockRejectedValue(new Error("Response unknown"));
    const api = apiWith({ evaluateAgentRun }); mount(api); const user = await condition();
    const button = screen.getByRole("button", { name: "Assess selected conditions" });
    fireEvent.click(button); fireEvent.click(button);
    expect(evaluateAgentRun).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Assessing…" })).toBeDisabled();
    reject(new Error("Response unknown"));
    await screen.findByText("Response unknown");
    await waitFor(() => expect(screen.getByRole("button", { name: "Assess selected conditions" })).toBeEnabled());
    expect(api.getAgentRunEvaluations).toHaveBeenCalledTimes(2);
    expect(evaluateAgentRun).toHaveBeenCalledTimes(1);
    const key = evaluateAgentRun.mock.calls[0][4].idempotencyKey;
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Assess selected conditions" })).toBeEnabled());
    expect(evaluateAgentRun.mock.calls[1][4].idempotencyKey).toBe(key);
    await user.clear(screen.getByRole("textbox", { name: "Expected JSON 1" }));
    await user.type(screen.getByRole("textbox", { name: "Expected JSON 1" }), "43");
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    expect(evaluateAgentRun.mock.calls[2][4].idempotencyKey).not.toBe(key);
    expect(screen.getByRole("textbox", { name: "Expected JSON 1" })).toHaveValue("43");
  });

  it("supports explicit history reuse, optional checks and set/physical-review methods without hidden expectations", async () => {
    const historical = report();
    const api = apiWith({ getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [historical] }) });
    mount(api, { ...run, result: { total: 99, rows: ["a"] } }); const user = userEvent.setup();
    await screen.findByText("Selected conditions accepted");
    expect(screen.queryByRole("textbox", { name: "Expected JSON 1" })).not.toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Edit these conditions" }));
    expect(screen.getByRole("textbox", { name: "Expected JSON 1" })).toHaveValue("42");
    await user.selectOptions(screen.getByRole("combobox", { name: "Method 1" }), "set_equals");
    expect(screen.getByRole("textbox", { name: "Expected JSON 1" })).toHaveValue("");
    fireEvent.change(screen.getByRole("textbox", { name: "Expected JSON 1" }), { target: { value: "{}" } });
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    expect(await screen.findByText("Expected set must be a JSON array.")).toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Method 1" }), "human_review");
    expect(screen.queryByRole("textbox", { name: "Expected JSON 1" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Baseline reference 1" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Required" }));
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await waitFor(() => expect(api.evaluateAgentRun).toHaveBeenCalledTimes(1));
    const submitted = vi.mocked(api.evaluateAgentRun!).mock.calls[0][3];
    expect(submitted.checks[0]).toEqual({ id: "condition-1", label: "Expected total", required: false, path: ["total"], method: "human_review" });
    await user.click(screen.getByRole("button", { name: "Remove condition 1" }));
    expect(screen.queryByRole("combobox", { name: "Method 1" })).not.toBeInTheDocument();
  });

  it("shows saved acceptance before its explicit editor without creating blank criteria or requests", async () => {
    const api = apiWith({ getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [report()] }) });
    const view = mount(api);
    await screen.findByText("Selected conditions accepted");
    expect(screen.queryByRole("textbox", { name: "Condition name 1" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assess selected conditions" })).not.toBeInTheDocument();
    const refresh = screen.getByRole("button", { name: "Refresh reports" });
    expect(refresh).toHaveAttribute("title", "Refresh reports");
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit these conditions" }));
    const history = view.container.querySelector(".run-evaluation-history")!;
    const editor = view.container.querySelector(".run-evaluation-compose")!;
    expect(history.compareDocumentPosition(editor) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Condition name 1" })).toHaveValue("Expected total");
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    expect(api.commandAgentRun).not.toHaveBeenCalled();
    expect(run.status).toBe("unverified");
  });

  it.each(["project_id", "target_id", "run_id", "version_id"] as const)("does not display a GET report with the wrong %s", async (field) => {
    const api = apiWith({ getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [report({ [field]: "wrong" })] }) });
    mount(api);
    expect(await screen.findByText("Evaluation report identity does not match this Run.")).toBeInTheDocument();
    expect(screen.queryByText("Selected conditions accepted")).not.toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
  });

  it("rejects a POST report for different identity or submitted conditions and only refreshes", async () => {
    const api = apiWith({ evaluateAgentRun: vi.fn().mockResolvedValue(report({ run_id: "wrong" })) }); mount(api);
    const user = await condition();
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    expect(await screen.findByText("Evaluation response identity or conditions do not match this submission.")).toBeInTheDocument();
    expect(api.evaluateAgentRun).toHaveBeenCalledTimes(1);
    expect(api.getAgentRunEvaluations).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Selected conditions accepted")).not.toBeInTheDocument();
  });

  it("shows required/advisory findings, true codes and untrusted model baseline scope", async () => {
    const modelCheck = { ...spec.checks[0], baseline: { kind: "model" as const, reference: "generated-answer", revision: "v1" } };
    const saved = report({ decision: "inconclusive", spec: { ...spec, checks: [modelCheck] }, checks: [
      { ...modelCheck, status: "unknown", code: "model_baseline_not_independent", baseline: modelCheck.baseline, evidence: [] },
      { id: "physical", label: "Physical fit", required: false, path: ["total"], method: "human_review", status: "awaiting_human", code: "human_review_required", baseline: null, evidence: [] },
    ] });
    mount(apiWith({ getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [saved] }) }));
    await screen.findByText("Selected conditions inconclusive");
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Advisory")).toBeInTheDocument();
    expect(screen.getByText("model_baseline_not_independent", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByText("A model baseline is not independent verification.")).toBeInTheDocument();
    expect(screen.getByText("Awaiting human review")).toBeInTheDocument();
    expect(screen.getByText(/does not change Run status/)).toBeInTheDocument();
  });

  it("has no active-run submission and degrades unavailable/failed result evidence locally", async () => {
    const api = apiWith(); const view = mount(api, { ...run, status: "waiting", finished_at: null });
    expect(screen.queryByRole("region", { name: "Result acceptance" })).not.toBeInTheDocument();
    expect(api.getAgentRunEvaluations).not.toHaveBeenCalled();
    view.rerender(<ThemeProvider><RunEvaluationPanel api={api} run={{ ...run, status: "failed", result: null }} locale="en" /></ThemeProvider>);
    expect(await screen.findByText(/business evidence is insufficient/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assess selected conditions" })).not.toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
  });

  it("handles a missing evaluator API or 404 without breaking Run Detail", async () => {
    const api = apiWith({ getAgentRunEvaluations: vi.fn().mockRejectedValue({ status: 404 }) }); mount(api, run, "zh");
    expect(await screen.findByText("当前 API 不支持结果验收。")).toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
  });

  it("binds Workflow reports and assessment to the Workflow target with honest missing input evidence", async () => {
    const { agent_id: _agent, ...base } = run;
    const workflowRun: WorkflowRunResponse = { ...base, workflow_id: "workflow-1", children: [], waiting: null };
    const getWorkflowRunEvaluations = vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [] });
    const evaluateWorkflowRun = vi.fn().mockImplementation(async (_p, _w, _r, submitted) => report({ target_kind: "workflow", target_id: "workflow-1", input_hash: null, input_evidence: "not_saved", spec: submitted }));
    const api = apiWith({ getWorkflowRunEvaluations, evaluateWorkflowRun }); mount(api, workflowRun); const user = await condition();
    await user.click(screen.getByRole("button", { name: "Assess selected conditions" }));
    await screen.findByText("Selected conditions accepted");
    expect(getWorkflowRunEvaluations).toHaveBeenCalledExactlyOnceWith("project-1", "workflow-1", "run-1");
    expect(evaluateWorkflowRun.mock.calls[0].slice(0, 3)).toEqual(["project-1", "workflow-1", "run-1"]);
    expect(screen.getByText("not_saved", { selector: "code" })).toBeInTheDocument();
    expect(api.evaluateAgentRun).not.toHaveBeenCalled();
    expect(api.commandWorkflowRun).not.toHaveBeenCalled();
  });

  it("opens artifact evidence only through an explicit content request", async () => {
    const saved = report({ checks: [{ id: "image", label: "Delivered image", required: true, path: ["image"], method: "artifact_integrity", status: "pass", code: "artifact_integrity_confirmed", baseline: null, evidence: [{ kind: "artifact", artifact_id: "artifact-1", sha256: "a".repeat(64), size_bytes: 42, source_run_id: "original-run" }] }] });
    const artifactContent = vi.fn().mockResolvedValue(new Blob(["image"]));
    const api = apiWith({ artifactContent, getAgentRunEvaluations: vi.fn().mockResolvedValue({ schema_version: "1.0", reports: [saved] }) });
    const create = vi.fn().mockReturnValue("blob:evidence");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: create, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revoke, configurable: true });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const view = mount(api); const user = userEvent.setup();
    await screen.findByText("Delivered image");
    expect(artifactContent).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Open artifact" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("blob:evidence", "_blank", "noopener,noreferrer"));
    expect(artifactContent).toHaveBeenCalledExactlyOnceWith("project-1", "artifact-1");
    view.unmount(); expect(revoke).toHaveBeenCalledWith("blob:evidence");
  });
});
