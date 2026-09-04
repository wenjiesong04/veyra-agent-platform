import { Bot, FolderKanban, Gauge, GitBranch, Home, MessageCirclePlus, Play, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation, type ProjectAgentRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { agentAncestryPath } from "./features/projects/agent-tree";

type DesktopHeader = { title: string; breadcrumbs?: { label: string; href?: string; icon?: typeof Home }[] };
type DesktopLocale = "zh" | "en";

const rootTitles: Record<"en" | "zh", Partial<Record<DesktopRouteLocation["kind"], string>>> = {
  en: { chat: "New chat", projects: "New chat", components: "Resource Library", files: "Knowledge base", runs: "Runs", monitor: "Monitor", community: "Community", account: "Account", settings: "Settings", "not-found": "Route not found" },
  zh: { chat: "新聊天", projects: "新聊天", components: "资源库", files: "知识库", runs: "运行记录", monitor: "监控", community: "社区", account: "账号", settings: "设置", "not-found": "找不到页面" },
};

function agentDisplayLabel(agent: ProjectAgentRecord): string {
  return agent.name || agent.slug;
}

function agentBreadcrumbChain(project: ProjectSummaryResponse, projectId: string, agentId: string) {
  return agentAncestryPath(project.agents, agentId).map((agent) => ({
    label: agentDisplayLabel(agent),
    href: projectRoutePaths.agentDesign(projectId, agent.agent_id),
    icon: Bot,
  }));
}

export function desktopHeader(route: DesktopRouteLocation, projects: ProjectSummaryResponse[], locale: DesktopLocale = "en"): DesktopHeader {
  const contextLabels = locale === "zh"
    ? { newChat: "新聊天", orchestration: "编排", analysis: "数据分析", run: "运行", version: "版本", overview: "概览", factory: "Factory" }
    : { newChat: "New chat", orchestration: "Orchestration", analysis: "Data analysis", run: "Run", version: "Version", overview: "Overview", factory: "Factory" };
  const title = rootTitles[locale][route.kind];
  if (title) return { title };
  const project = "projectId" in route ? projects.find((item) => item.project_id === route.projectId) : undefined;
  const projectLabel = project?.name ?? ("projectId" in route ? route.projectId : "Project");
  const home = { label: "Home", href: desktopRoutePaths.projects, icon: Home };
  const projectCrumb = "projectId" in route ? { label: projectLabel, href: projectRoutePaths.project(route.projectId), icon: FolderKanban } : undefined;
  if (!projectCrumb) return { title: "Route not found" };

  if (route.kind === "project" || route.kind === "project-agents") {
    return { title: projectLabel, breadcrumbs: [home, { label: contextLabels.overview, href: projectCrumb.href, icon: FolderKanban }, projectCrumb] };
  }
  if (route.kind === "project-chat") {
    return { title: contextLabels.newChat, breadcrumbs: [home, { label: contextLabels.newChat, href: projectRoutePaths.projectChat(route.projectId), icon: MessageCirclePlus }, projectCrumb] };
  }
  if (route.kind === "project-analysis") {
    return { title: contextLabels.analysis, breadcrumbs: [home, { label: contextLabels.analysis, href: projectRoutePaths.projectAnalysis(route.projectId), icon: Gauge }, projectCrumb] };
  }
  if (route.kind === "factory") {
    return { title: contextLabels.factory, breadcrumbs: [home, { label: contextLabels.factory, href: projectRoutePaths.factory(route.projectId), icon: Wrench }, projectCrumb] };
  }

  if ("agentId" in route && route.agentId && project) {
    const agentId = route.agentId;
    const agentChain = agentBreadcrumbChain(project, route.projectId, agentId);
    const fallbackAgent = project.agents.find((item) => item.agent_id === agentId);
    const resolvedAgentChain = agentChain.length
      ? agentChain
      : [{ label: fallbackAgent ? agentDisplayLabel(fallbackAgent) : agentId, icon: Bot }];
    if (route.kind === "agent-detail") {
      return {
        title: fallbackAgent ? agentDisplayLabel(fallbackAgent) : agentId,
        breadcrumbs: [home, { label: contextLabels.newChat, href: projectRoutePaths.agent(route.projectId, agentId), icon: MessageCirclePlus }, projectCrumb, ...resolvedAgentChain],
      };
    }
    if (route.kind === "agent-design") {
      return {
        title: contextLabels.orchestration,
        breadcrumbs: [home, { label: contextLabels.orchestration, href: projectRoutePaths.agentDesign(route.projectId, agentId), icon: GitBranch }, projectCrumb, ...resolvedAgentChain],
      };
    }
    if (route.kind === "agent-analysis") {
      return {
        title: contextLabels.analysis,
        breadcrumbs: [home, { label: contextLabels.analysis, href: projectRoutePaths.agentAnalysis(route.projectId, agentId), icon: Gauge }, projectCrumb, ...resolvedAgentChain],
      };
    }
    if (route.kind === "agent-version") {
      const versionLabel = `${contextLabels.version} / ${route.versionId ?? ""}`.trim();
      return {
        title: versionLabel,
        breadcrumbs: [home, { label: contextLabels.orchestration, href: projectRoutePaths.agentDesign(route.projectId, agentId), icon: GitBranch }, projectCrumb, ...resolvedAgentChain, { label: versionLabel, icon: Wrench }],
      };
    }
    return {
      title: contextLabels.run,
      breadcrumbs: [home, { label: contextLabels.orchestration, href: projectRoutePaths.agentDesign(route.projectId, agentId), icon: GitBranch }, projectCrumb, ...resolvedAgentChain, { label: contextLabels.run, icon: Play }],
    };
  }

  return { title: "Route not found" };
}
