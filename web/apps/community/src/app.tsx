import { Compass, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { communityRoutePaths } from "@veyra/api-contracts";
import { ApplicationShell, LinkButton, ThemeProvider, useLocale, type NavigationGroup } from "@veyra/ui";
import { CatalogPage } from "./pages/catalog";
import { CommunityAccountPage } from "./pages/account";
import { EntryDetailPage } from "./pages/detail";
import { CommunityNotFoundPage } from "./pages/not-found";

const navigation: NavigationGroup[] = [
  { label: "Explore", items: [{ href: communityRoutePaths.catalog, label: "Catalog", icon: Compass }] },
  { label: "Your space", items: [{ href: "#/account", label: "Account", icon: UserRound }] },
];

function pathFromHash(): string {
  return window.location.hash.replace(/^#\/?/, "").split("?")[0] ?? "";
}

function useHashPath(): string {
  const [path, setPath] = useState(pathFromHash);
  useEffect(() => {
    const onHashChange = () => setPath(pathFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return path;
}

type CommunityLocation =
  | { kind: "catalog" }
  | { kind: "account" }
  | { kind: "entry"; owner: string; slug: string; versionId?: string }
  | { kind: "not-found" };

function parseCommunityRoute(path: string): CommunityLocation {
  const normalized = path.replace(/^#\/?/, "").replace(/^\/+|\/+$/g, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0 || (parts.length === 1 && parts[0] === "community")) return { kind: "catalog" };
  if (parts.length === 1 && parts[0] === "account") return { kind: "account" };
  if (parts.length === 3 && parts[0] === "community" && parts[1] && parts[2]) return { kind: "entry", owner: parts[1], slug: parts[2] };
  if (parts.length === 5 && parts[0] === "community" && parts[1] && parts[2] && parts[3] === "versions" && parts[4]) return { kind: "entry", owner: parts[1], slug: parts[2], versionId: parts[4] };
  return { kind: "not-found" };
}

function CommunityWorkspace() {
  const { locale } = useLocale();
  const location = parseCommunityRoute(useHashPath());
  const title = location.kind === "account" ? "Account" : location.kind === "entry" ? "Entry detail" : location.kind === "not-found" ? "Route not found" : "Community";
  const activeHref = location.kind === "account" ? "#/account" : communityRoutePaths.catalog;
  const browseLabel = locale === "zh" ? "浏览目录" : "Browse catalog";

  const content = location.kind === "account" ? <CommunityAccountPage /> : location.kind === "entry" ? <EntryDetailPage owner={location.owner} slug={location.slug} versionId={location.versionId} /> : location.kind === "not-found" ? <CommunityNotFoundPage /> : <CatalogPage />;
  return <ApplicationShell brand={{ name: "Veyra", subtitle: "Community", mark: "V" }} navigation={navigation} activeHref={activeHref} eyebrow="Version-aware catalog" title={title} headerActions={<LinkButton href={communityRoutePaths.catalog} icon={Compass} variant="primary">{browseLabel}</LinkButton>}><div className="community-content">{content}</div></ApplicationShell>;
}

export function CommunityApp() {
  return <ThemeProvider><CommunityWorkspace /></ThemeProvider>;
}
