import { ArrowLeft, GitBranch, Plus, RefreshCw } from "lucide-react";
import { projectRoutePaths, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

export function ProjectWorkflowsPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? {
    eyebrow: "项目", back: "返回项目", refresh: "刷新", create: "创建工作流", workflows: "工作流", noWorkflows: "还没有工作流", noWorkflowsDetail: "当工作流加入这个项目后，它们会显示在这里。", serviceError: "无法读取这个项目。", notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。", descriptionFallback: "这个项目尚未添加描述。",
  } : {
    eyebrow: "Project", back: "Back to Projects", refresh: "Refresh", create: "Create Workflow", workflows: "Workflows", noWorkflows: "No Workflows yet", noWorkflowsDetail: "Workflows will appear here when they are added to this Project.", serviceError: "This Project could not be read.", notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.", descriptionFallback: "This Project has no description yet.",
  };
  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getProject(projectId);
      setProject(response);
      upsertProject(response);
    } catch (cause) {
      setProject(null);
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setLoading(false);
    }
  }, [api, copy.serviceError, projectId, upsertProject]);
  useEffect(() => { void loadProject(); }, [loadProject]);
  const createWorkflow = async () => {
    if (!api.createWorkflow) return;
    setCreating(true);
    setError(null);
    try {
      const created = await api.createWorkflow(projectId, { name: zh ? "新工作流" : "New Workflow" });
      const refreshed = await api.getProject(projectId);
      setProject(refreshed);
      upsertProject(refreshed);
      window.location.hash = projectRoutePaths.workflow(projectId, created.workflow_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setCreating(false);
    }
  };
  if (loading && !project) return <LoadingState label={zh ? "正在加载项目…" : "Loading Project…"} />;
  if (error && !project) return <div className="project-missing"><ErrorState message={error || copy.notFound} onRetry={() => void loadProject()} /><p>{copy.notFound}</p><div className="intro-actions"><LinkButton href="#/projects" icon={ArrowLeft} variant="primary">{copy.back}</LinkButton><Button icon={RefreshCw} onClick={() => void loadProject()}>{copy.refresh}</Button></div></div>;
  if (!project) return null;
  const workflows = project.workflows ?? [];
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{project.name}</h2><p>{project.description || copy.descriptionFallback}</p></div><div className="intro-actions"><Button icon={Plus} variant="primary" onClick={() => void createWorkflow()} disabled={creating || !api.createWorkflow}>{copy.create}</Button><Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button></div></div>
    {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
    <Panel><SectionHeading eyebrow={copy.workflows} title={`${workflows.length} ${copy.workflows}`} />{workflows.length === 0 ? <EmptyState icon={GitBranch} title={copy.noWorkflows} detail={copy.noWorkflowsDetail} /> : <div className="project-agent-tree">{workflows.map((workflow) => <a className="project-agent-row" href={projectRoutePaths.workflow(project.project_id, workflow.workflow_id)} key={workflow.workflow_id}><span className="row-icon"><GitBranch size={17} aria-hidden="true" /></span><span className="row-copy"><strong>{workflow.name || workflow.slug}</strong><small>{workflow.source_path}</small></span></a>)}</div>}</Panel>
  </div>;
}
