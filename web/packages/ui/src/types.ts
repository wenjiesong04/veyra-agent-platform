import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type ThemeChoice = "system" | "light" | "dark";

export type Brand = {
  name: string;
  subtitle: string;
  mark?: string;
  iconSrc?: string;
};

export type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  active?: boolean;
  onClick?: () => void;
};

export type NavigationGroupStatus = "loading" | "empty" | "error";

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
  section?: "fixed" | "projects" | "recent";
  action?: ReactNode;
  status?: NavigationGroupStatus;
  statusText?: string;
};

/** Sidebar account chip + popover. Local mode stays useful without a remote identity. */
export type AccountMenuConfig = {
  displayName: string;
  detail?: string;
  initials?: string;
  authenticated?: boolean;
  accountHref: string;
  settingsHref?: string;
  onSignOut?: () => void;
};
