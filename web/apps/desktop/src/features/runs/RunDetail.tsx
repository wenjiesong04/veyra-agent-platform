import { useEffect, useRef, useState } from "react";
import type { AgentRunResponse, WorkflowRunResponse } from "@veyra/api-contracts";
import { Alert, Button, ErrorState, LinkButton, LoadingState, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { newUuidV7 } from "../../api/uuid";
import { RunEventList } from "../studio/RunEventList";
import { runStatusLabel, runTone, workflowRunAsAgentRun } from "../studio/studio-run-ui";
import { RunApprovalBar } from "../studio/RunApprovalBar";
import { runDetailHref, runMonitorHref, runStudioHref, type RunIdentity } from "./run-location";

export function RunEvidence({ run, locale }: { run: AgentRunResponse | WorkflowRunResponse; locale: "zh" | "en" }) {
  const identity: RunIdentity = { projectId: run.project_id, runId: run.run_id, ...("agent_id" in run ? { agentId: run.agent_id } : { workflowId: run.workflow_id }) };
  const lineage = run.events?.find((event) => event.kind === "run.created")?.payload;
  const origin = lineage?.retry_of_run_id ?? lineage?.resume_of_run_id;
  return <>
    <h3>{run.run_id}</h3>
    <StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} />
    <dl className="detail-list">
      <div><dt>{locale === "zh" ? "版本" : "Version"}</dt><dd>{run.version_id}</dd></div>
      <div><dt>{locale === "zh" ? "开始时间" : "Started"}</dt><dd>{run.created_at}</dd></div>
      <div><dt>{locale === "zh" ? "结束时间" : "Finished"}</dt><dd>{run.finished_at ?? "—"}</dd></div>
    </dl>
    <div className="button-row">
      {typeof origin === "string" ? <LinkButton href={runDetailHref({ ...identity, runId: origin })}>{locale === "zh" ? "原运行" : "Original run"}</LinkButton> : null}
      <LinkButton href={runDetailHref(identity)}>{locale === "zh" ? "运行详情" : "Run detail"}</LinkButton>
      <LinkButton href={runStudioHref(identity)}>Studio</LinkButton>
      <LinkButton href={runMonitorHref(identity)}>Monitor</LinkButton>
    </div>
    {run.error ? <Alert type="error" title={run.error.message} description={run.error.code} /> : null}
    {run.result ? <pre><code>{JSON.stringify(run.result, null, 2)}</code></pre> : null}
    {run.events ? <RunEventList events={run.events} locale={locale} /> : null}
  </>;
}

export function RunDetail({ api, projectId, agentId, workflowId, runId, locale }: RunIdentity & { api: LocalProjectApi; locale: "zh" | "en" }) {
  const [run, setRun] = useState<AgentRunResponse | WorkflowRunResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const pendingCommand = useRef<string | null>(null);
  const recoveryKeys = useRef(new Map<string, string>());
  const identity = `${projectId}:${agentId}:${workflowId}:${runId}`;
  const activeIdentity = useRef(identity);
  activeIdentity.current = identity;
  const checkpoint = run?.events?.filter((event) => event.kind === "checkpoint.created").at(-1);
  const checkpointId = checkpoint?.payload.waiting_kind === "execution" && typeof checkpoint.payload.checkpoint_id === "string" ? checkpoint.payload.checkpoint_id : undefined;
  const dispatchedAfterCheckpoint = checkpoint && run?.events?.some((event) => event.kind === "tool.started" && event.sequence > checkpoint.sequence);
  const command = async (value: "approve" | "reject" | "stop" | "retry" | "resume") => {
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
      else if (workflowId) await api.commandWorkflowRun!(projectId, workflowId, runId, { command: value });
      else await api.commandAgentRun!(projectId, agentId!, runId, { command: value });
      if (activeIdentity.current === identity) setRefresh((value) => value + 1);
    } catch (cause) {
      if (activeIdentity.current === identity) setError(cause instanceof Error ? cause.message : "Run command failed");
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
  return <>
    {error ? <Alert type="error" title={error} /> : null}
    <RunApprovalBar run={"workflow_id" in run ? workflowRunAsAgentRun(run) : run} locale={locale} disabled={busy || !canCommand} onCommand={(value) => void command(value)} />
    {run.status === "running" && canCommand ? <Button disabled={busy} onClick={() => void command("stop")}>{locale === "zh" ? "停止" : "Stop"}</Button> : null}
    {!workflowId && canCommand && ["failed", "interrupted", "cancelled"].includes(run.status) ? <Button disabled={busy} onClick={() => void command("retry")}>{locale === "zh" ? "安全重试" : "Retry safely"}</Button> : null}
    {!workflowId && canCommand && ["failed", "interrupted"].includes(run.status) && checkpointId && !dispatchedAfterCheckpoint ? <Button disabled={busy} onClick={() => void command("resume")}>{locale === "zh" ? "从检查点恢复" : "Resume from checkpoint"}</Button> : null}
    {workflowId && ["failed", "interrupted"].includes(run.status) ? <p>{locale === "zh" ? "此 Workflow 没有可安全恢复的执行检查点；不支持 Retry / Resume。" : "This Workflow has no safely recoverable execution checkpoint; Retry / Resume are unsupported."}</p> : null}
    <RunEvidence run={run} locale={locale} />
  </>;
}
