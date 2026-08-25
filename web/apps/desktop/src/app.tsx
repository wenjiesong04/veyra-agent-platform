import * as React from "react";
import { Activity, Bot, FolderKanban, Gauge, Globe2, Settings2, UserRound, Wrench } from "lucide-react";
import { desktopRoutePaths, type DesktopRoute } from "@veyra/api-contracts";
import { ApplicationShell, LinkButton, ThemeProvider } from "@veyra/ui";
import type { NavigationGroup } from "@veyra/ui";
import { AccountPage } from "./pages/account";
import { CommunityPage } from "./pages/community";
import { FactoryPage } from "./pages/factory";
import { MonitorPage } from "./pages/monitor";
import { NotFoundPage } from "./pages/not-found";
import { ProjectsPage } from "./pages/projects";
import { RunsPage } from "./pages/runs";
import { SettingsPage } from "./pages/settings";
import { StudioPage } from "./pages/studio";

const navigation: NavigationGroup[] = [
  {
    label: "Build",
    items: [
      { href: desktopRoutePaths.projects, label: "Projects", icon: FolderKanban },
      { href: desktopRoutePaths.factory, label: "Factory", icon: Bot },
      { href: desktopRoutePaths.studio, label: "Studio", icon: Wrench },
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

const pageMeta: Record<DesktopRoute, { eyebrow: string; title: string }> = {
  projects: { eyebrow: "Workspace", title: "Projects" },
  factory: { eyebrow: "Create", title: "Factory" },
  studio: { eyebrow: "Design", title: "Studio" },
  runs: { eyebrow: "History", title: "Runs" },
  monitor: { eyebrow: "Operate", title: "Monitor" },
  community: { eyebrow: "Discover", title: "Community" },
  account: { eyebrow: "Identity", title: "Account" },
  settings: { eyebrow: "Preferences", title: "Settings" },
};

function pathFromHash(): string {
  return window.location.hash.replace(/^#\/?/, "").split("?")[0] ?? "";
}

function routeFromPath(path: string): DesktopRoute | null {
  const first = path.split("/").filter(Boolean)[0] as DesktopRoute | undefined;
  return first && first in pageMeta ? first : null;
}

function useHashPath(): string {
  const [path, setPath] = React.useState(pathFromHash);

  React.useEffect(() => {
    const onHashChange = () => setPath(pathFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return path;
}

function PageContent({ route, path }: { route: DesktopRoute | null; path: string }) {
  if (route === "projects") return <ProjectsPage />;
  if (route === "factory") return <FactoryPage />;
  if (route === "studio") return <StudioPage agentId={path.split("/")[1]} />;
  if (route === "runs") return <RunsPage runId={path.split("/")[1]} />;
  if (route === "monitor") return <MonitorPage />;
  if (route === "community") return <CommunityPage />;
  if (route === "account") return <AccountPage />;
  if (route === "settings") return <SettingsPage />;
  return <NotFoundPage />;
}

function DesktopWorkspace() {
  const path = useHashPath();
  const route = routeFromPath(path) ?? "projects";
  const activeHref = desktopRoutePaths[route];
  const meta = pageMeta[route];

  React.useEffect(() => {
    if (routeFromPath(path)) return;
    window.location.hash = desktopRoutePaths.projects;
  }, [path]);

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: "Agent Platform", mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      eyebrow={meta.eyebrow}
      title={meta.title}
      headerActions={<LinkButton href={desktopRoutePaths.factory} icon={Bot} variant="primary">Create agent</LinkButton>}
    >
      <PageContent route={route} path={path} />
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
