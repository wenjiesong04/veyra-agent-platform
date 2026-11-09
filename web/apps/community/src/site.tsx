import { useEffect, useState } from "react";
import { AuthProvider } from "@veyra/connected-account";
import { ThemeProvider } from "@veyra/ui";
import { CommunityWorkspace } from "./app";
import { ShowcaseApp } from "./showcase";
import { publicCommunityApi, SiteAccountControl } from "./site-auth";

const communityRoots = new Set(["community", "account", "login", "register", "forgot-password"]);

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

export function isCommunitySitePath(path: string): boolean {
  const root = path.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean)[0] ?? "";
  return communityRoots.has(root);
}

function CommunitySiteRoutes() {
  const path = useHashPath();
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("preview") === "studio") url.searchParams.delete("preview");
    if (url.hash.startsWith("#/") && !isCommunitySitePath(path) && !/^docs(?:\/|$)/.test(path)) url.hash = "home";
    if (url.href !== window.location.href) {
      window.history.replaceState(window.history.state, "", url);
    }
  }, [path]);
  const community = isCommunitySitePath(path);
  if (/^(login|register|forgot-password)$/.test(path)) return <ThemeProvider><CommunityWorkspace /></ThemeProvider>;
  const headerAccount = <SiteAccountControl />;
  if (community) return <ShowcaseApp community headerAccount={headerAccount}><CommunityWorkspace /></ShowcaseApp>;
  return <ShowcaseApp documentation={/^docs(?:\/|$)/.test(path)} documentSection={path.split("/")[1]} headerAccount={headerAccount} />;
}

export function CommunitySite() {
  return <AuthProvider api={publicCommunityApi}><CommunitySiteRoutes /></AuthProvider>;
}
