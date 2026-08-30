import { Bot, Box, ChevronDown, ChevronRight, FileUp, FolderKanban, FolderOpen, MoreHorizontal, Pencil, Pin, Plus, Trash2, type LucideIcon } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type ProjectSummaryResponse } from "@veyra/api-contracts";
import type { ProjectAgentRecord } from "@veyra/api-contracts";
import type { NavigationGroup, NavigationItem } from "@veyra/ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../../api/project-workspace";
import { AgentCreateDialog, AgentDeleteDialog, AgentEditDialog, ProjectDeleteDialog, ProjectDialog, ProjectEditDialog, type AgentCreateMode, type ProjectDialogMode } from "./project-dialog";

type ProjectNavigationProps = { scopedProjectId?: string; activeAgentId?: string; routeKey?: string };
type ProjectModal = { kind: "create" | "open" } | { kind: "edit" | "delete" | "agent-create"; project: ProjectSummaryResponse; agentMode?: AgentCreateMode; parentAgentId?: string } | { kind: "agent-edit" | "agent-delete"; project: ProjectSummaryResponse; agent: ProjectAgentRecord } | null;
type SidebarPopover =
  | { kind: "project-actions" | "agent-chooser"; project: ProjectSummaryResponse; anchor: HTMLButtonElement }
  | { kind: "agent-actions"; project: ProjectSummaryResponse; agent: ProjectAgentRecord; anchor: HTMLButtonElement }
  | null;

export function useProjectNavigation({ scopedProjectId, activeAgentId, routeKey }: ProjectNavigationProps): { navigation: NavigationGroup[]; dialogs: ReactNode } {
  const { t, locale } = useLocale();
  const { api, projects, status, setProjectPinned, upsertProject } = useProjectWorkspace();
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(() => new Set(scopedProjectId ? [scopedProjectId] : []));
  const [popover, setPopover] = useState<SidebarPopover>(null);
  const [modal, setModal] = useState<ProjectModal>(null);

  useEffect(() => { if (scopedProjectId) setExpandedProjectIds((current) => current.has(scopedProjectId) ? current : new Set(current).add(scopedProjectId)); }, [scopedProjectId]);
  useEffect(() => { setPopover(null); }, [activeAgentId, routeKey, scopedProjectId]);

  const pinned = useMemo(() => projects.filter((project) => project.pinned).sort(byIndexedAt).slice(0, 1), [projects]);
  const normal = useMemo(() => projects.filter((project) => !project.pinned).sort(byIndexedAt), [projects]);
  const statusValue = status === "ready" && projects.length > 0 ? undefined : status === "ready" ? "empty" : status;
  const chooseAgentMode = (project: ProjectSummaryResponse, agentMode: AgentCreateMode, parentAgentId?: string) => { setPopover(null); setModal({ kind: "agent-create", project, agentMode, parentAgentId }); };
  const pinAgent = (project: ProjectSummaryResponse, agent: ProjectAgentRecord) => {
    setPopover(null);
    void api.updateAgent(project.project_id, agent.agent_id, { pinned: true }).then(upsertProject).catch(() => undefined);
  };
  const makeGroup = (label: "Projects" | "Pinned", items: ProjectSummaryResponse[], showActions: boolean): NavigationGroup => ({
    label, section: label === "Pinned" ? "pinned" : "projects", status: label === "Projects" ? statusValue : undefined,
    action: showActions ? <span className="sidebar-project-actions"><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "open" })} aria-label={t("openExistingProject")} title={t("openExistingProject")}><FolderOpen size={15} aria-hidden="true" /></button><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "create" })} aria-label={t("createProjectShortcut")} title={t("createProjectShortcut")}><Plus size={15} aria-hidden="true" /></button></span> : undefined,
    items: items.map((project) => projectItem(project)),
  });

  const projectItem = (project: ProjectSummaryResponse) => {
    const expanded = expandedProjectIds.has(project.project_id);
    const isProjectRoute = project.project_id === scopedProjectId && !activeAgentId;
    const isScopedProject = project.project_id === scopedProjectId;
    const isProjectPopoverOpen = (kind: "project-actions" | "agent-chooser") => popover?.kind === kind && popover.project.project_id === project.project_id;
    const isAgentPopoverOpen = (agentId: string) => popover?.kind === "agent-actions" && popover.project.project_id === project.project_id && popover.agent.agent_id === agentId;
    const toggleProjectPopover = (kind: "project-actions" | "agent-chooser", event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault(); event.stopPropagation();
      const anchor = event.currentTarget;
      setPopover((current) => current?.kind === kind && current.project.project_id === project.project_id ? null : { kind, project, anchor });
    };
    const toggleAgentPopover = (agent: ProjectAgentRecord, event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault(); event.stopPropagation();
      const anchor = event.currentTarget;
      setPopover((current) => current?.kind === "agent-actions" && current.project.project_id === project.project_id && current.agent.agent_id === agent.agent_id ? null : { kind: "agent-actions", project, agent, anchor });
    };
    const agentItem = (agent: ProjectAgentRecord): NavigationItem => ({
      href: projectRoutePaths.agentDesign(project.project_id, agent.agent_id),
      label: agent.name || agent.slug,
      icon: Bot,
      active: isScopedProject && agent.agent_id === activeAgentId,
      trailingAction: <span className="agent-row-actions"><button type="button" aria-label={`${t("agentActions")}: ${agent.name || agent.slug}`} title={t("agentActions")} aria-haspopup="menu" aria-expanded={isAgentPopoverOpen(agent.agent_id)} onClick={(event) => toggleAgentPopover(agent, event)}><MoreHorizontal size={15} aria-hidden="true" /></button><button type="button" aria-label={`${t("addChildAgent")}: ${agent.name || agent.slug}`} title={t("addChildAgent")} onClick={(event) => { event.preventDefault(); event.stopPropagation(); chooseAgentMode(project, "blank", agent.agent_id); }}><Plus size={14} aria-hidden="true" /></button></span>,
    });
    const rootAgents = project.agents.filter((agent) => !agent.parent_agent_id);
    return {
      href: projectRoutePaths.project(project.project_id), label: project.name, icon: FolderKanban, active: isProjectRoute, expanded,
      leadingAction: <button type="button" aria-label={`${expanded ? t("collapseProject") : t("expandProject")}: ${project.name}`} aria-expanded={expanded} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setExpandedProjectIds((current) => { const next = new Set(current); if (next.has(project.project_id)) next.delete(project.project_id); else next.add(project.project_id); return next; }); }}>{expanded ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}</button>,
      trailingAction: <span className="project-row-actions"><button type="button" aria-label={`${t("projectActions")}: ${project.name}`} title={t("projectActions")} aria-haspopup="menu" aria-expanded={isProjectPopoverOpen("project-actions")} onClick={(event) => toggleProjectPopover("project-actions", event)}><MoreHorizontal size={15} aria-hidden="true" /></button><button type="button" aria-label={`${t("addAgent")}: ${project.name}`} title={`${t("addAgent")}: ${project.name}`} aria-haspopup="menu" aria-expanded={isProjectPopoverOpen("agent-chooser")} onClick={(event) => toggleProjectPopover("agent-chooser", event)}><Plus size={15} aria-hidden="true" /></button></span>,
      children: rootAgents.length ? rootAgents.map((agent) => ({
        ...agentItem(agent),
        children: project.agents.filter((child) => child.parent_agent_id === agent.agent_id).map(agentItem),
        expanded: true,
      })) : undefined,
    };
  };

  const navigation = [...(pinned.length ? [makeGroup("Pinned", pinned, false)] : []), makeGroup("Projects", normal, true)];
  const dialogs = <>
    {popover ? <FixedSidebarPopover anchor={popover.anchor} estimatedWidth={240} className={popover.kind === "agent-chooser" ? "agent-add-chooser" : popover.kind === "agent-actions" ? "sidebar-agent-menu" : "sidebar-project-menu"} onClose={() => setPopover(null)}>
      {popover.kind === "project-actions" ? <ProjectActionsPopover onPin={() => { setPopover(null); void setProjectPinned(popover.project.project_id, !popover.project.pinned).catch(() => undefined); }} onEdit={() => { setPopover(null); setModal({ kind: "edit", project: popover.project }); }} onDelete={() => { setPopover(null); setModal({ kind: "delete", project: popover.project }); }} labels={{ pin: popover.project.pinned ? t("unpinProject") : t("pinProject"), edit: t("editProject"), delete: t("deleteProject"), pinDetail: t("pinProjectDetail"), editDetail: t("editProjectDetail"), deleteDetail: t("deleteProjectDetail"), actions: `${t("projectActions")}: ${popover.project.name}` }} /> : popover.kind === "agent-actions" ? <AgentActionsPopover onPin={() => pinAgent(popover.project, popover.agent)} onEdit={() => { setPopover(null); setModal({ kind: "agent-edit", project: popover.project, agent: popover.agent }); }} onDelete={() => { setPopover(null); setModal({ kind: "agent-delete", project: popover.project, agent: popover.agent }); }} labels={{ pin: t("pinAgent"), edit: t("editAgent"), delete: t("deleteAgent"), pinDetail: t("pinAgentDetail"), editDetail: t("editAgentDetail"), deleteDetail: t("deleteAgentDetail"), actions: `${t("agentActions")}: ${popover.agent.name || popover.agent.slug}` }} /> : <AgentChooserPopover project={popover.project} zh={locale === "zh"} onChoose={chooseAgentMode} />}
    </FixedSidebarPopover> : null}
    {modal?.kind === "create" || modal?.kind === "open" ? <ProjectDialog mode={modal.kind as ProjectDialogMode} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "edit" ? <ProjectEditDialog project={modal.project} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "delete" ? <ProjectDeleteDialog project={modal.project} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId ? () => { window.location.hash = desktopRoutePaths.projects; } : undefined} /> : null}
    {modal?.kind === "agent-create" ? <AgentCreateDialog project={modal.project} mode={modal.agentMode!} parentAgentId={modal.parentAgentId} onCreated={(projectId) => setExpandedProjectIds((current) => current.has(projectId) ? current : new Set(current).add(projectId))} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "agent-edit" ? <AgentEditDialog project={modal.project} agent={modal.agent} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "agent-delete" ? <AgentDeleteDialog project={modal.project} agent={modal.agent} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId && modal.agent.agent_id === activeAgentId ? () => { window.location.hash = projectRoutePaths.project(modal.project.project_id); } : undefined} /> : null}
  </>;
  return { navigation, dialogs };
}

function ProjectActionsPopover({ labels, onPin, onEdit, onDelete }: { labels: { pin: string; edit: string; delete: string; pinDetail: string; editDetail: string; deleteDetail: string; actions: string }; onPin: () => void; onEdit: () => void; onDelete: () => void }) {
  return <div className="sidebar-action-menu" role="menu" aria-label={labels.actions}><SidebarMenuItem icon={Pin} title={labels.pin} detail={labels.pinDetail} onClick={onPin} /><SidebarMenuItem icon={Pencil} title={labels.edit} detail={labels.editDetail} onClick={onEdit} /><SidebarMenuItem icon={Trash2} title={labels.delete} detail={labels.deleteDetail} onClick={onDelete} destructive /></div>;
}

function AgentActionsPopover({ labels, onPin, onEdit, onDelete }: { labels: { pin: string; edit: string; delete: string; pinDetail: string; editDetail: string; deleteDetail: string; actions: string }; onPin: () => void; onEdit: () => void; onDelete: () => void }) {
  return <div className="sidebar-action-menu" role="menu" aria-label={labels.actions}><SidebarMenuItem icon={Pin} title={labels.pin} detail={labels.pinDetail} onClick={onPin} /><SidebarMenuItem icon={Pencil} title={labels.edit} detail={labels.editDetail} onClick={onEdit} /><SidebarMenuItem icon={Trash2} title={labels.delete} detail={labels.deleteDetail} onClick={onDelete} destructive /></div>;
}

function AgentChooserPopover({ project, zh, onChoose }: { project: ProjectSummaryResponse; zh: boolean; onChoose: (project: ProjectSummaryResponse, mode: AgentCreateMode) => void }) {
  const options = zh ? [
    { mode: "blank" as const, icon: Plus, title: "创建空白 Agent", detail: "从空白定义开始" }, { mode: "template" as const, icon: Box, title: "从模板导入 Agent", detail: "选择已注册的模板" }, { mode: "file" as const, icon: FileUp, title: "导入 Agent 文件", detail: "导入 .vagent.yaml 文件" },
  ] : [
    { mode: "blank" as const, icon: Plus, title: "Create blank Agent", detail: "Start from an empty definition" }, { mode: "template" as const, icon: Box, title: "Import Agent from template", detail: "Choose a registered template" }, { mode: "file" as const, icon: FileUp, title: "Import Agent file", detail: "Import a .vagent.yaml file" },
  ];
  return <div className="sidebar-action-menu" role="menu" aria-label={zh ? `添加 Agent：${project.name}` : `Add Agent: ${project.name}`}>{options.map(({ mode, icon: Icon, title, detail }) => <SidebarMenuItem key={mode} icon={Icon} title={title} detail={detail} onClick={() => onChoose(project, mode)} />)}</div>;
}

function SidebarMenuItem({ icon: Icon, title, detail, onClick, destructive = false }: { icon: LucideIcon; title: string; detail: string; onClick: () => void; destructive?: boolean }) {
  return <button className={`sidebar-popover-item ${destructive ? "is-destructive" : ""}`} type="button" role="menuitem" aria-label={title} onClick={onClick}><span className="sidebar-popover-icon"><Icon size={15} aria-hidden="true" /></span><span className="sidebar-popover-copy"><strong>{title}</strong><small>{detail}</small></span></button>;
}

function FixedSidebarPopover({ anchor, estimatedWidth, className, onClose, children }: { anchor: HTMLButtonElement; estimatedWidth: number; className: string; onClose: () => void; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState(() => popoverPosition(anchor, estimatedWidth));
  useEffect(() => {
    const update = () => setPosition(popoverPosition(anchor, estimatedWidth));
    const onPointerDown = (event: MouseEvent) => { if (!anchor.contains(event.target as Node) && !root.current?.contains(event.target as Node)) onClose(); };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    update(); window.addEventListener("resize", update); window.addEventListener("scroll", update, true); document.addEventListener("mousedown", onPointerDown); document.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); document.removeEventListener("mousedown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
  }, [anchor, estimatedWidth, onClose]);
  return createPortal(<div ref={root} className={`sidebar-fixed-popover ${className}`} style={position}>{children}</div>, document.body);
}

function popoverPosition(anchor: HTMLButtonElement, width: number): { top: number; left: number } {
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
  const top = rect.bottom + 6 > window.innerHeight - 120 ? Math.max(8, rect.top - 180) : rect.bottom + 6;
  return { top, left };
}

function byIndexedAt(left: ProjectSummaryResponse, right: ProjectSummaryResponse): number { return right.indexed_at.localeCompare(left.indexed_at); }
