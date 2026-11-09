import * as React from "react";
import { useLocale, LoadingState, ErrorState } from "@veyra/ui";
import { ChatLanding } from "../features/agents/chat/chat-landing";
import { useChatScopeNavigation, type ChatTarget } from "../features/agents/chat/chat-scope";
import { ProjectBuilderConversation } from "../features/builder/ProjectBuilderConversation";
import { useProjectWorkspace } from "../api/project-workspace";

export function NewChatPage({ projectId, conversationId }: { projectId?: string; conversationId?: string } = {}) {
  const { locale } = useLocale();
  const { api, projects, upsertProject } = useProjectWorkspace();
  const { select, createProject, start } = useChatScopeNavigation();
  const [scopedProject, setScopedProject] = React.useState(() => projects.find((project) => project.project_id === projectId) ?? null);
  const [scopedErrorProjectId, setScopedErrorProjectId] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!projectId) {
      setScopedProject(null);
      setScopedErrorProjectId(null);
      return;
    }
    const existing = projects.find((project) => project.project_id === projectId);
    if (existing) {
      setScopedProject(existing);
      setScopedErrorProjectId(null);
      return;
    }
    let active = true;
    setScopedErrorProjectId(null);
    void api.getProject(projectId).then((next) => {
      if (!active) return;
      setScopedProject(next);
      upsertProject(next);
    }).catch(() => {
      if (!active) return;
      setScopedProject(null);
      setScopedErrorProjectId(projectId);
    });
    return () => { active = false; };
  }, [api, projectId, projects, upsertProject]);

  const currentProject = scopedProject?.project_id === projectId ? scopedProject : null;
  const current: ChatTarget = currentProject
    ? { kind: "project", projectId: currentProject.project_id, name: currentProject.name }
    : { kind: "new" };

  if (projectId && scopedErrorProjectId === projectId) {
    return <ErrorState message={locale === "zh" ? "无法打开这个项目。" : "This Project could not be opened."} />;
  }

  if (projectId && !currentProject) {
    return <LoadingState label={locale === "zh" ? "正在打开项目…" : "Opening Project…"} />;
  }

  if (projectId && currentProject) {
    return (
      <ProjectBuilderConversation
        key={`${currentProject.project_id}:${conversationId ?? "new"}`}
        project={currentProject}
        locale={locale}
        conversationId={conversationId}
        scope={{
          current,
          projects,
          onSelect: select,
          onCreateProject: createProject,
        }}
      />
    );
  }

  return <ChatLanding locale={locale} projects={projects} onSelect={select} onCreateProject={createProject} onStart={start} />;
}
