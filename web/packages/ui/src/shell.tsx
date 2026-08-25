import { Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { IconButton } from "./primitives";
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
};

function readCollapsed(storageKey: string): boolean {
  try {
    return window.localStorage.getItem(storageKey) === "true";
  } catch {
    return false;
  }
}

export function ApplicationShell({ brand, navigation, activeHref, eyebrow, title, headerActions, children, footer, storageKey = "veyra.ui.sidebar-collapsed" }: ApplicationShellProps) {
  const [collapsed, setCollapsed] = useState(() => readCollapsed(storageKey));
  const [mobileOpen, setMobileOpen] = useState(false);

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
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  return (
    <div className={`app-shell ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}>
      <aside className="app-sidebar" aria-label={`${brand.name} navigation`}>
        <div className="sidebar-header">
          <a className="brand" href={navigation[0]?.items[0]?.href ?? "#/"} onClick={() => setMobileOpen(false)}>
            <span className="brand-mark" aria-hidden="true">{brand.mark ?? "V"}</span>
            <span className="brand-copy"><strong>{brand.name}</strong><small>{brand.subtitle}</small></span>
          </a>
          <IconButton
            className="sidebar-toggle"
            icon={collapsed ? PanelLeftOpen : PanelLeftClose}
            label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((value) => !value)}
          />
          <IconButton className="sidebar-close" icon={X} label="Close navigation" onClick={() => setMobileOpen(false)} />
        </div>

        <div className="sidebar-context">
          <span className="context-mark" aria-hidden="true"><span /></span>
          <span className="context-copy"><small>Workspace</small><strong>Ready to build</strong><em>Local control surface</em></span>
        </div>

        <nav className="sidebar-nav">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = item.href === activeHref;
                return <a className={active ? "active" : ""} href={item.href} aria-current={active ? "page" : undefined} key={item.href} onClick={() => setMobileOpen(false)}><Icon size={18} aria-hidden="true" /><span>{item.label}</span></a>;
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="footer-pulse" aria-hidden="true" />
          <span><strong>{brand.name}</strong><small>Local first</small></span>
          {footer}
        </div>
      </aside>

      {mobileOpen ? <button className="sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} /> : null}

      <div className="app-main">
        <header className="app-header">
          <IconButton className="mobile-menu" icon={Menu} label="Open navigation" onClick={() => setMobileOpen(true)} />
          <div className="header-copy"><span className="ui-eyebrow">{eyebrow}</span><h1>{title}</h1></div>
          <div className="header-actions">{headerActions}</div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
