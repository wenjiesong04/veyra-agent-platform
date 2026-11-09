import * as React from "react";
import { ErrorState, LoadingState, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { AgentChatSurface } from "../features/agents/chat/AgentChatSurface";

export function AgentDetailPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const { api, projects, upsertProject } = useProjectWorkspace();
  const cached = projects.find((project) => project.project_id === projectId) ?? null;
  const [loading, setLoading] = React.useState(!cached);
  const [error, setError] = React.useState("");
  const [project, setProject] = React.useState(cached);

  React.useEffect(() => {
    const existing = projects.find((item) => item.project_id === projectId);
    if (existing) {
      setProject(existing);
      setLoading(false);
      return;
    }
    let current = true;
    setLoading(true);
    void api.getProject(projectId)
      .then((next) => {
        if (!current) return;
        setProject(next);
        upsertProject(next);
      })
      .catch((cause) => {
        if (!current) return;
        setError(cause instanceof Error ? cause.message : (locale === "zh" ? "无法读取这个 Agent。" : "This Agent could not be read."));
      })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, locale, projectId, projects, upsertProject]);

  if (loading && !project) return <LoadingState label={locale === "zh" ? "正在打开 Agent…" : "Opening Agent…"} />;
  const agent = project?.agents.find((item) => item.agent_id === agentId);
  if (error || !project || !agent) {
    return <ErrorState message={error || (locale === "zh" ? "找不到这个 Agent。" : "This Agent was not found.")} />;
  }
  return <AgentChatSurface api={api} projectId={projectId} agentId={agent.agent_id} locale={locale} />;
}
