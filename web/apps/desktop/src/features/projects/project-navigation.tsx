import { BookOpen, Bot, Box, ChevronDown, ChevronRight, FileArchive, FileText, FileUp, FolderKanban, FolderOpen, MoreHorizontal, Pencil, Pin, Plus, Trash2, Workflow, type LucideIcon } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type ProjectSummaryResponse } from "@veyra/api-contracts";
import type { ProjectAgentRecord, ProjectKnowledgeRecord, ProjectWorkflowRecord } from "@veyra/api-contracts";
import type { NavigationGroup, NavigationItem } from "@veyra/ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocale } from "@veyra/ui";
import { LocalApiClientError } from "../../api/local-client";
import { useProjectWorkspace } from "../../api/project-workspace";
import { type ProjectTreeSelection } from "../agents/agent-navigation";
import { AgentCreateDialog, AgentDeleteDialog, AgentEditDialog, KnowledgeDeleteDialog, KnowledgeEditDialog, ProjectDeleteDialog, ProjectDialog, ProjectEditDialog, WorkflowDeleteDialog, WorkflowEditDialog, type AgentCreateMode, type ProjectDialogMode } from "./project-dialog";
import { agentTree, type AgentTreeNode } from "./agent-tree";
import { readSidebarResourcePins, sortPinnedFirst, toggleSidebarResourcePin, writeSidebarResourcePins, type SidebarResourceKind, type SidebarResourcePins } from "./sidebar-pins";

type ProjectNavigationProps = { scopedProjectId?: string; activeAgentId?: string; selection?: ProjectTreeSelection; routeKey?: string; suppressProjectHighlight?: boolean };
type ProjectModal =
  | { kind: "create" | "open" }
  | { kind: "edit" | "delete" | "agent-create"; project: ProjectSummaryResponse; agentMode?: AgentCreateMode; parentAgentId?: string }
  | { kind: "agent-edit" | "agent-delete"; project: ProjectSummaryResponse; agent: ProjectAgentRecord }
  | { kind: "workflow-edit" | "workflow-delete"; project: ProjectSummaryResponse; workflow: ProjectWorkflowRecord }
  | { kind: "knowledge-edit" | "knowledge-delete"; project: ProjectSummaryResponse; knowledge: ProjectKnowledgeRecord }
  | null;
type SidebarPopover =
  | { kind: "project-actions" | "agent-chooser"; project: ProjectSummaryResponse; anchor: HTMLButtonElement }
  | { kind: "agent-actions"; project: ProjectSummaryResponse; agent: ProjectAgentRecord; anchor: HTMLButtonElement }
  | { kind: "workflow-actions"; project: ProjectSummaryResponse; workflow: ProjectWorkflowRecord; anchor: HTMLButtonElement }
  | { kind: "knowledge-actions"; project: ProjectSummaryResponse; knowledge: ProjectKnowledgeRecord; anchor: HTMLButtonElement }
  | null;

export function useProjectNavigation({ scopedProjectId, activeAgentId, selection, routeKey, suppressProjectHighlight = false }: ProjectNavigationProps): { navigation: NavigationGroup[]; dialogs: ReactNode } {
  const { t, locale } = useLocale();
  const { api, projects, status, setProjectPinned, upsertProject } = useProjectWorkspace();
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(() => new Set(scopedProjectId ? [scopedProjectId] : []));
  const [popover, setPopover] = useState<SidebarPopover>(null);
  const [modal, setModal] = useState<ProjectModal>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [resourcePins, setResourcePins] = useState<SidebarResourcePins>(readSidebarResourcePins);

  useEffect(() => { if (scopedProjectId) setExpandedProjectIds((current) => current.has(scopedProjectId) ? current : new Set(current).add(scopedProjectId)); }, [scopedProjectId]);
  useEffect(() => { setPopover(null); }, [activeAgentId, routeKey, scopedProjectId]);

  const pinned = useMemo(() => projects.filter((project) => project.pinned).sort(byIndexedAt).slice(0, 1), [projects]);
  const normal = useMemo(() => projects.filter((project) => !project.pinned).sort(byIndexedAt), [projects]);
  const statusValue = status === "ready" && projects.length > 0 ? undefined : status === "ready" ? "empty" : status;
  const chooseAgentMode = (project: ProjectSummaryResponse, agentMode: AgentCreateMode, parentAgentId?: string) => { setPopover(null); setModal({ kind: "agent-create", project, agentMode, parentAgentId }); };
  const createWorkflow = (target: ProjectSummaryResponse) => {
    if (!api.createWorkflow) {
      setActionError(locale === "zh" ? "当前工作区无法创建工作流。" : "This workspace cannot create a Workflow.");
      return;
    }
    setActionError(null);
    void api.createWorkflow(target.project_id, { name: locale === "zh" ? "新工作流" : "New Workflow" }).then(async (created) => {
      try {
        const refreshed = await api.getProject(target.project_id);
        upsertProject(refreshed);
      } catch {
        /* Open the new Workflow even if the tree refresh fails. */
      }
      setExpandedProjectIds((current) => current.has(target.project_id) ? current : new Set(current).add(target.project_id));
      window.location.hash = projectRoutePaths.workflow(target.project_id, created.workflow_id);
    }).catch((cause) => {
      setActionError(localActionError(cause, locale, locale === "zh" ? "无法创建工作流。" : "Could not create a Workflow."));
    });
  };
  const createKnowledge = (target: ProjectSummaryResponse) => {
    if (!api.createKnowledge) {
      setActionError(locale === "zh" ? "当前工作区无法创建知识文档。" : "This workspace cannot create Knowledge.");
      return;
    }
    setActionError(null);
    void api.createKnowledge(target.project_id, { name: locale === "zh" ? "新知识" : "New Knowledge" }).then(async (created) => {
      try {
        const refreshed = await api.getProject(target.project_id);
        upsertProject(refreshed);
      } catch {
        /* Open the new document even if the tree refresh fails. */
      }
      setExpandedProjectIds((current) => current.has(target.project_id) ? current : new Set(current).add(target.project_id));
      window.location.hash = projectRoutePaths.knowledgeItem(target.project_id, created.knowledge_id);
    }).catch((cause) => {
      setActionError(localActionError(cause, locale, locale === "zh" ? "无法创建知识文档。" : "Could not create Knowledge."));
    });
  };
  const pinAgent = (project: ProjectSummaryResponse, agent: ProjectAgentRecord) => {
    setPopover(null);
    setActionError(null);
    void api.updateAgent(project.project_id, agent.agent_id, { pinned: true }).then(upsertProject).catch((cause) => {
      setActionError(localActionError(cause, locale, locale === "zh" ? "无法置顶 Agent。" : "Could not pin the Agent."));
    });
  };
  const pinResource = (projectId: string, kind: SidebarResourceKind, id: string) => {
    setPopover(null);
    setResourcePins((current) => {
      const next = toggleSidebarResourcePin(current, projectId, kind, id);
      writeSidebarResourcePins(next);
      return next;
    });
  };
  const revealProject = (project: ProjectSummaryResponse) => {
    setPopover(null);
    if (!api.revealProject) return;
    setActionError(null);
    void api.revealProject(project.project_id).catch((cause) => {
      setActionError(localActionError(cause, locale, locale === "zh" ? "无法在访达中显示项目文件夹。" : "The Project folder could not be shown in Finder."));
    });
  };
  const makeGroup = (label: "Projects" | "Pinned", items: ProjectSummaryResponse[], showActions: boolean): NavigationGroup => ({
    label, section: label === "Pinned" ? "pinned" : "projects", status: label === "Projects" ? (actionError ? "error" : statusValue) : undefined, statusText: label === "Projects" && actionError ? actionError : undefined,
    action: showActions ? <span className="sidebar-project-actions"><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "open" })} aria-label={t("openExistingProject")} title={t("openExistingProject")}><FolderOpen size={15} aria-hidden="true" /></button><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "create" })} aria-label={t("createProjectShortcut")} title={t("createProjectShortcut")}><Plus size={15} aria-hidden="true" /></button></span> : undefined,
    items: items.map((project) => projectItem(project)),
  });

  const projectItem = (project: ProjectSummaryResponse): NavigationItem => {
    const expanded = expandedProjectIds.has(project.project_id);
    const isScopedProject = project.project_id === scopedProjectId;
    const selected = isScopedProject ? selection : undefined;
    const currentAgentId = selected?.agentId ?? (isScopedProject ? activeAgentId : undefined);
    const currentWorkflowId = selected?.workflowId;
    const currentKnowledgeId = selected?.knowledgeId;
    const currentKind = selected?.resourceKind;
    const resourceOpen = Boolean(currentAgentId || currentWorkflowId || currentKnowledgeId || currentKind);
    const isProjectRoute = isScopedProject && !resourceOpen;
    const projectPins = resourcePins[project.project_id];
    const isProjectPopoverOpen = (kind: "project-actions" | "agent-chooser") => popover?.kind === kind && popover.project.project_id === project.project_id;
    const isAgentPopoverOpen = (agentId: string) => popover?.kind === "agent-actions" && popover.project.project_id === project.project_id && popover.agent.agent_id === agentId;
    const isWorkflowPopoverOpen = (workflowId: string) => popover?.kind === "workflow-actions" && popover.project.project_id === project.project_id && popover.workflow.workflow_id === workflowId;
    const isKnowledgePopoverOpen = (knowledgeId: string) => popover?.kind === "knowledge-actions" && popover.project.project_id === project.project_id && popover.knowledge.knowledge_id === knowledgeId;
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
    const toggleWorkflowPopover = (workflow: ProjectWorkflowRecord, event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault(); event.stopPropagation();
      const anchor = event.currentTarget;
      setPopover((current) => current?.kind === "workflow-actions" && current.project.project_id === project.project_id && current.workflow.workflow_id === workflow.workflow_id ? null : { kind: "workflow-actions", project, workflow, anchor });
    };
    const toggleKnowledgePopover = (knowledge: ProjectKnowledgeRecord, event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault(); event.stopPropagation();
      const anchor = event.currentTarget;
      setPopover((current) => current?.kind === "knowledge-actions" && current.project.project_id === project.project_id && current.knowledge.knowledge_id === knowledge.knowledge_id ? null : { kind: "knowledge-actions", project, knowledge, anchor });
    };
    const kindState = (kind: NonNullable<ProjectTreeSelection["resourceKind"]>, instanceSelected: boolean) => ({
      active: isScopedProject && currentKind === kind && !instanceSelected,
    });
    const agentItem = (agent: ProjectAgentRecord): NavigationItem => {
      const isCurrentAgent = agent.agent_id === currentAgentId;
      return {
        href: projectRoutePaths.agentDesign(project.project_id, agent.agent_id),
        label: agent.name || agent.slug,
        icon: Bot,
        tone: "instance",
        resourceKind: "agent",
        active: isCurrentAgent,
        trailingAction: <span className="agent-row-actions"><button type="button" aria-label={`${t("agentActions")}: ${agent.name || agent.slug}`} title={t("agentActions")} aria-haspopup="menu" aria-expanded={isAgentPopoverOpen(agent.agent_id)} onClick={(event) => toggleAgentPopover(agent, event)}><MoreHorizontal size={15} aria-hidden="true" /></button><button type="button" aria-label={`${t("addChildAgent")}: ${agent.name || agent.slug}`} title={t("addChildAgent")} onClick={(event) => { event.preventDefault(); event.stopPropagation(); chooseAgentMode(project, "blank", agent.agent_id); }}><Plus size={15} aria-hidden="true" /></button></span>,
      };
    };
    const toNavItem = (node: AgentTreeNode<ProjectAgentRecord>): NavigationItem => ({
      ...agentItem(node),
      children: node.children.length ? node.children.map(toNavItem) : undefined,
      expanded: true,
    });
    const workflowItem = (workflow: ProjectWorkflowRecord): NavigationItem => ({
      href: projectRoutePaths.workflow(project.project_id, workflow.workflow_id),
      label: workflow.name || workflow.slug,
      icon: Workflow,
      tone: "instance",
      resourceKind: "workflow",
      active: workflow.workflow_id === currentWorkflowId,
      trailingAction: <span className="agent-row-actions"><button type="button" aria-label={`${t("workflowActions")}: ${workflow.name || workflow.slug}`} title={t("workflowActions")} aria-haspopup="menu" aria-expanded={isWorkflowPopoverOpen(workflow.workflow_id)} onClick={(event) => toggleWorkflowPopover(workflow, event)}><MoreHorizontal size={15} aria-hidden="true" /></button></span>,
    });
    const knowledgeItem = (knowledge: ProjectKnowledgeRecord): NavigationItem => ({
      href: projectRoutePaths.knowledgeItem(project.project_id, knowledge.knowledge_id),
      label: knowledge.name || knowledge.slug,
      icon: BookOpen,
      tone: "instance",
      resourceKind: "knowledge",
      active: knowledge.knowledge_id === currentKnowledgeId,
      trailingAction: <span className="agent-row-actions"><button type="button" aria-label={`${t("knowledgeActions")}: ${knowledge.name || knowledge.slug}`} title={t("knowledgeActions")} aria-haspopup="menu" aria-expanded={isKnowledgePopoverOpen(knowledge.knowledge_id)} onClick={(event) => toggleKnowledgePopover(knowledge, event)}><MoreHorizontal size={15} aria-hidden="true" /></button></span>,
    });
    const treeNodes = agentTree(project.agents);
    const workflows = sortPinnedFirst(project.workflows ?? [], projectPins?.workflow, (item) => item.workflow_id);
    const knowledge = sortPinnedFirst(project.knowledge ?? [], projectPins?.knowledge, (item) => item.knowledge_id);
    const agentsKind: NavigationItem = {
      href: projectRoutePaths.agents(project.project_id),
      label: "Agents",
      icon: Bot,
      tone: "kind",
      resourceKind: "agent",
      expanded: true,
      ...kindState("agents", Boolean(currentAgentId)),
      trailingAction: <span className="kind-row-actions"><button type="button" aria-label={`${t("addAgent")}: ${project.name}`} title={`${t("addAgent")}: ${project.name}`} aria-haspopup="menu" aria-expanded={isProjectPopoverOpen("agent-chooser")} onClick={(event) => toggleProjectPopover("agent-chooser", event)}><Plus size={15} aria-hidden="true" /></button></span>,
      children: treeNodes.length ? treeNodes.map(toNavItem) : undefined,
    };
    const workflowsKind: NavigationItem = {
      href: projectRoutePaths.workflows(project.project_id),
      label: "Workflows",
      icon: Workflow,
      tone: "kind",
      resourceKind: "workflow",
      expanded: true,
      ...kindState("workflows", Boolean(currentWorkflowId)),
      trailingAction: <span className="kind-row-actions"><button type="button" aria-label={`${t("addWorkflow")}: ${project.name}`} title={`${t("addWorkflow")}: ${project.name}`} onClick={(event) => { event.preventDefault(); event.stopPropagation(); createWorkflow(project); }}><Plus size={15} aria-hidden="true" /></button></span>,
      children: workflows.length ? workflows.map(workflowItem) : undefined,
    };
    const knowledgeKind: NavigationItem = {
      href: projectRoutePaths.knowledge(project.project_id),
      label: "Knowledge",
      icon: BookOpen,
      tone: "kind",
      resourceKind: "knowledge",
      expanded: true,
      ...kindState("knowledge", Boolean(currentKnowledgeId)),
      trailingAction: <span className="kind-row-actions"><button type="button" aria-label={`${t("addKnowledge")}: ${project.name}`} title={`${t("addKnowledge")}: ${project.name}`} onClick={(event) => { event.preventDefault(); event.stopPropagation(); createKnowledge(project); }}><Plus size={15} aria-hidden="true" /></button></span>,
      children: knowledge.length ? knowledge.map(knowledgeItem) : undefined,
    };
    const filesKind: NavigationItem = {
      href: projectRoutePaths.files(project.project_id),
      label: "Files",
      icon: FileText,
      tone: "collection",
      resourceKind: "files",
      ...kindState("files", false),
    };
    return {
      href: projectRoutePaths.project(project.project_id),
      label: project.name,
      icon: FolderKanban,
      tone: "project",
      active: !suppressProjectHighlight && isProjectRoute,
      contextual: isScopedProject && suppressProjectHighlight && !resourceOpen,
      expanded,
      leadingAction: <button type="button" aria-label={`${expanded ? t("collapseProject") : t("expandProject")}: ${project.name}`} aria-expanded={expanded} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setExpandedProjectIds((current) => { const next = new Set(current); if (next.has(project.project_id)) next.delete(project.project_id); else next.add(project.project_id); return next; }); }}>{expanded ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}</button>,
      trailingAction: <span className="project-row-actions"><button type="button" aria-label={`${t("projectActions")}: ${project.name}`} title={t("projectActions")} aria-haspopup="menu" aria-expanded={isProjectPopoverOpen("project-actions")} onClick={(event) => toggleProjectPopover("project-actions", event)}><MoreHorizontal size={15} aria-hidden="true" /></button></span>,
      children: [agentsKind, workflowsKind, knowledgeKind, filesKind],
    };
  };

  const navigation = [...(pinned.length ? [makeGroup("Pinned", pinned, false)] : []), makeGroup("Projects", normal, true)];
  const resourceMenu = popover?.kind === "agent-actions" ? (
    <ResourceActionsPopover
      onPin={() => pinAgent(popover.project, popover.agent)}
      onEdit={() => { setPopover(null); setModal({ kind: "agent-edit", project: popover.project, agent: popover.agent }); }}
      onDelete={() => { setPopover(null); setModal({ kind: "agent-delete", project: popover.project, agent: popover.agent }); }}
      labels={{ pin: t("pinAgent"), edit: t("editAgent"), delete: t("deleteAgent"), pinDetail: t("pinAgentDetail"), editDetail: t("editAgentDetail"), deleteDetail: t("deleteAgentDetail"), actions: `${t("agentActions")}: ${popover.agent.name || popover.agent.slug}` }}
    />
  ) : popover?.kind === "workflow-actions" ? (
    <ResourceActionsPopover
      onPin={() => pinResource(popover.project.project_id, "workflow", popover.workflow.workflow_id)}
      onEdit={() => { setPopover(null); setModal({ kind: "workflow-edit", project: popover.project, workflow: popover.workflow }); }}
      onDelete={() => { setPopover(null); setModal({ kind: "workflow-delete", project: popover.project, workflow: popover.workflow }); }}
      labels={{ pin: resourcePins[popover.project.project_id]?.workflow === popover.workflow.workflow_id ? t("unpinResource") : t("pinAgent"), edit: t("editAgent"), delete: t("deleteAgent"), pinDetail: t("pinWorkflowDetail"), editDetail: t("editWorkflowDetail"), deleteDetail: t("deleteWorkflowDetail"), actions: `${t("workflowActions")}: ${popover.workflow.name || popover.workflow.slug}` }}
    />
  ) : popover?.kind === "knowledge-actions" ? (
    <ResourceActionsPopover
      onPin={() => pinResource(popover.project.project_id, "knowledge", popover.knowledge.knowledge_id)}
      onEdit={() => { setPopover(null); setModal({ kind: "knowledge-edit", project: popover.project, knowledge: popover.knowledge }); }}
      onDelete={() => { setPopover(null); setModal({ kind: "knowledge-delete", project: popover.project, knowledge: popover.knowledge }); }}
      labels={{ pin: resourcePins[popover.project.project_id]?.knowledge === popover.knowledge.knowledge_id ? t("unpinResource") : t("pinAgent"), edit: t("editAgent"), delete: t("deleteAgent"), pinDetail: t("pinKnowledgeDetail"), editDetail: t("editKnowledgeDetail"), deleteDetail: t("deleteKnowledgeDetail"), actions: `${t("knowledgeActions")}: ${popover.knowledge.name || popover.knowledge.slug}` }}
    />
  ) : null;
  const dialogs = <>
    {popover ? <FixedSidebarPopover anchor={popover.anchor} estimatedWidth={168} className={popover.kind === "agent-chooser" ? "agent-add-chooser" : popover.kind === "project-actions" ? "sidebar-project-menu" : "sidebar-agent-menu"} onClose={() => setPopover(null)}>
      {popover.kind === "project-actions" ? <ProjectActionsPopover onPin={() => { setPopover(null); void setProjectPinned(popover.project.project_id, !popover.project.pinned).catch(() => undefined); }} onReveal={() => revealProject(popover.project)} onEdit={() => { setPopover(null); setModal({ kind: "edit", project: popover.project }); }} onDelete={() => { setPopover(null); setModal({ kind: "delete", project: popover.project }); }} labels={{ pin: popover.project.pinned ? t("unpinProject") : t("pinProject"), reveal: t("revealProject"), edit: t("editProject"), delete: t("deleteProject"), pinDetail: t("pinProjectDetail"), revealDetail: t("revealProjectDetail"), editDetail: t("editProjectDetail"), deleteDetail: t("deleteProjectDetail"), actions: `${t("projectActions")}: ${popover.project.name}` }} /> : popover.kind === "agent-chooser" ? <AgentChooserPopover project={popover.project} zh={locale === "zh"} onChoose={chooseAgentMode} /> : resourceMenu}
    </FixedSidebarPopover> : null}
    {modal?.kind === "create" || modal?.kind === "open" ? <ProjectDialog mode={modal.kind as ProjectDialogMode} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "edit" ? <ProjectEditDialog project={modal.project} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "delete" ? <ProjectDeleteDialog project={modal.project} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId ? () => { window.location.hash = desktopRoutePaths.projects; } : undefined} /> : null}
    {modal?.kind === "agent-create" ? <AgentCreateDialog project={modal.project} mode={modal.agentMode!} parentAgentId={modal.parentAgentId} onCreated={(projectId, agentId) => { setExpandedProjectIds((current) => current.has(projectId) ? current : new Set(current).add(projectId)); window.location.hash = projectRoutePaths.agentDesign(projectId, agentId); }} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "agent-edit" ? <AgentEditDialog project={modal.project} agent={modal.agent} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "agent-delete" ? <AgentDeleteDialog project={modal.project} agent={modal.agent} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId && modal.agent.agent_id === activeAgentId ? () => { window.location.hash = projectRoutePaths.project(modal.project.project_id); } : undefined} /> : null}
    {modal?.kind === "workflow-edit" ? <WorkflowEditDialog project={modal.project} workflow={modal.workflow} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "workflow-delete" ? <WorkflowDeleteDialog project={modal.project} workflow={modal.workflow} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId && modal.workflow.workflow_id === selection?.workflowId ? () => { window.location.hash = projectRoutePaths.workflows(modal.project.project_id); } : undefined} /> : null}
    {modal?.kind === "knowledge-edit" ? <KnowledgeEditDialog project={modal.project} knowledge={modal.knowledge} onClose={() => setModal(null)} /> : null}
    {modal?.kind === "knowledge-delete" ? <KnowledgeDeleteDialog project={modal.project} knowledge={modal.knowledge} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId && modal.knowledge.knowledge_id === selection?.knowledgeId ? () => { window.location.hash = projectRoutePaths.knowledge(modal.project.project_id); } : undefined} /> : null}
  </>;
  return { navigation, dialogs };
}

function ProjectActionsPopover({ labels, onPin, onReveal, onEdit, onDelete }: { labels: { pin: string; reveal: string; edit: string; delete: string; pinDetail: string; revealDetail: string; editDetail: string; deleteDetail: string; actions: string }; onPin: () => void; onReveal: () => void; onEdit: () => void; onDelete: () => void }) {
  return <div className="sidebar-action-menu" role="menu" aria-label={labels.actions}><SidebarMenuItem icon={Pin} title={labels.pin} detail={labels.pinDetail} onClick={onPin} /><SidebarMenuItem icon={FolderOpen} title={labels.reveal} detail={labels.revealDetail} onClick={onReveal} /><SidebarMenuItem icon={Pencil} title={labels.edit} detail={labels.editDetail} onClick={onEdit} /><SidebarMenuItem icon={Trash2} title={labels.delete} detail={labels.deleteDetail} onClick={onDelete} destructive /></div>;
}

function ResourceActionsPopover({ labels, onPin, onEdit, onDelete }: { labels: { pin: string; edit: string; delete: string; pinDetail: string; editDetail: string; deleteDetail: string; actions: string }; onPin: () => void; onEdit: () => void; onDelete: () => void }) {
  return <div className="sidebar-action-menu" role="menu" aria-label={labels.actions}><SidebarMenuItem icon={Pin} title={labels.pin} detail={labels.pinDetail} onClick={onPin} /><SidebarMenuItem icon={Pencil} title={labels.edit} detail={labels.editDetail} onClick={onEdit} /><SidebarMenuItem icon={Trash2} title={labels.delete} detail={labels.deleteDetail} onClick={onDelete} destructive /></div>;
}

function AgentChooserPopover({ project, zh, onChoose }: { project: ProjectSummaryResponse; zh: boolean; onChoose: (project: ProjectSummaryResponse, mode: AgentCreateMode) => void }) {
  const options = zh ? [
    { mode: "blank" as const, icon: Plus, title: "创建空白 Agent", detail: "从空白定义开始" }, { mode: "template" as const, icon: Box, title: "从模板导入 Agent", detail: "选择已注册的模板" }, { mode: "file" as const, icon: FileUp, title: "导入 Agent 文件", detail: "导入 .vagent.yaml 文件" }, { mode: "external" as const, icon: FileArchive, title: "导入外部 Agent", detail: "分析 YAML、文件夹或 ZIP" },
  ] : [
    { mode: "blank" as const, icon: Plus, title: "Create blank Agent", detail: "Start from an empty definition" }, { mode: "template" as const, icon: Box, title: "Import Agent from template", detail: "Choose a registered template" }, { mode: "file" as const, icon: FileUp, title: "Import Agent file", detail: "Import a .vagent.yaml file" }, { mode: "external" as const, icon: FileArchive, title: "Import external Agent", detail: "Analyze YAML, folder, or ZIP" },
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
    const update = () => setPosition(popoverPosition(anchor, root.current?.offsetWidth || estimatedWidth));
    const onPointerDown = (event: MouseEvent) => { if (!anchor.contains(event.target as Node) && !root.current?.contains(event.target as Node)) onClose(); };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    update();
    const observer = typeof ResizeObserver === "function" && root.current ? new ResizeObserver(update) : null;
    if (observer && root.current) observer.observe(root.current);
    window.addEventListener("resize", update); window.addEventListener("scroll", update, true); document.addEventListener("mousedown", onPointerDown); document.addEventListener("keydown", onKeyDown);
    return () => { observer?.disconnect(); window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); document.removeEventListener("mousedown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
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

function localActionError(cause: unknown, locale: string, fallback: string): string {
  if (cause instanceof LocalApiClientError) {
    if (cause.code === "directory_picker_failed" || cause.code === "directory_picker_unsupported") {
      return locale === "zh"
        ? "无法在访达中显示项目文件夹。请允许本机访问磁盘后重试。"
        : "The Project folder could not be shown in Finder. Allow disk access and try again.";
    }
    if (cause.status >= 500) {
      return locale === "zh"
        ? `本机服务执行失败（${cause.status}）。请重启本机 sidecar 后再试。`
        : `The local service failed (${cause.status}). Restart the desktop sidecar and retry.`;
    }
  }
  return cause instanceof Error ? cause.message : fallback;
}
