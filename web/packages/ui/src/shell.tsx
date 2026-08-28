import { ArrowLeft, History, Languages, LogIn, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Settings2, Sun, UserRound, X, type LucideIcon } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useLocale } from "./i18n";
import { IconButton } from "./primitives";
import { useTheme } from "./theme";
import type { AccountMenuConfig, Brand, NavigationGroup } from "./types";

type ApplicationShellProps = {
  brand: Brand;
  navigation: NavigationGroup[];
  activeHref: string;
  eyebrow?: string;
  title: string;
  breadcrumbs?: { label: string; href?: string; icon?: LucideIcon }[];
  backHref?: string;
  headerActions?: ReactNode;
  children: ReactNode;
  account?: AccountMenuConfig;
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

function initialsFromName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "V";
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0]![0] ?? ""}${parts[1]![0] ?? ""}`.toUpperCase();
  return trimmed.slice(0, 2).toUpperCase();
}

const shellLabelKeys: Record<string, string> = {
  Workspace: "workspace",
  "Agent Platform": "agentPlatform",
  Features: "features",
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
  Pinned: "pinned",
  Home: "home",
  Agent: "agent",
  Factory: "factory",
  Version: "version",
  Run: "run",
  "New chat": "newChat",
  "Run workspace": "runWorkspace",
  "Resource library": "resourceLibrary",
  "Knowledge base": "knowledgeBase",
  Recent: "recent",
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

function navigationStatusText(group: NavigationGroup, translate: (key: string, fallback?: string) => string): string {
  if (group.statusText) return group.statusText;
  if (group.status === "loading") return translate("loadingProjects");
  if (group.status === "error") return translate("projectsUnavailable");
  return group.label === "Recent" ? translate("noRecentProjects") : translate("noProjects");
}

function SidebarAccountMenu({ account, collapsed, onNavigate }: { account: AccountMenuConfig; collapsed: boolean; onNavigate: () => void }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const initials = account.initials?.trim() || initialsFromName(account.displayName);
  const detail = account.detail ?? t("notSignedIn");
  const authenticated = account.authenticated === true;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        window.requestAnimationFrame(() => triggerRef.current?.focus());
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const closeAndNavigate = () => {
    setOpen(false);
    onNavigate();
  };

  const handleSignOut = () => {
    setOpen(false);
    account.onSignOut?.();
    onNavigate();
  };

  return (
    <div className={`shell-account ${open ? "is-open" : ""} ${collapsed ? "is-collapsed-account" : ""}`} ref={rootRef}>
      {open ? (
        <div className="shell-account-menu" id={menuId} role="menu" aria-label={t("openAccountMenu")}>
          <div className="shell-account-menu-header">
            <span className="shell-account-avatar" aria-hidden="true">{initials}</span>
            <span className="shell-account-menu-copy">
              <strong>{account.displayName}</strong>
              <small>{detail}</small>
            </span>
          </div>
          <div className="shell-account-menu-list">
            {authenticated ? (
              <>
                <a className="shell-account-menu-item" role="menuitem" href={account.accountHref} onClick={closeAndNavigate}>
                  <UserRound size={16} aria-hidden="true" />
                  <span>{t("accountInfo")}</span>
                </a>
                {account.settingsHref ? (
                  <a className="shell-account-menu-item" role="menuitem" href={account.settingsHref} onClick={closeAndNavigate}>
                    <Settings2 size={16} aria-hidden="true" />
                    <span>{t("settings")}</span>
                  </a>
                ) : null}
                <button className="shell-account-menu-item shell-account-menu-signout" role="menuitem" type="button" onClick={handleSignOut}>
                  <LogOut size={16} aria-hidden="true" />
                  <span>{t("signOut")}</span>
                </button>
              </>
            ) : (
              <>
                <a className="shell-account-menu-item" role="menuitem" href={account.accountHref} onClick={closeAndNavigate}>
                  <LogIn size={16} aria-hidden="true" />
                  <span>{t("signInOrRegister")}</span>
                </a>
                {account.settingsHref ? (
                  <a className="shell-account-menu-item" role="menuitem" href={account.settingsHref} onClick={closeAndNavigate}>
                    <Settings2 size={16} aria-hidden="true" />
                    <span>{t("settings")}</span>
                  </a>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}
      <button
        ref={triggerRef}
        className="shell-account-trigger"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={open ? t("closeAccountMenu") : t("openAccountMenu")}
        title={account.displayName}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="shell-account-avatar" aria-hidden="true">{initials}</span>
        <span className="shell-account-trigger-copy">
          <strong>{account.displayName}</strong>
          <small>{detail}</small>
        </span>
      </button>
    </div>
  );
}

export function ApplicationShell({ brand, navigation, activeHref, eyebrow, title, breadcrumbs, backHref, headerActions, children, account, footer, storageKey = "veyra.sidebar-collapsed.v1", onHistoryClick }: ApplicationShellProps) {
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
  const localizedEyebrow = eyebrow ? shellText(eyebrow, t) : undefined;
  const localizedTitle = shellText(title, t);
  const resolvedAccount: AccountMenuConfig = account ?? {
    displayName: t("localWorkspace"),
    detail: t("notSignedIn"),
    initials: locale === "zh" ? "本" : "LW",
    authenticated: false,
    accountHref: "#/account",
  };

  return (
    <div className={`app-shell ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}>
      <aside id="primary-navigation" className="app-sidebar" aria-label={`${brand.name} navigation`} aria-hidden={mobileViewport && !mobileOpen ? true : undefined} inert={mobileViewport && !mobileOpen ? true : undefined}>
        <div className="sidebar-header">
          <a className="brand" href={navigation[0]?.items[0]?.href ?? "#/"} onClick={() => setMobileOpen(false)}>
            <span className="brand-mark" aria-hidden="true"><img src={iconSrc} alt="" /></span>
            <span className="brand-copy"><strong>{brand.name}</strong><small>{shellText(brand.subtitle, t)}</small></span>
          </a>
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}
            aria-expanded={!collapsed}
            aria-controls="primary-navigation"
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <PanelLeftOpen size={17} aria-hidden="true" /> : <PanelLeftClose size={17} aria-hidden="true" />}
          </button>
          <IconButton ref={sidebarCloseRef} className="sidebar-close" icon={X} label={t("closeNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={closeMobile} />
        </div>

        <nav className="sidebar-nav">
          {navigation.map((group) => (
            <div className={`nav-group ${group.section === "fixed" || group.section === undefined ? "nav-group-fixed" : "nav-group-list"} nav-group-${group.section ?? "fixed"}`} key={group.label}>
              <div className="nav-group-heading"><span className="nav-group-label">{shellText(group.label, t)}</span>{group.action ? <span className="nav-group-action">{group.action}</span> : null}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.active ?? item.href === activeHref;
                const label = shellText(item.label, t);
                return <div className={`sidebar-nav-item ${item.children ? "has-children" : ""}`} key={`${item.href}-${label}`}>
                  {item.leadingAction ? <span className="sidebar-nav-item-leading-action">{item.leadingAction}</span> : null}
                  <a className={active ? "active" : ""} href={item.href} aria-label={label} title={label} aria-current={active ? "page" : undefined} onClick={() => { item.onClick?.(); closeMobile(); }}><Icon size={18} aria-hidden="true" /><span>{label}</span></a>
                  {item.trailingAction ? <span className="sidebar-nav-item-action" onClickCapture={(event) => { if ((event.target as Element).closest("a")) closeMobile(); }}>{item.trailingAction}</span> : null}
                  {item.children && item.expanded ? <div className="sidebar-nav-children">{item.children.map((child) => {
                    const ChildIcon = child.icon;
                    const childActive = child.active ?? child.href === activeHref;
                    const childLabel = shellText(child.label, t);
                    return <a className={childActive ? "active" : ""} key={`${child.href}-${childLabel}`} href={child.href} aria-label={childLabel} title={childLabel} aria-current={childActive ? "page" : undefined} onClick={() => { child.onClick?.(); closeMobile(); }}><ChildIcon size={16} aria-hidden="true" /><span>{childLabel}</span></a>;
                  })}</div> : null}
                </div>;
              })}
              {group.status ? <span className="nav-group-state" role="status">{navigationStatusText(group, t)}</span> : null}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <SidebarAccountMenu account={resolvedAccount} collapsed={collapsed && !mobileViewport} onNavigate={closeMobile} />
          {footer}
        </div>
      </aside>

      {mobileOpen ? <button className="sidebar-backdrop" type="button" aria-label="Close navigation" aria-controls="primary-navigation" onClick={closeMobile} /> : null}

      <div className="app-main">
        <header className="app-header">
          <IconButton ref={mobileMenuRef} className="mobile-menu" icon={Menu} label={t("openNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={openMobile} />
          <div className={`header-copy ${breadcrumbs ? "has-breadcrumbs" : ""}`}>
            {breadcrumbs ? <nav className="header-breadcrumbs" aria-label={t("breadcrumb")}>{backHref ? <a className="breadcrumb-back" href={backHref} aria-label={t("back")}><ArrowLeft size={16} aria-hidden="true" /></a> : null}{breadcrumbs.map((crumb, index) => {
              const Icon = crumb.icon;
              const current = index === breadcrumbs.length - 1;
              return <span className="breadcrumb-part" key={`${crumb.label}-${crumb.href ?? index}`}>{index > 0 ? <span className="breadcrumb-separator" aria-hidden="true">/</span> : null}{current ? <span aria-current="page">{Icon ? <Icon size={15} aria-hidden="true" /> : null}{shellText(crumb.label, t)}</span> : <a href={crumb.href}>{Icon ? <Icon size={15} aria-hidden="true" /> : null}{shellText(crumb.label, t)}</a>}</span>;
            })}</nav> : <>{localizedEyebrow ? <span className="ui-eyebrow">{localizedEyebrow}</span> : null}<h1>{localizedTitle}</h1></>}
          </div>
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
