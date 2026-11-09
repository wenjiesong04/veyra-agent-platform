import { useEffect, useState } from "react";
import { LinkButton, ThemeProvider, useLocale } from "@veyra/ui";
import { AuthProvider, ConnectedAccountPage, ForgotPasswordPage, LoginPage, RegisterPage, useAuth, type CommunitySection } from "@veyra/connected-account";
import { CatalogPage } from "./pages/catalog";
import { EntryDetailPage } from "./pages/detail";
import { CommunityNotFoundPage } from "./pages/not-found";
import { CommunitySiteLayout } from "./community-layout";
import { publicCommunityApi } from "./site-auth";
import { MyCommunityPage } from "./pages/mine";

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
  | { kind: "catalog"; section: CommunitySection }
  | { kind: "account" | "login" | "register" | "forgot-password" | "not-found" }
  | { kind: "entry"; owner: string; slug: string; versionId?: string };

function parseCommunityRoute(path: string): CommunityLocation {
  let parts: string[];
  try {
    parts = path.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return { kind: "not-found" };
  }
  if (!parts.length || (parts.length === 1 && parts[0] === "community")) return { kind: "catalog", section: "discover" };
  if (parts.length === 1 && parts[0] === "account") return { kind: "catalog", section: "mine" };
  if (parts.length === 1 && ["login", "register", "forgot-password"].includes(parts[0]!)) return { kind: parts[0] as "login" | "register" | "forgot-password" };
  if (parts.length === 3 && parts[0] === "community" && parts[1] === "mine" && parts[2] === "settings") return { kind: "account" };
  if (parts.length === 2 && parts[0] === "community" && ["published", "starred", "mine"].includes(parts[1]!)) return { kind: "catalog", section: parts[1] as CommunitySection };
  if (parts.length === 3 && parts[0] === "community" && parts[1] && parts[2]) return { kind: "entry", owner: parts[1], slug: parts[2] };
  if (parts.length === 5 && parts[0] === "community" && parts[1] && parts[2] && parts[3] === "versions" && parts[4]) return { kind: "entry", owner: parts[1], slug: parts[2], versionId: parts[4] };
  return { kind: "not-found" };
}

export function CommunityWorkspace() {
  const { locale } = useLocale();
  const { account } = useAuth();
  const path = useHashPath();
  const location = parseCommunityRoute(path);
  if (location.kind === "login") return <LoginPage />;
  if (location.kind === "register") return <RegisterPage />;
  if (location.kind === "forgot-password") return <ForgotPasswordPage />;

  const section = location.kind === "catalog" ? location.section : location.kind === "account" ? "mine" : "discover";
  const content = location.kind === "account"
    ? <div className="community-page-stack"><LinkButton href="#/community/mine" variant="ghost">{locale === "zh" ? "返回我的" : "Back to Mine"}</LinkButton><ConnectedAccountPage key={account?.id ?? "anonymous"} /></div>
    : location.kind === "entry"
      ? <EntryDetailPage key={`${location.owner}/${location.slug}/${location.versionId ?? "latest"}`} owner={location.owner} slug={location.slug} versionId={location.versionId} />
      : location.kind === "not-found"
        ? <CommunityNotFoundPage />
        : section === "mine" ? <MyCommunityPage key={account?.id ?? "anonymous"} /> : <CatalogPage key={`${account?.id ?? "anonymous"}:${section}`} section={section} />;
  return <CommunitySiteLayout section={section} locationKey={path}>{content}</CommunitySiteLayout>;
}

export function CommunityApp({ embedded = false }: { embedded?: boolean }) {
  const content = <AuthProvider api={publicCommunityApi}><CommunityWorkspace /></AuthProvider>;
  return embedded ? content : <ThemeProvider>{content}</ThemeProvider>;
}
