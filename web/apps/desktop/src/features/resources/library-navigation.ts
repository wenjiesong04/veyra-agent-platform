import { desktopRoutePaths, projectRoutePaths } from "@veyra/api-contracts";

export type ResourceLibraryTab = "all" | "component" | "tooling" | "skill" | "policy" | "template";

const lastProjectStorageKey = "veyra.last-project-id";

export function rememberProjectId(projectId: string): void {
  try {
    window.localStorage.setItem(lastProjectStorageKey, projectId);
  } catch {
    /* Last Project is a convenience for Resource Library chrome. */
  }
}

export function resourceLibraryHref(projects: Array<{ project_id: string }>): string {
  let lastId: string | null = null;
  try {
    lastId = window.localStorage.getItem(lastProjectStorageKey);
  } catch {
    lastId = null;
  }
  const last = lastId ? projects.find((project) => project.project_id === lastId) : undefined;
  const target = last ?? projects[0];
  return target ? projectRoutePaths.project(target.project_id) : desktopRoutePaths.components;
}

export function resourceLibraryCatalogHref(tab: ResourceLibraryTab, catalogHref: string = desktopRoutePaths.components): string {
  const base = catalogHref.split("?")[0] || catalogHref;
  return tab === "all" ? base : `${base}?tab=${tab}`;
}

export const resourceLibraryTabPaths: Record<ResourceLibraryTab, string> = {
  all: resourceLibraryCatalogHref("all"),
  component: resourceLibraryCatalogHref("component"),
  tooling: resourceLibraryCatalogHref("tooling"),
  skill: resourceLibraryCatalogHref("skill"),
  policy: resourceLibraryCatalogHref("policy"),
  template: resourceLibraryCatalogHref("template"),
};

export function resourceLibraryTabFromHash(hash: string): ResourceLibraryTab {
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const tab = new URLSearchParams(query).get("tab");
  if (tab === "tooling" || tab === "skill" || tab === "policy" || tab === "template" || tab === "component") return tab;
  return "all";
}
