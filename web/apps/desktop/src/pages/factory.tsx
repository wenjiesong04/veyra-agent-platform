import { ErrorState, LoadingState, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../api/project-workspace";
import { useChatScopeNavigation } from "../features/agents/chat/chat-scope";
import { ProjectBuilderConversation } from "../features/builder/ProjectBuilderConversation";

export function FactoryPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const { api, projects, upsertProject } = useProjectWorkspace();
  const { select, createProject } = useChatScopeNavigation();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const zh = locale === "zh";
  const copy = zh
    ? { loading: "正在加载项目…", unavailable: "无法读取这个项目。" }
    : { loading: "Loading Project…", unavailable: "This Project could not be read." };

  useEffect(() => {
    let current = true;
    setLoading(true);
    void api.getProject(projectId)
      .then((next) => { if (current) { setProject(next); upsertProject(next); } })
      .catch(() => { if (current) setError(copy.unavailable); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, copy.unavailable, projectId, upsertProject]);

  if (loading) return <LoadingState label={copy.loading} />;
  if (error || !project) return <ErrorState message={error ?? copy.unavailable} />;
  return (
    <ProjectBuilderConversation
      key={projectId}
      project={project}
      locale={locale}
      scope={{
        current: { kind: "project", projectId, name: project.name },
        projects,
        onSelect: select,
        onCreateProject: createProject,
      }}
    />
  );
}
