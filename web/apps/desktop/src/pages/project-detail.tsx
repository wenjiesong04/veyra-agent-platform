import { ArrowLeft, Bot, FolderOpen, RefreshCw } from "lucide-react";
import { projectRoutePaths, type ProjectAgentRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { AgentRelationGraph } from "../features/projects/AgentRelationGraph";
import { agentTree, type AgentTreeNode } from "../features/projects/agent-tree";

export function ProjectDetailPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? {
    eyebrow: "项目", back: "返回项目", refresh: "刷新", reveal: "查看项目位置", revealFailed: "无法在访达中显示项目文件夹。请允许本机访问磁盘后重试。", agents: "Agent", graph: "协作关系", noAgents: "还没有 Agent", noAgentsDetail: "当 Agent 加入这个项目后，它们会显示在这里。", noGraph: "没有可显示的协作关系。协作边来自 parent_agent_id。", serviceError: "无法读取这个项目。", notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。", descriptionFallback: "这个项目尚未添加描述。",
  } : {
    eyebrow: "Project", back: "Back to Projects", refresh: "Refresh", reveal: "Show Project Location", revealFailed: "The Project folder could not be shown in Finder. Allow disk access and try again.", agents: "Agents", graph: "Collaboration", noAgents: "No Agents yet", noAgentsDetail: "Agents will appear here when they are added to this Project.", noGraph: "No collaboration edges to show. Edges come from parent_agent_id.", serviceError: "This Project could not be read.", notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.", descriptionFallback: "This Project has no description yet.",
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
  const revealProject = () => {
    if (!api.revealProject || !project) return;
    void api.revealProject(project.project_id).catch((cause) => {
      const pickerFailed = cause instanceof LocalApiClientError && (
        cause.code === "directory_picker_failed" || cause.code === "directory_picker_unsupported"
      );
      setError(pickerFailed ? copy.revealFailed : cause instanceof Error ? cause.message : copy.revealFailed);
    });
  };
  if (loading && !project) return <LoadingState label={zh ? "正在加载项目…" : "Loading Project…"} />;
  if (error && !project) return <div className="project-missing"><ErrorState message={error || copy.notFound} onRetry={() => void loadProject()} /><p>{copy.notFound}</p><div className="intro-actions"><LinkButton href="#/projects" icon={ArrowLeft} variant="primary">{copy.back}</LinkButton><Button icon={RefreshCw} onClick={() => void loadProject()}>{copy.refresh}</Button></div></div>;
  if (!project) return null;
  const tree = agentTree(project.agents);
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{project.name}</h2><p>{project.description || copy.descriptionFallback}</p></div><div className="intro-actions"><Button icon={FolderOpen} onClick={revealProject} disabled={!api.revealProject}>{copy.reveal}</Button><Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button></div></div>
    {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
    <Panel><SectionHeading eyebrow={copy.agents} title={`${project.agents.length} ${copy.agents}`} />{tree.length === 0 ? <EmptyState icon={Bot} title={copy.noAgents} detail={copy.noAgentsDetail} /> : <div className="project-agent-tree">{tree.map((node) => <AgentTreeRows key={node.agent_id} projectId={project.project_id} node={node} />)}</div>}</Panel>
    <Panel><SectionHeading eyebrow={copy.graph} title={copy.graph} /><AgentRelationGraph projectId={project.project_id} agents={project.agents} emptyLabel={copy.noGraph} /></Panel>
  </div>;
}

function AgentTreeRows({ projectId, node }: { projectId: string; node: AgentTreeNode<ProjectAgentRecord> }) {
  return (
    <div className="project-agent-tree-node">
      <a className="project-agent-row" href={projectRoutePaths.agentDesign(projectId, node.agent_id)}>
        <span className="row-icon"><Bot size={17} aria-hidden="true" /></span>
        <span className="row-copy"><strong>{node.slug}</strong><small>{node.source_path}</small></span>
      </a>
      {node.children.length ? <div className="project-agent-tree-children">{node.children.map((child) => <AgentTreeRows key={child.agent_id} projectId={projectId} node={child} />)}</div> : null}
    </div>
  );
}
