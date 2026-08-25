import * as React from "react";
import { Activity, FolderKanban, Gauge, Globe2, Settings2, UserRound } from "lucide-react";
import { desktopRoutePaths, parseDesktopRoute, projectRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import { ApplicationShell, LinkButton, ThemeProvider } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { AccountPage } from "./pages/account";
import { AgentRunPage } from "./pages/agent-run";
import { AgentDetailPage } from "./pages/agent-detail";
import { AgentVersionPage } from "./pages/agent-version";
import { CommunityPage } from "./pages/community";
import { ComponentsPage } from "./pages/components";
import { FilesPage } from "./pages/files";
import { FactoryPage } from "./pages/factory";
import { MonitorPage } from "./pages/monitor";
import { NotFoundPage } from "./pages/not-found";
import { ProjectDetailPage } from "./pages/project-detail";
import { ProjectsPage } from "./pages/projects";
import { RunsPage } from "./pages/runs";
import { SettingsPage } from "./pages/settings";
import { StudioPage } from "./pages/studio";

const navigation: NavigationGroup[] = [
  {
    label: "Build",
    items: [
      { href: desktopRoutePaths.projects, label: "Projects", icon: FolderKanban },
    ],
  },
  {
    label: "Operate",
    items: [
      { href: desktopRoutePaths.runs, label: "Runs", icon: Activity },
      { href: desktopRoutePaths.monitor, label: "Monitor", icon: Gauge },
    ],
  },
  {
    label: "Library",
    items: [
      { href: desktopRoutePaths.components, label: "Components", icon: FolderKanban },
      { href: desktopRoutePaths.files, label: "Files", icon: FolderKanban },
    ],
  },
  {
    label: "Connect",
    items: [{ href: desktopRoutePaths.community, label: "Community", icon: Globe2 }],
  },
  {
    label: "Identity",
    items: [
      { href: desktopRoutePaths.account, label: "Account", icon: UserRound },
      { href: desktopRoutePaths.settings, label: "Settings", icon: Settings2 },
    ],
  },
];

const pageMeta: Record<"projects" | "components" | "files" | "runs" | "monitor" | "community" | "account" | "settings" | "not-found", { eyebrow: string; title: string }> = {
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
  if (route.kind === "projects") return <ProjectsPage />;
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
  if (route.kind === "not-found" && route.path.startsWith("#/community")) return <NotFoundPage backHref={desktopRoutePaths.community} backLabel="Back to Community" />;
  if (route.kind === "not-found" && route.path.startsWith("#/components")) return <NotFoundPage backHref={desktopRoutePaths.components} backLabel="Back to Components" />;
  if (route.kind === "not-found" && route.path.startsWith("#/files")) return <NotFoundPage backHref={desktopRoutePaths.files} backLabel="Back to Files" />;
  return <NotFoundPage />;
}

function DesktopWorkspace() {
  const route = useHashRoute();
  const scopedProjectId = route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run" ? route.projectId : undefined;
  const activeHref = route.kind === "projects" || route.kind === "project" || route.kind === "project-agents" || route.kind === "agent-detail" || route.kind === "agent-version" || route.kind === "factory" || route.kind === "agent-design" || route.kind === "agent-run"
    ? desktopRoutePaths.projects
    : route.kind === "component" || route.kind === "components" ? desktopRoutePaths.components
      : route.kind === "file" || route.kind === "files" ? desktopRoutePaths.files
        : route.kind === "community-entry" || route.kind === "community-version" ? desktopRoutePaths.community
          : route.kind === "not-found" ? desktopRoutePaths.projects : desktopRoutePaths[route.kind];
  const meta = route.kind === "projects" || route.kind === "components" || route.kind === "files" || route.kind === "runs" || route.kind === "monitor" || route.kind === "community" || route.kind === "account" || route.kind === "settings" || route.kind === "not-found"
    ? pageMeta[route.kind]
    : route.kind === "factory" ? { eyebrow: "Create / Project", title: "Factory" }
      : route.kind === "project" ? { eyebrow: "Project", title: route.projectId }
        : route.kind === "project-agents" ? { eyebrow: "Project", title: "Agents" }
          : route.kind === "agent-detail" ? { eyebrow: "Agent / Project", title: route.agentId ?? "Agent" }
            : route.kind === "agent-version" ? { eyebrow: "Version / Project", title: route.versionId ?? "Agent version" }
        : route.kind === "agent-run" ? { eyebrow: "Run / Project", title: "Agent run" }
          : route.kind === "component" ? { eyebrow: "Library", title: "Component" }
            : route.kind === "file" ? { eyebrow: "Library", title: "File" }
              : route.kind === "community-entry" || route.kind === "community-version" ? { eyebrow: "Community", title: "Entry detail" }
                : { eyebrow: "Design / Project", title: "Studio" };

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: "Agent Platform", mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      eyebrow={meta.eyebrow}
      title={meta.title}
      headerActions={scopedProjectId ? <LinkButton href={projectRoutePaths.factory(scopedProjectId)} variant="primary">Create agent</LinkButton> : undefined}
    >
      <PageContent route={route} />
    </ApplicationShell>
  );
}

export function DesktopApp() {
  return (
    <ThemeProvider>
      <DesktopWorkspace />
    </ThemeProvider>
  );
}
