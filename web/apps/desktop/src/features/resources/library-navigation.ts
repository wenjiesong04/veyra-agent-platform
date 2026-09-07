import { Box, Braces, FileCode2, ShieldCheck, Sparkles } from "lucide-react";
import { desktopRoutePaths, type DesktopRouteLocation } from "@veyra/api-contracts";
import type { NavigationItem } from "@veyra/ui";

export type ResourceLibraryTab = "component" | "tooling" | "skill" | "policy" | "template";

export const resourceLibraryTabPaths: Record<ResourceLibraryTab, string> = {
  component: desktopRoutePaths.components,
  tooling: `${desktopRoutePaths.components}?tab=tooling`,
  skill: `${desktopRoutePaths.components}?tab=skill`,
  policy: `${desktopRoutePaths.components}?tab=policy`,
  template: `${desktopRoutePaths.components}?tab=template`,
};

const catalogItems: Array<{ tab: ResourceLibraryTab; label: string; icon: typeof Box; resourceKind: "component" | "tooling" | "skill" | "policy" | "template" }> = [
  { tab: "component", label: "Components", icon: Box, resourceKind: "component" },
  { tab: "tooling", label: "Tools / MCP", icon: Braces, resourceKind: "tooling" },
  { tab: "skill", label: "Skills", icon: Sparkles, resourceKind: "skill" },
  { tab: "policy", label: "Policies", icon: ShieldCheck, resourceKind: "policy" },
  { tab: "template", label: "Templates", icon: FileCode2, resourceKind: "template" },
];

export function resourceLibraryTabFromHash(hash: string): ResourceLibraryTab {
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const tab = new URLSearchParams(query).get("tab");
  if (tab === "tooling" || tab === "skill" || tab === "policy" || tab === "template" || tab === "component") return tab;
  return "component";
}

export function resourceLibraryChildren(route: DesktopRouteLocation, hash: string): NavigationItem[] | undefined {
  if (route.kind !== "components" && route.kind !== "component") return undefined;
  const tab = route.kind === "component" ? "component" : resourceLibraryTabFromHash(hash);
  return catalogItems.map((item) => ({
    href: resourceLibraryTabPaths[item.tab],
    label: item.label,
    icon: item.icon,
    tone: "catalog",
    resourceKind: item.resourceKind,
    active: route.kind === "components" && tab === item.tab,
    contextual: route.kind === "component" && item.tab === "component",
  }));
}
