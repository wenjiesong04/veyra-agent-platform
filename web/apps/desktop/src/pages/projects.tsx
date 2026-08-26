import { ArrowUpRight, FileCode2, FolderKanban, FolderOpen, FolderPlus, RefreshCw } from "lucide-react";
import { projectRoutePaths, type AgentSummary, type ProjectSummary, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useState, type FormEvent } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

// These empty exports keep the not-yet-migrated Agent routes type-safe without
// reintroducing fixture Projects or Agent data into the Project surface.
export const projects: ProjectSummary[] = [];
export const agents: AgentSummary[] = [];

export function defaultAgentForProject(_projectId: string): AgentSummary | undefined {
  return undefined;
}

function isAbsolutePath(value: string): boolean {
  return value.startsWith("/") || value.startsWith("\\\\") || /^[A-Za-z]:[\\/]/.test(value);
}

function shortHash(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function navigateToProject(project: ProjectSummaryResponse): void {
  window.location.hash = projectRoutePaths.project(project.project_id);
}

export function ProjectsPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const {
    api,
    projects: projectList,
    status,
    error,
    refresh,
    markProjectRecent,
    upsertProject,
  } = useProjectWorkspace();
  const [projectName, setProjectName] = useState("");
  const [createRootPath, setCreateRootPath] = useState("");
  const [openRootPath, setOpenRootPath] = useState("");
  const [action, setAction] = useState<"create" | "open" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const copy = zh ? {
    eyebrow: "Desktop 工作区",
    title: "项目",
    description: "管理与 Desktop sidecar 连接的真实项目目录。",
    refresh: "刷新",
    projectEyebrow: "项目",
    createTitle: "创建空项目",
    createDetail: "在绝对路径下创建项目清单；Agent 将在后续阶段加入。",
    projectName: "项目名称",
    projectNamePlaceholder: "例如：Research workspace",
    absolutePath: "绝对路径",
    createPathPlaceholder: "/Users/you/Projects/research-workspace",
    create: "创建项目",
    openTitle: "打开已有项目",
    openDetail: "索引一个已有的项目目录，不会把目录复制进浏览器。",
    openPathPlaceholder: "/Users/you/Projects/existing-project",
    open: "打开目录",
    connectedProjects: "已连接项目",
    projectCount: (count: number) => `${count} 个项目`,
    listDetail: "名称、绝对路径、manifest 和 Agent 数量均来自 Desktop API。",
    agents: (count: number) => `${count} 个 Agent`,
    manifest: "manifest",
    noProjects: "还没有项目",
    noProjectsDetail: "创建一个空项目，或打开一个包含 project.vproject.yaml 的已有目录。",
    invalidName: "请输入项目名称。",
    invalidPath: "请输入绝对路径。",
    requestFailed: "Project 操作失败。",
    serviceError: "Desktop API 当前不可用。",
  } : {
    eyebrow: "Desktop workspace",
    title: "Projects",
    description: "Manage real Project directories connected to the Desktop sidecar.",
    refresh: "Refresh",
    createTitle: "Create empty Project",
    createDetail: "Create the Project manifest at an absolute path; Agents will be added later.",
    projectEyebrow: "Project",
    projectName: "Project name",
    projectNamePlaceholder: "For example: Research workspace",
    absolutePath: "Absolute path",
    createPathPlaceholder: "/Users/you/Projects/research-workspace",
    create: "Create Project",
    openTitle: "Open existing Project",
    openDetail: "Index an existing Project directory without copying it into the browser.",
    openPathPlaceholder: "/Users/you/Projects/existing-project",
    open: "Open directory",
    connectedProjects: "Connected Projects",
    projectCount: (count: number) => `${count} ${count === 1 ? "Project" : "Projects"}`,
    listDetail: "Names, absolute paths, manifest hashes, and Agent counts come from the Desktop API.",
    agents: (count: number) => `${count} ${count === 1 ? "Agent" : "Agents"}`,
    manifest: "manifest",
    noProjects: "No Projects yet",
    noProjectsDetail: "Create an empty Project or open an existing directory containing project.vproject.yaml.",
    invalidName: "Enter a Project name.",
    invalidPath: "Enter an absolute path.",
    requestFailed: "The Project operation failed.",
    serviceError: "The Desktop API is currently unavailable.",
  };

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = projectName.trim();
    const rootPath = createRootPath.trim();
    if (!name) {
      setActionError(copy.invalidName);
      return;
    }
    if (!isAbsolutePath(rootPath)) {
      setActionError(copy.invalidPath);
      return;
    }
    setAction("create");
    setActionError(null);
    try {
      const project = await api.createProject({ root_path: rootPath, name });
      upsertProject(project);
      markProjectRecent(project.project_id);
      await refresh();
      navigateToProject(project);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : copy.requestFailed);
    } finally {
      setAction(null);
    }
  };

  const submitOpen = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rootPath = openRootPath.trim();
    if (!isAbsolutePath(rootPath)) {
      setActionError(copy.invalidPath);
      return;
    }
    setAction("open");
    setActionError(null);
    try {
      const project = await api.openProject({ root_path: rootPath });
      upsertProject(project);
      markProjectRecent(project.project_id);
      await refresh();
      navigateToProject(project);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : copy.requestFailed);
    } finally {
      setAction(null);
    }
  };

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <Button icon={RefreshCw} onClick={() => void refresh()} disabled={status === "loading" || action !== null}>{copy.refresh}</Button>
        </div>
      </div>

      {actionError ? <ErrorState message={actionError} /> : null}
      {status === "error" ? <ErrorState message={error ?? copy.serviceError} onRetry={() => void refresh()} /> : null}

      <div className="project-action-grid">
        <Panel>
          <SectionHeading eyebrow={copy.projectEyebrow} title={copy.createTitle} detail={copy.createDetail} />
          <form className="project-form" onSubmit={submitCreate}>
            <label>
              <span>{copy.projectName}</span>
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder={copy.projectNamePlaceholder} autoComplete="off" />
            </label>
            <label>
              <span>{copy.absolutePath}</span>
              <input value={createRootPath} onChange={(event) => setCreateRootPath(event.target.value)} placeholder={copy.createPathPlaceholder} autoComplete="off" spellCheck={false} />
            </label>
            <Button icon={FolderPlus} variant="primary" type="submit" disabled={action !== null}>{action === "create" ? "…" : copy.create}</Button>
          </form>
        </Panel>

        <Panel>
          <SectionHeading eyebrow={copy.projectEyebrow} title={copy.openTitle} detail={copy.openDetail} />
          <form className="project-form" onSubmit={submitOpen}>
            <label>
              <span>{copy.absolutePath}</span>
              <input value={openRootPath} onChange={(event) => setOpenRootPath(event.target.value)} placeholder={copy.openPathPlaceholder} autoComplete="off" spellCheck={false} />
            </label>
            <Button icon={FolderOpen} variant="secondary" type="submit" disabled={action !== null}>{action === "open" ? "…" : copy.open}</Button>
          </form>
        </Panel>
      </div>

      <Panel>
        <SectionHeading eyebrow={copy.connectedProjects} title={copy.projectCount(projectList.length)} detail={copy.listDetail} />
        {status === "loading" && projectList.length === 0 ? <LoadingState label={zh ? "正在加载 Projects…" : "Loading Projects…"} /> : null}
        {status === "ready" && projectList.length === 0 ? <EmptyState icon={FolderKanban} title={copy.noProjects} detail={copy.noProjectsDetail} /> : null}
        {projectList.length > 0 ? (
          <div className="project-list">
            {projectList.map((project) => (
              <a
                className="project-row"
                href={projectRoutePaths.project(project.project_id)}
                key={project.project_id}
                onClick={() => markProjectRecent(project.project_id)}
              >
                <span className="row-icon"><FolderKanban size={18} aria-hidden="true" /></span>
                <span className="row-copy">
                  <strong>{project.name}</strong>
                  <small>{project.root_path}</small>
                  <em><span>{copy.agents(project.agents.length)}</span><span>{copy.manifest} {shortHash(project.manifest_hash)}</span></em>
                </span>
                <ArrowUpRight size={16} className="row-arrow" aria-hidden="true" />
              </a>
            ))}
          </div>
        ) : null}
      </Panel>

      <Panel className="project-capability-note">
        <FileCode2 size={17} aria-hidden="true" />
        <span>{zh ? "Project 目录由 Desktop sidecar 访问；浏览器不会伪造本机目录或执行 Agent。" : "Project directories are accessed by the Desktop sidecar; the browser does not pretend to access local folders or execute Agents."}</span>
        <LinkButton href="#/community" variant="ghost" size="sm">{zh ? "打开 Community" : "Open Community"}</LinkButton>
      </Panel>
    </div>
  );
}
