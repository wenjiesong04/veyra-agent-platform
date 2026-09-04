import { FolderKanban, Gauge, GitBranch, MessageCirclePlus, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import type { NavigationGroup } from "@veyra/ui";

export type AgentContextRouteKind = "agent-detail" | "agent-design" | "agent-analysis" | "agent-run" | "agent-version";
export type AgentContextRoute = { kind: AgentContextRouteKind; path: string; projectId: string; agentId: string; versionId?: string };
export type ProjectContextRouteKind = "project" | "project-chat" | "project-analysis" | "project-agents" | "factory";
export type ProjectContextRoute = { kind: ProjectContextRouteKind; path: string; projectId: string };
export type DesktopLocale = "zh" | "en";

export function isAgentContextRoute(route: DesktopRouteLocation): route is AgentContextRoute {
  return (route.kind === "agent-detail" || route.kind === "agent-design" || route.kind === "agent-analysis" || route.kind === "agent-run" || route.kind === "agent-version") && typeof route.agentId === "string";
}

export function isProjectContextRoute(route: DesktopRouteLocation): route is ProjectContextRoute {
  return route.kind === "project" || route.kind === "project-chat" || route.kind === "project-analysis" || route.kind === "project-agents" || route.kind === "factory";
}

export function isWorkspaceContextRoute(route: DesktopRouteLocation): route is AgentContextRoute | ProjectContextRoute {
  return isAgentContextRoute(route) || isProjectContextRoute(route);
}

export function workspaceContextBackLink(locale: DesktopLocale): { href: string; label: string } {
  return {
    href: desktopRoutePaths.projects,
    label: locale === "zh" ? "返回主页" : "Back to home",
  };
}

/** The context item with a direct route is active; deep Run/Version pages have no sibling top item. */
export function agentContextActiveHref(route: AgentContextRoute): string {
  if (route.kind === "agent-design") return projectRoutePaths.agentDesign(route.projectId, route.agentId);
  if (route.kind === "agent-analysis") return projectRoutePaths.agentAnalysis(route.projectId, route.agentId);
  if (route.kind === "agent-detail") return projectRoutePaths.agent(route.projectId, route.agentId);
  return "";
}

export function projectContextActiveHref(route: ProjectContextRoute): string {
  if (route.kind === "project-chat") return projectRoutePaths.projectChat(route.projectId);
  if (route.kind === "project-analysis") return projectRoutePaths.projectAnalysis(route.projectId);
  if (route.kind === "project" || route.kind === "project-agents") return projectRoutePaths.project(route.projectId);
  return "";
}

export function agentContextNavigation(route: AgentContextRoute, locale: DesktopLocale): NavigationGroup {
  const labels = locale === "zh"
    ? { root: "新聊天", orchestration: "编排", analysis: "数据分析" }
    : { root: "New chat", orchestration: "Orchestration", analysis: "Data analysis" };
  const activeHref = agentContextActiveHref(route);
  return {
    label: "Agent",
    section: "fixed",
    backLink: workspaceContextBackLink(locale),
    items: [
      { href: projectRoutePaths.agent(route.projectId, route.agentId), label: labels.root, icon: MessageCirclePlus, active: activeHref === projectRoutePaths.agent(route.projectId, route.agentId) },
      { href: projectRoutePaths.agentDesign(route.projectId, route.agentId), label: labels.orchestration, icon: GitBranch, active: activeHref === projectRoutePaths.agentDesign(route.projectId, route.agentId) },
      { href: projectRoutePaths.agentAnalysis(route.projectId, route.agentId), label: labels.analysis, icon: Gauge, active: activeHref === projectRoutePaths.agentAnalysis(route.projectId, route.agentId) },
    ],
  };
}

export function projectContextNavigation(route: ProjectContextRoute, locale: DesktopLocale): NavigationGroup {
  const labels = locale === "zh"
    ? { newChat: "新聊天", overview: "概览", analysis: "数据分析", factory: "Factory" }
    : { newChat: "New chat", overview: "Overview", analysis: "Data analysis", factory: "Factory" };
  const activeHref = projectContextActiveHref(route);
  const projectHref = projectRoutePaths.project(route.projectId);
  const factoryHref = projectRoutePaths.factory(route.projectId);
  return {
    label: "Project",
    section: "fixed",
    backLink: workspaceContextBackLink(locale),
    items: [
      { href: projectRoutePaths.projectChat(route.projectId), label: labels.newChat, icon: MessageCirclePlus, active: activeHref === projectRoutePaths.projectChat(route.projectId) },
      { href: projectHref, label: labels.overview, icon: FolderKanban, active: activeHref === projectHref },
      { href: projectRoutePaths.projectAnalysis(route.projectId), label: labels.analysis, icon: Gauge, active: activeHref === projectRoutePaths.projectAnalysis(route.projectId) },
      ...(route.kind === "factory" ? [{ href: factoryHref, label: labels.factory, icon: Wrench, active: true }] : []),
    ],
  };
}

export function agentRecentNavigation(locale: DesktopLocale): NavigationGroup {
  return {
    label: "Recent",
    section: "recent",
    items: [],
    status: "empty",
    statusText: locale === "zh" ? "暂无最近聊天或运行记录。" : "No recent conversations or runs yet.",
  };
}
