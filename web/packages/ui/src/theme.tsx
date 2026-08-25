import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { LocaleProvider } from "./i18n";
import type { ThemeChoice } from "./types";

type ThemeContextValue = {
  theme: ThemeChoice;
  setTheme: (theme: ThemeChoice) => void;
  effectiveDark: boolean;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);
const defaultStorageKey = "veyra.theme";

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
  const [systemDark, setSystemDark] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    setSystemDark(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(storageKey, theme);
    } catch {
      // Theme is a convenience preference; the app remains usable without storage.
    }
  }, [storageKey, theme]);

  const effectiveDark = theme === "dark" || (theme === "system" && systemDark);
  const value = useMemo(() => ({ theme, setTheme, effectiveDark }), [effectiveDark, theme]);
  return <LocaleProvider><ThemeContext.Provider value={value}>{children}</ThemeContext.Provider></LocaleProvider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
