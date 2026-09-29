import { ArrowUpRight, Search, Star } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { communityRoutePaths, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, StatusBadge, Tag, toast, useLocale } from "@veyra/ui";
import { useAuth, type CommunityApi } from "@veyra/connected-account";

export function CatalogPage() {
  const { locale } = useLocale();
  const { api } = useAuth();
  const zh = locale === "zh";
  const copy = zh ? {
    eyebrow: "社区 Agent", title: "发现", description: "找到可复用的 Agent，先检查能力、依赖和权限，再决定是否导入。", entries: "个版本", search: "搜索 Agent 名称或描述", refresh: "刷新", sort: "排序", recent: "最近发布", stars: "收藏最多", rating: "评分最高", loading: "正在读取 Community 注册表…", error: "Community 注册表暂时不可用。", noMatch: "没有匹配的已发布 Agent。", broaden: "尝试其他名称，或清除搜索。", by: "发布者", inspect: "查看版本", unavailable: "无扫描报告", none: "无额外声明", noRating: "暂无评分", star: "收藏", unstar: "取消收藏",
  } : {
    eyebrow: "Community Agents", title: "Discover", description: "Find reusable Agents, inspect capabilities, dependencies, and permissions, then decide whether to import a release.", entries: "releases", search: "Search Agent names or descriptions", refresh: "Refresh", sort: "Sort", recent: "Recently published", stars: "Most starred", rating: "Top rated", loading: "Loading Community registry…", error: "The Community registry is temporarily unavailable.", noMatch: "No published Agents match this search.", broaden: "Try another name or clear the search.", by: "Published by", inspect: "Inspect release", unavailable: "Not scanned", none: "None declared", noRating: "No rating", star: "Star", unstar: "Unstar",
  };
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"recent" | "stars" | "rating">("recent");
  const [entries, setEntries] = useState<CommunityRegistryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setEntries(await api.listRegistryAgents(query));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.error);
    } finally {
      setLoading(false);
    }
  }, [api, copy.error, query]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, query]);

  const sortedEntries = useMemo(() => [...entries].sort((left, right) => sort === "stars"
    ? right.star_count - left.star_count
    : sort === "rating"
      ? right.average_rating - left.average_rating || right.review_count - left.review_count
      : (right.published_at ?? right.created_at).localeCompare(left.published_at ?? left.created_at)), [entries, sort]);

  return <div className="community-page-stack">
    <div className="community-intro">
      <div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div>
      {!loading && !error ? <Tag>{entries.length} {copy.entries}</Tag> : null}
    </div>
    <div className="catalog-toolbar">
      <label className="search-box" htmlFor="catalog-search"><Search size={16} /><input id="catalog-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.search} /></label>
      <div className="button-row"><label className="community-sort"><span>{copy.sort}</span><select value={sort} onChange={(event) => setSort(event.target.value as "recent" | "stars" | "rating")}><option value="recent">{copy.recent}</option><option value="stars">{copy.stars}</option><option value="rating">{copy.rating}</option></select></label><Button size="sm" variant="ghost" onClick={() => void load()} disabled={loading}>{copy.refresh}</Button></div>
    </div>
    {loading ? <Panel><LoadingState label={copy.loading} /></Panel> : error ? <ErrorState message={`${copy.error} ${error}`} onRetry={() => void load()} /> : sortedEntries.length ? <div className="community-entry-grid">
      {sortedEntries.map((entry) => <CommunityBrowseCard api={api} entry={entry} copy={copy} key={`${entry.owner_handle}/${entry.slug}/${entry.version}`} />)}
    </div> : <Panel><EmptyState icon={Search} title={copy.noMatch} detail={copy.broaden} /></Panel>}
  </div>;
}

function CommunityBrowseCard({
  api,
  entry,
  copy,
}: {
  api: CommunityApi;
  entry: CommunityRegistryEntry;
  copy: { by: string; inspect: string; unavailable: string; noRating: string; star: string; unstar: string };
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [starred, setStarred] = useState(false);
  const [busy, setBusy] = useState(false);
  const [starCount, setStarCount] = useState(entry.star_count);

  const toggleStar = async () => {
    setBusy(true);
    try {
      const feedback = starred
        ? await api.unstarRegistryAgent(entry.owner_handle, entry.slug, entry.version)
        : await api.starRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      setStarred(feedback.starred);
      setStarCount(feedback.star_count);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "无法更新收藏。" : "Could not update this Star."));
    } finally {
      setBusy(false);
    }
  };

  return <Panel className="community-entry-card">
    <div className="entry-card-header"><span className="entry-icon"><Search size={18} /></span><StatusBadge label={entry.scan?.status ?? copy.unavailable} tone={entry.scan?.status === "passed" ? "good" : "warn"} /></div>
    <h3>{entry.name}</h3><p>{entry.description}</p>
    <div className="entry-meta"><span>{copy.by} @{entry.owner_handle}</span><span>{entry.slug}</span><span>v{entry.version}</span></div>
    <div className="entry-stats"><span>★ {starCount}</span><span>{entry.average_rating ? `${entry.average_rating.toFixed(1)} / 5` : copy.noRating}</span><span>{entry.capabilities?.node_count ?? 0} nodes</span></div>
    <div className="resource-card-meta">{(entry.capabilities?.tools ?? []).slice(0, 2).map((tool) => <Tag key={tool}>{tool}</Tag>)}{(entry.capabilities?.risk_reasons ?? []).map((reason) => <Tag key={reason} tone="warn">{reason}</Tag>)}</div>
    <div className="community-browse-actions"><Button size="sm" variant={starred ? "secondary" : "ghost"} icon={Star} disabled={busy} onClick={() => void toggleStar()}>{starred ? copy.unstar : copy.star}</Button><LinkButton href={communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version)} icon={ArrowUpRight} variant="secondary" size="sm">{copy.inspect} · {entry.name}</LinkButton></div>
  </Panel>;
}
