import { History, Languages, Menu, Moon, PanelLeftClose, PanelLeftOpen, ShieldCheck, Sparkles, Sun, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocale } from "./i18n";
import { IconButton } from "./primitives";
import { useTheme } from "./theme";
import type { Brand, NavigationGroup } from "./types";

type ApplicationShellProps = {
  brand: Brand;
  navigation: NavigationGroup[];
  activeHref: string;
  eyebrow: string;
  title: string;
  headerActions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  storageKey?: string;
  onHistoryClick?: () => void;
};

function readCollapsed(storageKey: string): boolean {
  try {
    return window.localStorage.getItem(storageKey) === "true";
  } catch {
    return false;
  }
}

function readMobileViewport(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 960px)").matches;
}

const shellLabelKeys: Record<string, string> = {
  Workspace: "workspace",
  "Agent Platform": "agentPlatform",
  Build: "build",
  Operate: "operate",
  Library: "library",
  Connect: "connect",
  Identity: "identity",
  Explore: "explore",
  "Your space": "yourSpace",
  History: "historyPage",
  Discover: "discover",
  Preferences: "preferences",
  "Create / Project": "createProject",
  Project: "project",
  Agents: "agents",
  "Agent / Project": "agentProject",
  "Version / Project": "versionProject",
  "Run / Project": "runProject",
  "Design / Project": "designProject",
  Studio: "studio",
  Component: "component",
  File: "file",
  "Entry detail": "entryDetail",
  Projects: "projects",
  Runs: "runs",
  Monitor: "monitor",
  Components: "components",
  Files: "files",
  Community: "community",
  Account: "account",
  Settings: "settings",
  Catalog: "catalog",
  "Route not found": "routeNotFound",
  "Version-aware catalog": "versionAwareCatalog",
};

function shellText(value: string, translate: (key: string, fallback?: string) => string): string {
  return translate(shellLabelKeys[value] ?? "", value);
}

export function ApplicationShell({ brand, navigation, activeHref, eyebrow, title, headerActions, children, footer, storageKey = "veyra.sidebar-collapsed.v1", onHistoryClick }: ApplicationShellProps) {
  const { locale, setLanguage, t } = useLocale();
  const { effectiveDark, setTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(() => readCollapsed(storageKey));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mobileViewport, setMobileViewport] = useState(readMobileViewport);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const sidebarCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, String(collapsed));
    } catch {
      // Layout preference is optional and never carries account identity.
    }
  }, [collapsed, storageKey]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 960px)");
    const onChange = (event: MediaQueryListEvent) => {
      setMobileViewport(event.matches);
      if (!event.matches) setMobileOpen(false);
    };
    setMobileViewport(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const openMobile = () => {
    setMobileOpen(true);
    window.requestAnimationFrame(() => sidebarCloseRef.current?.focus());
  };

  const closeMobile = () => {
    setMobileOpen(false);
    window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
  };

  const iconSrc = brand.iconSrc ?? "/veyra-icon.png";
  const languageIsEnglish = locale === "en";
  const localizedEyebrow = shellText(eyebrow, t);
  const localizedTitle = shellText(title, t);

  return (
    <div className={`app-shell ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}>
      <aside id="primary-navigation" className="app-sidebar" aria-label={`${brand.name} navigation`} aria-hidden={mobileViewport && !mobileOpen ? true : undefined} inert={mobileViewport && !mobileOpen ? true : undefined}>
        <div className="sidebar-header">
          <a className="brand" href={navigation[0]?.items[0]?.href ?? "#/"} onClick={() => setMobileOpen(false)}>
            <span className="brand-mark" aria-hidden="true"><img src={iconSrc} alt="" /></span>
            <span className="brand-copy"><strong>{brand.name}</strong><small>{shellText(brand.subtitle, t)}</small></span>
          </a>
          <IconButton
            className="sidebar-toggle"
            icon={collapsed ? PanelLeftOpen : PanelLeftClose}
            label={collapsed ? t("expandSidebar") : t("collapseSidebar")}
            aria-expanded={!collapsed}
            aria-controls="primary-navigation"
            onClick={() => setCollapsed((value) => !value)}
          />
          <IconButton ref={sidebarCloseRef} className="sidebar-close" icon={X} label={t("closeNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={closeMobile} />
        </div>

        <div className="sidebar-context">
          <span className="context-mark" aria-hidden="true"><Sparkles size={16} /><span /></span>
          <span className="context-copy"><small>{t("workspace")}</small><strong>{t("readyToBuild")}</strong><em>{t("localControlSurface")}</em></span>
        </div>

        <nav className="sidebar-nav">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{shellText(group.label, t)}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.href === activeHref;
                const label = shellText(item.label, t);
                return <a className={active ? "active" : ""} href={item.href} aria-label={label} title={label} aria-current={active ? "page" : undefined} key={item.href} onClick={closeMobile}><Icon size={18} aria-hidden="true" /><span>{label}</span></a>;
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <ShieldCheck size={18} aria-hidden="true" />
          <span><strong>{t("localOnly")}</strong><small>{t("noAutomaticExecution")}</small></span>
          {footer}
        </div>
      </aside>

      {mobileOpen ? <button className="sidebar-backdrop" type="button" aria-label="Close navigation" aria-controls="primary-navigation" onClick={closeMobile} /> : null}

      <div className="app-main">
        <header className="app-header">
          <IconButton ref={mobileMenuRef} className="mobile-menu" icon={Menu} label={t("openNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={openMobile} />
          <div className="header-copy"><span className="ui-eyebrow">{localizedEyebrow}</span><h1>{localizedTitle}</h1></div>
          <div className="header-actions">
            {headerActions}
            <button className="header-control history-control" type="button" onClick={onHistoryClick} aria-label={t("history")} title={t("history")}><History size={17} /><span>{t("history")}</span></button>
            <button className="header-control language-control" type="button" onClick={() => setLanguage(languageIsEnglish ? "zh" : "en")} aria-label={languageIsEnglish ? t("switchToChinese") : t("switchToEnglish")} title={languageIsEnglish ? t("switchToChinese") : t("switchToEnglish")}><Languages size={17} /><span>{languageIsEnglish ? "中" : "EN"}</span></button>
            <button className="header-control theme-control" type="button" onClick={() => setTheme(effectiveDark ? "light" : "dark")} aria-label={effectiveDark ? t("switchToLight") : t("switchToDark")} title={effectiveDark ? t("switchToLight") : t("switchToDark")}><span aria-hidden="true">{effectiveDark ? <Sun size={17} /> : <Moon size={17} />}</span><span>{effectiveDark ? t("day") : t("night")}</span></button>
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
