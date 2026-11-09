import { describe, expect, it, vi } from "vitest";
import type { EvaluationReport } from "@veyra/api-contracts";
import { LocalApiClient } from "./local-client";

function report(): EvaluationReport {
  const baseline = { kind: "user" as const, reference: "Answer", revision: "1" };
  const check = { id: "total", label: "Exact total", required: true, path: ["result", "含.点", "$schema", ""], method: "number_equals" as const, expected: "14.50", baseline };
  return {
    schema_version: "1.0", evaluator_version: "1", scope: "declared_checks", evaluation_id: "evaluation-1", project_id: "project-1", target_kind: "agent", target_id: "agent-1", run_id: "run-1", version_id: "version-1", run_status: "unverified", source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), spec_hash: "d".repeat(64), input_hash: "e".repeat(64), input_evidence: "persisted", result_hash: "f".repeat(64), created_at: "2026-10-15T00:00:00Z",
    spec: { version: "1", version_id: "version-1", checks: [check] },
    decision: "accepted", output_contract: "pass", independent_scope: "baseline_comparison_and_artifact_integrity_only",
    checks: [{ id: check.id, label: check.label, required: check.required, path: check.path, method: check.method, status: "pass", code: "baseline_match", baseline, actual_hash: "f".repeat(64), expected_hash: "a".repeat(64), evidence: [] }],
  };
}

function response(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}

function manualReport(): EvaluationReport {
  const value = report();
  const check = { id: "visual", label: "Visual identity", required: true, path: ["result"], method: "human_review" as const };
  const decision = { check_id: check.id, outcome: "fail" as const, reason: "Unexpected mark in this view" };
  const source = { ...decision, review_id: "review-1", source: "local_user" as const, created_at: value.created_at, base_evaluation_id: "base-1" };
  return { ...value, evaluator_version: "2", root_evaluation_id: "base-1", parent_evaluation_id: "base-1", spec: { ...value.spec, checks: [check] }, decision: "rejected", checks: [{ ...check, status: "fail", code: "user_review_rejected", baseline: null, actual_hash: "f".repeat(64), evidence: [], human_review: source }], independent_scope: "baseline_comparison_artifact_integrity_and_user_review", review: { review_id: source.review_id, source: source.source, created_at: source.created_at, base_evaluation_id: "base-1", supersedes_review_id: null, decisions: [decision] } };
}

describe("local offline result evaluation", () => {
  it.each(["agent", "workflow"] as const)("submits %s user review with an explicit stable key and the exact snapshot", async (kind) => {
    const value = manualReport();
    if (kind === "workflow") { value.target_kind = "workflow"; value.target_id = "workflow-1"; }
    const fetcher = vi.fn().mockImplementation(async () => response(value));
    const api = new LocalApiClient({ fetcher });
    const input = { expected_report_id: "base-1", version_id: value.version_id, spec_hash: value.spec_hash, result_hash: value.result_hash!, decisions: value.review!.decisions };
    const method = kind === "agent" ? api.reviewAgentRunEvaluation : api.reviewWorkflowRunEvaluation;
    for (let index = 0; index < 2; index += 1) await expect(method.call(api, "project-1", value.target_id, "run-1", "base-1", input, { idempotencyKey: "stable-review-key" })).resolves.toEqual(value);
    expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/projects/project-1/${kind === "agent" ? "agents" : "workflows"}/${value.target_id}/runs/run-1/evaluations/base-1/reviews`);
    for (const [, options] of fetcher.mock.calls) {
      expect(new Headers(options.headers).get("Idempotency-Key")).toBe("stable-review-key");
      expect(JSON.parse(options.body)).toEqual(input);
    }
  });

  it.each(["missing-proof", "model-source", "wrong-check", "wrong-decision", "old-version"])("rejects invalid human review provenance: %s", async (defect) => {
    const value = manualReport();
    if (defect === "missing-proof") delete value.checks[0].human_review;
    if (defect === "model-source") (value.checks[0].human_review as unknown as Record<string, unknown>).source = "model";
    if (defect === "wrong-check") value.checks[0].human_review!.check_id = "another";
    if (defect === "wrong-decision") value.checks[0].human_review!.outcome = "pass";
    if (defect === "old-version") value.evaluator_version = "1";
    const api = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response({ reports: [value], schema_version: "1.0" })) });
    await expect(api.getAgentRunEvaluations("p", "a", "r")).rejects.toMatchObject({ code: "invalid_response" });
  });
  it("sends the frozen spec and explicit stable key without starting or approving a Run", async () => {
    const value = report();
    const fetcher = vi.fn().mockResolvedValue(response(value));
    const api = new LocalApiClient({ fetcher });
    await expect(api.evaluateAgentRun("project-1", "agent-1", "run-1", value.spec, { idempotencyKey: "same-key" })).resolves.toEqual(value);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/agents/agent-1/runs/run-1/evaluations");
    const options = fetcher.mock.calls[0]?.[1];
    expect(options?.method).toBe("POST");
    expect(new Headers(options?.headers).get("Idempotency-Key")).toBe("same-key");
    expect(JSON.parse(String(options?.body))).toEqual({ spec: value.spec });
  });

  it("reads persisted Workflow reports with unknown original inputs", async () => {
    const value = { ...report(), target_kind: "workflow", target_id: "workflow-1", input_hash: null, input_evidence: "not_saved" };
    const fetcher = vi.fn().mockResolvedValue(response({ schema_version: "1.0", reports: [value] }));
    const api = new LocalApiClient({ fetcher });
    await expect(api.getWorkflowRunEvaluations("project-1", "workflow-1", "run-1")).resolves.toMatchObject({ reports: [value] });
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/workflows/workflow-1/runs/run-1/evaluations");
    expect(fetcher.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it.each(["unknown", "not_evaluated", "awaiting_human", "fail"] as const)("rejects an accepted report with a required %s result", async (state) => {
    const value = report();
    value.checks[0].status = state;
    const api = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(value)) });
    await expect(api.evaluateAgentRun("p", "a", "r", value.spec, { idempotencyKey: "key" })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("rejects model provenance laundered into a deterministic pass", async () => {
    const value = report();
    value.spec.checks[0].baseline!.kind = "model";
    value.checks[0].baseline = { kind: "user", reference: "Answer", revision: "1" };
    const api = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(value)) });
    await expect(api.evaluateAgentRun("p", "a", "r", value.spec, { idempotencyKey: "key" })).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("rejects inconsistent version and missing candidate provenance", async () => {
    for (const mutate of [(value: EvaluationReport) => { value.spec.version_id = "another-version"; }, (value: EvaluationReport) => { value.result_hash = null; }]) {
      const value = report();
      mutate(value);
      const api = new LocalApiClient({ fetcher: vi.fn().mockResolvedValue(response(value)) });
      await expect(api.evaluateAgentRun("p", "a", "r", value.spec, { idempotencyKey: "key" })).rejects.toMatchObject({ code: "invalid_response" });
    }
  });
});
