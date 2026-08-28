import * as React from "react";
import { Boxes, FileText, Gauge, Globe2, MessageCirclePlus } from "lucide-react";
import { desktopRoutePaths, parseDesktopRoute, type DesktopRouteLocation } from "@veyra/api-contracts";
import { accountInitials, AuthProvider, createCommunityApi, ForgotPasswordPage, LoginPage, RegisterPage, useAuth, type CommunityApi } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider, useLocale } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { createLocalApiClient, type LocalProjectApi } from "./api/local-client";
import { ProjectWorkspaceProvider, useProjectWorkspace } from "./api/project-workspace";
import { desktopHeader } from "./desktop-header";
import { AccountPage } from "./pages/account";
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
import { ProjectDetailPage } from "./pages/project-detail";
import { useProjectNavigation } from "./features/projects/project-navigation";
import { RunsPage } from "./pages/runs";
import { SettingsPage } from "./pages/settings";
import { StudioPage } from "./pages/studio";

const desktopCommunityApi = createCommunityApi({ baseUrl: "/community-api/api/v1" });

const fixedNavigation: NavigationGroup = {
  label: "Features",
  section: "fixed",
  items: [
    { href: desktopRoutePaths.chat, label: "New chat", icon: MessageCirclePlus },
    { href: desktopRoutePaths.monitor, label: "Run workspace", icon: Gauge },
    { href: desktopRoutePaths.components, label: "Resource library", icon: Boxes },
    { href: desktopRoutePaths.files, label: "Knowledge base", icon: FileText },
    { href: desktopRoutePaths.community, label: "Community", icon: Globe2 },
  ],
};

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
  if (route.kind === "project-agents") return <ProjectDetailPage projectId={route.projectId} />;
  if (route.kind === "agent-detail") return <AgentDetailPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
  if (route.kind === "agent-version") return <AgentVersionPage projectId={route.projectId} agentId={route.agentId ?? ""} versionId={route.versionId ?? ""} />;
  if (route.kind === "factory") return <FactoryPage projectId={route.projectId} />;
  if (route.kind === "agent-design") return <StudioPage projectId={route.projectId} agentId={route.agentId ?? ""} />;
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
  const scopedProjectId = route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run" ? route.projectId : undefined;
  const activeAgentId = route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "agent-design" || route.kind === "agent-run" ? route.agentId : undefined;
  const activeHref = route.kind === "projects" || route.kind === "chat"
    ? desktopRoutePaths.chat
    : route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run"
    ? desktopRoutePaths.projects
    : route.kind === "component" || route.kind === "components" ? desktopRoutePaths.components
      : route.kind === "file" || route.kind === "files" ? desktopRoutePaths.files
        : route.kind === "community-entry" || route.kind === "community-version" ? desktopRoutePaths.community
          : route.kind === "not-found" ? desktopRoutePaths.projects : desktopRoutePaths[route.kind];
  const { navigation: projectNavigation, dialogs } = useProjectNavigation({ scopedProjectId, activeAgentId, routeKey: route.path });
  const header = desktopHeader(route, projects);
  const navigation: NavigationGroup[] = [fixedNavigation, ...projectNavigation];

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: t("agentPlatform"), mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      title={header.title}
      breadcrumbs={header.breadcrumbs}
      backHref={header.backHref}
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
      <PageContent route={route} />
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
