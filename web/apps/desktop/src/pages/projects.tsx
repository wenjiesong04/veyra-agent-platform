import { ArrowUpRight, FolderKanban, FolderOpen, FolderPlus, Plus, RefreshCw, X } from "lucide-react";
import { projectRoutePaths, type AgentSummary, type ProjectSummary, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LoadingState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

export const projects: ProjectSummary[] = [];
export const agents: AgentSummary[] = [];
export function defaultAgentForProject(_projectId: string): AgentSummary | undefined { return undefined; }

type ProjectAction = "create" | "open";
function isAbsolutePath(value: string): boolean { return value.startsWith("/") || value.startsWith("\\\\") || /^[A-Za-z]:[\\/]/.test(value); }
function navigateToProject(project: ProjectSummaryResponse): void { window.location.hash = projectRoutePaths.project(project.project_id); }

function ProjectModal({ onClose }: { onClose: () => void }) {
  const { locale } = useLocale(); const zh = locale === "zh";
  const { api, refresh, upsertProject } = useProjectWorkspace();
  const [mode, setMode] = useState<ProjectAction>("create"); const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [rootPath, setRootPath] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const pathFieldRef = useRef<HTMLInputElement>(null);
  const copy = zh ? {
    title: "连接项目", create: "创建项目", open: "打开已有项目", name: "项目名称", description: "描述（可选）", path: "绝对路径", createHint: "在所选目录创建 project.vproject.yaml。", openHint: "索引已有目录，不会复制文件。", namePlaceholder: "例如：研究工作区", descriptionPlaceholder: "这个项目要完成什么？", pathPlaceholder: "/Users/you/Projects/research-workspace", cancel: "取消", submitCreate: "创建项目", submitOpen: "打开项目", invalidName: "请输入项目名称。", invalidPath: "请输入绝对路径。", close: "关闭对话框",
  } : {
    title: "Connect a Project", create: "Create Project", open: "Open existing", name: "Project name", description: "Description (optional)", path: "Absolute path", createHint: "Create project.vproject.yaml in the selected directory.", openHint: "Index an existing directory without copying its files.", namePlaceholder: "For example: Research workspace", descriptionPlaceholder: "What belongs in this Project?", pathPlaceholder: "/Users/you/Projects/research-workspace", cancel: "Cancel", submitCreate: "Create Project", submitOpen: "Open Project", invalidName: "Enter a Project name.", invalidPath: "Enter an absolute path.", close: "Close dialog",
  };
  useEffect(() => { (mode === "create" ? firstFieldRef : pathFieldRef).current?.focus(); const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; document.addEventListener("keydown", onKeyDown); return () => document.removeEventListener("keydown", onKeyDown); }, [onClose, mode]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const normalizedPath = rootPath.trim();
    if (mode === "create" && !name.trim()) return setError(copy.invalidName);
    if (!isAbsolutePath(normalizedPath)) return setError(copy.invalidPath);
    setBusy(true); setError(null);
    try {
      const project = mode === "create" ? await api.createProject({ root_path: normalizedPath, name: name.trim(), description: description.trim() }) : await api.openProject({ root_path: normalizedPath });
      upsertProject(project); await refresh(); onClose(); navigateToProject(project);
    } catch (cause) { setError(cause instanceof Error ? cause.message : zh ? "项目操作失败。" : "The Project operation failed."); } finally { setBusy(false); }
  };
  return <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="project-modal" role="dialog" aria-modal="true" aria-labelledby="project-modal-title">
      <div className="project-modal-header"><div><span className="ui-eyebrow">Veyra Desktop</span><h2 id="project-modal-title">{copy.title}</h2></div><button type="button" className="project-modal-close" onClick={onClose} aria-label={copy.close}><X size={18} /></button></div>
      <div className="project-modal-tabs" role="tablist" aria-label={copy.title}><button type="button" role="tab" aria-selected={mode === "create"} className={mode === "create" ? "active" : ""} onClick={() => { setMode("create"); setError(null); }}>{copy.create}</button><button type="button" role="tab" aria-selected={mode === "open"} className={mode === "open" ? "active" : ""} onClick={() => { setMode("open"); setError(null); }}>{copy.open}</button></div>
      <p className="project-modal-hint">{mode === "create" ? copy.createHint : copy.openHint}</p>
      <form className="project-form" onSubmit={submit}>
        {mode === "create" ? <><label><span>{copy.name}</span><input ref={firstFieldRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" /></label><label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} /><small>{description.length}/500</small></label></> : null}
        <label><span>{copy.path}</span><input ref={pathFieldRef} value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder={copy.pathPlaceholder} autoComplete="off" spellCheck={false} /></label>
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
        <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={busy}>{copy.cancel}</Button><Button icon={mode === "create" ? FolderPlus : FolderOpen} variant="primary" type="submit" disabled={busy}>{busy ? "…" : mode === "create" ? copy.submitCreate : copy.submitOpen}</Button></div>
      </form>
    </div>
  </div>;
}

export function ProjectsPage() {
  const { locale } = useLocale(); const zh = locale === "zh"; const { projects: projectList, status, error, refresh } = useProjectWorkspace(); const [modalOpen, setModalOpen] = useState(false);
  useEffect(() => { const onProjectAction = () => setModalOpen(true); window.addEventListener("veyra:project-action", onProjectAction); return () => window.removeEventListener("veyra:project-action", onProjectAction); }, []);
  const copy = zh ? { eyebrow: "Desktop 工作区", title: "项目", description: "在一个真实目录中组织 Agent、文件与后续运行。", refresh: "刷新", connect: "连接项目", connected: "已连接项目", count: (count: number) => `${count} 个项目`, noProjects: "还没有项目", noProjectsDetail: "创建一个项目，或打开一个已有的 project.vproject.yaml 目录。", serviceError: "Desktop API 当前不可用。", agents: (count: number) => `${count} 个 Agent` } : { eyebrow: "Desktop workspace", title: "Projects", description: "Organize Agents, files, and later runs in real directories.", refresh: "Refresh", connect: "Connect Project", connected: "Connected Projects", count: (count: number) => `${count} ${count === 1 ? "Project" : "Projects"}`, noProjects: "No Projects yet", noProjectsDetail: "Create a Project or open a directory that already contains project.vproject.yaml.", serviceError: "The Desktop API is currently unavailable.", agents: (count: number) => `${count} ${count === 1 ? "Agent" : "Agents"}` };
  return <div className="page-stack"><div className="page-intro project-landing"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><div className="intro-actions"><Button icon={RefreshCw} onClick={() => void refresh()} disabled={status === "loading"}>{copy.refresh}</Button><Button icon={Plus} variant="primary" onClick={() => setModalOpen(true)}>{copy.connect}</Button></div></div>
    {status === "error" ? <ErrorState message={error ?? copy.serviceError} onRetry={() => void refresh()} /> : null}
    <Panel><SectionHeading eyebrow={copy.connected} title={copy.count(projectList.length)} />{status === "loading" && projectList.length === 0 ? <LoadingState label={zh ? "正在加载项目…" : "Loading Projects…"} /> : null}{status === "ready" && projectList.length === 0 ? <EmptyState icon={FolderKanban} title={copy.noProjects} detail={copy.noProjectsDetail} /> : null}{projectList.length > 0 ? <div className="project-list">{projectList.map((project) => <a className="project-row" href={projectRoutePaths.project(project.project_id)} key={project.project_id}><span className="row-icon"><FolderKanban size={18} aria-hidden="true" /></span><span className="row-copy"><strong>{project.name}</strong><small>{project.description || project.root_path}</small><em>{copy.agents(project.agents.length)}</em></span><ArrowUpRight size={16} className="row-arrow" aria-hidden="true" /></a>)}</div> : null}</Panel>
    {modalOpen ? <ProjectModal onClose={() => setModalOpen(false)} /> : null}
  </div>;
}
