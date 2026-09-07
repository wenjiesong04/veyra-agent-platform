import * as React from "react";
import { Boxes, FileText, Gauge, Globe2, MessageCirclePlus } from "lucide-react";
import { desktopRoutePaths, parseDesktopRoute, projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import { accountInitials, AuthProvider, createCommunityApi, ForgotPasswordPage, LoginPage, RegisterPage, useAuth, type CommunityApi } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider, useLocale } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { createLocalApiClient, type LocalProjectApi } from "./api/local-client";
import { ProjectWorkspaceProvider, useProjectWorkspace } from "./api/project-workspace";
import { desktopHeader } from "./desktop-header";
import { agentRecentNavigation, isAgentContextRoute, projectContextActiveHref, projectContextNavigation, projectTreeSelection, workspaceNavRoute } from "./features/agents/agent-navigation";
import { resourceLibraryChildren } from "./features/resources/library-navigation";
import { AccountPage } from "./pages/account";
import { AgentAnalysisPage } from "./pages/agent-analysis";
import { AgentRunPage } from "./pages/agent-run";
import { AgentDetailPage } from "./pages/agent-detail";
import { AgentVersionPage } from "./pages/agent-version";
import { CommunityPage } from "./pages/community";
import { ComponentsPage } from "./pages/components";
import { FilesPage } from "./pages/files";
import { FactoryPage } from "./pages/factory";
import { MonitorPage } from "./pages/monitor";
import { NewChatPage } from "./pages/new-chat";
import { NotFoundPage } from "./pages/not-found";
import { PageErrorBoundary } from "./pages/page-error-boundary";
import { ProjectAnalysisPage } from "./pages/project-analysis";
import { ProjectChatPage } from "./pages/project-chat";
import { ProjectDetailPage } from "./pages/project-detail";
import { ProjectKnowledgePage } from "./pages/project-knowledge";
import { ProjectWorkflowsPage } from "./pages/project-workflows";
import { useProjectNavigation } from "./features/projects/project-navigation";
import { RunsPage } from "./pages/runs";
import { SettingsPage } from "./pages/settings";
import { StudioPage } from "./pages/studio";

const desktopCommunityApi = createCommunityApi({ baseUrl: "/community-api/api/v1" });

function homeNavigation(route: DesktopRouteLocation, hash: string): NavigationGroup {
  const libraryChildren = resourceLibraryChildren(route, hash);
  const onLibrary = route.kind === "components" || route.kind === "component";
  return {
    label: "Features",
    section: "fixed",
    items: [
      { href: desktopRoutePaths.chat, label: "New chat", icon: MessageCirclePlus },
      { href: desktopRoutePaths.monitor, label: "Run workspace", icon: Gauge },
      {
        href: desktopRoutePaths.components,
        label: "Resource library",
        icon: Boxes,
        active: onLibrary ? false : undefined,
        contextual: onLibrary,
        expanded: Boolean(libraryChildren),
        children: libraryChildren,
      },
      { href: desktopRoutePaths.files, label: "Knowledge base", icon: FileText },
      { href: desktopRoutePaths.community, label: "Community", icon: Globe2 },
    ],
  };
}

function routeFromHash(): DesktopRouteLocation {
  return parseDesktopRoute(window.location.hash);
}

function useHashRoute(): DesktopRouteLocation {
  const [route, setRoute] = React.useState(routeFromHash);

  React.useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route;
}

function PageContent({ route }: { route: DesktopRouteLocation }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  if (route.kind === "login") return <LoginPage />;
  if (route.kind === "register") return <RegisterPage />;
  if (route.kind === "forgot-password") return <ForgotPasswordPage />;
  if (route.kind === "chat") return <NewChatPage />;
  if (route.kind === "projects") return <NewChatPage />;
  if (route.kind === "project") return <ProjectDetailPage projectId={route.projectId} />;
  if (route.kind === "project-chat") return <ProjectChatPage projectId={route.projectId} />;
  if (route.kind === "project-analysis") return <ProjectAnalysisPage projectId={route.projectId} />;
  if (route.kind === "project-agents") return <ProjectDetailPage projectId={route.projectId} />;
  if (route.kind === "project-workflows") return <ProjectWorkflowsPage projectId={route.projectId} />;
  if (route.kind === "project-workflow") return <StudioPage projectId={route.projectId} workflowId={route.workflowId ?? ""} />;
  if (route.kind === "project-knowledge" || route.kind === "project-knowledge-item") return <ProjectKnowledgePage projectId={route.projectId} knowledgeId={route.knowledgeId} />;
  if (route.kind === "project-files") return <FilesPage projectId={route.projectId} />;
  if (route.kind === "project-runs") return <RunsPage projectId={route.projectId} />;
  if (route.kind === "agent-detail") return <AgentDetailPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
  if (route.kind === "agent-version") return <AgentVersionPage projectId={route.projectId} agentId={route.agentId ?? ""} versionId={route.versionId ?? ""} workflowId={route.workflowId} />;
  if (route.kind === "factory") return <FactoryPage projectId={route.projectId} />;
  if (route.kind === "agent-design") return <StudioPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
  if (route.kind === "agent-analysis") return <AgentAnalysisPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
  if (route.kind === "agent-run") return <AgentRunPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
  if (route.kind === "components") return <ComponentsPage />;
  if (route.kind === "component") return <ComponentsPage componentId={route.componentId} />;
  if (route.kind === "files") return <FilesPage />;
  if (route.kind === "file") return <FilesPage fileId={route.fileId} />;
  if (route.kind === "runs") return <RunsPage />;
  if (route.kind === "monitor") return <MonitorPage />;
  if (route.kind === "community") return <CommunityPage />;
  if (route.kind === "community-entry") return <CommunityPage owner={route.owner} slug={route.slug} />;
  if (route.kind === "community-version") return <CommunityPage owner={route.owner} slug={route.slug} versionId={route.versionId} />;
  if (route.kind === "account") return <AccountPage />;
  if (route.kind === "settings") return <SettingsPage />;
  if (route.kind === "not-found" && route.path.startsWith("#/community")) return <NotFoundPage backHref={desktopRoutePaths.community} backLabel={zh ? "返回社区" : "Back to Community"} />;
  if (route.kind === "not-found" && route.path.startsWith("#/components")) return <NotFoundPage backHref={desktopRoutePaths.components} backLabel={zh ? "返回组件库" : "Back to Components"} />;
  if (route.kind === "not-found" && route.path.startsWith("#/files")) return <NotFoundPage backHref={desktopRoutePaths.files} backLabel={zh ? "返回文件" : "Back to Files"} />;
  return <NotFoundPage />;
}

function DesktopWorkspace() {
  const { locale, t } = useLocale();
  const zh = locale === "zh";
  const route = useHashRoute();
  const { account, logout } = useAuth();
  const { projects } = useProjectWorkspace();
  if (route.kind === "login") return <LoginPage />;
  if (route.kind === "register") return <RegisterPage />;
  if (route.kind === "forgot-password") return <ForgotPasswordPage />;
  const agentContextRoute = isAgentContextRoute(route) ? route : undefined;
  const workspaceRoute = workspaceNavRoute(route);
  const treeSelection = projectTreeSelection(route);
  const scopedProjectId = treeSelection.projectId;
  const activeAgentId = agentContextRoute?.agentId;
  const activeHref = workspaceRoute
    ? projectContextActiveHref(workspaceRoute) || (workspaceRoute.kind === "factory" ? projectRoutePaths.factory(workspaceRoute.projectId) : projectRoutePaths.project(workspaceRoute.projectId))
    : route.kind === "projects" || route.kind === "chat"
    ? desktopRoutePaths.chat
    : route.kind === "component" || route.kind === "components" ? (window.location.hash.startsWith("#/components") ? window.location.hash : desktopRoutePaths.components)
      : route.kind === "file" || route.kind === "files" ? desktopRoutePaths.files
        : route.kind === "community-entry" || route.kind === "community-version" ? desktopRoutePaths.community
          : route.kind === "not-found" ? desktopRoutePaths.projects : (route.kind in desktopRoutePaths ? desktopRoutePaths[route.kind as keyof typeof desktopRoutePaths] : desktopRoutePaths.projects);
  const suppressProjectTreeHighlight = Boolean(workspaceRoute && projectContextActiveHref(workspaceRoute));
  const { navigation: projectNavigation, dialogs } = useProjectNavigation({ scopedProjectId, activeAgentId, selection: treeSelection, routeKey: route.path, suppressProjectHighlight: suppressProjectTreeHighlight });
  const header = desktopHeader(route, projects, locale);
  const historyHref = scopedProjectId ? projectRoutePaths.runs(scopedProjectId) : desktopRoutePaths.runs;
  const historyActive = route.kind === "runs" || route.kind === "project-runs";
  const navigation: NavigationGroup[] = workspaceRoute
    ? [projectContextNavigation(workspaceRoute, locale), ...projectNavigation, agentRecentNavigation(locale)]
    : [homeNavigation(route, window.location.hash), ...projectNavigation];

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: t("agentPlatform"), mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      title={header.title}
      breadcrumbs={header.breadcrumbs}
      historyHref={historyHref}
      historyActive={historyActive}
      contentClassName={route.kind === "agent-design" || route.kind === "project-workflow" ? "agent-studio-content" : (route.kind === "chat" || route.kind === "projects" || route.kind === "project-chat" || route.kind === "agent-detail" || route.kind === "factory" ? "agent-conversation-content" : undefined)}
      account={account ? {
        displayName: account.display_name || account.handle,
        detail: account.email,
        initials: accountInitials(account.display_name, account.handle),
        authenticated: true,
        accountHref: desktopRoutePaths.account,
        settingsHref: desktopRoutePaths.settings,
        onSignOut: () => {
          void logout().catch(() => undefined);
        },
      } : {
        displayName: t("localWorkspace"),
        detail: t("notSignedIn"),
        initials: zh ? "本" : "LW",
        authenticated: false,
        accountHref: desktopRoutePaths.account,
        settingsHref: desktopRoutePaths.settings,
      }}
    >
      <PageErrorBoundary resetKey={route.path} locale={locale}>
        <PageContent route={route} />
      </PageErrorBoundary>
      {dialogs}
    </ApplicationShell>
  );
}

export type DesktopAppProps = {
  api?: LocalProjectApi;
  communityApi?: CommunityApi;
};

export function DesktopApp({ api, communityApi }: DesktopAppProps = {}) {
  const projectApi = React.useMemo(() => api ?? createLocalApiClient(), [api]);
  const accountApi = React.useMemo(() => communityApi ?? desktopCommunityApi, [communityApi]);
  return (
    <ThemeProvider>
      <AuthProvider api={accountApi}>
        <ProjectWorkspaceProvider api={projectApi}>
          <DesktopWorkspace />
        </ProjectWorkspaceProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
