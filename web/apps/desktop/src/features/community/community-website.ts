import { parseDesktopRoute, type DesktopRouteLocation } from "@veyra/api-contracts";

export const COMMUNITY_SITE_ENV = "VITE_COMMUNITY_SITE_URL";
export const COMMUNITY_SITE_SETUP = `${COMMUNITY_SITE_ENV}=https://your-community.example`;
export type CommunityWebsiteConfig = { status: "ready"; baseUrl: string } | { status: "missing" | "invalid" };

export function resolveCommunityWebsite(value: string | undefined, development: boolean): CommunityWebsiteConfig {
  const configured = value?.trim();
  if (!configured && !development) return { status: "missing" };
  try {
    const url = new URL(configured || "http://127.0.0.1:5174");
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) return { status: "invalid" };
    return { status: "ready", baseUrl: url.href };
  } catch {
    return { status: "invalid" };
  }
}

export function communityWebsiteConfig(): CommunityWebsiteConfig {
  return resolveCommunityWebsite(import.meta.env.VITE_COMMUNITY_SITE_URL, import.meta.env.DEV);
}

export function isCommunityWebsiteRoute(hash: string): boolean {
  return /^#\/?community(?:\/|\?|$)/.test(hash);
}

export function communityWebsiteHref(config: Extract<CommunityWebsiteConfig, { status: "ready" }>, route: DesktopRouteLocation | string, locale: "zh" | "en"): string {
  const location = typeof route === "string" ? parseDesktopRoute(route) : route;
  let hash = "/community";
  if (location.kind === "community-published") hash += "/published";
  else if (location.kind === "community-starred") hash += "/starred";
  else if (location.kind === "community-mine") hash += "/mine";
  else if ((location.kind === "community-entry" || location.kind === "community-version") && location.owner && location.slug) {
    hash += `/${encodeURIComponent(location.owner)}/${encodeURIComponent(location.slug)}`;
    if (location.kind === "community-version" && location.versionId) hash += `/versions/${encodeURIComponent(location.versionId)}`;
  }
  const url = new URL(config.baseUrl);
  url.searchParams.set("lang", locale);
  url.hash = hash;
  return url.href;
}

type TauriWindow = Window & { __TAURI__?: { core?: { invoke: (command: string, args: Record<string, unknown>) => Promise<unknown> } } };

export async function openCommunityWebsite(href: string): Promise<void> {
  const url = new URL(href);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error("unsafe_community_website");
  const runtime = window as TauriWindow;
  if (runtime.__TAURI__ || "__TAURI_INTERNALS__" in window || window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost") {
    const invoke = runtime.__TAURI__?.core?.invoke;
    if (!invoke) throw new Error("community_browser_bridge_unavailable");
    await invoke("plugin:shell|open", { path: url.href });
    return;
  }
  // noopener intentionally provides no reliable Window return value; null is not proof of a blocked popup.
  window.open(url.href, "_blank", "noopener,noreferrer");
}
