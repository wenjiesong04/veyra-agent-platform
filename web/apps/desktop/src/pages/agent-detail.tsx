import { ArrowLeft, Code2, Play, Wrench } from "lucide-react";
import { projectRoutePaths, type DraftResponse, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

export function AgentDetailPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? { loading: "正在加载 Agent…", loadFailed: "无法加载这个 Agent。", notFound: "找不到 Agent", missing: "请求的 Agent 不属于此项目。", back: "返回项目", list: "Agent 列表", studio: "打开 Studio", run: "运行", eyebrow: "当前草稿", detail: "这是当前由服务器提供的 Agent 源定义。", revision: "修订版本", nodes: "节点", definition: "定义", inspectable: "可检查", views: "源码视图", roundTrip: "往返编辑界面", viewDetail: "表单、Canvas 和源码编辑同一份规范化 Agent 定义。" } : { loading: "Loading Agent…", loadFailed: "This Agent could not be loaded.", notFound: "Agent not found", missing: "The requested Agent does not belong to this Project.", back: "Back to Project", list: "Agent list", studio: "Open Studio", run: "Run", eyebrow: "Current draft", detail: "This is the current server-backed Agent source.", revision: "Revision", nodes: "Nodes", definition: "Definition", inspectable: "Inspectable", views: "Source views", roundTrip: "Round-trip surface", viewDetail: "Form, Canvas, and Source edit the same normalized Agent definition." };
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let current = true;
    setLoading(true); setError(null);
    void Promise.all([api.getProject(projectId), api.getDraft(projectId, agentId)]).then(([nextProject, nextDraft]) => {
      if (!current) return;
      setProject(nextProject); setDraft(nextDraft); upsertProject(nextProject);
    }).catch((cause: unknown) => { if (current) setError(cause instanceof Error ? cause.message : copy.loadFailed); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [agentId, api, copy.loadFailed, projectId, upsertProject]);

  if (loading) return <LoadingState label={copy.loading} />;
  if (error || !project || !draft) return <div className="project-missing"><ErrorState message={error ?? copy.notFound} /><LinkButton href={project ? projectRoutePaths.project(project.project_id) : "#/projects"} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  const agent = project.agents.find((item) => item.agent_id === agentId);
  if (!agent) return <div className="project-missing"><StatusBadge label={copy.notFound} tone="bad" /><p>{copy.missing}</p><LinkButton href={projectRoutePaths.project(project.project_id)} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  const source = draft.source;
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Agent / {project.name}</span><h2>{source.name}</h2><p>{source.description || agent.source_path}</p></div><div className="intro-actions"><LinkButton href={projectRoutePaths.agents(project.project_id)} icon={ArrowLeft} variant="ghost">{copy.list}</LinkButton><LinkButton href={projectRoutePaths.agentDesign(project.project_id, agent.agent_id)} icon={Wrench} variant="primary">{copy.studio}</LinkButton><LinkButton href={projectRoutePaths.agentRun(project.project_id, agent.agent_id)} icon={Play}>{copy.run}</LinkButton></div></div><div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.eyebrow} title={source.slug} detail={copy.detail} /><div className="settings-facts"><div><span>{copy.revision}</span><strong>{draft.revision}</strong></div><div><span>{copy.nodes}</span><strong>{source.nodes.length}</strong></div><div><span>{copy.definition}</span><Tag tone="good">{copy.inspectable}</Tag></div></div></Panel><Panel><SectionHeading eyebrow={copy.views} title={copy.roundTrip} /><div className="account-note"><Code2 size={15} /><span>{copy.viewDetail}</span></div><p className="project-path">{agent.source_path}</p></Panel></div></div>;
}
