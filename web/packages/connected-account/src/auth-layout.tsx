import { Languages, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { brandIconUrl, useLocale, useTheme } from "@veyra/ui";

export function AuthLayout({ children }: { children: ReactNode }) {
  const { locale, setLanguage, t } = useLocale();
  const { effectiveDark, setTheme } = useTheme();
  const english = locale === "en";

  return (
    <div className="auth-shell">
      <header className="auth-header">
        <a className="auth-brand" href="#/community" aria-label="Veyra">
          <img src={brandIconUrl} alt="" />
          <span><strong>Veyra</strong><small>Agent Platform</small></span>
        </a>
        <div className="auth-preferences">
          <button
            className="header-control language-control"
            type="button"
            onClick={() => setLanguage(english ? "zh" : "en")}
            aria-label={english ? t("switchToChinese") : t("switchToEnglish")}
            title={english ? t("switchToChinese") : t("switchToEnglish")}
          >
            <Languages size={17} aria-hidden="true" />
            <span>{english ? "中" : "EN"}</span>
          </button>
          <button
            className="header-control theme-control"
            type="button"
            onClick={() => setTheme(effectiveDark ? "light" : "dark")}
            aria-label={effectiveDark ? t("switchToLight") : t("switchToDark")}
            title={effectiveDark ? t("switchToLight") : t("switchToDark")}
          >
            {effectiveDark ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
            <span>{effectiveDark ? t("day") : t("night")}</span>
          </button>
        </div>
      </header>
      <main className="auth-main">{children}</main>
    </div>
  );
}
