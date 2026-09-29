import * as React from "react";
import { Boxes, FileText, Gauge, Globe2, MessageCirclePlus } from "lucide-react";
import { desktopLoginHash, desktopPathAfterAuth, desktopRoutePaths, isDesktopPublicAuthRoute, parseDesktopRoute, projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import { accountInitials, AuthProvider, createCommunityApi, ForgotPasswordPage, LoginPage, RegisterPage, useAuth, type CommunityApi } from "@veyra/connected-account";
import { ApplicationShell, BrandLoading, ThemeProvider, useLocale } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { createLocalApiClient, type LocalProjectApi } from "./api/local-client";
import { ProjectWorkspaceProvider, useProjectWorkspace } from "./api/project-workspace";
import { desktopHeader } from "./desktop-header";
import { isAgentContextRoute, projectContextActiveHref, projectContextNavigation, projectTreeSelection, workspaceNavRoute } from "./features/agents/agent-navigation";
import { useRecentConversationNavigation } from "./features/builder/recent-conversations";
import { resourceLibraryHref, rememberProjectId } from "./features/resources/library-navigation";
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
import { ProjectResourcesPage } from "./pages/project-resources";
import { ProjectKnowledgePage } from "./pages/project-knowledge";
import { ProjectWorkflowsPage } from "./pages/project-workflows";
import { useProjectNavigation } from "./features/projects/project-navigation";
import { RunsPage } from "./pages/runs";
import { SettingsPage } from "./pages/settings";
import { StudioPage } from "./pages/studio";
import { TrashPage } from "./pages/trash";

const desktopCommunityApi = createCommunityApi({ baseUrl: "/community-api/api/v1" });

function homeNavigation(libraryHref: string, locale: "zh" | "en"): NavigationGroup {
  const resourceCatalog = locale === "zh" ? "资源目录" : "Resource catalog";
  return {
    label: "Features",
    section: "fixed",
    items: [
      { href: desktopRoutePaths.chat, label: "New chat", icon: MessageCirclePlus },
      { href: desktopRoutePaths.monitor, label: "Run workspace", icon: Gauge },
      { href: libraryHref, label: resourceCatalog, icon: Boxes },
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

function AuthBootScreen() {
  const { locale } = useLocale();
  return <BrandLoading fullscreen size={88} label={locale === "zh" ? "正在确认登录状态…" : "Checking sign-in…"} />;
}

function DesktopAuthPages({ route }: { route: DesktopRouteLocation }) {
  const home = desktopRoutePaths.chat;
  if (route.kind === "register") return <RegisterPage afterAuthHref={home} />;
  if (route.kind === "forgot-password") return <ForgotPasswordPage />;
  return <LoginPage afterAuthHref={home} />;
}

function DesktopSession({ children }: { children: React.ReactNode }) {
  const { status, ensureSession } = useAuth();
  const route = useHashRoute();
  const publicAuth = isDesktopPublicAuthRoute(route.kind);

  const booted = status !== "booting";

  React.useEffect(() => {
    if (!booted) return;
    void ensureSession();
  }, [booted, ensureSession, route.path]);

  React.useEffect(() => {
    if (status === "booting") return;
    if (status !== "authenticated") {
      const nextHash = desktopLoginHash(window.location.hash);
      if (window.location.hash !== nextHash) window.location.hash = nextHash;
      return;
    }
    if (publicAuth) {
      const destination = desktopPathAfterAuth(window.location.hash, desktopRoutePaths.chat);
      if (window.location.hash !== destination) window.location.hash = destination;
    }
  }, [publicAuth, route.path, status]);

  React.useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void ensureSession();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [ensureSession]);

  if (status === "booting") return <AuthBootScreen />;
  if (status !== "authenticated") return <DesktopAuthPages route={route} />;
  if (publicAuth) return <AuthBootScreen />;
  return children;
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
  if (route.kind === "project-resources") return <ProjectResourcesPage projectId={route.projectId} />;
  if (route.kind === "project-chat") return <ProjectChatPage projectId={route.projectId} conversationId={route.conversationId} />;
  if (route.kind === "project-analysis") return <ProjectAnalysisPage projectId={route.projectId} />;
  if (route.kind === "project-agents") return <ProjectDetailPage projectId={route.projectId} collection="agents" />;
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
  if (route.kind === "components" || route.kind === "resources") return <ComponentsPage catalogHref={desktopRoutePaths.resources} />;
  if (route.kind === "component") return <ComponentsPage componentId={route.componentId} />;
  if (route.kind === "files") return <FilesPage />;
  if (route.kind === "file") return <FilesPage fileId={route.fileId} />;
  if (route.kind === "runs") return <RunsPage />;
  if (route.kind === "monitor") return <MonitorPage />;
  if (route.kind === "community") return <CommunityPage section="discover" />;
  if (route.kind === "community-published") return <CommunityPage section="published" />;
  if (route.kind === "community-starred") return <CommunityPage section="starred" />;
  if (route.kind === "community-mine") return <CommunityPage section="mine" />;
  if (route.kind === "community-entry") return <CommunityPage section="discover" owner={route.owner} slug={route.slug} />;
  if (route.kind === "community-version") return <CommunityPage section="discover" owner={route.owner} slug={route.slug} versionId={route.versionId} />;
  if (route.kind === "account") return <AccountPage />;
  if (route.kind === "settings") return <SettingsPage />;
  if (route.kind === "trash") return <TrashPage />;
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
  const agentContextRoute = isAgentContextRoute(route) ? route : undefined;
  const workspaceRoute = workspaceNavRoute(route);
  const treeSelection = projectTreeSelection(route);
  const scopedProjectId = treeSelection.projectId;
  const activeAgentId = agentContextRoute?.agentId;
  const conversationId = route.kind === "project-chat" ? route.conversationId : undefined;
  const scopedProject = projects.find((item) => item.project_id === scopedProjectId);
  const { navigation: recentNavigation, dialogs: recentDialogs, conversationTitle } = useRecentConversationNavigation({
    locale,
    projectId: scopedProjectId,
    projectName: scopedProject?.name,
    projectNames: Object.fromEntries(projects.map((item) => [item.project_id, item.name])),
    conversationId,
  });
  React.useEffect(() => {
    if (scopedProjectId) rememberProjectId(scopedProjectId);
  }, [scopedProjectId]);
  const libraryHref = resourceLibraryHref(projects);
  const activeHref = workspaceRoute
    ? projectContextActiveHref(workspaceRoute) || (workspaceRoute.kind === "factory" ? projectRoutePaths.factory(workspaceRoute.projectId) : projectRoutePaths.project(workspaceRoute.projectId))
    : route.kind === "projects" || route.kind === "chat"
    ? desktopRoutePaths.chat
    : route.kind === "component" || route.kind === "components" ? (window.location.hash.startsWith("#/components") ? window.location.hash : desktopRoutePaths.components)
      : route.kind === "file" || route.kind === "files" ? desktopRoutePaths.files
        : route.kind === "community-entry" || route.kind === "community-version" || route.kind === "community-published" || route.kind === "community-starred" || route.kind === "community-mine" ? desktopRoutePaths.community
          : route.kind === "not-found" ? desktopRoutePaths.projects : (route.kind in desktopRoutePaths ? desktopRoutePaths[route.kind as keyof typeof desktopRoutePaths] : desktopRoutePaths.projects);
  const suppressProjectTreeHighlight = Boolean(workspaceRoute && workspaceRoute.kind !== "project" && workspaceRoute.kind !== "project-files" && projectContextActiveHref(workspaceRoute));
  const { navigation: projectNavigation, dialogs } = useProjectNavigation({ scopedProjectId, activeAgentId, selection: treeSelection, routeKey: route.path, suppressProjectHighlight: suppressProjectTreeHighlight });
  const header = desktopHeader(route, projects, locale, { conversationTitle });
  const historyHref = scopedProjectId ? projectRoutePaths.runs(scopedProjectId) : desktopRoutePaths.runs;
  const historyActive = route.kind === "runs" || route.kind === "project-runs";
  const navigation: NavigationGroup[] = workspaceRoute
    ? [projectContextNavigation(workspaceRoute, locale), ...projectNavigation, recentNavigation]
    : [homeNavigation(libraryHref, locale), ...projectNavigation, recentNavigation];

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
        avatarUrl: account.avatar_url,
        authenticated: true,
        accountHref: desktopRoutePaths.account,
        settingsHref: desktopRoutePaths.settings,
        trashHref: desktopRoutePaths.trash,
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
        trashHref: desktopRoutePaths.trash,
      }}
    >
      <PageErrorBoundary resetKey={route.path} locale={locale}>
        <PageContent route={route} />
      </PageErrorBoundary>
      {dialogs}
      {recentDialogs}
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
        <DesktopSession>
          <ProjectWorkspaceProvider api={projectApi} cloudApi={accountApi}>
            <DesktopWorkspace />
          </ProjectWorkspaceProvider>
        </DesktopSession>
      </AuthProvider>
    </ThemeProvider>
  );
}
