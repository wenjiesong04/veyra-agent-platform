import { Gauge, GitBranch, MessageCirclePlus } from "lucide-react";
import { projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import type { NavigationGroup } from "@veyra/ui";

export type AgentContextRouteKind = "agent-detail" | "agent-design" | "agent-analysis" | "agent-run" | "agent-version";
export type AgentContextRoute = { kind: AgentContextRouteKind; path: string; projectId: string; agentId: string; versionId?: string };
export type DesktopLocale = "zh" | "en";

export function isAgentContextRoute(route: DesktopRouteLocation): route is AgentContextRoute {
  return (route.kind === "agent-detail" || route.kind === "agent-design" || route.kind === "agent-analysis" || route.kind === "agent-run" || route.kind === "agent-version") && typeof route.agentId === "string";
}

/** The context item with a direct route is active; deep Run/Version pages have no sibling top item. */
export function agentContextActiveHref(route: AgentContextRoute): string {
  if (route.kind === "agent-design") return projectRoutePaths.agentDesign(route.projectId, route.agentId);
  if (route.kind === "agent-analysis") return projectRoutePaths.agentAnalysis(route.projectId, route.agentId);
  if (route.kind === "agent-detail") return projectRoutePaths.agent(route.projectId, route.agentId);
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
    items: [
      { href: projectRoutePaths.agent(route.projectId, route.agentId), label: labels.root, icon: MessageCirclePlus, active: activeHref === projectRoutePaths.agent(route.projectId, route.agentId) },
      { href: projectRoutePaths.agentDesign(route.projectId, route.agentId), label: labels.orchestration, icon: GitBranch, active: activeHref === projectRoutePaths.agentDesign(route.projectId, route.agentId) },
      { href: projectRoutePaths.agentAnalysis(route.projectId, route.agentId), label: labels.analysis, icon: Gauge, active: activeHref === projectRoutePaths.agentAnalysis(route.projectId, route.agentId) },
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
