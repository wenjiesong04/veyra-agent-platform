import * as React from "react";
import { useLocale, LoadingState, ErrorState } from "@veyra/ui";
import { ChatLanding } from "../features/agents/chat/chat-landing";
import { useChatScopeNavigation, type ChatTarget } from "../features/agents/chat/chat-scope";
import { ProjectBuilderConversation } from "../features/builder/ProjectBuilderConversation";
import { useProjectWorkspace } from "../api/project-workspace";

export function NewChatPage({ projectId }: { projectId?: string } = {}) {
  const { locale } = useLocale();
  const { api, projects, upsertProject } = useProjectWorkspace();
  const { select, createProject, start } = useChatScopeNavigation();
  const [scopedProject, setScopedProject] = React.useState(() => projects.find((project) => project.project_id === projectId) ?? null);
  const [scopedError, setScopedError] = React.useState(false);

  React.useEffect(() => {
    if (!projectId) return;
    const existing = projects.find((project) => project.project_id === projectId);
    if (existing) {
      setScopedProject(existing);
      setScopedError(false);
      return;
    }
    setScopedError(false);
    void api.getProject(projectId).then((next) => {
      setScopedProject(next);
      upsertProject(next);
    }).catch(() => {
      setScopedProject(null);
      setScopedError(true);
    });
  }, [api, projectId, projects, upsertProject]);

  const current: ChatTarget = scopedProject
    ? { kind: "project", projectId: scopedProject.project_id, name: scopedProject.name }
    : { kind: "new" };

  if (projectId && scopedError) {
    return <ErrorState message={locale === "zh" ? "无法打开这个项目。" : "This Project could not be opened."} />;
  }

  if (projectId && !scopedProject) {
    return <LoadingState label={locale === "zh" ? "正在打开项目…" : "Opening Project…"} />;
  }

  if (projectId && scopedProject) {
    return (
      <ProjectBuilderConversation
        key={scopedProject.project_id}
        project={scopedProject}
        locale={locale}
        scope={{
          current,
          projects,
          onSelect: select,
          onCreateProject: createProject,
        }}
      />
    );
  }

  return (
    <ChatLanding
      locale={locale}
      projects={projects}
      onSelect={select}
      onCreateProject={createProject}
      onStart={start}
    />
  );
}
