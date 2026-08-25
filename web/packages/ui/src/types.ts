import type { LucideIcon } from "lucide-react";

export type ThemeChoice = "system" | "light" | "dark";

export type Brand = {
  name: string;
  subtitle: string;
  mark?: string;
};

export type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};
