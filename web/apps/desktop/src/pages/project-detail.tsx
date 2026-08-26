import { ArrowLeft, Bot, FileCode2, FolderKanban, RefreshCw, ShieldCheck } from "lucide-react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

function shortHash(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

export function ProjectDetailPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, markProjectRecent, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const copy = zh ? {
    eyebrow: "项目",
    description: "这个项目的目录边界与真实 Agent 索引。",
    back: "返回项目",
    refresh: "刷新",
    boundary: "项目边界",
    boundaryDetail: "源文件与后续运行能力都以这个项目目录为范围。",
    rootPath: "绝对路径",
    projectId: "项目 ID",
    manifest: "Manifest hash",
    trustEyebrow: "Desktop 连接",
    trustTitle: "由 sidecar 访问",
    trustDetail: "浏览器只展示 Desktop API 返回的目录和 Agent 数组，不伪造本机文件状态。",
    agentsEyebrow: "Agent 列表",
    agentCount: (count: number) => `${count} 个 Agent`,
    agentsDetail: "当前列表只展示 Project manifest 中的真实 Agent 记录。",
    noAgents: "还没有 Agent",
    noAgentsDetail: "Agents 将在后续阶段加入。当前 Project 已经可以作为目录边界使用。",
    sourcePath: "源文件",
    fileHash: "文件 hash",
    serviceError: "无法读取这个项目。",
    notFound: "请求的项目不存在，或 Desktop sidecar 无法访问它。",
  } : {
    eyebrow: "Project",
    description: "The directory boundary and real Agent index for this Project.",
    back: "Back to Projects",
    refresh: "Refresh",
    boundary: "Project boundary",
    boundaryDetail: "Source files and later runtime capabilities stay scoped to this Project directory.",
    rootPath: "Absolute path",
    projectId: "Project ID",
    manifest: "Manifest hash",
    trustEyebrow: "Desktop connection",
    trustTitle: "Accessed by the sidecar",
    trustDetail: "The browser displays only the directory and Agent array returned by the Desktop API; it does not fake local file state.",
    agentsEyebrow: "Agents",
    agentCount: (count: number) => `${count} ${count === 1 ? "Agent" : "Agents"}`,
    agentsDetail: "This list contains only real Agent records from the Project manifest.",
    noAgents: "No Agents yet",
    noAgentsDetail: "Agents will be added later. This Project is ready to serve as a directory boundary.",
    sourcePath: "Source file",
    fileHash: "File hash",
    serviceError: "This Project could not be read.",
    notFound: "The requested Project does not exist or the Desktop sidecar cannot access it.",
  };

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getProject(projectId);
      setProject(response);
      upsertProject(response);
      markProjectRecent(response.project_id);
    } catch (cause) {
      setProject(null);
      setError(cause instanceof Error ? cause.message : copy.serviceError);
    } finally {
      setLoading(false);
    }
  }, [api, copy.serviceError, markProjectRecent, projectId, upsertProject]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  if (loading && !project) return <LoadingState label={zh ? "正在加载 Project…" : "Loading Project…"} />;

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

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{project.name}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <LinkButton href="#/projects" icon={ArrowLeft} variant="ghost">{copy.back}</LinkButton>
          <Button icon={RefreshCw} onClick={() => void loadProject()} disabled={loading}>{copy.refresh}</Button>
        </div>
      </div>

      {error ? <ErrorState message={error} onRetry={() => void loadProject()} /> : null}

      <div className="project-overview-grid">
        <Panel>
          <div className="project-overview-icon"><FolderKanban size={19} aria-hidden="true" /></div>
          <strong>{copy.boundary}</strong>
          <p>{copy.boundaryDetail}</p>
          <dl className="project-facts">
            <div><dt>{copy.rootPath}</dt><dd className="project-path">{project.root_path}</dd></div>
            <div><dt>{copy.projectId}</dt><dd><Tag>{project.project_id}</Tag></dd></div>
            <div><dt>{copy.manifest}</dt><dd><Tag tone="good">{shortHash(project.manifest_hash)}</Tag></dd></div>
          </dl>
        </Panel>
        <Panel>
          <SectionHeading eyebrow={copy.trustEyebrow} title={copy.trustTitle} />
          <div className="project-trust">
            <ShieldCheck size={18} aria-hidden="true" />
            <span><strong>{copy.trustTitle}</strong><small>{copy.trustDetail}</small></span>
          </div>
          <LinkButton href="#/community" icon={FileCode2} size="sm" variant="ghost">{zh ? "查看 Community" : "View Community"}</LinkButton>
        </Panel>
      </div>

      <Panel>
        <SectionHeading eyebrow={copy.agentsEyebrow} title={copy.agentCount(project.agents.length)} detail={copy.agentsDetail} />
        {project.agents.length === 0 ? (
          <EmptyState icon={Bot} title={copy.noAgents} detail={copy.noAgentsDetail} />
        ) : (
          <div className="project-agent-list">
            {project.agents.map((agent) => (
              <div className="project-agent-row" key={agent.agent_id}>
                <span className="row-icon"><Bot size={17} aria-hidden="true" /></span>
                <span className="row-copy">
                  <strong>{agent.slug}</strong>
                  <small>{copy.sourcePath}: {agent.source_path}</small>
                  <em>{copy.fileHash}: {shortHash(agent.source_file_hash)}</em>
                </span>
                <Tag>{agent.agent_id}</Tag>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
