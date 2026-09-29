import { useEffect, useState } from "react";
import { CommunityApp } from "./app";
import { ShowcaseApp } from "./showcase";

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

export function CommunitySite() {
  const path = useHashPath();
  if (isCommunitySitePath(path)) return <CommunityApp />;
  return <ShowcaseApp />;
}
