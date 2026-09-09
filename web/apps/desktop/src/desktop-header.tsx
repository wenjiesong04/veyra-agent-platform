import { BookOpen, Bot, Boxes, FileText, FolderKanban, Gauge, History, Home, MessageCirclePlus, Play, Workflow, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation, type ProjectAgentRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { agentAncestryPath } from "./features/projects/agent-tree";

type Crumb = { label: string; href?: string; icon?: typeof Home };
type DesktopHeader = { title: string; breadcrumbs?: Crumb[] };
type DesktopLocale = "zh" | "en";

const rootTitles: Record<"en" | "zh", Partial<Record<DesktopRouteLocation["kind"], string>>> = {
  en: { chat: "New chat", projects: "New chat", components: "Resource Library", files: "Knowledge base", runs: "History", monitor: "Monitor", community: "Community", account: "Account", settings: "Settings", "not-found": "Route not found" },
  zh: { chat: "新聊天", projects: "新聊天", components: "资源库", files: "知识库", runs: "历史", monitor: "监控", community: "社区", account: "账号", settings: "设置", "not-found": "找不到页面" },
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

export function desktopHeader(route: DesktopRouteLocation, projects: ProjectSummaryResponse[], locale: DesktopLocale = "en"): DesktopHeader {
  const contextLabels = locale === "zh"
    ? { newChat: "新聊天", analysis: "数据分析", run: "运行", version: "版本", resourceLibrary: "资源库", factory: "Factory", agents: "Agent", workflows: "工作流", knowledge: "知识", files: "文件", history: "历史" }
    : { newChat: "New chat", analysis: "Data analysis", run: "Run", version: "Version", resourceLibrary: "Resource library", factory: "Factory", agents: "Agents", workflows: "Workflows", knowledge: "Knowledge", files: "Files", history: "History" };
  const title = rootTitles[locale][route.kind];
  if (title) return { title };
  const project = "projectId" in route ? projects.find((item) => item.project_id === route.projectId) : undefined;
  const projectLabel = project?.name ?? ("projectId" in route ? route.projectId : "Project");
  const home = { label: "Home", href: desktopRoutePaths.projects, icon: Home };
  const projectCrumb = "projectId" in route ? { label: projectLabel, href: projectRoutePaths.project(route.projectId), icon: FolderKanban } : undefined;
  if (!projectCrumb) return { title: "Route not found" };

  if (route.kind === "project") {
    return { title: contextLabels.resourceLibrary, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.resourceLibrary, href: projectCrumb.href, icon: Boxes }) };
  }
  if (route.kind === "project-agents") {
    return { title: projectLabel, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.agents, href: projectRoutePaths.agents(route.projectId), icon: Bot }) };
  }
  if (route.kind === "project-chat") {
    return { title: contextLabels.newChat, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.newChat, href: projectRoutePaths.projectChat(route.projectId), icon: MessageCirclePlus }) };
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
  if (route.kind === "project-workflow") {
    const workflow = project?.workflows?.find((item) => item.workflow_id === route.workflowId);
    const workflowLabel = workflow?.name || workflow?.slug || contextLabels.workflows;
    return { title: workflowLabel, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.workflows, href: projectRoutePaths.workflows(route.projectId), icon: Workflow }, { label: workflowLabel, href: projectRoutePaths.workflow(route.projectId, route.workflowId ?? ""), icon: Workflow }) };
  }
  if (route.kind === "project-knowledge" || route.kind === "project-knowledge-item") {
    return { title: contextLabels.knowledge, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.knowledge, href: projectRoutePaths.knowledge(route.projectId), icon: BookOpen }) };
  }
  if (route.kind === "project-files") {
    return { title: contextLabels.files, breadcrumbs: projectTrail(home, projectCrumb, { label: contextLabels.files, href: projectRoutePaths.files(route.projectId), icon: FileText }) };
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
