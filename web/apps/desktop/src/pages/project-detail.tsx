import { ArrowLeft, Bot, FolderKanban, Pin, PinOff, RefreshCw } from "lucide-react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

export function ProjectDetailPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale(); const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null); const [loading, setLoading] = useState(true); const [pinning, setPinning] = useState(false); const [error, setError] = useState<string | null>(null);
  const copy = zh ? { eyebrow: "项目", back: "返回项目", refresh: "刷新", pin: "置顶项目", unpin: "取消置顶", agents: "Agent", noAgents: "还没有 Agent", noAgentsDetail: "当 Agent 加入这个项目后，它们会显示在这里。", serviceError: "无法读取这个项目。", notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。", descriptionFallback: "这个项目尚未添加描述。", path: "目录" } : { eyebrow: "Project", back: "Back to Projects", refresh: "Refresh", pin: "Pin Project", unpin: "Unpin Project", agents: "Agents", noAgents: "No Agents yet", noAgentsDetail: "Agents will appear here when they are added to this Project.", serviceError: "This Project could not be read.", notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.", descriptionFallback: "This Project has no description yet.", path: "Directory" };
  const loadProject = useCallback(async () => { setLoading(true); setError(null); try { const response = await api.getProject(projectId); setProject(response); upsertProject(response); } catch (cause) { setProject(null); setError(cause instanceof Error ? cause.message : copy.serviceError); } finally { setLoading(false); } }, [api, copy.serviceError, projectId, upsertProject]);
  useEffect(() => { void loadProject(); }, [loadProject]);
  const togglePinned = async () => { if (!project) return; setPinning(true); setError(null); try { const response = await api.updateProject(project.project_id, { pinned: !project.pinned }); setProject(response); upsertProject(response); } catch (cause) { setError(cause instanceof Error ? cause.message : copy.serviceError); } finally { setPinning(false); } };
  if (loading && !project) return <LoadingState label={zh ? "正在加载项目…" : "Loading Project…"} />;
  if (error && !project) return <div className="project-missing"><ErrorState message={error || copy.notFound} onRetry={() => void loadProject()} /><p>{copy.notFound}</p><div className="intro-actions"><LinkButton href="#/projects" icon={ArrowLeft} variant="primary">{copy.back}</LinkButton><Button icon={RefreshCw} onClick={() => void loadProject()}>{copy.refresh}</Button></div></div>;
  if (!project) return null;
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{project.name}</h2><p>{project.description || copy.descriptionFallback}</p></div><div className="intro-actions"><LinkButton href="#/projects" icon={ArrowLeft} variant="ghost">{copy.back}</LinkButton><Button icon={project.pinned ? PinOff : Pin} onClick={() => void togglePinned()} disabled={pinning}>{project.pinned ? copy.unpin : copy.pin}</Button><Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button></div></div>
    {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
    <Panel className="project-detail-summary"><span className="project-overview-icon"><FolderKanban size={19} aria-hidden="true" /></span><div><span className="ui-eyebrow">{copy.path}</span><p className="project-path">{project.root_path}</p></div><div><span className="ui-eyebrow">{copy.agents}</span><strong>{project.agents.length}</strong></div></Panel>
    <Panel><SectionHeading eyebrow={copy.agents} title={`${project.agents.length} ${copy.agents}`} />{project.agents.length === 0 ? <EmptyState icon={Bot} title={copy.noAgents} detail={copy.noAgentsDetail} /> : <div className="project-agent-list">{project.agents.map((agent) => <div className="project-agent-row" key={agent.agent_id}><span className="row-icon"><Bot size={17} aria-hidden="true" /></span><span className="row-copy"><strong>{agent.slug}</strong><small>{agent.source_path}</small></span></div>)}</div>}</Panel>
  </div>;
}
