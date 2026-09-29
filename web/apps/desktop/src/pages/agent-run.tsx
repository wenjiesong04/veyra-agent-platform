import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { ErrorState, LinkButton, LoadingState, Panel, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { AgentChatSurface } from "../features/agents/chat/AgentChatSurface";
import { RunDetail } from "../features/runs/RunDetail";
import { useRunQuery } from "../features/runs/run-location";

export function AgentRunPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects } = useProjectWorkspace();
  const runQuery = useRunQuery();
  const runId = runQuery.get("run_id");
  const cached = projects.find((item) => item.project_id === projectId) ?? null;
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState("");
  const [project, setProject] = useState<ProjectSummaryResponse | null>(cached);

  const load = useCallback(async () => {
    if (runId) return;
    setLoading(true);
    setError("");
    try {
      const next = cached ?? await api.getProject(projectId);
      setProject(next);
      const agent = next.agents.find((item) => item.agent_id === agentId);
      if (!agent) throw new Error(zh ? "这个 Agent 不属于当前项目。" : "This Agent does not belong to the requested Project.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法读取这个 Agent。" : "This Agent could not be read."));
    } finally {
      setLoading(false);
    }
  }, [agentId, api, cached, projectId, zh, runId]);

  useEffect(() => { void load(); }, [load]);

  const agent = project?.agents.find((item) => item.agent_id === agentId);
  const copy = zh ? { back: "返回应用", missing: "找不到这个 Agent。" } : { back: "Back to Agent", missing: "This Agent was not found." };

  if (runId) return <Panel><RunDetail api={api} projectId={projectId} agentId={agentId} runId={runId} locale={locale} /></Panel>;
  if (loading && !agent) return <LoadingState label={zh ? "正在打开 Agent 应用…" : "Opening Agent App…"} />;
  if (error || !project || !agent) {
    return <div className="project-missing"><ErrorState message={error || copy.missing} onRetry={() => void load()} /><LinkButton href={project ? projectRoutePaths.agent(project.project_id, agentId) : "#/projects"} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  }
  return <AgentChatSurface api={api} projectId={projectId} agentId={agent.agent_id} locale={locale} />;
}
