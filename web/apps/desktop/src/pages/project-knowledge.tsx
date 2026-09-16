import { ArrowLeft, BookOpen, Plus, RefreshCw, Trash2, Upload } from "lucide-react";
import {
  projectRoutePaths,
  type KnowledgeProcessing,
  type ProjectKnowledgeRecord,
  type ProjectSummaryResponse,
} from "@veyra/api-contracts";
import {
  Button,
  EmptyState,
  ErrorState,
  IconButton,
  LinkButton,
  LoadingState,
  Panel,
  SectionHeading,
  StatusBadge,
  Tag,
  useLocale,
} from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";
import { LocalApiClientError } from "../api/local-client";
import { bindKnowledgeToAgent } from "../features/projects/knowledge-runtime";

type IndexStatus = KnowledgeProcessing["index_status"];

function indexTone(status: IndexStatus | undefined): "good" | "warn" | "bad" | "neutral" {
  if (status === "indexed") return "good";
  if (status === "failed") return "bad";
  if (status === "stale") return "warn";
  return "neutral";
}

function badgeLabel(status: IndexStatus | undefined, zh: boolean): string {
  if (status === "indexed") return zh ? "已建立索引" : "Indexed";
  if (status === "stale") return zh ? "需重建" : "Needs rebuild";
  if (status === "failed") return zh ? "索引失败" : "Index failed";
  return zh ? "未建立索引" : "Not indexed";
}

function indexLabel(status: IndexStatus | undefined, zh: boolean): string {
  if (status === "indexed") return zh ? "已建立索引" : "Indexed";
  if (status === "stale") {
    return zh
      ? "内容已变化，需要重建索引；旧索引不再有效。"
      : "Content changed; rebuild the index. The old index is no longer valid.";
  }
  if (status === "failed") return zh ? "索引失败（failed）" : "Index failed";
  return zh ? "未建立索引" : "Not indexed";
}

function nextAction(status: IndexStatus | undefined, zh: boolean): string {
  if (status === "indexed") {
    return zh ? "下一步：绑定到 Agent，然后运行查看引用。" : "Next: bind it to an Agent, then run to inspect citations.";
  }
  if (status === "stale") {
    return zh ? "下一步：重建索引后再绑定或运行。" : "Next: rebuild the index before binding or running.";
  }
  if (status === "failed") {
    return zh ? "下一步：查看失败原因后重建索引。" : "Next: review the failure, then rebuild the index.";
  }
  return zh ? "下一步：显式构建检索索引。" : "Next: explicitly build a retrieval index.";
}

export function ProjectKnowledgePage({ projectId, knowledgeId }: { projectId: string; knowledgeId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [upload, setUpload] = useState<File | null>(null);
  const [bindingAgentId, setBindingAgentId] = useState("");
  const [binding, setBinding] = useState(false);
  const [building, setBuilding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? {
    eyebrow: "项目",
    back: "返回项目",
    backKnowledge: "返回知识",
    refresh: "刷新",
    create: "创建知识",
    knowledge: "知识",
    noKnowledge: "还没有知识资料",
    noKnowledgeDetail: "当资料加入这个项目后，它们会显示在这里。",
    serviceError: "无法读取这个项目。",
    notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。",
    descriptionFallback: "这个项目尚未添加描述。",
    preview: "预览",
    runtime: "Runtime 上下文",
    useInAgent: "在 Agent 中使用",
    useInAgentDetail: "显式构建索引并绑定后，Agent 校验版本和内容 hash，仅将相关片段加入模型上下文。",
    chooseAgent: "选择 Agent",
    bind: "绑定并打开 Studio",
    binding: "正在绑定…",
    noAgents: "当前 Project 还没有 Agent。请先创建一个 Agent。",
    title: "知识库",
    description: "上传你明确要给 Agent 使用的资料。文件不会自动进入模型；需要先索引，再绑定。",
    uploadTitle: "上传本地知识文件",
    uploadDetail: "仅 UTF-8 .txt / .md，最大 1,000,000 字节。不自动绑定 Agent。",
    drop: "选择或拖入 .txt / .md",
    selected: "已选择",
    ingest: "上传并解析",
    ingesting: "正在解析…",
    fileLabel: "知识文件",
  } : {
    eyebrow: "Project",
    back: "Back to Projects",
    backKnowledge: "Back to Knowledge",
    refresh: "Refresh",
    create: "Create Knowledge",
    knowledge: "Knowledge",
    noKnowledge: "No Knowledge yet",
    noKnowledgeDetail: "Knowledge documents will appear here when they are added to this Project.",
    serviceError: "This Project could not be read.",
    notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.",
    descriptionFallback: "This Project has no description yet.",
    preview: "Preview",
    runtime: "Runtime context",
    useInAgent: "Use in an Agent",
    useInAgentDetail: "After explicit index build and binding, the Agent verifies version and content hash and adds only relevant chunks to model context.",
    chooseAgent: "Choose an Agent",
    bind: "Bind and open Studio",
    binding: "Binding…",
    noAgents: "This Project has no Agent yet. Create an Agent first.",
    title: "Knowledge",
    description: "Upload sources you explicitly want Agents to use. Files are never injected automatically; index them, then bind.",
    uploadTitle: "Upload local Knowledge file",
    uploadDetail: "UTF-8 .txt / .md only, up to 1,000,000 bytes. Does not automatically bind an Agent.",
    drop: "Choose or drop a .txt / .md file",
    selected: "Selected",
    ingest: "Upload and parse",
    ingesting: "Parsing…",
    fileLabel: "Knowledge file",
  };

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let response = await api.getProject(projectId);
      if (knowledgeId && api.getKnowledge) {
        const document = await api.getKnowledge(projectId, knowledgeId);
        setText(document.text);
        response = {
          ...response,
          knowledge: response.knowledge?.map((item) => (
            item.knowledge_id === knowledgeId ? document : item
          )),
        };
      } else {
        setText(null);
      }
      setProject(response);
      upsertProject(response);
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

  const bindKnowledge = async (selected: ProjectKnowledgeRecord) => {
    if (!bindingAgentId || !api.saveDraft) return;
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

  const ingestKnowledge = async () => {
    if (!upload || !api.ingestKnowledge) return;
    setCreating(true);
    setError(null);
    try {
      const created = await api.ingestKnowledge(projectId, upload);
      const refreshed = await api.getProject(projectId);
      setProject(refreshed);
      upsertProject(refreshed);
      setUpload(null);
      window.location.hash = projectRoutePaths.knowledgeItem(projectId, created.knowledge_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setCreating(false);
    }
  };

  const deleteKnowledge = async (id: string) => {
    if (!api.deleteKnowledge || deletingId) return;
    if (!window.confirm(zh ? "将这份知识移入废纸篓？" : "Move this Knowledge to trash?")) return;
    setDeletingId(id);
    setError(null);
    try {
      const removed = await api.deleteKnowledge(projectId, id);
      setProject(removed.project);
      upsertProject(removed.project);
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "knowledge_in_use") {
        const owner = cause.details?.name || cause.details?.agent_id;
        const version = cause.details?.version_id;
        setError(
          (zh
            ? "该知识仍被 Agent 使用，请先解除绑定。保留的已提交版本仍会阻止删除。"
            : "This Knowledge is still used by an Agent. Unbind it first; retained committed versions still prevent deletion.")
          + (owner ? ` Agent: ${owner}` : "")
          + (version ? ` (${version})` : ""),
        );
      } else {
        setError(cause instanceof Error ? cause.message : copy.serviceError);
      }
    } finally {
      setDeletingId(null);
    }
  };

  const buildIndex = async () => {
    if (!knowledgeId || !api.buildKnowledgeIndex || building || loading) return;
    setBuilding(true);
    setError(null);
    try {
      const document = await api.buildKnowledgeIndex(projectId, knowledgeId);
      setText(document.text);
      if (project) {
        const updated = {
          ...project,
          knowledge: project.knowledge?.map((item) => (
            item.knowledge_id === knowledgeId ? document : item
          )),
        };
        setProject(updated);
        upsertProject(updated);
      }
    } catch (cause) {
      setError(
        cause instanceof LocalApiClientError
          ? `${cause.code}: ${cause.message}`
          : cause instanceof Error ? cause.message : copy.serviceError,
      );
    } finally {
      setBuilding(false);
    }
  };

  if (loading && !project) return <LoadingState label={zh ? "正在加载项目…" : "Loading Project…"} />;
  if (error && !project) {
    return (
      <div className="project-missing">
        <ErrorState message={error || copy.notFound} onRetry={() => void loadProject()} />
        <p>{copy.notFound}</p>
        <div className="intro-actions">
          <LinkButton href="#/projects" icon={ArrowLeft} variant="primary">{copy.back}</LinkButton>
          <Button icon={RefreshCw} onClick={() => void loadProject()}>{copy.refresh}</Button>
        </div>
      </div>
    );
  }
  if (!project) return null;

  const documents = project.knowledge ?? [];
  const selected = knowledgeId ? documents.find((item) => item.knowledge_id === knowledgeId) : undefined;

  if (knowledgeId && selected) {
    const processing = selected.processing;
    const canBind = processing == null || processing.index_status === "indexed";
    return (
      <div className="page-stack knowledge-workbench">
        <div className="page-intro">
          <div>
            <span className="ui-eyebrow">{copy.knowledge}</span>
            <h2>{selected.name || selected.slug}</h2>
            <p>{selected.source_path}</p>
          </div>
          <div className="intro-actions">
            <LinkButton href={projectRoutePaths.knowledge(projectId)} icon={ArrowLeft} variant="ghost">{copy.backKnowledge}</LinkButton>
            <Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading || building}>{copy.refresh}</Button>
          </div>
        </div>
        {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
        <Panel>
          <div className="knowledge-card-top">
            <SectionHeading title={zh ? "当前状态" : "Current state"} />
            <StatusBadge label={badgeLabel(processing?.index_status, zh)} tone={indexTone(processing?.index_status)} />
          </div>
          <p className="knowledge-next">{nextAction(processing?.index_status, zh)}</p>
          <KnowledgeState processing={processing} projectName={project.name} zh={zh} />
          <Button
            variant="primary"
            onClick={() => void buildIndex()}
            disabled={building || loading || !api.buildKnowledgeIndex}
          >
            {building
              ? (zh ? "正在构建…" : "Building…")
              : !processing || processing.index_status === "not_indexed"
                ? (zh ? "构建索引" : "Build index")
                : (zh ? "重建索引" : "Rebuild index")}
          </Button>
        </Panel>
        <Panel>
          <SectionHeading eyebrow={copy.preview} title={selected.name || selected.slug} />
          {text !== null ? <pre className="knowledge-preview">{text}</pre> : null}
        </Panel>
        <Panel>
          <SectionHeading eyebrow={copy.runtime} title={copy.useInAgent} detail={copy.useInAgentDetail} />
          {project.agents.length ? (
            <div className="knowledge-bind">
              <select
                aria-label={copy.chooseAgent}
                value={bindingAgentId}
                onChange={(event) => setBindingAgentId(event.target.value)}
              >
                {project.agents.map((agent) => (
                  <option value={agent.agent_id} key={agent.agent_id}>{agent.name || agent.slug}</option>
                ))}
              </select>
              <Button
                variant="primary"
                onClick={() => void bindKnowledge(selected)}
                disabled={binding || !bindingAgentId || !api.saveDraft || !canBind}
              >
                {binding ? copy.binding : copy.bind}
              </Button>
              {processing && processing.index_status !== "indexed"
                ? <Tag tone="warn">{zh ? "先构建索引再绑定" : "Index before binding"}</Tag>
                : null}
            </div>
          ) : <p className="knowledge-note">{copy.noAgents}</p>}
        </Panel>
      </div>
    );
  }

  return (
    <div className="page-stack knowledge-workbench">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <Tag>{`${documents.length} ${copy.knowledge}`}</Tag>
          <Button icon={Plus} onClick={() => void createKnowledge()} disabled={creating || !api.createKnowledge}>
            {copy.create}
          </Button>
          <Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button>
        </div>
      </div>
      {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}
      <Panel className="knowledge-upload">
        <SectionHeading title={copy.uploadTitle} detail={copy.uploadDetail} />
        <label className={`knowledge-upload-drop${upload ? " is-selected" : ""}`}>
          <span className="knowledge-icon"><Upload size={18} aria-hidden="true" /></span>
          <strong>{copy.drop}</strong>
          <small>{upload ? `${copy.selected}: ${upload.name}` : copy.uploadDetail}</small>
          <input
            aria-label={copy.fileLabel}
            type="file"
            accept=".txt,.md"
            disabled={creating}
            onChange={(event) => setUpload(event.target.files?.[0] ?? null)}
          />
        </label>
        <div className="knowledge-upload-actions">
          <Button
            variant="primary"
            onClick={() => void ingestKnowledge()}
            disabled={creating || !upload || !api.ingestKnowledge}
          >
            {creating && upload ? copy.ingesting : copy.ingest}
          </Button>
        </div>
      </Panel>
      {documents.length === 0 ? (
        <Panel>
          <EmptyState icon={BookOpen} title={copy.noKnowledge} detail={copy.noKnowledgeDetail} />
        </Panel>
      ) : (
        <div className="knowledge-card-grid">
          {documents.map((item) => {
            const status = item.processing?.index_status;
            const title = item.name || item.slug;
            return (
              <div className="knowledge-card-wrap" key={item.knowledge_id}>
                <a
                  className="knowledge-card"
                  href={projectRoutePaths.knowledgeItem(project.project_id, item.knowledge_id)}
                >
                  <div className="knowledge-card-top">
                    <span className="knowledge-icon"><BookOpen size={18} aria-hidden="true" /></span>
                    <StatusBadge label={badgeLabel(status, zh)} tone={indexTone(status)} />
                  </div>
                  <h3>{title}</h3>
                  <p>{item.processing?.filename || item.source_path}</p>
                  <div className="knowledge-card-meta">
                    <Tag>{item.version ?? "1.0.0"}</Tag>
                    <Tag>{item.processing?.chunk_count ?? "—"} {zh ? "个片段" : "chunks"}</Tag>
                  </div>
                </a>
                <IconButton
                  className="knowledge-card-remove"
                  icon={Trash2}
                  label={zh ? `删除 ${title}` : `Delete ${title}`}
                  disabled={deletingId !== null || !api.deleteKnowledge}
                  onClick={() => void deleteKnowledge(item.knowledge_id)}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function KnowledgeState({
  processing,
  projectName,
  zh,
}: {
  processing?: KnowledgeProcessing;
  projectName: string;
  zh: boolean;
}) {
  if (!processing) return <p>{zh ? "后端未提供处理状态" : "Processing state not provided by the backend"}</p>;
  return (
    <div>
      <div className="knowledge-facts">
        <div>
          <dt>Project</dt>
          <dd>{projectName}</dd>
        </div>
        <div>
          <dt>{zh ? "来源" : "Origin"}</dt>
          <dd>{processing.origin} · {processing.filename} · {processing.media_type}</dd>
        </div>
        <div>
          <dt>Content SHA-256</dt>
          <dd>{processing.content_hash}</dd>
        </div>
        {processing.uploaded_content_hash ? (
          <div>
            <dt>Upload SHA-256</dt>
            <dd>{processing.uploaded_content_hash}</dd>
          </div>
        ) : null}
        <div>
          <dt>Ingest / Parse / Index</dt>
          <dd>{processing.ingest_status} / {processing.parse_status} / {processing.index_status}</dd>
        </div>
        <div>
          <dt>{zh ? "索引状态" : "Index status"}</dt>
          <dd>{indexLabel(processing.index_status, zh)}</dd>
        </div>
        <div>
          <dt>{zh ? "片段数" : "Chunk count"}</dt>
          <dd>{processing.chunk_count ?? "—"}</dd>
        </div>
        <div>
          <dt>{zh ? "更新时间" : "Updated"}</dt>
          <dd>{processing.updated_at}</dd>
        </div>
      </div>
      <p className="knowledge-note">
        {processing.index_status === "not_indexed"
          ? (zh ? "尚未建立检索索引；运行前请显式构建索引。" : "No retrieval index yet; explicitly build before running.")
          : (zh
            ? "仅检索 Agent 已绑定的相关片段；索引不会自动重建，Agent 绑定不会自动升级。"
            : "Retrieves only relevant chunks from Agent-bound Knowledge. No automatic rebuild or Agent pin upgrade.")}
      </p>
      {processing.failure_reason ? <p role="alert">{processing.failure_reason}</p> : null}
    </div>
  );
}
