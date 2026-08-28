import { Bot, FolderKanban, Home, Play, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation, type ProjectSummaryResponse } from "@veyra/api-contracts";

type DesktopHeader = { title: string; breadcrumbs?: { label: string; href?: string; icon?: typeof Home }[]; backHref?: string };

const rootTitles: Partial<Record<DesktopRouteLocation["kind"], string>> = {
  chat: "New chat", projects: "New chat", components: "Components", files: "Files", runs: "Runs", monitor: "Monitor", community: "Community", account: "Account", settings: "Settings", "not-found": "Route not found",
};

export function desktopHeader(route: DesktopRouteLocation, projects: ProjectSummaryResponse[]): DesktopHeader {
  const title = rootTitles[route.kind];
  if (title) return { title };
  const project = "projectId" in route ? projects.find((item) => item.project_id === route.projectId) : undefined;
  const projectLabel = project?.name ?? ("projectId" in route ? route.projectId : "Project");
  const home = { label: "Home", href: desktopRoutePaths.projects, icon: Home };
  const projectCrumb = "projectId" in route ? { label: projectLabel, href: projectRoutePaths.project(route.projectId), icon: FolderKanban } : undefined;
  const agent = project && "agentId" in route ? project.agents.find((item) => item.agent_id === route.agentId) : undefined;
  const agentCrumb = agent && "projectId" in route && "agentId" in route ? { label: agent.slug, href: projectRoutePaths.agent(route.projectId, agent.agent_id), icon: Bot } : undefined;
  if (!projectCrumb) return { title: "Route not found" };
  if (route.kind === "project" || route.kind === "project-agents") return { title: projectLabel, breadcrumbs: [home, { label: projectLabel, icon: FolderKanban }], backHref: desktopRoutePaths.projects };
  if (route.kind === "factory") return { title: "Factory", breadcrumbs: [home, projectCrumb, { label: "Factory", icon: Wrench }], backHref: projectCrumb.href };
  if (route.kind === "agent-detail") return { title: agent?.slug ?? route.agentId ?? "Agent", breadcrumbs: [home, projectCrumb, { label: agent?.slug ?? route.agentId ?? "Agent", icon: Bot }], backHref: projectCrumb.href };
  if (route.kind === "agent-version") return { title: route.versionId ?? "Version", breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: route.versionId ?? "Version", icon: Wrench }], backHref: agentCrumb?.href ?? projectCrumb.href };
  if (route.kind === "agent-design") return { title: "Studio", breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: "Studio", icon: Wrench }], backHref: agentCrumb?.href ?? projectCrumb.href };
  return { title: "Run", breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: "Run", icon: Play }], backHref: agentCrumb?.href ?? projectCrumb.href };
}
