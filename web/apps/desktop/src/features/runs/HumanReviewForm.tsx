import * as React from "react";
import type { AgentRunResponse, EvaluationReport, EvaluationReviewDecision, EvaluationReviewRequest, JsonValue, WorkflowRunResponse } from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
import { CheckCheck, RefreshCw } from "lucide-react";
import type { LocalProjectApi } from "../../api/local-client";
import { newUuidV7 } from "../../api/uuid";
import { ReviewArtifactPreview } from "./ReviewArtifactPreview";

type Draft = { outcome: "" | EvaluationReviewDecision["outcome"]; reason: string };
type Props = { api: LocalProjectApi; run: AgentRunResponse | WorkflowRunResponse; report: EvaluationReport; reports: EvaluationReport[]; locale: "zh" | "en"; busy: boolean; operation: React.MutableRefObject<string | null>; onBusy: (busy: boolean) => void; onReport: (report: EvaluationReport) => void; onReports: (reports: EvaluationReport[]) => void; onSelect: (id: string) => void };

function stable(value: unknown): string {
  const sort = (item: unknown): unknown => Array.isArray(item) ? item.map(sort) : item !== null && typeof item === "object" ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, sort(child)])) : item;
  return JSON.stringify(sort(value));
}

function validResponse(response: EvaluationReport, base: EvaluationReport, input: EvaluationReviewRequest): boolean {
  const keys = ["project_id", "target_kind", "target_id", "run_id", "version_id", "run_status", "source_hash", "behavior_hash", "lock_hash", "spec_hash", "input_hash", "input_evidence", "result_hash", "output_contract"] as const;
  if (keys.some((key) => response[key] !== base[key]) || stable(response.spec) !== stable(base.spec) || response.evaluator_version !== "2" || response.evaluation_id === base.evaluation_id || response.parent_evaluation_id !== base.evaluation_id || response.root_evaluation_id !== (base.root_evaluation_id ?? base.evaluation_id) || response.review?.base_evaluation_id !== base.evaluation_id || response.review.source !== "local_user" || response.review.supersedes_review_id !== (base.review?.review_id ?? null) || stable(response.review.decisions) !== stable(input.decisions) || response.checks.length !== base.checks.length) return false;
  return response.checks.every((finding, index) => {
    const previous = base.checks[index];
    const decision = input.decisions.find((entry) => entry.check_id === previous.id);
    if (!decision) return stable(finding) === stable(previous);
    const { status: _status, code: _code, human_review: _review, ...snapshot } = finding;
    const { status: _oldStatus, code: _oldCode, human_review: _oldReview, ...oldSnapshot } = previous;
    return stable(snapshot) === stable(oldSnapshot) && finding.method === "human_review" && finding.status === decision.outcome && finding.human_review?.review_id === response.review!.review_id && finding.human_review.check_id === decision.check_id && finding.human_review.reason === decision.reason && finding.human_review.outcome === decision.outcome && finding.human_review.source === "local_user" && finding.human_review.base_evaluation_id === base.evaluation_id;
  });
}

export function HumanReviewForm({ api, run, report, reports, locale, busy, operation, onBusy, onReport, onReports, onSelect }: Props) {
  const zh = locale === "zh";
  const isAgent = "agent_id" in run;
  const targetId = isAgent ? run.agent_id : run.workflow_id;
  const identity = `${run.project_id}:${isAgent ? "agent" : "workflow"}:${targetId}:${run.run_id}:${run.version_id}`;
  const mounted = React.useRef(false);
  const activeIdentity = React.useRef(identity); activeIdentity.current = identity;
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [drafts, setDrafts] = React.useState<Record<string, Record<string, Draft>>>({});
  const [error, setError] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [previews, setPreviews] = React.useState(false);
  const keys = React.useRef(new Map<string, string>());
  const submit = isAgent ? api.reviewAgentRunEvaluation : api.reviewWorkflowRunEvaluation;
  const get = isAgent ? api.getAgentRunEvaluations : api.getWorkflowRunEvaluations;
  const rootId = report.root_evaluation_id ?? report.evaluation_id;
  const head = reports.find((entry) => (entry.root_evaluation_id ?? entry.evaluation_id) === rootId) ?? report;
  const historical = head.evaluation_id !== report.evaluation_id;
  const findings = report.checks.filter((finding) => finding.method === "human_review");
  if (!findings.length) return null;
  const disabled = busy || submitting || historical || !submit || !get || !report.result_hash;
  const draft = drafts[report.evaluation_id] ?? {};
  const patch = (id: string, value: Partial<Draft>) => setDrafts((current) => ({ ...current, [report.evaluation_id]: { ...current[report.evaluation_id], [id]: { ...(current[report.evaluation_id]?.[id] ?? { outcome: "", reason: "" }), ...value } } }));
  const send = async () => {
    if (disabled || operation.current === identity) return;
    const decisions: EvaluationReviewDecision[] = [];
    for (const finding of findings) {
      const item = draft[finding.id];
      if (!item?.outcome) continue;
      if (!item.reason.trim()) { setError(zh ? "请填写每条评审结论的依据。" : "Give a reason for each review decision."); return; }
      decisions.push({ check_id: finding.id, outcome: item.outcome, reason: item.reason.trim() });
    }
    if (!decisions.length || !submit || !get || !report.result_hash) return;
    const input: EvaluationReviewRequest = { expected_report_id: report.evaluation_id, version_id: report.version_id, spec_hash: report.spec_hash, result_hash: report.result_hash, decisions };
    const fingerprint = `${identity}:${rootId}:${stable(input)}`;
    if (!keys.current.has(fingerprint)) keys.current.set(fingerprint, newUuidV7());
    operation.current = identity; setSubmitting(true); onBusy(true); setError("");
    const current = () => mounted.current && activeIdentity.current === identity;
    try {
      const response = await submit.call(api, run.project_id, targetId, run.run_id, rootId, input, { idempotencyKey: keys.current.get(fingerprint)! });
      if (!validResponse(response, report, input)) throw new Error(zh ? "评审响应与本次结果快照或意见不匹配。" : "Review response does not match this snapshot or submission.");
      if (current()) { keys.current.delete(fingerprint); onReport(response); }
    } catch (cause) {
      if (current()) {
        setError(cause instanceof Error ? cause.message : String(cause));
        const response = await get.call(api, run.project_id, targetId, run.run_id).catch(() => null);
        if (current() && response) {
          try { onReports(response.reports); } catch (refreshError) { setError(refreshError instanceof Error ? refreshError.message : String(refreshError)); }
        }
      }
    } finally {
      if (operation.current === identity) operation.current = null;
      if (current()) { setSubmitting(false); onBusy(false); }
    }
  };
  return <section className="run-human-review" aria-label={zh ? "人工评审" : "Human review"}>
    <h4>{zh ? "人工评审" : "Human review"}</h4>
    <small>{zh ? "本地用户提交，不代表认证专家意见；不会启动运行或产生模型调用。" : "Submitted by the local user, not a certified expert. No Run or model call is started."}</small>
    {historical ? <div><p>{zh ? "这是历史快照。" : "This is a historical snapshot."}</p><Button icon={RefreshCw} size="sm" variant="ghost" onClick={() => onSelect(head.evaluation_id)}>{zh ? "查看最新报告" : "View latest report"}</Button></div> : null}
    {!submit || !get ? <p>{zh ? "当前 API 不支持提交人工评审。" : "Human review submission is unavailable on this API."}</p> : null}
    {api.artifactContent && findings.some((item) => item.evidence.length) ? <>
      <label className="run-human-review-preview-toggle"><input type="checkbox" checked={previews} onChange={(event) => setPreviews(event.target.checked)} />{zh ? "显示图片快照" : "Show image snapshots"}</label>
      {previews ? <div className="run-review-previews">{[...new Map(findings.flatMap((item) => item.evidence).map((item) => [item.artifact_id, item])).values()].map((item) => <ReviewArtifactPreview key={`${run.project_id}:${item.artifact_id}:${item.sha256}`} api={api} projectId={run.project_id} evidence={item} locale={locale} />)}</div> : null}
    </> : null}
    {error ? <Alert type="error" title={error} /> : null}
    {findings.map((finding) => {
      const available = Boolean(finding.actual_hash) && (finding.status === "awaiting_human" || Boolean(finding.human_review));
      const value = draft[finding.id] ?? { outcome: "", reason: "" };
      return <div className="run-human-review-finding" key={finding.id}>
        <strong>{finding.label}</strong>
        <code>{JSON.stringify(finding.path)}</code>
        <label>{zh ? "实际结果" : "Actual result"}<code>{"actual_value" in finding ? JSON.stringify(finding.actual_value as JsonValue) : finding.actual_hash ?? (zh ? "无结果" : "No result")}</code></label>
        {finding.human_review ? <p>{finding.human_review.created_at} · {finding.human_review.reason}</p> : null}
        <label>{zh ? "评审结论" : "Review decision"}<select aria-label={`${zh ? "评审结论" : "Review decision"}: ${finding.label}`} disabled={disabled || !available} value={value.outcome} onChange={(event) => patch(finding.id, { outcome: event.target.value as Draft["outcome"] })}><option value="">{zh ? "选择结论" : "Select decision"}</option><option value="pass">{zh ? "通过" : "Pass"}</option><option value="fail">{zh ? "未通过" : "Fail"}</option><option value="unknown">{zh ? "证据不足" : "Insufficient evidence"}</option></select></label>
        <label>{zh ? "评审依据" : "Review reason"}<textarea aria-label={`${zh ? "评审依据" : "Review reason"}: ${finding.label}`} rows={3} maxLength={4000} disabled={disabled || !available} value={value.reason} onChange={(event) => patch(finding.id, { reason: event.target.value })} /></label>
      </div>;
    })}
    <Button icon={CheckCheck} size="sm" variant="primary" disabled={disabled || !Object.values(draft).some((item) => item.outcome)} onClick={() => void send()}>{submitting ? (zh ? "正在记录…" : "Recording…") : (zh ? "记录评审意见" : "Record review")}</Button>
  </section>;
}
