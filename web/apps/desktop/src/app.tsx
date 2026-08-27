import * as React from "react";
import { Boxes, FileText, FolderKanban, Gauge, Globe2, MessageCirclePlus, MoreHorizontal, Pin, PinOff, Plus } from "lucide-react";
import { desktopRoutePaths, parseDesktopRoute, projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import { accountInitials, AuthProvider, createCommunityApi, ForgotPasswordPage, LoginPage, RegisterPage, useAuth, type CommunityApi } from "@veyra/connected-account";
import { ApplicationShell, ThemeProvider, useLocale } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { createLocalApiClient, type LocalProjectApi } from "./api/local-client";
import { ProjectWorkspaceProvider, useProjectWorkspace } from "./api/project-workspace";
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
import { ProjectDialog, type ProjectDialogMode } from "./features/projects/project-dialog";
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

const pageMeta: Record<"chat" | "projects" | "components" | "files" | "runs" | "monitor" | "community" | "account" | "settings" | "not-found", { eyebrow: string; title: string }> = {
  chat: { eyebrow: "Workspace", title: "New chat" },
  projects: { eyebrow: "Workspace", title: "Projects" },
  components: { eyebrow: "Library", title: "Components" },
  files: { eyebrow: "Library", title: "Files" },
  runs: { eyebrow: "History", title: "Runs" },
  monitor: { eyebrow: "Operate", title: "Monitor" },
  community: { eyebrow: "Discover", title: "Community" },
  account: { eyebrow: "Identity", title: "Account" },
  settings: { eyebrow: "Preferences", title: "Settings" },
  "not-found": { eyebrow: "Workspace", title: "Route not found" },
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
  const { projects, status, setProjectPinned } = useProjectWorkspace();
  const [projectsExpanded, setProjectsExpanded] = React.useState(false);
  const [projectMenuOpen, setProjectMenuOpen] = React.useState(false);
  const [projectDialogMode, setProjectDialogMode] = React.useState<ProjectDialogMode | null>(null);
  if (route.kind === "login") return <LoginPage />;
  if (route.kind === "register") return <RegisterPage />;
  if (route.kind === "forgot-password") return <ForgotPasswordPage />;
  const scopedProjectId = route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run" ? route.projectId : undefined;
  const activeHref = route.kind === "projects" || route.kind === "chat"
    ? desktopRoutePaths.chat
    : route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run"
    ? desktopRoutePaths.projects
    : route.kind === "component" || route.kind === "components" ? desktopRoutePaths.components
      : route.kind === "file" || route.kind === "files" ? desktopRoutePaths.files
        : route.kind === "community-entry" || route.kind === "community-version" ? desktopRoutePaths.community
          : route.kind === "not-found" ? desktopRoutePaths.projects : desktopRoutePaths[route.kind];
  const projectName = scopedProjectId ? projects.find((project) => project.project_id === scopedProjectId)?.name ?? scopedProjectId : undefined;
  const meta = route.kind === "projects" ? pageMeta.chat
    : route.kind === "chat" || route.kind === "components" || route.kind === "files" || route.kind === "runs" || route.kind === "monitor" || route.kind === "community" || route.kind === "account" || route.kind === "settings" || route.kind === "not-found"
    ? pageMeta[route.kind]
    : route.kind === "project" ? { eyebrow: "Project", title: projectName ?? route.projectId }
      : route.kind === "project-agents" ? { eyebrow: "Project", title: projectName ?? "Agents" }
        : route.kind === "factory" ? { eyebrow: "Project", title: projectName ?? "Factory" }
          : route.kind === "agent-detail" ? { eyebrow: "Agent / Project", title: route.agentId ?? "Agent" }
            : route.kind === "agent-version" ? { eyebrow: "Version / Project", title: route.versionId ?? "Agent version" }
              : route.kind === "agent-run" ? { eyebrow: "Run / Project", title: "Agent run" }
                : route.kind === "component" ? { eyebrow: "Library", title: "Component" }
                  : route.kind === "file" ? { eyebrow: "Library", title: "File" }
                    : route.kind === "community-entry" || route.kind === "community-version" ? { eyebrow: "Community", title: "Entry detail" }
                      : { eyebrow: "Design / Project", title: "Studio" };

  const orderedProjects = [...projects].sort((left, right) => {
    if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
    if (left.pinned && right.pinned) return (right.pinned_at ?? "").localeCompare(left.pinned_at ?? "");
    return right.indexed_at.localeCompare(left.indexed_at);
  });
  const visibleProjects = projectsExpanded
    ? orderedProjects
    : [...orderedProjects.filter((project) => project.pinned), ...orderedProjects.filter((project) => !project.pinned).slice(0, 8)];
  const hasProjectOverflow = orderedProjects.filter((project) => !project.pinned).length > 8;
  const projectNavigationItems = visibleProjects.map((project) => ({
    href: projectRoutePaths.project(project.project_id),
    label: project.name,
    icon: FolderKanban,
    active: project.project_id === scopedProjectId,
    trailingAction: <button type="button" aria-label={project.pinned ? t("unpinProject") : t("pinProject")} title={project.pinned ? t("unpinProject") : t("pinProject")} onClick={(event) => { event.preventDefault(); event.stopPropagation(); void setProjectPinned(project.project_id, !project.pinned).catch(() => undefined); }}>{project.pinned ? <PinOff size={15} aria-hidden="true" /> : <Pin size={15} aria-hidden="true" />}</button>,
  }));
  const projectStatus = status === "ready" && projects.length > 0 ? undefined : status === "ready" ? "empty" : status;
  const navigation: NavigationGroup[] = [
    fixedNavigation,
    {
      label: "Projects",
      section: "projects",
      items: projectNavigationItems,
      status: projectStatus,
      action: <>
        <span className="sidebar-project-actions">
          <button className="sidebar-section-button" type="button" onClick={() => setProjectMenuOpen((value) => !value)} aria-label={t("projectActions")} title={t("projectActions")} aria-haspopup="menu" aria-expanded={projectMenuOpen}><MoreHorizontal size={15} aria-hidden="true" /></button>
          {projectMenuOpen ? <div className="sidebar-project-menu" role="menu" aria-label={t("projectActions")}>
            <button type="button" role="menuitem" onClick={() => { setProjectMenuOpen(false); setProjectDialogMode("open"); }}>{t("openExistingProject")}</button>
            {hasProjectOverflow ? <button type="button" role="menuitem" onClick={() => { setProjectMenuOpen(false); setProjectsExpanded((value) => !value); }}>{projectsExpanded ? t("collapseProjects") : t("moreProjects")}</button> : null}
          </div> : null}
        </span>
        <button className="sidebar-section-button" type="button" onClick={() => setProjectDialogMode("create")} aria-label={t("createProjectShortcut")} title={t("createProjectShortcut")}><Plus size={15} aria-hidden="true" /></button>
      </>,
    },
  ];

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: t("agentPlatform"), mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      eyebrow={meta.eyebrow}
      title={meta.title}
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
      {projectDialogMode ? <ProjectDialog mode={projectDialogMode} onClose={() => setProjectDialogMode(null)} /> : null}
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
