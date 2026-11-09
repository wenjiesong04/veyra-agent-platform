import * as React from "react";
import type { AgentRunResponse, JsonValue, RuntimeEvent, RuntimeRunStatus, WorkflowRunResponse } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { persistRunId } from "../runs/run-location";
import { newUuidV7 } from "../../api/uuid";
import { isBudgetWaiting } from "./BudgetContinuation";

export type LiveRunCommand = "approve" | "reject" | "stop" | "reply" | "extend_budget";

export function runCommandKey(keys: Map<string, string>, run: AgentRunResponse | WorkflowRunResponse, command: string, additionalTurns?: number): string {
  const identity = `${run.project_id}:${run.run_id}:${command}:${approvalRequestId(run) ?? ""}:${additionalTurns ?? ""}`;
  const existing = keys.get(identity);
  if (existing) return existing;
  const key = newUuidV7();
  keys.set(identity, key);
  return key;
}

export type NodeRunState = "pending" | "running" | "waiting" | "completed" | "failed";

export type StartLiveRunOptions = {
  conversationId?: string;
  source?: "draft" | "committed";
  versionId?: string;
};

export type LiveRunSession = {
  run: AgentRunResponse | null;
  error: string;
  busy: boolean;
  start: (inputs: Record<string, JsonValue>, options?: StartLiveRunOptions) => Promise<void>;
  sendCommand: (command: LiveRunCommand, inputs?: Record<string, JsonValue>, additionalTurns?: number) => Promise<void>;
  restore: (runId: string) => Promise<void>;
  clear: () => void;
};

const LiveRunContext = React.createContext<LiveRunSession | null>(null);

function asRunStatus(value: unknown): RuntimeRunStatus | null {
  return value === "running" || value === "waiting" || value === "verified" || value === "unverified"
    || value === "failed" || value === "interrupted" || value === "cancelled"
    ? value
    : null;
}

export function inferRunStatus(current: RuntimeRunStatus, events: RuntimeEvent[]): RuntimeRunStatus {
  let status = current;
  for (const event of events) {
    if (event.kind === "run.completed") status = asRunStatus(event.payload.state) ?? "unverified";
    else if (event.kind === "run.failed") status = "failed";
    else if (event.kind === "run.cancelled") status = "cancelled";
    else if (event.kind === "run.interrupted") status = "interrupted";
    else if (event.kind === "node.waiting" || event.kind === "approval.requested") status = "waiting";
    else if (event.kind === "approval.resolved" || event.kind === "run.started") status = "running";
  }
  return status;
}

export function streamText(events: RuntimeEvent[]): string {
  return events
    .filter((event) => event.kind === "model.delta")
    .map((event) => event.payload.delta)
    .filter((value): value is string => typeof value === "string")
    .join("");
}

export function applyRuntimeEvent(run: AgentRunResponse | null, event: RuntimeEvent): AgentRunResponse | null {
  if (!run || run.run_id !== event.run_id) return run;
  const events = [...(run.events ?? [])];
  if (events.some((item) => item.event_id === event.event_id || item.sequence === event.sequence)) return run;
  events.push(event);
  events.sort((left, right) => left.sequence - right.sequence);
  return { ...run, events, stream_text: streamText(events), status: inferRunStatus(run.status, events) };
}

export function nodeRunStates(source: { nodes: Array<{ id: string }> }, events: RuntimeEvent[]): { id: string; state: NodeRunState }[] {
  return source.nodes.map((node) => {
    let state: NodeRunState = "pending";
    for (const event of events) {
      if (event.node_id !== node.id) continue;
      if (event.kind === "node.failed") state = "failed";
      else if (event.kind === "node.waiting") state = "waiting";
      else if (event.kind === "node.completed") state = "completed";
      else if (event.kind === "node.started" && state === "pending") state = "running";
    }
    return { id: node.id, state };
  });
}

export function approvalPrompt(run: AgentRunResponse | null): string {
  const prompt = [...(run?.events ?? [])].reverse().find((event) => event.kind === "approval.requested")?.payload.prompt;
  return typeof prompt === "string" ? prompt : "";
}

export function approvalRequestId(run: AgentRunResponse | WorkflowRunResponse | null): string | undefined {
  if (run?.status !== "waiting") return undefined;
  if ("workflow_id" in run) {
    const id = run.waiting?.request_id;
    return typeof id === "string" && id.trim() ? id : undefined;
  }
  const request = [...(run.events ?? [])].reverse().find((event) => event.kind === "approval.requested");
  const id = request?.payload.request_id;
  return typeof id === "string" && id.trim() ? id : request?.payload.kind === "budget" ? undefined : request?.event_id;
}

export function approvalRequestBinding(run: AgentRunResponse | WorkflowRunResponse | null, command: string): { expected_request_id?: string } {
  if (command === "extend_budget" || (command === "stop" && isBudgetWaiting(run))) {
    if (!isBudgetWaiting(run)) throw new Error("The current budget request is unavailable. Refresh the run before responding.");
    const id = approvalRequestId(run);
    if (!id) throw new Error("The current budget request is unavailable. Refresh the run before responding.");
    return { expected_request_id: id };
  }
  if (!["approve", "reject", "reply"].includes(command)) return {};
  const id = approvalRequestId(run);
  if (!id) throw new Error("The current request is unavailable. Refresh the run before responding.");
  return { expected_request_id: id };
}

function useLiveRunSession({
  api,
  projectId,
  agentId,
  locale = "en",
  inactive = false,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  locale?: "zh" | "en";
  inactive?: boolean;
}): LiveRunSession {
  const [run, setRun] = React.useState<AgentRunResponse | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const commandKeys = React.useRef(new Map<string, string>());
  const pendingCommand = React.useRef(false);
  const restoreEpoch = React.useRef(0);
  React.useEffect(() => () => { restoreEpoch.current += 1; }, [api, projectId, agentId, inactive]);

  const adopt = React.useCallback((next: AgentRunResponse, previous: AgentRunResponse | null = null) => {
    const bySequence = new Map<number, RuntimeEvent>();
    for (const event of [...(previous?.events ?? []), ...(next.events ?? [])]) {
      if (event.run_id === next.run_id) bySequence.set(event.sequence, event);
    }
    const events = [...bySequence.values()].sort((left, right) => left.sequence - right.sequence);
    return {
      ...next,
      events,
      status: inferRunStatus(next.status, events),
      stream_text: streamText(events) || next.stream_text || previous?.stream_text || "",
    };
  }, []);

  const start = React.useCallback(async (inputs: Record<string, JsonValue>, options: StartLiveRunOptions = {}) => {
    if (inactive || !api.runAgent || busy) return;
    restoreEpoch.current += 1;
    setBusy(true);
    setError("");
    try {
      const started = await api.runAgent(projectId, agentId, {
        inputs,
        ...(options.conversationId ? { conversation_id: options.conversationId } : {}),
        ...(options.source ? { source: options.source } : {}),
        ...(options.versionId ? { version_id: options.versionId } : {}),
      });
      if (window.location.hash.split("?")[0]?.endsWith("/design")) persistRunId(started.run_id);
      const detailed = api.getAgentRun
        ? await api.getAgentRun(projectId, agentId, started.run_id)
        : started;
      setRun(adopt(detailed, started));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (locale === "zh" ? "本地运行失败。" : "The local run failed."));
    } finally {
      setBusy(false);
    }
  }, [inactive, api, projectId, agentId, busy, adopt, locale]);

  const sendCommand = React.useCallback(async (command: LiveRunCommand, inputs?: Record<string, JsonValue>, additionalTurns?: number) => {
    if (inactive || !run || !api.commandAgentRun || busy || pendingCommand.current) return;
    pendingCommand.current = true;
    setBusy(true);
    setError("");
    try {
      const updated = await api.commandAgentRun(projectId, agentId, run.run_id, { command, ...approvalRequestBinding(run, command), ...(inputs ? { inputs } : {}), ...(command === "extend_budget" ? { additional_turns: additionalTurns } : {}) }, ...(isBudgetWaiting(run) ? [{ idempotencyKey: runCommandKey(commandKeys.current, run, command, additionalTurns) }] as const : [] as const));
      if (updated.run_id !== run.run_id || updated.project_id !== projectId || updated.agent_id !== agentId) throw new Error("Runtime run identity mismatch");
      const detailed = api.getAgentRun
        ? await api.getAgentRun(projectId, agentId, updated.run_id)
        : updated;
      if (detailed.run_id !== run.run_id || detailed.project_id !== projectId || detailed.agent_id !== agentId) throw new Error("Runtime run identity mismatch");
      setRun((current) => adopt(detailed, current?.run_id === detailed.run_id ? current : updated));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (locale === "zh" ? "运行命令失败。" : "The run command failed."));
      if (api.getAgentRun) {
        const detailed = await api.getAgentRun(projectId, agentId, run.run_id).catch(() => null);
        if (detailed?.run_id === run.run_id && detailed.project_id === projectId && detailed.agent_id === agentId) {
          setRun((current) => current?.run_id === run.run_id ? adopt(detailed, current) : current);
        }
      }
    } finally {
      pendingCommand.current = false;
      setBusy(false);
    }
  }, [inactive, run, api, projectId, agentId, busy, adopt, locale]);

  const restore = React.useCallback(async (runId: string) => {
    if (inactive || !api.getAgentRun) return;
    const epoch = ++restoreEpoch.current;
    try {
      const detailed = await api.getAgentRun(projectId, agentId, runId);
      if (epoch !== restoreEpoch.current) return;
      if (detailed.run_id !== runId || detailed.project_id !== projectId || detailed.agent_id !== agentId) throw new Error("Runtime run identity mismatch");
      setRun((current) => adopt(detailed, current?.run_id === runId ? current : null));
    } catch (cause) {
      if (epoch === restoreEpoch.current) setError(cause instanceof Error ? cause.message : "Could not restore the active run");
    }
  }, [inactive, api, projectId, agentId, adopt]);

  const clear = React.useCallback(() => {
    restoreEpoch.current += 1;
    setRun(null);
    setError("");
    if (!inactive && window.location.hash.split("?")[0]?.endsWith("/design")) persistRunId(null);
  }, [inactive]);

  React.useEffect(() => {
    if (inactive || !run?.run_id || !api.watchAgentRunEvents) return;
    if (run.status !== "running" && run.status !== "waiting") return;
    const runId = run.run_id;
    const refresh = () => {
      if (!api.getAgentRun) return;
      void api.getAgentRun(projectId, agentId, runId).then((detailed) => {
        setRun((current) => (current?.run_id === detailed.run_id ? adopt(detailed, current) : current));
      }).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not refresh run"));
    };
    return api.watchAgentRunEvents(
      projectId,
      agentId,
      runId,
      {
        onEvent: (event) => {
          setRun((current) => applyRuntimeEvent(current, event));
          if (event.run_id === runId && ["run.completed", "run.failed", "run.cancelled", "run.interrupted"].includes(event.kind)) refresh();
        },
        onDone: refresh,
        onError: () => { refresh(); },
      },
      { after: Math.max(0, ...(run.events ?? []).map((event) => event.sequence)) },
    );
  }, [inactive, api, projectId, agentId, run?.run_id, run?.status, adopt]);

  return { run, error, busy, start, sendCommand, restore, clear };
}

export function LiveRunProvider({
  api,
  projectId,
  agentId,
  locale = "en",
  inactive = false,
  children,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  locale?: "zh" | "en";
  inactive?: boolean;
  children: React.ReactNode;
}) {
  const live = useLiveRunSession({ api, projectId, agentId, locale, inactive });
  return React.createElement(LiveRunContext.Provider, { value: live }, children);
}

export function useLiveRun(opts: { api: LocalProjectApi; projectId: string; agentId: string; locale?: "zh" | "en" }): LiveRunSession {
  const ctx = React.useContext(LiveRunContext);
  const owned = useLiveRunSession({ ...opts, inactive: ctx !== null });
  return ctx ?? owned;
}
