import * as React from "react";

export const STUDIO_CHROME_STORAGE_KEY = "veyra.studio-rails.v1";

export type StudioChromeState = {
  paletteCollapsed: boolean;
  inspectorCollapsed: boolean;
  runCollapsed: boolean;
};

const defaults: StudioChromeState = {
  paletteCollapsed: false,
  inspectorCollapsed: false,
  runCollapsed: false,
};

export function readStudioChrome(): StudioChromeState {
  try {
    const raw = window.localStorage.getItem(STUDIO_CHROME_STORAGE_KEY);
    if (!raw) return { ...defaults };
    const parsed = JSON.parse(raw) as Partial<Record<string, unknown>>;
    return {
      paletteCollapsed: parsed.paletteCollapsed === true,
      inspectorCollapsed: parsed.inspectorCollapsed === true,
      runCollapsed: parsed.runCollapsed === true,
    };
  } catch {
    return { ...defaults };
  }
}

type StudioChromeContextValue = {
  chrome: StudioChromeState;
  setChrome: (patch: Partial<StudioChromeState>) => void;
};

const StudioChromeContext = React.createContext<StudioChromeContextValue | null>(null);

function useStudioChromeState(inactive = false): StudioChromeContextValue {
  const [chrome, setState] = React.useState(readStudioChrome);
  React.useEffect(() => {
    if (inactive) return;
    try {
      window.localStorage.setItem(STUDIO_CHROME_STORAGE_KEY, JSON.stringify(chrome));
    } catch {
      // Layout chrome only; never account identity.
    }
  }, [chrome, inactive]);
  const setChrome = React.useCallback((patch: Partial<StudioChromeState>) => {
    setState((current) => ({ ...current, ...patch }));
  }, []);
  return { chrome, setChrome };
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
