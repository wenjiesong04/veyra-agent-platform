import { BookOpen, Bookmark, Bot, Boxes, Compass, FileText, FolderKanban, Gauge, Globe2, History, Home, MessageCircle, MessageCirclePlus, PackageCheck, Play, Settings, Trash2, UserRound, Workflow, Wrench } from "lucide-react";
import { communityRoutePaths, desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation, type ProjectAgentRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { agentAncestryPath } from "./features/projects/agent-tree";
import { displayConversationTitle } from "./features/agents/conversation-title";

type Crumb = { label: string; href?: string; icon?: typeof Home };
type DesktopHeader = { title: string; breadcrumbs?: Crumb[] };
type DesktopLocale = "zh" | "en";

const rootTitles: Record<"en" | "zh", Partial<Record<DesktopRouteLocation["kind"], string>>> = {
  en: { chat: "New chat", projects: "New chat", components: "Resource Catalog", resources: "Resource Catalog", files: "Knowledge base", runs: "History", monitor: "Monitor", account: "Account", settings: "Settings", trash: "Trash", "not-found": "Route not found" },
  zh: { chat: "新聊天", projects: "新聊天", components: "资源目录", resources: "资源目录", files: "知识库", runs: "历史", monitor: "监控", account: "账号", settings: "设置", trash: "回收站", "not-found": "找不到页面" },
};

const rootIcons: Partial<Record<DesktopRouteLocation["kind"], typeof Home>> = {
  chat: MessageCirclePlus,
  projects: MessageCirclePlus,
  components: Boxes,
  resources: Boxes,
  files: FileText,
  runs: History,
  monitor: Gauge,
  account: UserRound,
  settings: Settings,
  trash: Trash2,
  "not-found": Compass,
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

function projectTrail(home: Crumb, project: Crumb, ...rest: Crumb[]): Crumb[] {
  return [home, project, ...rest];
}

function communityHeader(route: DesktopRouteLocation, locale: DesktopLocale): DesktopHeader | null {
  const labels = locale === "zh"
    ? { community: "社区", discover: "发现", published: "已发布", starred: "已收藏", mine: "我的", release: "版本详情" }
    : { community: "Community", discover: "Discover", published: "Published", starred: "Starred", mine: "Mine", release: "Release" };
  const community = { label: labels.community, href: desktopRoutePaths.community, icon: Globe2 };
  const discover = { label: labels.discover, href: communityRoutePaths.catalog, icon: Compass };
  if (route.kind === "community") return { title: labels.discover, breadcrumbs: [community, { label: labels.discover, icon: Compass }] };
  if (route.kind === "community-published") return { title: labels.published, breadcrumbs: [community, { label: labels.published, icon: PackageCheck }] };
  if (route.kind === "community-starred") return { title: labels.starred, breadcrumbs: [community, { label: labels.starred, icon: Bookmark }] };
  if (route.kind === "community-mine") return { title: labels.mine, breadcrumbs: [community, { label: labels.mine, icon: UserRound }] };
  if (route.kind === "community-entry" || route.kind === "community-version") {
    const release = route.slug || labels.release;
    const version = route.kind === "community-version" && route.versionId ? `v${route.versionId}` : "";
    return {
      title: version || release,
      breadcrumbs: version
        ? [community, discover, { label: release, href: communityRoutePaths.entry(route.owner ?? "", route.slug ?? "") }, { label: version }]
        : [community, discover, { label: release }],
    };
  }
  return null;
}

export function desktopHeader(
  route: DesktopRouteLocation,
  projects: ProjectSummaryResponse[],
  locale: DesktopLocale = "en",
  context: { conversationTitle?: string } = {},
): DesktopHeader {
  const contextLabels = locale === "zh"
    ? { newChat: "新聊天", analysis: "数据分析", run: "运行详情", version: "版本", resourceLibrary: "项目资源", factory: "Factory", agents: "Agent", workflows: "工作流", knowledge: "知识", files: "文件", history: "运行记录", app: "应用", studio: "Studio" }
    : { newChat: "New chat", analysis: "Data analysis", run: "Run Detail", version: "Version", resourceLibrary: "Project resources", factory: "Factory", agents: "Agents", workflows: "Workflows", knowledge: "Knowledge", files: "Files", history: "Runs", app: "App", studio: "Studio" };
  const communityTrail = communityHeader(route, locale);
  if (communityTrail) return communityTrail;
  const title = rootTitles[locale][route.kind];
  if (title) return { title, breadcrumbs: [{ label: title, icon: rootIcons[route.kind] }] };
  const project = "projectId" in route ? projects.find((item) => item.project_id === route.projectId) : undefined;
  const projectLabel = project?.name ?? ("projectId" in route ? route.projectId : "Project");
  const home = { label: "Home", href: desktopRoutePaths.projects, icon: Home };
  const projectCrumb = "projectId" in route ? { label: projectLabel, href: projectRoutePaths.project(route.projectId), icon: FolderKanban } : undefined;
  if (!projectCrumb) return { title: "Route not found" };

  if (route.kind === "project") {
    return { title: projectLabel, breadcrumbs: projectTrail(home, projectCrumb) };
  }
  if (route.kind === "project-files") {
    return { title: contextLabels.files, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.files, href: projectRoutePaths.files(route.projectId), icon: FileText }) };
  }
  if (route.kind === "project-resources") {
    return { title: contextLabels.resourceLibrary, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.resourceLibrary, href: projectRoutePaths.projectResources(route.projectId), icon: Boxes }) };
  }
  if (route.kind === "project-agents") {
    return { title: projectLabel, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }) };
  }
  if (route.kind === "project-chat") {
    const chatLabel = route.conversationId
      ? displayConversationTitle(context.conversationTitle, locale)
      : contextLabels.newChat;
    const href = route.conversationId
      ? projectRoutePaths.projectChat(route.projectId, route.conversationId)
      : projectRoutePaths.projectChat(route.projectId);
    return {
      title: chatLabel,
      breadcrumbs: projectTrail(home, projectCrumb, { label: chatLabel, href, icon: MessageCircle }),
    };
  }
  if (route.kind === "project-analysis") {
    return { title: contextLabels.analysis, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.analysis, href: projectRoutePaths.projectAnalysis(route.projectId), icon: Gauge }) };
  }
  if (route.kind === "factory") {
    return { title: contextLabels.factory, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.factory, href: projectRoutePaths.factory(route.projectId), icon: Wrench }) };
  }
  if (route.kind === "project-workflows") {
    return { title: contextLabels.workflows, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.workflows, href: projectRoutePaths.workflows(route.projectId), icon: Workflow }) };
  }
  if (route.kind === "project-workflow" || route.kind === "project-workflow-run") {
    const workflow = project?.workflows?.find((item) => item.workflow_id === route.workflowId);
    const workflowLabel = workflow?.name || workflow?.slug || contextLabels.workflows;
    const workflowCrumb = { label: workflowLabel, href: projectRoutePaths.workflow(route.projectId, route.workflowId ?? ""), icon: Workflow };
    return { title: workflowLabel, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.workflows, href: projectRoutePaths.workflows(route.projectId), icon: Workflow }, workflowCrumb, ...(route.kind === "project-workflow-run" ? [{ label: locale === "zh" ? "运行" : "Run", href: projectRoutePaths.workflowRun(route.projectId, route.workflowId ?? ""), icon: Play }] : [])) };
  }
  if (route.kind === "project-knowledge" || route.kind === "project-knowledge-item") {
    return { title: contextLabels.knowledge, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.knowledge, href: projectRoutePaths.knowledge(route.projectId), icon: BookOpen }) };
  }
  if (route.kind === "project-runs") {
    return { title: contextLabels.history, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.history, href: projectRoutePaths.runs(route.projectId), icon: History }) };
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
        breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }, ...resolvedAgentChain),
      };
    }
    if (route.kind === "agent-design") {
      const fromWorkflow = route.workflowId ? project.workflows?.find((item) => item.workflow_id === route.workflowId) : undefined;
      const agentTitle = fallbackAgent ? agentDisplayLabel(fallbackAgent) : (resolvedAgentChain.at(-1)?.label ?? agentId);
      return {
        title: agentTitle,
        breadcrumbs: fromWorkflow
          ? projectTrail(home, projectCrumb, { label: contextLabels.workflows, href: projectRoutePaths.workflows(route.projectId), icon: Workflow }, { label: fromWorkflow.name || fromWorkflow.slug, href: projectRoutePaths.workflow(route.projectId, fromWorkflow.workflow_id), icon: Workflow }, ...resolvedAgentChain)
          : projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }, ...resolvedAgentChain),
      };
    }
    if (route.kind === "agent-analysis") {
      return {
        title: contextLabels.analysis,
        breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }, ...resolvedAgentChain, { label: contextLabels.analysis, icon: Gauge }),
      };
    }
    if (route.kind === "agent-version") {
      const versionLabel = `${contextLabels.version} / ${route.versionId ?? ""}`.trim();
      return {
        title: versionLabel,
        breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }, ...resolvedAgentChain, { label: versionLabel, icon: Wrench }),
      };
    }
    return {
      title: contextLabels.run,
      breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }, ...resolvedAgentChain, { label: contextLabels.run, icon: Play }),
    };
  }

  return { title: "Route not found" };
}
