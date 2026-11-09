import { Bookmark, Bot, GitBranch, PackageOpen, Star } from "lucide-react";
import { communityRoutePaths, type CommunityPluginEntry, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { LinkButton, StatusBadge, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";

export type CatalogKind = "agent" | "plugin";

export type CatalogCard = {
  id: string;
  kind: CatalogKind;
  name: string;
  description: string;
  href: string | null;
  ownerHandle: string;
  ownerAvatarUrl: string | null;
  version: string;
  hash: string;
  publishedAt: string | null;
  starCount: number | null;
  rating: number;
  nodeCount: number | null;
  risk: "low" | "medium" | "high" | null;
  status: "published" | "quarantined" | "rejected";
  starred?: boolean;
  onToggleStar?: () => Promise<void>;
};

export function agentCatalogCard(
  entry: CommunityRegistryEntry,
  options: { starred?: boolean; onToggleStar?: () => Promise<void> } = {},
): CatalogCard {
  return {
    id: `${entry.owner_handle}/${entry.slug}/${entry.version}`,
    kind: "agent",
    name: entry.name,
    description: entry.description,
    href: communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version),
    ownerHandle: entry.owner_display_name || entry.owner_handle,
    ownerAvatarUrl: entry.owner_avatar_url ?? null,
    version: entry.version,
    hash: entry.source_hash,
    publishedAt: entry.published_at,
    starCount: entry.star_count,
    rating: entry.average_rating,
    nodeCount: entry.capabilities?.node_count ?? 0,
    risk: entry.capabilities?.risk_level ?? entry.scan?.risk_level ?? "low",
    status: entry.status,
    starred: options.starred,
    onToggleStar: options.onToggleStar,
  };
}

export function pluginCatalogCard(entry: CommunityPluginEntry): CatalogCard {
  return {
    id: `plugin/${entry.owner_handle}/${entry.slug}/${entry.version}`,
    kind: "plugin",
    name: entry.name,
    description: entry.description,
    href: null,
    ownerHandle: entry.owner_display_name || entry.owner_handle,
    ownerAvatarUrl: entry.owner_avatar_url ?? null,
    version: entry.version,
    hash: entry.package_hash,
    publishedAt: entry.published_at,
    starCount: null,
    rating: 0,
    nodeCount: entry.skill_count + entry.mcp_count,
    risk: null,
    status: entry.status,
  };
}

export function CommunityAgentCard({
  entry,
  isStarred,
  onStar,
  onUnstar,
}: {
  entry: CommunityRegistryEntry;
  isStarred?: boolean;
  onStar?: (entry: CommunityRegistryEntry) => Promise<void>;
  onUnstar?: (entry: CommunityRegistryEntry) => Promise<void>;
}) {
  const starred = isStarred ?? (!onStar && Boolean(onUnstar));
  const toggle = onStar || onUnstar
    ? async () => {
      const action = starred ? onUnstar : onStar;
      if (action) await action(entry);
    }
    : undefined;
  return <CommunityCatalogCard card={agentCatalogCard(entry, { starred, onToggleStar: toggle })} />;
}

export function CommunityCatalogCard({ card }: { card: CatalogCard }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [starred, setStarred] = useState(Boolean(card.starred));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setStarred(Boolean(card.starred)); }, [card.starred]);
  const riskLabel = card.risk
    ? (zh ? { low: "低风险", medium: "中风险", high: "高风险" }[card.risk] : `${card.risk} risk`)
    : "";
  const starLabel = starred ? (zh ? "取消收藏" : "Unstar") : (zh ? "收藏" : "Star");
  const initial = (card.ownerHandle.trim()[0] ?? "V").toUpperCase();
  const kindLabel = card.kind === "plugin" ? "Plugin Pack" : "Agent";

  const toggleStar = async () => {
    if (!card.onToggleStar) return;
    setBusy(true);
    try {
      await card.onToggleStar();
      setStarred(!starred);
    } catch {
      // The parent surfaces the API error without changing the saved state.
    } finally {
      setBusy(false);
    }
  };

  const title = card.href ? <a href={card.href}>{card.name}</a> : <span>{card.name}</span>;

  return <article className="community-resource-card">
    <div className="community-resource-card-top">
      <div className="community-resource-meta">
        <span className="community-type-pill">{kindLabel}</span>
        {card.risk ? <span className={`community-risk-pill tone-${card.risk}`}>{riskLabel}</span> : null}
      </div>
      {card.onToggleStar ? <button className={`community-card-save${starred ? " is-saved" : ""}`} type="button" aria-label={starLabel} disabled={busy} onClick={() => void toggleStar()}>{starred ? <Bookmark size={16} /> : <Star size={16} />}</button> : null}
    </div>
    <div className={`community-card-preview cover-${card.kind}`} aria-hidden="true"><span className="community-card-preview-grid" /><span className="community-card-preview-node main">{card.kind === "plugin" ? <PackageOpen size={22} /> : <Bot size={22} />}</span><span className="community-card-preview-node small" /><span className="community-card-preview-node tiny" /></div>
    <div className="community-resource-card-content"><h3>{title}</h3><p>{card.description}</p></div>
    <div className="community-resource-owner">{card.ownerAvatarUrl ? <img src={card.ownerAvatarUrl} alt="" /> : <span className="community-author-mark" aria-hidden="true">{initial}</span>}<span>{card.ownerHandle}</span></div>
    <div className="community-resource-metrics">{card.starCount !== null ? <span><Star size={13} /> {card.starCount}</span> : null}{card.nodeCount !== null ? <span><GitBranch size={13} /> {card.nodeCount} {zh ? "个节点" : "nodes"}</span> : null}<span>v{card.version}</span></div>
  </article>;
}

export function CommunityCatalogTable({
  cards,
  locale,
}: {
  cards: CatalogCard[];
  locale: string;
}) {
  const zh = locale === "zh";
  const statusLabel = (card: CatalogCard) => card.status === "quarantined"
    ? (zh ? "审核中" : "In review")
    : card.status === "rejected"
      ? (zh ? "已拒绝" : "Rejected")
      : (zh ? "已发布" : "Published");
  return <div className="community-record-list">
    <div className="community-record-header"><span>{zh ? "资源" : "Resource"}</span><span>{zh ? "类型" : "Type"}</span><span>{zh ? "最新版本" : "Latest"}</span><span>{zh ? "状态" : "Status"}</span><span>{zh ? "发布时间" : "Published"}</span><span>{zh ? "操作" : "Action"}</span></div>
    {cards.map((card) => <article className="community-record" key={card.id}>
      <div className="community-record-resource"><span className="community-record-icon">{card.kind === "plugin" ? <PackageOpen size={16} /> : <Bot size={16} />}</span><div className="community-release-copy"><strong>{card.name}</strong><small>{card.description}</small></div></div>
      <span className="community-type-pill">{card.kind === "plugin" ? "Plugin Pack" : "Agent"}</span>
      <span className="community-record-version"><b>v{card.version}</b><small>{card.hash.slice(0, 10)}…</small></span>
      <StatusBadge label={statusLabel(card)} tone={card.status === "published" ? "good" : card.status === "quarantined" ? "warn" : "bad"} />
      <span className="community-record-date">{card.publishedAt ? new Date(card.publishedAt).toLocaleString(locale, { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : (zh ? "尚未公开" : "Not public")}</span>
      {card.href ? <LinkButton href={card.href} size="sm" variant="secondary">{zh ? "查看" : "View"}</LinkButton> : <span />}
    </article>)}
  </div>;
}
