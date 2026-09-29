import { Bookmark, Compass, PackageCheck, UserRound } from "lucide-react";
import { communityRoutePaths } from "@veyra/api-contracts";
import { useLocale } from "@veyra/ui";

export type CommunitySection = "discover" | "published" | "starred" | "mine";

const sectionPaths: Record<CommunitySection, string> = {
  discover: communityRoutePaths.catalog,
  published: communityRoutePaths.published,
  starred: communityRoutePaths.starred,
  mine: communityRoutePaths.mine,
};

export function CommunitySectionNav({ active }: { active: CommunitySection }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const tabs = [
    { id: "discover", label: zh ? "发现" : "Discover", icon: Compass },
    { id: "published", label: zh ? "已发布" : "Published", icon: PackageCheck },
    { id: "starred", label: zh ? "已收藏" : "Starred", icon: Bookmark },
    { id: "mine", label: zh ? "我的" : "Mine", icon: UserRound },
  ] as const;

  return <nav className="community-section-nav" aria-label={zh ? "社区页面" : "Community pages"}>
    {tabs.map(({ id, label, icon: Icon }) => <a
      key={id}
      href={sectionPaths[id]}
      className={active === id ? "is-active" : ""}
      aria-current={active === id ? "page" : undefined}
    ><Icon size={16} aria-hidden="true" /><span>{label}</span></a>)}
  </nav>;
}
