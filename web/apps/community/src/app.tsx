import { BookOpen, Compass, Heart, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { ApplicationShell, LinkButton, ThemeProvider, type NavigationGroup } from "@veyra/ui";
import { CatalogPage } from "./pages/catalog";
import { CommunityAccountPage } from "./pages/account";
import { EntryDetailPage } from "./pages/detail";

const navigation: NavigationGroup[] = [
  { label: "Explore", items: [{ href: "#/", label: "Catalog", icon: Compass }, { href: "#/collections", label: "Collections", icon: BookOpen }] },
  { label: "Your space", items: [{ href: "#/saved", label: "Saved", icon: Heart }, { href: "#/account", label: "Account", icon: UserRound }] },
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

function CommunityWorkspace() {
  const path = useHashPath();
  const parts = path.split("/").filter(Boolean);
  const isAccount = parts[0] === "account";
  const isDetail = parts[0] === "entry" && Boolean(parts[1]);
  const title = isAccount ? "Account" : isDetail ? "Entry detail" : "Community";
  const activeHref = isAccount ? "#/account" : isDetail ? "#/" : parts[0] === "collections" ? "#/collections" : "#/";

  return <ApplicationShell brand={{ name: "Veyra", subtitle: "Community", mark: "V" }} navigation={navigation} activeHref={activeHref} eyebrow="Version-aware catalog" title={title} headerActions={<LinkButton href="#/" icon={Compass} variant="primary">Browse catalog</LinkButton>}><div className="community-content">{isAccount ? <CommunityAccountPage /> : isDetail ? <EntryDetailPage entryId={parts[1] ?? ""} /> : <CatalogPage collection={parts[0] === "collections" ? "collections" : "all"} />}</div></ApplicationShell>;
}

export function CommunityApp() {
  return <ThemeProvider><CommunityWorkspace /></ThemeProvider>;
}
