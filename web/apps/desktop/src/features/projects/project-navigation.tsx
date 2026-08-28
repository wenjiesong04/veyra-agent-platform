import { Bot, ChevronDown, ChevronRight, FolderKanban, FolderOpen, MoreHorizontal, Plus } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type ProjectSummaryResponse } from "@veyra/api-contracts";
import type { NavigationGroup } from "@veyra/ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../../api/project-workspace";
import { ProjectDeleteDialog, ProjectDialog, ProjectEditDialog, type ProjectDialogMode } from "./project-dialog";

type ProjectNavigationProps = {
  scopedProjectId?: string;
  activeAgentId?: string;
};

type ProjectModal =
  | { kind: "create" | "open" }
  | { kind: "edit" | "delete"; project: ProjectSummaryResponse }
  | null;

export function useProjectNavigation({ scopedProjectId, activeAgentId }: ProjectNavigationProps): { navigation: NavigationGroup[]; dialogs: ReactNode } {
  const { t } = useLocale();
  const { projects, status, setProjectPinned } = useProjectWorkspace();
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(() => new Set(scopedProjectId ? [scopedProjectId] : []));
  const [openMenuProjectId, setOpenMenuProjectId] = useState<string | null>(null);
  const [modal, setModal] = useState<ProjectModal>(null);
  const menuRoot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scopedProjectId) setExpandedProjectIds((current) => current.has(scopedProjectId) ? current : new Set(current).add(scopedProjectId));
  }, [scopedProjectId]);

  useEffect(() => {
    if (!openMenuProjectId) return;
    const onPointerDown = (event: MouseEvent) => { if (!menuRoot.current?.contains(event.target as Node)) setOpenMenuProjectId(null); };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setOpenMenuProjectId(null); };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("mousedown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
  }, [openMenuProjectId]);

  const pinned = useMemo(() => projects.filter((project) => project.pinned).sort(byIndexedAt).slice(0, 1), [projects]);
  const normal = useMemo(() => projects.filter((project) => !project.pinned).sort(byIndexedAt), [projects]);
  const statusValue = status === "ready" && projects.length > 0 ? undefined : status === "ready" ? "empty" : status;
  const makeGroup = (label: "Projects" | "Pinned", items: ProjectSummaryResponse[], showActions: boolean): NavigationGroup => ({
    label,
    section: label === "Pinned" ? "pinned" : "projects",
    status: label === "Projects" ? statusValue : undefined,
    action: showActions ? <span className="sidebar-project-actions"><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "open" })} aria-label={t("openExistingProject")} title={t("openExistingProject")}><FolderOpen size={15} aria-hidden="true" /></button><button className="sidebar-section-button" type="button" onClick={() => setModal({ kind: "create" })} aria-label={t("createProjectShortcut")} title={t("createProjectShortcut")}><Plus size={15} aria-hidden="true" /></button></span> : undefined,
    items: items.map((project) => projectItem(project)),
  });

  const projectItem = (project: ProjectSummaryResponse) => {
    const expanded = expandedProjectIds.has(project.project_id);
    const isProjectRoute = project.project_id === scopedProjectId && !activeAgentId;
    const isScopedProject = project.project_id === scopedProjectId;
    return {
      href: projectRoutePaths.project(project.project_id),
      label: project.name,
      icon: FolderKanban,
      active: isProjectRoute,
      expanded,
      leadingAction: <button type="button" aria-label={`${expanded ? t("collapseProject") : t("expandProject")}: ${project.name}`} aria-expanded={expanded} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setExpandedProjectIds((current) => { const next = new Set(current); if (next.has(project.project_id)) next.delete(project.project_id); else next.add(project.project_id); return next; }); }}>{expanded ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}</button>,
      trailingAction: <span className="project-row-actions" ref={openMenuProjectId === project.project_id ? menuRoot : undefined}><button type="button" aria-label={`${t("projectActions")}: ${project.name}`} title={t("projectActions")} aria-haspopup="menu" aria-expanded={openMenuProjectId === project.project_id} onClick={(event) => { event.preventDefault(); event.stopPropagation(); setOpenMenuProjectId((current) => current === project.project_id ? null : project.project_id); }}><MoreHorizontal size={15} aria-hidden="true" /></button><a href={projectRoutePaths.factory(project.project_id)} aria-label={`${t("addAgent")}: ${project.name}`} title={`${t("addAgent")}: ${project.name}`} onClick={(event) => event.stopPropagation()}><Plus size={15} aria-hidden="true" /></a>{openMenuProjectId === project.project_id ? <div className="sidebar-project-menu" role="menu" aria-label={`${t("projectActions")}: ${project.name}`}><button type="button" role="menuitem" onClick={() => { setOpenMenuProjectId(null); void setProjectPinned(project.project_id, !project.pinned).catch(() => undefined); }}>{project.pinned ? t("unpinProject") : t("pinProject")}</button><button type="button" role="menuitem" onClick={() => { setOpenMenuProjectId(null); setModal({ kind: "edit", project }); }}>{t("editProject")}</button><button type="button" role="menuitem" onClick={() => { setOpenMenuProjectId(null); setModal({ kind: "delete", project }); }}>{t("deleteProject")}</button></div> : null}</span>,
      children: project.agents.map((agent) => ({ href: projectRoutePaths.agent(project.project_id, agent.agent_id), label: agent.slug, icon: Bot, active: isScopedProject && agent.agent_id === activeAgentId })),
    };
  };

  const navigation = [
    ...(pinned.length ? [makeGroup("Pinned", pinned, false)] : []),
    makeGroup("Projects", normal, true),
  ];
  const dialogs = modal?.kind === "create" || modal?.kind === "open"
    ? <ProjectDialog mode={modal.kind as ProjectDialogMode} onClose={() => setModal(null)} />
    : modal?.kind === "edit"
      ? <ProjectEditDialog project={modal.project} onClose={() => setModal(null)} />
      : modal?.kind === "delete"
        ? <ProjectDeleteDialog project={modal.project} onClose={() => setModal(null)} onDeleted={modal.project.project_id === scopedProjectId ? () => { window.location.hash = desktopRoutePaths.projects; } : undefined} />
        : null;
  return { navigation, dialogs };
}

function byIndexedAt(left: ProjectSummaryResponse, right: ProjectSummaryResponse): number {
  return right.indexed_at.localeCompare(left.indexed_at);
}
