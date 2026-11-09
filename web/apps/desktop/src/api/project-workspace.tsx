import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import type { CommunityApi } from "@veyra/connected-account";
import { LocalApiClientError, type LocalProjectApi } from "./local-client";

export type ProjectLoadState = "loading" | "ready" | "error";

type ProjectWorkspaceValue = {
  api: LocalProjectApi;
  cloudApi?: CommunityApi;
  projects: ProjectSummaryResponse[];
  status: ProjectLoadState;
  error: string | null;
  refresh: () => Promise<void>;
  upsertProject: (project: ProjectSummaryResponse) => void;
  removeProject: (projectId: string) => void;
  setProjectPinned: (projectId: string, pinned: boolean) => Promise<ProjectSummaryResponse>;
  createProject: (input: Parameters<LocalProjectApi["createProject"]>[0]) => Promise<ProjectSummaryResponse>;
  updateProject: (projectId: string, input: Parameters<LocalProjectApi["updateProject"]>[1]) => Promise<ProjectSummaryResponse>;
  syncProjectArtifacts: (projectId: string) => Promise<void>;
};

const ProjectWorkspaceContext = createContext<ProjectWorkspaceValue | null>(null);

function errorMessage(error: unknown): string {
  if (error instanceof LocalApiClientError) return error.message;
  return "The local Project service is unavailable. Check that the Desktop sidecar is running.";
}

function uniqueProjects(projects: readonly ProjectSummaryResponse[]): ProjectSummaryResponse[] {
  const seen = new Set<string>();
  return projects.filter((project) => {
    if (seen.has(project.project_id)) return false;
    seen.add(project.project_id);
    return true;
  });
}

export function ProjectWorkspaceProvider({ api, cloudApi, children }: PropsWithChildren<{ api: LocalProjectApi; cloudApi?: CommunityApi }>) {
  const [projects, setProjects] = useState<ProjectSummaryResponse[]>([]);
  const [status, setStatus] = useState<ProjectLoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const response = await api.listProjects();
      setProjects(uniqueProjects(response.projects));
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(errorMessage(cause));
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const upsertProject = useCallback((project: ProjectSummaryResponse) => {
    setProjects((current) => {
      const normalized = uniqueProjects(current).map((item) => project.pinned
        ? item.project_id === project.project_id ? project : { ...item, pinned: false, pinned_at: null }
        : item);
      const index = normalized.findIndex((item) => item.project_id === project.project_id);
      if (index < 0) return [...normalized, project];
      return normalized.map((item, itemIndex) => itemIndex === index ? project : item);
    });
  }, []);

  const removeProject = useCallback((projectId: string) => {
    setProjects((current) => current.filter((project) => project.project_id !== projectId));
  }, []);

  const setProjectPinned = useCallback(async (projectId: string, pinned: boolean) => {
    const project = await api.updateProject(projectId, { pinned });
    upsertProject(project);
    return project;
  }, [api, upsertProject]);

  const createProject = useCallback(async (input: Parameters<LocalProjectApi["createProject"]>[0]) => {
    const project = await api.createProject(input);
    upsertProject(project);
    return project;
  }, [api, upsertProject]);

  const updateProject = useCallback(async (projectId: string, input: Parameters<LocalProjectApi["updateProject"]>[1]) => {
    const project = await api.updateProject(projectId, input);
    upsertProject(project);
    return project;
  }, [api, upsertProject]);

  const syncProjectArtifacts = useCallback(async (_projectId: string) => {
    return;
  }, []);

  const value = useMemo<ProjectWorkspaceValue>(() => ({
    api,
    cloudApi,
    projects,
    status,
    error,
    refresh,
    upsertProject,
    removeProject,
    setProjectPinned,
    createProject,
    updateProject,
    syncProjectArtifacts,
  }), [api, cloudApi, projects, status, error, refresh, upsertProject, removeProject, setProjectPinned, createProject, updateProject, syncProjectArtifacts]);

  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
}

export function useProjectWorkspace(): ProjectWorkspaceValue {
  const context = useContext(ProjectWorkspaceContext);
  if (!context) throw new Error("useProjectWorkspace must be used inside ProjectWorkspaceProvider");
  return context;
}
