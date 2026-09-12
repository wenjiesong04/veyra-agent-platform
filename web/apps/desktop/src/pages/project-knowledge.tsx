import { ArrowLeft, BookOpen, Plus, RefreshCw } from "lucide-react";
import { projectRoutePaths, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";
import { bindKnowledgeToAgent } from "../features/projects/knowledge-runtime";

export function ProjectKnowledgePage({ projectId, knowledgeId }: { projectId: string; knowledgeId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [bindingAgentId, setBindingAgentId] = useState("");
  const [binding, setBinding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? {
    eyebrow: "项目", back: "返回项目", backKnowledge: "返回知识", refresh: "刷新", create: "创建知识", knowledge: "知识", noKnowledge: "还没有知识资料", noKnowledgeDetail: "当资料加入这个项目后，它们会显示在这里。", serviceError: "无法读取这个项目。", notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。", descriptionFallback: "这个项目尚未添加描述。", preview: "预览", runtime: "Runtime 上下文", useInAgent: "在 Agent 中使用", useInAgentDetail: "绑定后，这份知识会按版本和内容 hash 注入所选 Agent 的模型上下文。", chooseAgent: "选择 Agent", bind: "绑定并打开 Studio", binding: "正在绑定…", noAgents: "当前 Project 还没有 Agent。请先创建一个 Agent。",
  } : {
    eyebrow: "Project", back: "Back to Projects", backKnowledge: "Back to Knowledge", refresh: "Refresh", create: "Create Knowledge", knowledge: "Knowledge", noKnowledge: "No Knowledge yet", noKnowledgeDetail: "Knowledge documents will appear here when they are added to this Project.", serviceError: "This Project could not be read.", notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.", descriptionFallback: "This Project has no description yet.", preview: "Preview", runtime: "Runtime context", useInAgent: "Use in an Agent", useInAgentDetail: "After binding, this document is injected into the selected Agent's model context with version and content-hash verification.", chooseAgent: "Choose an Agent", bind: "Bind and open Studio", binding: "Binding…", noAgents: "This Project has no Agent yet. Create an Agent first.",
  };
  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getProject(projectId);
      setProject(response);
      upsertProject(response);
      if (knowledgeId && api.getKnowledge) {
        const document = await api.getKnowledge(projectId, knowledgeId);
        setText(document.text);
      } else {
        setText(null);
      }
    } catch (cause) {
      setProject(null);
      setText(null);
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setLoading(false);
    }
  }, [api, copy.serviceError, knowledgeId, projectId, upsertProject]);
  useEffect(() => { void loadProject(); }, [loadProject]);
  useEffect(() => {
    setBindingAgentId((current) => (
      project?.agents.some((agent) => agent.agent_id === current)
        ? current
        : project?.agents[0]?.agent_id ?? ""
    ));
  }, [project]);
  const createKnowledge = async () => {
    if (!api.createKnowledge) return;
    setCreating(true);
    setError(null);
    try {
      const created = await api.createKnowledge(projectId, { name: zh ? "新知识" : "New Knowledge" });
      const refreshed = await api.getProject(projectId);
      setProject(refreshed);
      upsertProject(refreshed);
      window.location.hash = projectRoutePaths.knowledgeItem(projectId, created.knowledge_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setCreating(false);
    }
  };
  const bindKnowledge = async () => {
    if (!selected || !bindingAgentId || !api.saveDraft) return;
    setBinding(true);
    setError(null);
    try {
      const current = api.getKnowledge
        ? await api.getKnowledge(projectId, selected.knowledge_id)
        : selected;
      await bindKnowledgeToAgent(api, projectId, bindingAgentId, {
        ...selected,
        version: current.version ?? selected.version,
        source_file_hash: current.source_file_hash,
      });
      window.location.hash = projectRoutePaths.agentDesign(projectId, bindingAgentId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setBinding(false);
    }
  };
  if (loading && !project) return <LoadingState label={zh ? "正在加载项目…" : "Loading Project…"} />;
  if (error && !project) return <div className="project-missing"><ErrorState message={error || copy.notFound} onRetry={() => void loadProject()} /><p>{copy.notFound}</p><div className="intro-actions"><LinkButton href="#/projects" icon={ArrowLeft} variant="primary">{copy.back}</LinkButton><Button icon={RefreshCw} onClick={() => void loadProject()}>{copy.refresh}</Button></div></div>;
  if (!project) return null;
  const documents = project.knowledge ?? [];
  const selected = knowledgeId ? documents.find((item) => item.knowledge_id === knowledgeId) : undefined;
  if (knowledgeId && selected) {
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.knowledge}</span><h2>{selected.name || selected.slug}</h2><p>{selected.source_path}</p></div><div className="intro-actions"><LinkButton href={projectRoutePaths.knowledge(projectId)} icon={ArrowLeft} variant="ghost">{copy.backKnowledge}</LinkButton><Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button></div></div>
      {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
      <Panel><SectionHeading eyebrow={copy.preview} title={selected.name || selected.slug} />{text !== null ? <pre className="project-file-preview">{text}</pre> : null}</Panel>
      <Panel><SectionHeading eyebrow={copy.runtime} title={copy.useInAgent} detail={copy.useInAgentDetail} />{project.agents.length ? <div className="button-row"><select aria-label={copy.chooseAgent} value={bindingAgentId} onChange={(event) => setBindingAgentId(event.target.value)}>{project.agents.map((agent) => <option value={agent.agent_id} key={agent.agent_id}>{agent.name || agent.slug}</option>)}</select><Button variant="primary" onClick={() => void bindKnowledge()} disabled={binding || !bindingAgentId || !api.saveDraft}>{binding ? copy.binding : copy.bind}</Button></div> : <p className="project-file-preview">{copy.noAgents}</p>}</Panel>
    </div>;
  }
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{project.name}</h2><p>{project.description || copy.descriptionFallback}</p></div><div className="intro-actions"><Button icon={Plus} variant="primary" onClick={() => void createKnowledge()} disabled={creating || !api.createKnowledge}>{copy.create}</Button><Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button></div></div>
    {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
    <Panel><SectionHeading eyebrow={copy.knowledge} title={`${documents.length} ${copy.knowledge}`} />{documents.length === 0 ? <EmptyState icon={BookOpen} title={copy.noKnowledge} detail={copy.noKnowledgeDetail} /> : <div className="project-agent-tree">{documents.map((item) => <a className="project-agent-row" href={projectRoutePaths.knowledgeItem(project.project_id, item.knowledge_id)} key={item.knowledge_id}><span className="row-icon"><BookOpen size={17} aria-hidden="true" /></span><span className="row-copy"><strong>{item.name || item.slug}</strong><small>{item.source_path}</small></span></a>)}</div>}</Panel>
  </div>;
}
