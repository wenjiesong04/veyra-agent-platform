import { Boxes, Gauge, MessageCircle, MessageCirclePlus, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type BuilderActivityItem, type DesktopRouteLocation } from "@veyra/api-contracts";
import type { NavigationGroup } from "@veyra/ui";

export type AgentContextRouteKind = "agent-detail" | "agent-design" | "agent-analysis" | "agent-run" | "agent-version";
export type AgentContextRoute = { kind: AgentContextRouteKind; path: string; projectId: string; agentId: string; versionId?: string };
export type ProjectContextRouteKind = "project" | "project-chat" | "project-analysis" | "project-resources" | "project-agents" | "project-workflows" | "project-workflow" | "project-knowledge" | "project-knowledge-item" | "project-files" | "project-runs" | "factory";
export type ProjectContextRoute = { kind: ProjectContextRouteKind; path: string; projectId: string; workflowId?: string; knowledgeId?: string; conversationId?: string };
export type DesktopLocale = "zh" | "en";

export function isAgentContextRoute(route: DesktopRouteLocation): route is AgentContextRoute {
  return (route.kind === "agent-detail" || route.kind === "agent-design" || route.kind === "agent-analysis" || route.kind === "agent-run" || route.kind === "agent-version") && typeof route.agentId === "string";
}

export function isProjectContextRoute(route: DesktopRouteLocation): route is ProjectContextRoute {
  return route.kind === "project" || route.kind === "project-chat" || route.kind === "project-analysis" || route.kind === "project-resources" || route.kind === "project-agents" || route.kind === "project-workflows" || route.kind === "project-workflow" || route.kind === "project-knowledge" || route.kind === "project-knowledge-item" || route.kind === "project-files" || route.kind === "project-runs" || route.kind === "factory";
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

/** Agent pages share Project chrome; the tree row is the selected object. */
export function workspaceNavRoute(route: DesktopRouteLocation): ProjectContextRoute | undefined {
  if (isProjectContextRoute(route)) return route;
  if (isAgentContextRoute(route)) return { kind: "project-agents", path: route.path, projectId: route.projectId };
  return undefined;
}

export function projectContextActiveHref(route: ProjectContextRoute): string {
  if (route.kind === "project-chat") return projectRoutePaths.projectChat(route.projectId);
  if (route.kind === "project-analysis") return projectRoutePaths.projectAnalysis(route.projectId);
  if (route.kind === "project") return projectRoutePaths.project(route.projectId);
  if (route.kind === "project-resources") return projectRoutePaths.projectResources(route.projectId);
  if (route.kind === "factory") return projectRoutePaths.factory(route.projectId);
  return "";
}

export type ProjectResourceKind = "agents" | "workflows" | "knowledge" | "files" | "runs";

export type ProjectTreeSelection = {
  projectId?: string;
  agentId?: string;
  workflowId?: string;
  knowledgeId?: string;
  resourceKind?: ProjectResourceKind;
};

export function projectTreeSelection(route: DesktopRouteLocation): ProjectTreeSelection {
  if (!("projectId" in route) || !route.projectId) return {};
  const projectId = route.projectId;
  if (isAgentContextRoute(route)) return { projectId, agentId: route.agentId, resourceKind: "agents" };
  if (route.kind === "project-agents") return { projectId, resourceKind: "agents" };
  if (route.kind === "project-workflows") return { projectId, resourceKind: "workflows" };
  if (route.kind === "project-workflow") return { projectId, workflowId: route.workflowId, resourceKind: "workflows" };
  if (route.kind === "project-knowledge") return { projectId, resourceKind: "knowledge" };
  if (route.kind === "project-knowledge-item") return { projectId, knowledgeId: route.knowledgeId, resourceKind: "knowledge" };
  if (route.kind === "project-runs") return { projectId, resourceKind: "runs" };
  if (route.kind === "project" || route.kind === "project-chat" || route.kind === "project-analysis" || route.kind === "factory" || route.kind === "project-files") return { projectId };
  return { projectId };
}

export function projectContextNavigation(route: ProjectContextRoute, locale: DesktopLocale): NavigationGroup {
  const labels = locale === "zh"
    ? { newChat: "新聊天", resourceLibrary: "项目资源", analysis: "数据分析", factory: "Factory" }
    : { newChat: "New chat", resourceLibrary: "Project resources", analysis: "Data analysis", factory: "Factory" };
  const chatHref = projectRoutePaths.projectChat(route.projectId);
  const activeHref = projectContextActiveHref(route);
  const projectHref = projectRoutePaths.projectResources(route.projectId);
  const factoryHref = projectRoutePaths.factory(route.projectId);
  return {
    label: "Project",
    section: "fixed",
    backLink: workspaceContextBackLink(locale),
    items: [
      { href: chatHref, label: labels.newChat, icon: MessageCirclePlus, active: route.kind === "project-chat" && !route.conversationId },
      { href: projectHref, label: labels.resourceLibrary, icon: Boxes, active: activeHref === projectHref },
      { href: projectRoutePaths.projectAnalysis(route.projectId), label: labels.analysis, icon: Gauge, active: activeHref === projectRoutePaths.projectAnalysis(route.projectId) },
      ...(route.kind === "factory" ? [{ href: factoryHref, label: labels.factory, icon: Wrench, active: true }] : []),
    ],
  };
}

export function relativeActivityTime(value: string, locale: DesktopLocale, now = Date.now()): string {
  const stamp = Date.parse(value);
  if (!Number.isFinite(stamp)) return value;
  const minutes = Math.max(0, Math.round((now - stamp) / 60_000));
  if (minutes < 1) return locale === "zh" ? "刚刚" : "just now";
  if (minutes < 60) return locale === "zh" ? `${minutes} 分钟前` : `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return locale === "zh" ? `${hours} 小时前` : `${hours}h ago`;
  const days = Math.round(hours / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

export function agentRecentNavigation(
  locale: DesktopLocale,
  items: BuilderActivityItem[] = [],
  context: {
    projectId?: string;
    projectName?: string;
    projectNames?: Record<string, string>;
    conversationId?: string;
  } = {},
): NavigationGroup {
  const empty = {
    label: "Recent",
    section: "recent" as const,
    items: [],
    status: "empty" as const,
    statusText: locale === "zh" ? "暂无最近聊天。" : "No recent chats yet.",
  };
  const conversations = items.filter((item) => item.kind === "conversation" && item.conversation_id);
  const mapped = conversations.flatMap((item) => {
    const projectId = item.project_id ?? context.projectId;
    if (!projectId) return [];
    const projectName = context.projectNames?.[projectId] ?? context.projectName ?? "";
    const when = relativeActivityTime(item.occurred_at, locale);
    const detail = [projectName, when].filter(Boolean).join(" · ");
    return [{
      href: projectRoutePaths.projectChat(projectId, item.conversation_id),
      label: item.title,
      icon: MessageCircle,
      active: context.conversationId === item.conversation_id,
      detail,
    }];
  });
  if (!mapped.length) return empty;
  return {
    label: "Recent",
    section: "recent",
    items: mapped,
  };
}
