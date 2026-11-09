import { AgentInputReply } from "../agents/chat/AgentInputReply";
import { productRunError } from "../agents/app-errors";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowUpRight, CheckCheck, ChevronDown, Clock3, History, Info, RotateCcw, Square } from "lucide-react";
import type { AgentRunResponse, WorkflowRunResponse } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { Alert, Button, ErrorState, LinkButton, LoadingState, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { newUuidV7 } from "../../api/uuid";
import { RunEventList } from "../studio/RunEventList";
import { runStatusLabel, runTone, workflowRunAsAgentRun } from "../studio/studio-run-ui";
import { RunApprovalBar } from "../studio/RunApprovalBar";
import { approvalRequestBinding, approvalRequestId, runCommandKey, type LiveRunCommand } from "../studio/live-run";
import { isBudgetWaiting } from "../studio/BudgetContinuation";
import { RuntimeOutputView } from "../runtime/RuntimeOutputView";
import { runDetailHref, runMonitorHref, runStudioHref, type RunIdentity } from "./run-location";
import { KnowledgeEvidence } from "./KnowledgeEvidence";
import { RunEvaluationPanel } from "./RunEvaluationPanel";
import "./run-detail.css";

function displayTime(value: string, locale: "zh" | "en"): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function elapsedTime(run: AgentRunResponse | WorkflowRunResponse, locale: "zh" | "en"): string | null {
  if (!run.finished_at) return null;
  const seconds = (Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  const rounded = Math.round(seconds);
  return rounded < 60 ? `${rounded}${locale === "zh" ? " 秒" : " s"}` : `${Math.floor(rounded / 60)}${locale === "zh" ? " 分 " : " m "}${rounded % 60}${locale === "zh" ? " 秒" : " s"}`;
}

function timeoutDescription(run: AgentRunResponse | WorkflowRunResponse, locale: "zh" | "en"): string {
  if (run.error?.code !== "runtime_timeout") return "";
  const failed = run.events?.filter(event => ["node.failed", "finalization.failed"].includes(event.kind) && event.payload.code === "runtime_timeout").at(-1);
  const diagnostic = failed?.payload.provider_diagnostic;
  if (!diagnostic || typeof diagnostic !== "object" || Array.isArray(diagnostic)) return "";
  const phases: Record<string, { zh: string; en: string }> = {
    read: { zh: "读取响应阶段", en: "Response read phase" },
    connect: { zh: "连接阶段", en: "Connection phase" },
    write: { zh: "发送请求阶段", en: "Request write phase" },
    pool: { zh: "等待连接阶段", en: "Connection pool phase" },
  };
  const phase = typeof diagnostic.timeout_phase === "string" ? phases[diagnostic.timeout_phase]?.[locale] : undefined;
  const seconds = diagnostic.timeout_seconds;
  const threshold = typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0 ? `${locale === "zh" ? "超时阈值 " : "Timeout threshold "}${seconds}${locale === "zh" ? " 秒" : " s"}` : undefined;
  return [phase, threshold].filter(Boolean).join(" · ");
}

export function RunEvidence({ run, locale, api, showResult = true, controls, children }: { run: AgentRunResponse | WorkflowRunResponse; locale: "zh" | "en"; api?: LocalProjectApi; showResult?: boolean; controls?: ReactNode; children?: ReactNode }) {
  const [rawOutputRunId, setRawOutputRunId] = useState<string | null>(null);
  const identity: RunIdentity = { projectId: run.project_id, runId: run.run_id, ...("agent_id" in run ? { agentId: run.agent_id } : { workflowId: run.workflow_id }) };
  const lineage = run.events?.find((event) => event.kind === "run.created")?.payload;
  const origin = lineage?.retry_of_run_id ?? lineage?.resume_of_run_id;
  const pendingRequest = run.events?.filter((event) => event.kind === "approval.requested").at(-1);
  const waitingKind = "workflow_id" in run ? run.waiting?.kind : pendingRequest?.payload.kind === "budget" ? "budget" : pendingRequest?.payload.kind === "input" ? "input" : pendingRequest ? "approval" : undefined;
  const statusLabel = run.status === "waiting" && waitingKind === "input"
    ? (locale === "zh" ? "等待输入" : "Waiting for input")
    : run.status === "waiting" && waitingKind === "budget"
      ? (locale === "zh" ? "等待追加轮次" : "Waiting for additional turns")
    : run.status === "waiting" && waitingKind === "approval"
      ? (locale === "zh" ? "等待审批" : "Waiting for approval")
      : runStatusLabel(run.status, locale);
  const elapsed = elapsedTime(run, locale);
  const eventCount = run.events?.filter((event) => event.kind !== "model.delta").length ?? 0;
  return <section className="run-detail-view">
    <header className="run-detail-heading">
      <div className="run-detail-title"><h1>{locale === "zh" ? "运行详情" : "Run detail"}</h1><StatusBadge label={statusLabel} tone={runTone(run.status)} /></div>
      <nav className="run-detail-navigation" aria-label={locale === "zh" ? "运行导航" : "Run navigation"}>
        {"agent_id" in run ? <LinkButton icon={ArrowLeft} variant="ghost" size="sm" href={projectRoutePaths.agent(run.project_id, run.agent_id)}>{locale === "zh" ? "返回应用" : "Back to Agent"}</LinkButton> : <LinkButton icon={ArrowLeft} variant="ghost" size="sm" href={runDetailHref(identity)}>{locale === "zh" ? "返回工作流应用" : "Back to Workflow App"}</LinkButton>}
        <LinkButton icon={ArrowUpRight} variant="ghost" size="sm" href={runStudioHref(identity)}>Studio</LinkButton>
        <LinkButton icon={ArrowUpRight} variant="ghost" size="sm" href={runMonitorHref(identity)}>Monitor</LinkButton>
      </nav>
      <div className="run-detail-meta">{["verified", "unverified"].includes(run.status) ? <span>{locale === "zh" ? "执行完成" : "Execution completed"}</span> : null}<span><Clock3 size={14} aria-hidden="true" /><time dateTime={run.created_at}>{displayTime(run.created_at, locale)}</time></span>{elapsed ? <span>{locale === "zh" ? "耗时" : "Elapsed"} {elapsed}</span> : null}<span title={run.version_id}>{locale === "zh" ? "固定版本" : "Pinned version"} <code>{run.version_id.slice(0, 8)}</code></span></div>
    </header>
    {controls ? <div className="run-detail-controls">{controls}</div> : null}
    {run.error ? <Alert type="error" title={productRunError(run.error.code, run.error.message, locale)} description={[run.error.code, timeoutDescription(run, locale)].filter(Boolean).join(" · ")} /> : null}
    {showResult && run.result != null ? <section className="run-detail-result" aria-label={locale === "zh" ? "运行结果" : "Run result"}><h2>{locale === "zh" ? "运行结果" : "Run result"}</h2><RuntimeOutputView result={run.result} locale={locale} api={api} projectId={run.project_id} presentation="reading" /></section> : null}
    {children}
    {run.events ? <details className="run-detail-disclosure"><summary><History size={16} aria-hidden="true" /><span>{locale === "zh" ? "执行记录" : "Execution record"}</span><small>{eventCount} {locale === "zh" ? "条事件" : "events"}</small><ChevronDown className="run-detail-chevron" size={16} aria-hidden="true" /></summary><div className="run-detail-record"><KnowledgeEvidence key={run.run_id} events={run.events} api={api} projectId={run.project_id} locale={locale} /><RunEventList events={run.events} locale={locale} /></div></details> : null}
    <details className="run-detail-disclosure"><summary><Info size={16} aria-hidden="true" /><span>{locale === "zh" ? "运行信息" : "Run information"}</span><ChevronDown className="run-detail-chevron" size={16} aria-hidden="true" /></summary><dl className="run-detail-identities">
      <div><dt>Run ID</dt><dd><code>{run.run_id}</code></dd></div>
      <div><dt>{locale === "zh" ? "版本" : "Version"}</dt><dd><code>{run.version_id}</code></dd></div>
      <div><dt>{locale === "zh" ? "开始时间" : "Started"}</dt><dd><time dateTime={run.created_at}>{run.created_at}</time></dd></div>
      <div><dt>{locale === "zh" ? "结束时间" : "Finished"}</dt><dd>{run.finished_at ? <time dateTime={run.finished_at}>{run.finished_at}</time> : "-"}</dd></div>
    </dl>{showResult && run.result != null ? <details key={run.run_id} className="run-detail-raw" onToggle={(event) => setRawOutputRunId(event.currentTarget.open ? run.run_id : null)}><summary>{locale === "zh" ? "原始输出" : "Raw output"}</summary>{rawOutputRunId === run.run_id ? <RuntimeOutputView result={run.result} locale={locale} api={api} projectId={run.project_id} /> : null}</details> : null}{typeof origin === "string" ? <LinkButton icon={History} variant="ghost" size="sm" href={runDetailHref({ ...identity, runId: origin })}>{locale === "zh" ? "原运行" : "Original run"}</LinkButton> : null}</details>
  </section>;
}

export function RunDetail({ api, projectId, agentId, workflowId, runId, locale }: RunIdentity & { api: LocalProjectApi; locale: "zh" | "en" }) {
  const [run, setRun] = useState<AgentRunResponse | WorkflowRunResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [evaluationIdentity, setEvaluationIdentity] = useState<string | null>(null);
  const pendingCommand = useRef<string | null>(null);
  const recoveryKeys = useRef(new Map<string, string>());
  const identity = `${projectId}:${agentId}:${workflowId}:${runId}`;
  const activeIdentity = useRef(identity);
  activeIdentity.current = identity;
  const checkpoint = run?.events?.filter((event) => event.kind === "checkpoint.created").at(-1);
  const checkpointId = checkpoint?.payload.waiting_kind === "execution" && typeof checkpoint.payload.checkpoint_id === "string" ? checkpoint.payload.checkpoint_id : undefined;
  const dispatchedAfterCheckpoint = checkpoint && run?.events?.some((event) => event.kind === "tool.started" && event.sequence > checkpoint.sequence);
  const command = async (value: LiveRunCommand | "retry" | "resume", inputs?: Record<string, import("@veyra/api-contracts").JsonValue>, additionalTurns?: number) => {
    if (!run) return;
    if (pendingCommand.current === identity) return;
    pendingCommand.current = identity;
    setBusy(true);
    setError("");
    try {
      if (value === "retry" || value === "resume") {
        const keyIdentity = `${identity}:${value}:${value === "resume" ? checkpointId : ""}`;
        if (!recoveryKeys.current.has(keyIdentity)) recoveryKeys.current.set(keyIdentity, newUuidV7());
        const child = await api.commandAgentRun!(projectId, agentId!, runId, { command: value, ...(value === "resume" ? { checkpoint_id: checkpointId } : {}) }, { idempotencyKey: recoveryKeys.current.get(keyIdentity)! });
        if (child.project_id !== projectId || child.agent_id !== agentId || child.run_id === runId) throw new Error("Runtime recovery identity mismatch");
        if (activeIdentity.current === identity) window.location.hash = runDetailHref({ projectId, agentId, runId: child.run_id });
      }
      else {
        const input = { command: value, ...approvalRequestBinding(run, value), ...(inputs ? { inputs } : {}), ...(value === "extend_budget" ? { additional_turns: additionalTurns } : {}) };
        const options = isBudgetWaiting(run) ? [{ idempotencyKey: runCommandKey(recoveryKeys.current, run, value, additionalTurns) }] as const : [] as const;
        const updated = workflowId ? await api.commandWorkflowRun!(projectId, workflowId, runId, input, ...options) : await api.commandAgentRun!(projectId, agentId!, runId, input, ...options);
        if (updated.run_id !== runId || updated.project_id !== projectId || (workflowId ? !("workflow_id" in updated) || updated.workflow_id !== workflowId : !("agent_id" in updated) || updated.agent_id !== agentId)) throw new Error("Runtime run identity mismatch");
      }
      if (activeIdentity.current === identity) setRefresh((value) => value + 1);
    } catch (cause) {
      if (activeIdentity.current === identity) {
        setError(cause instanceof Error ? cause.message : "Run command failed");
        const detail = await (workflowId
          ? api.getWorkflowRun?.(projectId, workflowId, runId)
          : api.getAgentRun?.(projectId, agentId!, runId))?.catch(() => null);
        if (activeIdentity.current === identity && detail?.run_id === runId && detail.project_id === projectId
          && (workflowId ? "workflow_id" in detail && detail.workflow_id === workflowId : "agent_id" in detail && detail.agent_id === agentId)) setRun(detail);
      }
    } finally {
      if (pendingCommand.current === identity) pendingCommand.current = null;
      if (activeIdentity.current === identity) setBusy(false);
    }
  };
  useEffect(() => {
    let current = true;
    let timer: number | undefined;
    setRun(null);
    setError("");
    setBusy(false);
    const load = async () => {
      try {
        const detail = workflowId
          ? await api.getWorkflowRun?.(projectId, workflowId, runId)
          : await api.getAgentRun?.(projectId, agentId!, runId);
        if (!detail) throw new Error("Runtime detail API unavailable");
        if (detail.run_id !== runId || detail.project_id !== projectId
          || (workflowId ? !("workflow_id" in detail) || detail.workflow_id !== workflowId : !("agent_id" in detail) || detail.agent_id !== agentId)) {
          throw new Error("Runtime run identity mismatch");
        }
        if (!current) return;
        setRun(detail);
        if (detail.status === "running" || detail.status === "waiting") timer = window.setTimeout(() => void load(), 1000);
      } catch (cause) {
        if (current) setError(cause instanceof Error ? cause.message : "Could not load run");
      }
    };
    void load();
    return () => { current = false; window.clearTimeout(timer); };
  }, [api, projectId, agentId, workflowId, runId, refresh]);
  if (error && !run) return <ErrorState message={error} onRetry={() => setRefresh((value) => value + 1)} />;
  if (!run) return <LoadingState label={locale === "zh" ? "正在读取运行详情…" : "Loading run detail…"} />;
  const canCommand = Boolean(workflowId ? api.commandWorkflowRun : api.commandAgentRun);
  const inputEvent = run.status === "waiting" && "agent_id" in run ? run.events?.filter((event) => event.kind === "approval.requested").at(-1) : undefined;
  const inputPrompt = inputEvent?.payload.kind === "input" && typeof inputEvent.payload.prompt === "string" ? inputEvent.payload : undefined;
  return <RunEvidence run={run} locale={locale} api={api} controls={<>
    {error ? <Alert type="error" title={error} /> : null}
    {inputPrompt ? <AgentInputReply key={approvalRequestId(run)} question={String(inputPrompt.prompt)} context={inputPrompt.context}
      locale={locale} busy={busy || !canCommand} projectId={projectId} api={api}
      onReply={(reply) => command("reply", { reply })} onStop={() => void command("stop")} /> : "workflow_id" in run && run.waiting?.kind === "input" ? <Alert type="info" title={locale === "zh" ? "工作流正在等待补充输入" : "Workflow is waiting for input"} description={locale === "zh" ? "请在工作流应用中按字段补充信息，再继续这次运行。" : "Open the Workflow App to provide typed input and continue this run."} /> : <RunApprovalBar run={"workflow_id" in run ? workflowRunAsAgentRun(run) : run} locale={locale} disabled={busy || !canCommand} onCommand={(value) => void command(value)} onExtendBudget={(turns) => void command("extend_budget", undefined, turns)} />}
    {run.status === "running" && canCommand ? <Button icon={Square} size="sm" disabled={busy} onClick={() => void command("stop")}>{locale === "zh" ? "停止" : "Stop"}</Button> : null}
    {!workflowId && canCommand && ["failed", "interrupted", "cancelled"].includes(run.status) ? <Button icon={RotateCcw} size="sm" disabled={busy} onClick={() => void command("retry")}>{locale === "zh" ? "安全重试" : "Retry safely"}</Button> : null}
    {!workflowId && canCommand && ["failed", "interrupted"].includes(run.status) && checkpointId && !dispatchedAfterCheckpoint ? <Button icon={History} size="sm" disabled={busy} onClick={() => void command("resume")}>{locale === "zh" ? "从检查点恢复" : "Resume from checkpoint"}</Button> : null}
    {workflowId && ["failed", "interrupted"].includes(run.status) ? <p>{locale === "zh" ? "此 Workflow 没有可安全恢复的执行检查点；不支持 Retry / Resume。" : "This Workflow has no safely recoverable execution checkpoint; Retry / Resume are unsupported."}</p> : null}
  </>}>
    {run.status !== "running" && run.status !== "waiting" ? <details key={identity} className="run-evaluation-disclosure run-detail-disclosure" onToggle={(event) => { if (event.currentTarget.open) setEvaluationIdentity(identity); }}>
      <summary><CheckCheck size={16} aria-hidden="true" /><span>{locale === "zh" ? "结果验收" : "Result acceptance"}</span><ChevronDown className="run-detail-chevron" size={16} aria-hidden="true" /></summary>
      {evaluationIdentity === identity ? <RunEvaluationPanel key={`${run.run_id}:${run.version_id}`} api={api} run={run} locale={locale} /> : null}
    </details> : null}
  </RunEvidence>;
}
