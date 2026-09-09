import type { StudioSource } from "@veyra/api-contracts";

const LIMIT = 80;

export type CanvasHistory = {
  past: StudioSource[];
  future: StudioSource[];
};

export function emptyCanvasHistory(): CanvasHistory {
  return { past: [], future: [] };
}

function sameSource(left: StudioSource, right: StudioSource): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function recordCanvasChange(history: CanvasHistory, previous: StudioSource, next: StudioSource): CanvasHistory {
  if (sameSource(previous, next)) return history;
  return { past: [...history.past, previous].slice(-LIMIT), future: [] };
}

export function undoCanvasChange(history: CanvasHistory, current: StudioSource): { history: CanvasHistory; source: StudioSource } | null {
  const previous = history.past.at(-1);
  if (!previous) return null;
  return {
    history: { past: history.past.slice(0, -1), future: [...history.future, current] },
    source: previous,
  };
}

export function redoCanvasChange(history: CanvasHistory, current: StudioSource): { history: CanvasHistory; source: StudioSource } | null {
  const next = history.future.at(-1);
  if (!next) return null;
  return {
    history: { past: [...history.past, current], future: history.future.slice(0, -1) },
    source: next,
  };
}
