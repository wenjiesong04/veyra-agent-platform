import { useEffect, useState } from "react";
import { projectRoutePaths } from "@veyra/api-contracts";

export type RunIdentity = { projectId: string; runId: string; agentId?: string; workflowId?: string };

export function withRunId(href: string, runId: string): string {
  return `${href}${href.includes("?") ? "&" : "?"}run_id=${encodeURIComponent(runId)}`;
}

export function runDetailHref(identity: RunIdentity): string {
  return withRunId(identity.workflowId
    ? projectRoutePaths.workflow(identity.projectId, identity.workflowId)
    : projectRoutePaths.agentRun(identity.projectId, identity.agentId!), identity.runId);
}

export function runStudioHref(identity: RunIdentity): string {
  return withRunId(identity.workflowId
    ? projectRoutePaths.workflow(identity.projectId, identity.workflowId)
    : projectRoutePaths.agentDesign(identity.projectId, identity.agentId!), identity.runId);
}

export function runMonitorHref(identity: RunIdentity): string {
  const query = new URLSearchParams({ project_id: identity.projectId, run_id: identity.runId });
  if (identity.agentId) query.set("agent_id", identity.agentId);
  if (identity.workflowId) query.set("workflow_id", identity.workflowId);
  return `#/monitor?${query}`;
}

export function useRunQuery(): URLSearchParams {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const update = () => setHash(window.location.hash);
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return new URLSearchParams(hash.split("?")[1] ?? "");
}

export function persistRunId(runId: string | null): void {
  const [path, rawQuery] = window.location.hash.split("?");
  const query = new URLSearchParams(rawQuery);
  if (runId) query.set("run_id", runId);
  else query.delete("run_id");
  window.history.replaceState(null, "", `${path}${query.size ? `?${query}` : ""}`);
}
