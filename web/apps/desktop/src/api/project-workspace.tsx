import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { LocalApiClientError, type LocalProjectApi } from "./local-client";

export type ProjectLoadState = "loading" | "ready" | "error";

type ProjectWorkspaceValue = {
  api: LocalProjectApi;
  projects: ProjectSummaryResponse[];
  status: ProjectLoadState;
  error: string | null;
  refresh: () => Promise<void>;
  upsertProject: (project: ProjectSummaryResponse) => void;
  setProjectPinned: (projectId: string, pinned: boolean) => Promise<ProjectSummaryResponse>;
};

const ProjectWorkspaceContext = createContext<ProjectWorkspaceValue | null>(null);

function errorMessage(error: unknown): string {
  if (error instanceof LocalApiClientError) return error.message;
  return "The local Project service is unavailable. Check that the Desktop sidecar is running.";
}

export function ProjectWorkspaceProvider({ api, children }: PropsWithChildren<{ api: LocalProjectApi }>) {
  const [projects, setProjects] = useState<ProjectSummaryResponse[]>([]);
  const [status, setStatus] = useState<ProjectLoadState>("loading");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const response = await api.listProjects();
      setProjects(response.projects);
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
      const index = current.findIndex((item) => item.project_id === project.project_id);
      if (index < 0) return [...current, project];
      return current.map((item, itemIndex) => itemIndex === index ? project : item);
    });
  }, []);

  const setProjectPinned = useCallback(async (projectId: string, pinned: boolean) => {
    const project = await api.updateProject(projectId, { pinned });
    upsertProject(project);
    return project;
  }, [api, upsertProject]);

  const value = useMemo<ProjectWorkspaceValue>(() => ({
    api,
    projects,
    status,
    error,
    refresh,
    upsertProject,
    setProjectPinned,
  }), [api, projects, status, error, refresh, upsertProject, setProjectPinned]);

  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
}

export function useProjectWorkspace(): ProjectWorkspaceValue {
  const context = useContext(ProjectWorkspaceContext);
  if (!context) throw new Error("useProjectWorkspace must be used inside ProjectWorkspaceProvider");
  return context;
}
