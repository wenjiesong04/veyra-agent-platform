import { ArrowLeft, ChevronDown, History, Languages, LogIn, LogOut, Menu, Moon, PanelLeftClose, Settings2, Sun, Trash2, UserRound, X, type LucideIcon } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type Ref } from "react";
import brandIconUrl from "./assets/veyra-icon.png";
import { useLocale } from "./i18n";
import { PaneResizeHandle } from "./pane-resize";
import { IconButton } from "./primitives";
import {
  emptyNavScrollFolds,
  isCollapsibleNavSection,
  stickyOffsetsForSections,
  useNavScrollAccordion,
  type CollapsibleNavSection,
  type NavScrollFoldState,
} from "./scroll-driven-sections";
import { useTheme } from "./theme";
import type { AccountMenuConfig, Brand, NavigationGroup, NavigationItem } from "./types";

export const SIDEBAR_WIDTH_MIN = 200;
const SIDEBAR_WIDTH_MAX = 420;
const SIDEBAR_WIDTH_DEFAULT = 248;
const SHELL_OVERLAY_LEFT_VAR = "--shell-overlay-left";
const NAV_SECTION_STORAGE = "veyra.nav-section-collapsed.v1";

type CollapsedNavSections = NavScrollFoldState;

function isFixedNavGroup(group: NavigationGroup): boolean {
  return group.section === "fixed" || group.section === undefined;
}

function readCollapsedNavSections(): CollapsedNavSections {
  const empty = emptyNavScrollFolds();
  try {
    const raw = window.localStorage.getItem(NAV_SECTION_STORAGE);
    if (!raw) return empty;
    const parsed = JSON.parse(raw) as Partial<Record<string, unknown>>;
    return {
      pinned: parsed.pinned === true,
      projects: parsed.projects === true,
      recent: parsed.recent === true,
    };
  } catch {
    return empty;
  }
}

function sectionFoldAriaLabel(collapsed: boolean, label: string, locale: string, translate: (key: string) => string): string {
  const verb = collapsed ? translate("expandSection") : translate("collapseSection");
  return locale === "zh" ? `${verb}${label}` : `${verb} ${label}`;
}

type ApplicationShellProps = {
  brand: Brand;
  navigation: NavigationGroup[];
  activeHref: string;
  eyebrow?: string;
  title: string;
  breadcrumbs?: { label: string; href?: string; icon?: LucideIcon }[];
  backHref?: string;
  headerActions?: ReactNode;
  contentClassName?: string;
  children: ReactNode;
  account?: AccountMenuConfig;
  footer?: ReactNode;
  storageKey?: string;
  historyHref?: string;
  historyActive?: boolean;
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
  Agents: "navAgents",
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
  Workflows: "workflows",
  Knowledge: "knowledge",
  Factory: "factory",
  Version: "version",
  Run: "run",
  "New chat": "newChat",
  "Run workspace": "runWorkspace",
  "Resource library": "resourceLibrary",
  Overview: "overview",
  "Back to app": "backToApp",
  "Back to home": "backToHome",
  "Knowledge base": "knowledgeBase",
  Recent: "recent",
  Runs: "runs",
  Monitor: "monitor",
  Components: "catalogComponents",
  "Tools / MCP": "catalogTools",
  Skills: "catalogSkills",
  Policies: "catalogPolicies",
  Templates: "catalogTemplates",
  Files: "files",
  Community: "community",
  Account: "account",
  Settings: "settings",
  Catalog: "catalog",
  "Route not found": "routeNotFound",
  "Version-aware catalog": "versionAwareCatalog",
  Trash: "trash",
};

function shellText(value: string, translate: (key: string, fallback?: string) => string): string {
  return translate(shellLabelKeys[value] ?? "", value);
}

function navigationItemAriaLabel(item: NavigationItem, label: string): string {
  return [label, item.detail, item.meta].filter(Boolean).join(". ");
}

function isNavigationItemActive(item: NavigationItem, activeHref: string): boolean {
  return item.active !== undefined ? item.active : item.href === activeHref;
}

function navigationStatusText(group: NavigationGroup, translate: (key: string, fallback?: string) => string): string {
  if (group.statusText) return group.statusText;
  if (group.status === "loading") return translate("loadingProjects");
  if (group.status === "error") return translate("projectsUnavailable");
  return group.label === "Recent" ? translate("noRecentProjects") : translate("noProjects");
}

function navigationLinkClassName(item: NavigationItem, active: boolean, contextual: boolean): string {
  const classes = ["sidebar-nav-link"];
  if (active) classes.push("active");
  else if (contextual) classes.push("contextual");
  if (item.tone) classes.push(`tone-${item.tone}`);
  if (item.resourceKind) classes.push(`kind-${item.resourceKind}`);
  return classes.join(" ");
}

function navigationRowClassName(item: NavigationItem, extra = ""): string {
  const classes = [extra, item.tone ? `tone-${item.tone}` : "", item.resourceKind ? `kind-${item.resourceKind}` : ""].filter(Boolean);
  return classes.join(" ");
}

function NavigationGlyph({ item, size }: { item: NavigationItem; size: number }) {
  const Icon = item.icon;
  const chip = item.tone === "kind" || item.tone === "collection" || item.tone === "catalog";
  return (
    <span className={chip ? "sidebar-nav-icon sidebar-nav-kind-icon" : "sidebar-nav-icon"} aria-hidden="true">
      <Icon size={chip ? 11 : size} />
    </span>
  );
}

function NavLinkLabel({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const onMouseEnter = () => {
    const node = ref.current;
    if (!node) return;
    if (node.scrollWidth > node.clientWidth + 1) node.setAttribute("title", text);
    else node.removeAttribute("title");
  };
  return <span ref={ref} onMouseEnter={onMouseEnter}>{text}</span>;
}

function SidebarToggle({
  collapsed,
  className,
  expandLabel,
  collapseLabel,
  buttonRef,
  onToggle,
}: {
  collapsed: boolean;
  className?: string;
  expandLabel: string;
  collapseLabel: string;
  buttonRef?: Ref<HTMLButtonElement>;
  onToggle: () => void;
}) {
  return (
    <button
      ref={buttonRef}
      className={className ? `sidebar-toggle ${className}` : "sidebar-toggle"}
      type="button"
      aria-label={collapsed ? expandLabel : collapseLabel}
      aria-expanded={!collapsed}
      aria-controls="primary-navigation"
      onClick={onToggle}
    >
      <span className={`sidebar-toggle-glyph${collapsed ? " is-flipped" : ""}`} aria-hidden="true">
        <PanelLeftClose size={17} />
      </span>
    </button>
  );
}

function NavLinkCopy({ item, label }: { item: NavigationItem; label: string }) {
  if (!item.detail && !item.meta) return <NavLinkLabel text={label} />;
  return (
    <span className="sidebar-nav-copy">
      <strong>{label}</strong>
      {item.detail ? <small>{item.detail}</small> : null}
      {item.meta ? <small>{item.meta}</small> : null}
    </span>
  );
}

function FoldableNavTree({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <div className={`sidebar-nav-children${open ? " is-open" : ""}`} aria-hidden={!open} inert={!open || undefined}>
      <div className="sidebar-nav-children-inner">{children}</div>
    </div>
  );
}

function NavSectionHeading({
  group,
  section,
  folded,
  locale,
  t,
  onToggle,
}: {
  group: NavigationGroup;
  section: CollapsibleNavSection;
  folded: boolean;
  locale: string;
  t: (key: string, fallback?: string) => string;
  onToggle: (section: CollapsibleNavSection) => void;
}) {
  const groupLabel = shellText(group.label, t);
  return (
    <div className="nav-group-heading">
      <button
        type="button"
        className={`nav-group-fold${folded ? "" : " is-open"}`}
        aria-label={sectionFoldAriaLabel(folded, groupLabel, locale, t)}
        aria-expanded={!folded}
        aria-controls={`nav-section-${section}`}
        onClick={() => onToggle(section)}
      >
        <span className="nav-group-label">{groupLabel}</span>
        <span className="nav-group-fold-mark" aria-hidden="true">
          <ChevronDown className="nav-group-fold-icon" size={14} />
        </span>
      </button>
      {group.action ? <span className="nav-group-action">{group.action}</span> : null}
    </div>
  );
}

function SidebarNavGroup({
  group,
  activeHref,
  collapsed,
  sectionCollapsed,
  scrollFolded = false,
  locale,
  t,
  closeMobile,
  onToggleSection,
}: {
  group: NavigationGroup;
  activeHref: string;
  collapsed: boolean;
  sectionCollapsed: boolean;
  scrollFolded?: boolean;
  locale: string;
  t: (key: string, fallback?: string) => string;
  closeMobile: () => void;
  onToggleSection: (section: CollapsibleNavSection) => void;
}) {
  const section = isCollapsibleNavSection(group.section) ? group.section : undefined;
  const groupLabel = shellText(group.label, t);
  const sectionBodyId = section ? `nav-section-${section}` : undefined;
  const folded = sectionCollapsed || scrollFolded;
  const bodyOpen = !folded;
  const groupBody = (
    <>
      {group.items.map((item) => {
        const active = isNavigationItemActive(item, activeHref);
        const contextual = item.contextual === true && !active;
        const label = shellText(item.label, t);
        return <div className={navigationRowClassName(item, `sidebar-nav-item ${item.children ? "has-children" : ""}`)} key={`${item.href}-${label}`}>
          <div className={navigationRowClassName(item, `sidebar-nav-item-row${item.trailingAction ? " has-action" : ""}`)}>
            {item.leadingAction ? <span className="sidebar-nav-item-leading-action">{item.leadingAction}</span> : null}
            <a className={navigationLinkClassName(item, active, contextual)} href={item.href} aria-label={navigationItemAriaLabel(item, label)} title={collapsed ? navigationItemAriaLabel(item, label) : undefined} aria-current={active ? "page" : undefined} onClick={() => { item.onClick?.(); closeMobile(); }}><NavigationGlyph item={item} size={16} /><NavLinkCopy item={item} label={label} /></a>
            {item.trailingAction ? <span className="sidebar-nav-item-action" onClickCapture={(event) => { if ((event.target as Element).closest("a")) closeMobile(); }}>{item.trailingAction}</span> : null}
          </div>
          {item.children ? <FoldableNavTree open={item.expanded === true}>{renderSidebarChildren(item.children, activeHref, closeMobile, t, collapsed)}</FoldableNavTree> : null}
        </div>;
      })}
      {group.status ? <span className="nav-group-state" role="status">{navigationStatusText(group, t)}</span> : null}
    </>
  );
  return (
    <div className={`nav-group ${isFixedNavGroup(group) ? "nav-group-fixed" : "nav-group-list"} nav-group-${group.section ?? "fixed"}${sectionCollapsed ? " is-folded" : ""}${scrollFolded ? " is-scroll-folded" : ""}`} data-nav-section={section}>
      {section ? (
        <div className="nav-group-chrome">
          <NavSectionHeading
            group={group}
            section={section}
            folded={folded}
            locale={locale}
            t={t}
            onToggle={onToggleSection}
          />
        </div>
      ) : (
        <div className="nav-group-heading"><span className="nav-group-label">{groupLabel}</span>{group.action ? <span className="nav-group-action">{group.action}</span> : null}</div>
      )}
      {group.backLink ? <a className="sidebar-context-back" href={group.backLink.href} aria-label={group.backLink.label} title={group.backLink.label} onClick={() => closeMobile()}><ArrowLeft size={16} aria-hidden="true" /><span>{group.backLink.label}</span></a> : null}
      {section ? (
        <div className={`nav-group-body${bodyOpen ? " is-open" : ""}`} id={sectionBodyId} aria-hidden={!bodyOpen} inert={bodyOpen ? undefined : true}>
          <div className="nav-group-body-inner">{groupBody}</div>
        </div>
      ) : groupBody}
    </div>
  );
}

function renderSidebarChildren(
  items: NavigationItem[],
  activeHref: string,
  closeMobile: () => void,
  translate: (key: string, fallback?: string) => string,
  collapsed: boolean,
): ReactNode {
  return items.map((child) => {
    const childActive = isNavigationItemActive(child, activeHref);
    const childLabel = shellText(child.label, translate);
    const childContextual = child.contextual === true && !childActive;
    return (
      <div className={navigationRowClassName(child, "sidebar-nav-child")} key={`${child.href}-${childLabel}`}>
        <div className={navigationRowClassName(child, `sidebar-nav-child-row ${child.trailingAction ? "has-action" : ""}`)}>
          <a className={navigationLinkClassName(child, childActive, childContextual)} href={child.href} aria-label={navigationItemAriaLabel(child, childLabel)} title={collapsed ? navigationItemAriaLabel(child, childLabel) : undefined} aria-current={childActive ? "page" : undefined} onClick={() => { child.onClick?.(); closeMobile(); }}><NavigationGlyph item={child} size={16} /><NavLinkCopy item={child} label={childLabel} /></a>
          {child.trailingAction ? <span className="sidebar-nav-item-action sidebar-nav-child-action" onClickCapture={(event) => { if ((event.target as Element).closest("a")) closeMobile(); }}>{child.trailingAction}</span> : null}
        </div>
        {child.children ? <FoldableNavTree open={child.expanded === true}>{renderSidebarChildren(child.children, activeHref, closeMobile, translate, collapsed)}</FoldableNavTree> : null}
      </div>
    );
  });
}

function AccountMenuLink({
  href,
  activeHref,
  onClick,
  children,
}: {
  href: string;
  activeHref: string;
  onClick: () => void;
  children: ReactNode;
}) {
  const current = href === activeHref;
  return (
    <a
      className={`shell-account-menu-item${current ? " is-current" : ""}`}
      role="menuitem"
      href={href}
      aria-current={current ? "page" : undefined}
      onClick={onClick}
    >
      {children}
    </a>
  );
}

function AccountAvatar({ initials, avatarUrl }: { initials: string; avatarUrl?: string | null }) {
  return <span className={`shell-account-avatar${avatarUrl ? " has-photo" : ""}`} aria-hidden="true">{avatarUrl ? <img src={avatarUrl} alt="" /> : initials}</span>;
}

function SidebarAccountMenu({ account, collapsed, onNavigate, activeHref }: { account: AccountMenuConfig; collapsed: boolean; onNavigate: () => void; activeHref: string }) {
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
            <AccountAvatar initials={initials} avatarUrl={account.avatarUrl} />
            <span className="shell-account-menu-copy">
              <strong>{account.displayName}</strong>
              <small>{detail}</small>
            </span>
          </div>
          <div className="shell-account-menu-list">
            {authenticated ? (
              <>
                <AccountMenuLink href={account.accountHref} activeHref={activeHref} onClick={closeAndNavigate}>
                  <UserRound size={16} aria-hidden="true" />
                  <span>{t("accountInfo")}</span>
                </AccountMenuLink>
                {account.settingsHref ? (
                  <AccountMenuLink href={account.settingsHref} activeHref={activeHref} onClick={closeAndNavigate}>
                    <Settings2 size={16} aria-hidden="true" />
                    <span>{t("settings")}</span>
                  </AccountMenuLink>
                ) : null}
                {account.trashHref ? (
                  <AccountMenuLink href={account.trashHref} activeHref={activeHref} onClick={closeAndNavigate}>
                    <Trash2 size={16} aria-hidden="true" />
                    <span>{t("trash")}</span>
                  </AccountMenuLink>
                ) : null}
                <button className="shell-account-menu-item shell-account-menu-signout" role="menuitem" type="button" onClick={handleSignOut}>
                  <LogOut size={16} aria-hidden="true" />
                  <span>{t("signOut")}</span>
                </button>
              </>
            ) : (
              <>
                <AccountMenuLink href={account.accountHref} activeHref={activeHref} onClick={closeAndNavigate}>
                  <LogIn size={16} aria-hidden="true" />
                  <span>{t("signInOrRegister")}</span>
                </AccountMenuLink>
                {account.settingsHref ? (
                  <AccountMenuLink href={account.settingsHref} activeHref={activeHref} onClick={closeAndNavigate}>
                    <Settings2 size={16} aria-hidden="true" />
                    <span>{t("settings")}</span>
                  </AccountMenuLink>
                ) : null}
                {account.trashHref ? (
                  <AccountMenuLink href={account.trashHref} activeHref={activeHref} onClick={closeAndNavigate}>
                    <Trash2 size={16} aria-hidden="true" />
                    <span>{t("trash")}</span>
                  </AccountMenuLink>
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
        <AccountAvatar initials={initials} avatarUrl={account.avatarUrl} />
        <span className="shell-account-trigger-copy">
          <strong>{account.displayName}</strong>
          <small>{detail}</small>
        </span>
      </button>
    </div>
  );
}

export function ApplicationShell({ brand, navigation, activeHref, eyebrow, title, breadcrumbs, headerActions, contentClassName, children, account, footer, storageKey = "veyra.sidebar-collapsed.v1", historyHref, historyActive = false }: ApplicationShellProps) {
  const { locale, setLanguage, t } = useLocale();
  const { effectiveDark, setTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(() => readCollapsed(storageKey));
  const [collapsedSections, setCollapsedSections] = useState(readCollapsedNavSections);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_WIDTH_DEFAULT);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mobileViewport, setMobileViewport] = useState(readMobileViewport);
  const mobileMenuRef = useRef<HTMLButtonElement>(null);
  const sidebarCloseRef = useRef<HTMLButtonElement>(null);
  const sidebarScrollRef = useRef<HTMLDivElement>(null);
  const sidebarToggleRef = useRef<HTMLButtonElement>(null);
  const headerToggleRef = useRef<HTMLButtonElement>(null);
  const pendingToggleFocus = useRef<"header" | "sidebar" | null>(null);
  const fixedNavigation = navigation.filter(isFixedNavGroup);
  const listNavigation = navigation.filter((group) => !isFixedNavGroup(group));
  const listSections = listNavigation.flatMap((group) => isCollapsibleNavSection(group.section) ? [group.section] : []);
  const stickyOffsets = stickyOffsetsForSections(listSections);
  const { autoCollapsed: scrollFolded, lockManualInteraction, scrollSectionIntoSlot } = useNavScrollAccordion(sidebarScrollRef, collapsedSections, listNavigation.length);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, String(collapsed));
    } catch {
      // Layout preference is optional and never carries account identity.
    }
  }, [collapsed, storageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(NAV_SECTION_STORAGE, JSON.stringify(collapsedSections));
    } catch {
      // Section fold preference is optional and never carries account identity.
    }
  }, [collapsedSections]);

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

  useEffect(() => {
    const root = document.documentElement;
    if (mobileViewport) {
      root.style.setProperty(SHELL_OVERLAY_LEFT_VAR, "0px");
    } else {
      if (collapsed) {
        root.style.setProperty(SHELL_OVERLAY_LEFT_VAR, "0px");
      } else {
        const sidebar = document.getElementById("primary-navigation");
        const measured = sidebar?.getBoundingClientRect().width ?? 0;
        const width = measured > 0 ? Math.round(measured) : sidebarWidth;
        root.style.setProperty(SHELL_OVERLAY_LEFT_VAR, `${width}px`);
      }
    }
    return () => {
      root.style.removeProperty(SHELL_OVERLAY_LEFT_VAR);
    };
  }, [collapsed, mobileViewport, sidebarWidth]);

  useLayoutEffect(() => {
    const target = pendingToggleFocus.current;
    if (!target) return;
    pendingToggleFocus.current = null;
    (target === "header" ? headerToggleRef : sidebarToggleRef).current?.focus();
  }, [collapsed]);

  const openMobile = () => {
    setMobileOpen(true);
    window.requestAnimationFrame(() => sidebarCloseRef.current?.focus());
  };

  const closeMobile = () => {
    setMobileOpen(false);
    window.requestAnimationFrame(() => mobileMenuRef.current?.focus());
  };

  const desktopSidebarHidden = collapsed && !mobileViewport;
  const sidebarHidden = mobileViewport ? !mobileOpen : collapsed;

  const toggleCollapsed = () => {
    pendingToggleFocus.current = collapsed ? "sidebar" : "header";
    setCollapsed((value) => !value);
  };

  const iconSrc = brand.iconSrc ?? brandIconUrl;
  const languageIsEnglish = locale === "en";
  const localizedEyebrow = eyebrow ? shellText(eyebrow, t) : undefined;
  const localizedTitle = shellText(title, t);
  const resolvedAccount: AccountMenuConfig = account ?? {
    displayName: t("localWorkspace"),
    detail: t("notSignedIn"),
    initials: locale === "zh" ? "本" : "LW",
    authenticated: false,
    accountHref: "#/account",
    trashHref: "#/trash",
  };
  const toggleNavSection = (section: CollapsibleNavSection) => {
    lockManualInteraction(section);
    if (scrollFolded[section] && !collapsedSections[section]) {
      window.requestAnimationFrame(() => scrollSectionIntoSlot(section));
      return;
    }
    setCollapsedSections((current) => ({ ...current, [section]: !current[section] }));
  };

  return (
    <div
      className={`app-shell ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}
      style={{ "--sidebar-width": collapsed ? "0px" : `${sidebarWidth}px` } as CSSProperties}
    >
      <aside id="primary-navigation" className="app-sidebar" aria-label={`${brand.name} navigation`} aria-hidden={sidebarHidden ? true : undefined} inert={sidebarHidden ? true : undefined}>
        <div className="sidebar-header">
          <a className="brand" href={navigation[0]?.items[0]?.href ?? "#/"} onClick={() => setMobileOpen(false)}>
            <span className="brand-mark" aria-hidden="true"><img src={iconSrc} alt="" /></span>
            <span className="brand-copy"><strong>{brand.name}</strong><small>{shellText(brand.subtitle, t)}</small></span>
          </a>
          {desktopSidebarHidden ? null : (
            <SidebarToggle
              collapsed={collapsed}
              expandLabel={t("expandSidebar")}
              collapseLabel={t("collapseSidebar")}
              buttonRef={sidebarToggleRef}
              onToggle={toggleCollapsed}
            />
          )}
          <IconButton ref={sidebarCloseRef} className="sidebar-close" icon={X} label={t("closeNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={closeMobile} />
        </div>

        <nav className="sidebar-nav">
          {fixedNavigation.length ? (
            <div className="sidebar-nav-fixed">
              {fixedNavigation.map((group) => (
                <SidebarNavGroup
                  key={group.label}
                  group={group}
                  activeHref={activeHref}
                  collapsed={collapsed}
                  sectionCollapsed={false}
                  locale={locale}
                  t={t}
                  closeMobile={closeMobile}
                  onToggleSection={toggleNavSection}
                />
              ))}
            </div>
          ) : null}
          {listNavigation.length ? (
            <div
              className="sidebar-nav-scroll"
              ref={sidebarScrollRef}
              style={{
                "--nav-sticky-first": `${stickyOffsets.projects}px`,
                "--nav-sticky-rest": `${Math.max(0, stickyOffsets.recent - stickyOffsets.projects)}px`,
              } as CSSProperties}
            >
              {listNavigation.map((group) => {
                const section = isCollapsibleNavSection(group.section) ? group.section : undefined;
                return (
                  <SidebarNavGroup
                    key={group.label}
                    group={group}
                    activeHref={activeHref}
                    collapsed={collapsed}
                    sectionCollapsed={section ? collapsedSections[section] : false}
                    scrollFolded={section ? scrollFolded[section] : false}
                    locale={locale}
                    t={t}
                    closeMobile={closeMobile}
                    onToggleSection={toggleNavSection}
                  />
                );
              })}
            </div>
          ) : null}
        </nav>

        <div className="sidebar-footer">
          <SidebarAccountMenu account={resolvedAccount} collapsed={collapsed && !mobileViewport} onNavigate={closeMobile} activeHref={activeHref} />
          {footer}
        </div>
        {collapsed || mobileViewport ? null : (
          <PaneResizeHandle
            label={t("resizeSidebar")}
            edge="right"
            value={sidebarWidth}
            min={SIDEBAR_WIDTH_MIN}
            max={SIDEBAR_WIDTH_MAX}
            onChange={setSidebarWidth}
          />
        )}
      </aside>

      {mobileOpen ? <button className="sidebar-backdrop" type="button" aria-label="Close navigation" aria-controls="primary-navigation" onClick={closeMobile} /> : null}

      <div className="app-main">
        <header className="app-header">
          {desktopSidebarHidden ? (
            <SidebarToggle
              collapsed
              className="header-sidebar-toggle"
              expandLabel={t("expandSidebar")}
              collapseLabel={t("collapseSidebar")}
              buttonRef={headerToggleRef}
              onToggle={toggleCollapsed}
            />
          ) : null}
          <IconButton ref={mobileMenuRef} className="mobile-menu" icon={Menu} label={t("openNavigation")} aria-expanded={mobileOpen} aria-controls="primary-navigation" onClick={openMobile} />
          <div className={`header-copy ${breadcrumbs ? "has-breadcrumbs" : ""}`}>
            {breadcrumbs ? <nav className="header-breadcrumbs" aria-label={t("breadcrumb")}>{breadcrumbs.map((crumb, index) => {
              const Icon = crumb.icon;
              const current = index === breadcrumbs.length - 1;
              const label = shellText(crumb.label, t);
              const content = <>{Icon ? <Icon size={15} aria-hidden="true" /> : null}<span className="breadcrumb-label" title={label}>{label}</span></>;
              return <span className="breadcrumb-part" key={`${crumb.label}-${crumb.href ?? index}`}>{index > 0 ? <span className="breadcrumb-separator" aria-hidden="true">/</span> : null}{current ? <span aria-current="page">{content}</span> : <a href={crumb.href}>{content}</a>}</span>;
            })}</nav> : <>{localizedEyebrow ? <span className="ui-eyebrow">{localizedEyebrow}</span> : null}<h1>{localizedTitle}</h1></>}
          </div>
          <div className="header-actions">
            {headerActions}
            {historyHref ? <a className={`header-control history-control${historyActive ? " is-current" : ""}`} href={historyHref} aria-current={historyActive ? "page" : undefined} aria-label={t("history")} title={t("history")}><History size={17} aria-hidden="true" /><span>{t("history")}</span></a> : null}
            <button className="header-control language-control" type="button" onClick={() => setLanguage(languageIsEnglish ? "zh" : "en")} aria-label={languageIsEnglish ? t("switchToChinese") : t("switchToEnglish")} title={languageIsEnglish ? t("switchToChinese") : t("switchToEnglish")}><Languages size={17} /><span>{languageIsEnglish ? "中" : "EN"}</span></button>
            <button className="header-control theme-control" type="button" onClick={() => setTheme(effectiveDark ? "light" : "dark")} aria-label={effectiveDark ? t("switchToLight") : t("switchToDark")} title={effectiveDark ? t("switchToLight") : t("switchToDark")}><span aria-hidden="true">{effectiveDark ? <Sun size={17} /> : <Moon size={17} />}</span><span>{effectiveDark ? t("day") : t("night")}</span></button>
          </div>
        </header>
        <main className={`page-content ${contentClassName ?? ""}`.trim()}>{children}</main>
      </div>
    </div>
  );
}
