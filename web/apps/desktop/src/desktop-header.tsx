import { Bot, FolderKanban, Gauge, Home, Play, Wrench } from "lucide-react";
import { desktopRoutePaths, projectRoutePaths, type DesktopRouteLocation, type ProjectSummaryResponse } from "@veyra/api-contracts";

type DesktopHeader = { title: string; breadcrumbs?: { label: string; href?: string; icon?: typeof Home }[]; backHref?: string };
type DesktopLocale = "zh" | "en";

const rootTitles: Record<"en" | "zh", Partial<Record<DesktopRouteLocation["kind"], string>>> = {
  en: { chat: "New chat", projects: "New chat", components: "Resource Library", files: "Knowledge base", runs: "Runs", monitor: "Monitor", community: "Community", account: "Account", settings: "Settings", "not-found": "Route not found" },
  zh: { chat: "新聊天", projects: "新聊天", components: "资源库", files: "知识库", runs: "运行记录", monitor: "监控", community: "社区", account: "账号", settings: "设置", "not-found": "找不到页面" },
};

export function desktopHeader(route: DesktopRouteLocation, projects: ProjectSummaryResponse[], locale: DesktopLocale = "en"): DesktopHeader {
  const contextLabels = locale === "zh"
    ? { orchestration: "编排", analysis: "数据分析", run: "运行", version: "版本" }
    : { orchestration: "Orchestration", analysis: "Data analysis", run: "Run", version: "Version" };
  const title = rootTitles[locale][route.kind];
  if (title) return { title };
  const project = "projectId" in route ? projects.find((item) => item.project_id === route.projectId) : undefined;
  const projectLabel = project?.name ?? ("projectId" in route ? route.projectId : "Project");
  const home = { label: "Home", href: desktopRoutePaths.projects, icon: Home };
  const projectCrumb = "projectId" in route ? { label: projectLabel, href: projectRoutePaths.project(route.projectId), icon: FolderKanban } : undefined;
  const agent = project && "agentId" in route ? project.agents.find((item) => item.agent_id === route.agentId) : undefined;
  const agentCrumb = agent && "projectId" in route && "agentId" in route ? { label: agent.slug, href: projectRoutePaths.agentDesign(route.projectId, agent.agent_id), icon: Bot } : undefined;
  if (!projectCrumb) return { title: "Route not found" };
  if (route.kind === "project" || route.kind === "project-agents") return { title: projectLabel, breadcrumbs: [home, { label: projectLabel, icon: FolderKanban }], backHref: desktopRoutePaths.projects };
  if (route.kind === "factory") return { title: "Factory", breadcrumbs: [home, projectCrumb, { label: "Factory", icon: Wrench }], backHref: projectCrumb.href };
  if (route.kind === "agent-detail") return { title: agent?.slug ?? route.agentId ?? "Agent", breadcrumbs: [home, projectCrumb, { label: agent?.slug ?? route.agentId ?? "Agent", icon: Bot }], backHref: projectCrumb.href };
  if (route.kind === "agent-version") return { title: `${contextLabels.version} / ${route.versionId ?? ""}`.trim(), breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: `${contextLabels.version} / ${route.versionId ?? ""}`.trim(), icon: Wrench }], backHref: agentCrumb?.href ?? projectCrumb.href };
  if (route.kind === "agent-design") return { title: contextLabels.orchestration, breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: contextLabels.orchestration, icon: Wrench }], backHref: agentCrumb?.href ?? projectCrumb.href };
  if (route.kind === "agent-analysis") return { title: contextLabels.analysis, breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: contextLabels.analysis, icon: Gauge }], backHref: agentCrumb?.href ?? projectCrumb.href };
  return { title: contextLabels.run, breadcrumbs: [home, projectCrumb, agentCrumb ?? { label: "Agent", href: projectCrumb.href, icon: Bot }, { label: contextLabels.run, icon: Play }], backHref: agentCrumb?.href ?? projectCrumb.href };
}
