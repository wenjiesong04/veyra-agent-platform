import { useEffect, useRef, type ReactNode } from "react";
import { CommunitySectionNav, type CommunitySection } from "@veyra/connected-account";
import { useLocale } from "@veyra/ui";
import "./community-layout.css";

export function CommunitySiteLayout({ section, locationKey, children }: { section: CommunitySection; locationKey: string; children: ReactNode }) {
  const { locale } = useLocale();
  const root = useRef<HTMLDivElement>(null);
  const zh = locale === "zh";
  useEffect(() => {
    root.current?.closest(".showcase")?.scrollTo({ top: 0, behavior: "instant" });
    const nav = root.current?.querySelector<HTMLElement>(".community-section-nav");
    const active = nav?.querySelector<HTMLElement>("[aria-current]");
    if (nav && active && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: Math.max(0, active.offsetLeft - nav.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2), behavior: "instant" });
  }, [locationKey, locale]);

  return <div className="site-community" ref={root}>
    <aside className="site-community-sidebar">
      <span className="site-community-label">{zh ? "社区" : "Community"}</span>
      <CommunitySectionNav active={section} />
    </aside>
    <div className="site-community-content">{children}</div>
  </div>;
}
