import { Compass } from "lucide-react";
import { useEffect, useState } from "react";
import { communityAuthRoutePaths, communityRoutePaths } from "@veyra/api-contracts";
import { ApplicationShell, LinkButton, ThemeProvider, useLocale, type NavigationGroup } from "@veyra/ui";
import { accountInitials, AuthProvider, ConnectedAccountPage, createCommunityApi, ForgotPasswordPage, LoginPage, RegisterPage, useAuth } from "@veyra/connected-account";
import { CatalogPage } from "./pages/catalog";
import { EntryDetailPage } from "./pages/detail";
import { CommunityNotFoundPage } from "./pages/not-found";

const communityApi = createCommunityApi({ baseUrl: "/api/v1" });

const navigation: NavigationGroup[] = [
  { label: "Explore", items: [{ href: communityRoutePaths.catalog, label: "Catalog", icon: Compass }] },
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
  | { kind: "login" }
  | { kind: "register" }
  | { kind: "forgot-password" }
  | { kind: "entry"; owner: string; slug: string; versionId?: string }
  | { kind: "not-found" };

function parseCommunityRoute(path: string): CommunityLocation {
  const normalized = path.replace(/^#\/?/, "").replace(/^\/+|\/+$/g, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0 || (parts.length === 1 && parts[0] === "community")) return { kind: "catalog" };
  if (parts.length === 1 && parts[0] === "account") return { kind: "account" };
  if (parts.length === 1 && parts[0] === "login") return { kind: "login" };
  if (parts.length === 1 && parts[0] === "register") return { kind: "register" };
  if (parts.length === 1 && parts[0] === "forgot-password") return { kind: "forgot-password" };
  if (parts.length === 3 && parts[0] === "community" && parts[1] && parts[2]) return { kind: "entry", owner: parts[1], slug: parts[2] };
  if (parts.length === 5 && parts[0] === "community" && parts[1] && parts[2] && parts[3] === "versions" && parts[4]) return { kind: "entry", owner: parts[1], slug: parts[2], versionId: parts[4] };
  return { kind: "not-found" };
}

function CommunityWorkspace() {
  const { locale } = useLocale();
  const { account, logout } = useAuth();
  const location = parseCommunityRoute(useHashPath());
  const zh = locale === "zh";

  if (location.kind === "login") return <LoginPage />;
  if (location.kind === "register") return <RegisterPage />;
  if (location.kind === "forgot-password") return <ForgotPasswordPage />;

  const title = location.kind === "account" ? "Account" : location.kind === "entry" ? "Entry detail" : location.kind === "not-found" ? "Route not found" : "Community";
  const activeHref = location.kind === "account" ? communityAuthRoutePaths.account : communityRoutePaths.catalog;
  const browseLabel = zh ? "浏览目录" : "Browse catalog";
  const content = location.kind === "account"
    ? <ConnectedAccountPage />
    : location.kind === "entry"
      ? <EntryDetailPage owner={location.owner} slug={location.slug} versionId={location.versionId} />
      : location.kind === "not-found"
        ? <CommunityNotFoundPage />
        : <CatalogPage />;

  return (
    <ApplicationShell
      brand={{ name: "Veyra", subtitle: "Community", mark: "V" }}
      navigation={navigation}
      activeHref={activeHref}
      eyebrow="Version-aware catalog"
      title={title}
      account={account ? {
        displayName: account.display_name || account.handle,
        detail: account.email,
        initials: accountInitials(account.display_name, account.handle),
        avatarUrl: account.avatar_url,
        authenticated: true,
        accountHref: communityAuthRoutePaths.account,
        onSignOut: () => {
          void logout().catch(() => {
            window.location.hash = communityAuthRoutePaths.account;
          });
        },
      } : {
        displayName: zh ? "本机工作区" : "Local workspace",
        detail: zh ? "未连接账号" : "Not signed in",
        initials: zh ? "本" : "LW",
        authenticated: false,
        accountHref: communityAuthRoutePaths.account,
      }}
      headerActions={<LinkButton href={communityRoutePaths.catalog} icon={Compass} variant="primary">{browseLabel}</LinkButton>}
    >
      <div className="community-content">{content}</div>
    </ApplicationShell>
  );
}

export function CommunityApp() {
  return <ThemeProvider><AuthProvider api={communityApi}><CommunityWorkspace /></AuthProvider></ThemeProvider>;
}
