import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import type { ThemeChoice } from "./types";

type ThemeContextValue = {
  theme: ThemeChoice;
  setTheme: (theme: ThemeChoice) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);
const defaultStorageKey = "veyra.ui.theme";

function readTheme(storageKey: string): ThemeChoice {
  try {
    const value = window.localStorage.getItem(storageKey);
    return value === "light" || value === "dark" || value === "system" ? value : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children, storageKey = defaultStorageKey }: PropsWithChildren<{ storageKey?: string }>) {
  const [theme, setTheme] = useState<ThemeChoice>(() => readTheme(storageKey));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(storageKey, theme);
    } catch {
      // Theme is a convenience preference; the app remains usable without storage.
    }
  }, [storageKey, theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
