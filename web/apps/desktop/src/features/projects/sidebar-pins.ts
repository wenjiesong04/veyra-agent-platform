/** Sidebar pin order for Workflows and Knowledge is a layout preference. */

export const SIDEBAR_RESOURCE_PINS_KEY = "veyra.sidebar-resource-pins";

export type SidebarResourceKind = "workflow" | "knowledge";

export type ProjectResourcePins = {
  workflow?: string;
  knowledge?: string;
};

export type SidebarResourcePins = Record<string, ProjectResourcePins>;

export function readSidebarResourcePins(): SidebarResourcePins {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_RESOURCE_PINS_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const pins: SidebarResourcePins = {};
    for (const [projectId, value] of Object.entries(parsed)) {
      if (!projectId || !value || typeof value !== "object" || Array.isArray(value)) continue;
      const record = value as Record<string, unknown>;
      const next: ProjectResourcePins = {};
      if (typeof record.workflow === "string" && record.workflow) next.workflow = record.workflow;
      if (typeof record.knowledge === "string" && record.knowledge) next.knowledge = record.knowledge;
      if (next.workflow || next.knowledge) pins[projectId] = next;
    }
    return pins;
  } catch {
    return {};
  }
}

export function writeSidebarResourcePins(pins: SidebarResourcePins): void {
  try {
    window.localStorage.setItem(SIDEBAR_RESOURCE_PINS_KEY, JSON.stringify(pins));
  } catch {
    /* Layout preferences are best-effort. */
  }
}

export function toggleSidebarResourcePin(
  pins: SidebarResourcePins,
  projectId: string,
  kind: SidebarResourceKind,
  id: string,
): SidebarResourcePins {
  const current = pins[projectId] ?? {};
  const nextValue = current[kind] === id ? undefined : id;
  const nextProject: ProjectResourcePins = { ...current, [kind]: nextValue };
  if (!nextProject.workflow && !nextProject.knowledge) {
    const { [projectId]: _removed, ...rest } = pins;
    return rest;
  }
  return { ...pins, [projectId]: nextProject };
}

export function sortPinnedFirst<T>(
  items: readonly T[],
  pinnedId: string | undefined,
  idOf: (item: T) => string,
): T[] {
  if (!pinnedId) return [...items];
  return [...items].sort((left, right) => {
    const leftPinned = idOf(left) === pinnedId;
    const rightPinned = idOf(right) === pinnedId;
    if (leftPinned === rightPinned) return 0;
    return leftPinned ? -1 : 1;
  });
}
