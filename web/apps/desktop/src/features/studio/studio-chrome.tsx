import * as React from "react";
import { clampPaneSize } from "@veyra/ui";

export const STUDIO_CHROME_STORAGE_KEY = "veyra.studio-rails.v1";
export const STUDIO_COMPACT_MEDIA = "(max-width: 960px)";

export const STUDIO_PANE_LIMITS = {
  paletteWidth: { min: 180, max: 420, default: 228 },
  inspectorWidth: { min: 220, max: 480, default: 300 },
  runHeight: { min: 120, max: 420, default: 0 },
} as const;

export type StudioChromeState = {
  paletteCollapsed: boolean;
  inspectorCollapsed: boolean;
  runCollapsed: boolean;
  paletteWidth: number;
  inspectorWidth: number;
  runHeight: number;
};

const defaults: StudioChromeState = {
  paletteCollapsed: false,
  inspectorCollapsed: false,
  runCollapsed: true,
  paletteWidth: STUDIO_PANE_LIMITS.paletteWidth.default,
  inspectorWidth: STUDIO_PANE_LIMITS.inspectorWidth.default,
  runHeight: STUDIO_PANE_LIMITS.runHeight.default,
};

export type StudioPaneName = keyof typeof STUDIO_PANE_LIMITS;

type StudioStageStyle = React.CSSProperties & Partial<Record<"--studio-rail-width" | "--studio-inspector-width" | "--studio-run-height", string>>;

export function clampStudioPane(pane: StudioPaneName, value: number, viewportHeight = typeof window === "undefined" ? 800 : window.innerHeight): number {
  const limits = STUDIO_PANE_LIMITS[pane];
  const max = pane === "runHeight" ? Math.min(limits.max, Math.round(viewportHeight * 0.5)) : limits.max;
  return clampPaneSize(value, limits.min, max);
}

export function fluidRunHeight(viewportHeight = typeof window === "undefined" ? 800 : window.innerHeight): number {
  return clampStudioPane("runHeight", Math.round(viewportHeight * 0.28), viewportHeight);
}

export function isStudioCompact(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(STUDIO_COMPACT_MEDIA).matches;
}

export function exclusiveStudioPatch(patch: Partial<StudioChromeState>, compact = isStudioCompact()): Partial<StudioChromeState> {
  if (!compact) return patch;
  if (patch.inspectorCollapsed === false) return { ...patch, paletteCollapsed: true, runCollapsed: true };
  if (patch.paletteCollapsed === false) return { ...patch, inspectorCollapsed: true, runCollapsed: true };
  if (patch.runCollapsed === false) return { ...patch, inspectorCollapsed: true, paletteCollapsed: true };
  return patch;
}

export function crowdCompactStudioChrome(state: StudioChromeState, compact = isStudioCompact()): StudioChromeState {
  if (!compact || state.paletteCollapsed || state.inspectorCollapsed) return state;
  return { ...state, paletteCollapsed: true, inspectorCollapsed: true, runCollapsed: true };
}

export function readStudioChrome(): StudioChromeState {
  try {
    const raw = window.localStorage.getItem(STUDIO_CHROME_STORAGE_KEY);
    if (!raw) return crowdCompactStudioChrome({ ...defaults });
    const parsed = JSON.parse(raw) as Partial<Record<string, unknown>>;
    return crowdCompactStudioChrome({
      ...defaults,
      paletteCollapsed: parsed.paletteCollapsed === true,
      inspectorCollapsed: parsed.inspectorCollapsed === true,
      runCollapsed: typeof parsed.runCollapsed === "boolean" ? parsed.runCollapsed : defaults.runCollapsed,
    });
  } catch {
    return crowdCompactStudioChrome({ ...defaults });
  }
}

export function studioStageStyle(chrome: StudioChromeState, compact = false): StudioStageStyle {
  return {
    ...(compact ? {} : {
      "--studio-rail-width": `${chrome.paletteWidth}px`,
      "--studio-inspector-width": `${chrome.inspectorWidth}px`,
    }),
    ...(chrome.runHeight > 0 ? { "--studio-run-height": `${chrome.runHeight}px` } : {}),
  } as StudioStageStyle;
}

type StudioChromeContextValue = {
  chrome: StudioChromeState;
  compact: boolean;
  setChrome: (patch: Partial<StudioChromeState>) => void;
};

const StudioChromeContext = React.createContext<StudioChromeContextValue | null>(null);

function useStudioChromeState(inactive = false): StudioChromeContextValue {
  const [chrome, setState] = React.useState(readStudioChrome);
  const [compact, setCompact] = React.useState(isStudioCompact);
  React.useEffect(() => {
    if (inactive || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(STUDIO_COMPACT_MEDIA);
    const sync = () => {
      const nextCompact = media.matches;
      setCompact(nextCompact);
      setState((current) => crowdCompactStudioChrome(current, nextCompact));
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, [inactive]);
  React.useEffect(() => {
    if (inactive) return;
    try {
      window.localStorage.setItem(STUDIO_CHROME_STORAGE_KEY, JSON.stringify({
        paletteCollapsed: chrome.paletteCollapsed,
        inspectorCollapsed: chrome.inspectorCollapsed,
        runCollapsed: chrome.runCollapsed,
      }));
    } catch {
      // Layout chrome only; never account identity.
    }
  }, [chrome, inactive]);
  const setChrome = React.useCallback((patch: Partial<StudioChromeState>) => {
    setState((current) => {
      const next = { ...current, ...exclusiveStudioPatch(patch, isStudioCompact()) };
      return {
        ...next,
        paletteWidth: clampStudioPane("paletteWidth", next.paletteWidth),
        inspectorWidth: clampStudioPane("inspectorWidth", next.inspectorWidth),
        runHeight: next.runHeight <= 0 ? 0 : clampStudioPane("runHeight", next.runHeight),
      };
    });
  }, []);
  return { chrome, compact, setChrome };
}

export function StudioChromeProvider({ children }: { children: React.ReactNode }) {
  const value = useStudioChromeState();
  return <StudioChromeContext.Provider value={value}>{children}</StudioChromeContext.Provider>;
}

export function useStudioChrome(): StudioChromeContextValue {
  const ctx = React.useContext(StudioChromeContext);
  const owned = useStudioChromeState(ctx !== null);
  return ctx ?? owned;
}
