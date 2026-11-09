import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentRunResponse, EvaluationReport, EvaluationReviewRequest, WorkflowRunResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { RunEvaluationPanel } from "./RunEvaluationPanel";

afterEach(cleanup);
const run: AgentRunResponse = { schema_version: "1.0", project_id: "p", agent_id: "a", run_id: "r", version_id: "v", status: "unverified", result: { front: "blue box", side: "blue box" }, error: null, created_at: "2026-10-16T00:00:00Z", finished_at: "2026-10-16T00:01:00Z", events: [] };
const base: EvaluationReport = {
  schema_version: "1.0", evaluator_version: "1", scope: "declared_checks", evaluation_id: "base", project_id: "p", target_kind: "agent", target_id: "a", run_id: "r", version_id: "v", run_status: "unverified", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), spec_hash: "d".repeat(64), input_hash: "e".repeat(64), input_evidence: "persisted", result_hash: "f".repeat(64), created_at: "2026-10-16T00:01:00Z", decision: "inconclusive", output_contract: "pass", independent_scope: "baseline_comparison_and_artifact_integrity_only",
  spec: { version: "1", version_id: "v", checks: ["front", "side"].map((name) => ({ id: name, label: name, required: true, path: [name], method: "human_review" })) },
  checks: ["front", "side"].map((name) => ({ id: name, label: name, required: true, path: [name], method: "human_review", baseline: null, status: "awaiting_human", code: "human_review_required", actual_hash: "a".repeat(64), actual_value: "blue box", evidence: [] })),
};

function revised(parent: EvaluationReport, input: EvaluationReviewRequest): EvaluationReport {
  const at = "2026-10-16T00:02:00Z";
  const review = { review_id: "review-1", source: "local_user" as const, created_at: at, base_evaluation_id: parent.evaluation_id, supersedes_review_id: parent.review?.review_id ?? null, decisions: input.decisions };
  const checks = parent.checks.map((finding) => {
    const decision = input.decisions.find((entry) => entry.check_id === finding.id);
    return decision ? { ...finding, status: decision.outcome, code: { pass: "user_review_accepted", fail: "user_review_rejected", unknown: "user_review_uncertain" }[decision.outcome], human_review: { ...decision, review_id: review.review_id, source: review.source, created_at: at, base_evaluation_id: parent.evaluation_id } } : finding;
  });
  return { ...parent, evaluator_version: "2", evaluation_id: "derived", root_evaluation_id: parent.root_evaluation_id ?? parent.evaluation_id, parent_evaluation_id: parent.evaluation_id, created_at: at, review, checks, independent_scope: "baseline_comparison_artifact_integrity_and_user_review", decision: checks.some((item) => item.status === "fail") ? "rejected" : checks.every((item) => item.status === "pass") ? "accepted" : "inconclusive" };
}

function mount(options: { workflow?: boolean; submit?: ReturnType<typeof vi.fn>; get?: ReturnType<typeof vi.fn>; reports?: EvaluationReport[] } = {}) {
  const original: EvaluationReport = options.workflow ? { ...base, target_kind: "workflow", target_id: "w", input_hash: null, input_evidence: "not_saved" } : base;
  const get = options.get ?? vi.fn().mockResolvedValue({ schema_version: "1.0", reports: options.reports ?? [original] });
  const submit = options.submit ?? vi.fn().mockImplementation(async (_p, _t, _r, _root, input) => revised(original, input));
  const api = { getAgentRunEvaluations: get, getWorkflowRunEvaluations: get, evaluateAgentRun: vi.fn(), evaluateWorkflowRun: vi.fn(), reviewAgentRunEvaluation: submit, reviewWorkflowRunEvaluation: submit, runAgent: vi.fn(), commandAgentRun: vi.fn(), runWorkflow: vi.fn(), commandWorkflowRun: vi.fn() } as unknown as LocalProjectApi;
  const current = options.workflow ? { ...run, workflow_id: "w", children: [] } as unknown as WorkflowRunResponse : run;
  if (options.workflow) delete (current as unknown as Record<string, unknown>).agent_id;
  render(<ThemeProvider><RunEvaluationPanel api={api} run={current} locale="en" /></ThemeProvider>);
  return { api, get, submit, original };
}

async function fill(user = userEvent.setup(), name = "front", outcome = "fail", note = "Identity differs from the selected design") {
  await user.selectOptions(await screen.findByRole("combobox", { name: `Review decision: ${name}` }), outcome);
  await user.type(screen.getByRole("textbox", { name: `Review reason: ${name}` }), note);
  return user;
}

describe("Manual result review", () => {
  it.each([false, true])("records snapshot-bound feedback without starting execution, workflow=%s", async (workflow) => {
    const { api, submit, original } = mount({ workflow });
    const user = await fill();
    await fill(user, "side", "pass", "Checked this view against the design");
    await user.click(screen.getByRole("button", { name: "Record review" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0].slice(0, 4)).toEqual(["p", workflow ? "w" : "a", "r", "base"]);
    expect(submit.mock.calls[0][4]).toMatchObject({ expected_report_id: "base", version_id: "v", spec_hash: original.spec_hash, result_hash: original.result_hash, decisions: [{ check_id: "front", outcome: "fail" }, { check_id: "side", outcome: "pass" }] });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Report history" })).toHaveValue("derived"));
    for (const action of [api.runAgent, api.commandAgentRun, api.runWorkflow, api.commandWorkflowRun]) expect(action).not.toHaveBeenCalled();
    expect(original.checks.every((entry) => entry.status === "awaiting_human")).toBe(true);
  });

  it("requires a reason, blocks double submit and preserves the key after an unknown response", async () => {
    let fail: (error: Error) => void = () => undefined;
    const pending = new Promise<EvaluationReport>((_resolve, reject) => { fail = reject; });
    const submit = vi.fn().mockReturnValueOnce(pending).mockRejectedValue(new Error("Still unknown"));
    const { get } = mount({ submit });
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByRole("combobox", { name: "Review decision: front" }), "fail");
    await user.click(screen.getByRole("button", { name: "Record review" }));
    expect(await screen.findByText("Give a reason for each review decision.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
    await user.type(screen.getByRole("textbox", { name: "Review reason: front" }), "A mismatched mark");
    const button = screen.getByRole("button", { name: "Record review" });
    fireEvent.click(button); fireEvent.click(button);
    expect(submit).toHaveBeenCalledTimes(1);
    fail(new Error("Response unknown"));
    await screen.findByText("Response unknown");
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("textbox", { name: "Review reason: front" })).toHaveValue("A mismatched mark");
    expect(submit).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Record review" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    expect(submit.mock.calls[1][5]).toEqual(submit.mock.calls[0][5]);
  });

  it("retains notes while an old report becomes historical and requires explicit head selection", async () => {
    const head = revised(base, { expected_report_id: "base", version_id: "v", spec_hash: base.spec_hash, result_hash: base.result_hash!, decisions: [{ check_id: "side", outcome: "pass", reason: "Other reviewer checked the side" }] });
    const get = vi.fn().mockResolvedValueOnce({ reports: [base] }).mockResolvedValue({ reports: [head, base] });
    const { submit } = mount({ get });
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Refresh reports" }));
    expect(await screen.findByText("This is a historical snapshot.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Review reason: front" })).toHaveValue("Identity differs from the selected design");
    expect(screen.getByRole("button", { name: "Record review" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "View latest report" }));
    expect(screen.getByRole("combobox", { name: "Report history" })).toHaveValue("derived");
    expect(submit).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Report history" }), "base");
    expect(screen.getByRole("textbox", { name: "Review reason: front" })).toHaveValue("Identity differs from the selected design");
  });

  it("rejects a wrong result snapshot response and preserves the draft", async () => {
    const submit = vi.fn().mockImplementation(async (_p, _a, _r, _root, input) => ({ ...revised(base, input), result_hash: "0".repeat(64) }));
    mount({ submit });
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Record review" }));
    expect(await screen.findByText("Review response does not match this snapshot or submission.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Report history" })).toHaveValue("base");
    expect(screen.getByRole("textbox", { name: "Review reason: front" })).toHaveValue("Identity differs from the selected design");
  });
});
