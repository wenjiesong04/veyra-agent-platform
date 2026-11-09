import { ArrowRight, Bookmark, Bot, Boxes, CheckCircle2, CircleAlert, Clock3, FilePenLine, FolderKanban, LayoutGrid, LayoutTemplate, List as ListIcon, Mail, MessageSquare, PackageCheck, PackageOpen, Search, Star, Workflow } from "lucide-react";
import { communityRoutePaths, type CommunityPluginEntry, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LinkButton, ListSkeleton, Panel, StatusBadge, toast, useLocale } from "@veyra/ui";
import { accountInitials, CommunityApiError, CommunitySectionNav, useAuth, type CommunitySection } from "@veyra/connected-account";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";
import { CommunityCatalogCard, CommunityCatalogTable, agentCatalogCard, pluginCatalogCard, type CatalogCard } from "../features/community/community-agent-card";
import { CommunityReleaseDetail } from "../features/community/community-release-detail";
import { CommunityPublishPanel } from "../features/community/community-publish-panel";
import { CommunityModerationPanel } from "../features/community/community-moderation-panel";
import { CommunityPluginPanel } from "../features/community/community-plugin-panel";
import { CommunityPluginModerationPanel } from "../features/community/community-plugin-moderation-panel";
import { NotFoundPage } from "./not-found";

type CommunitySort = "recent" | "stars" | "rating";
type ReleaseFilter = "all" | "published" | "quarantined" | "rejected";
type CatalogFilter = "all" | "agent" | "plugin" | "workflow" | "skill" | "tool";
type CommunityViewMode = "grid" | "list";
const COMMUNITY_VIEW_STORAGE = "veyra.community-view-mode.v1";

function readCommunityViewMode(): CommunityViewMode {
  try {
    return window.localStorage.getItem(COMMUNITY_VIEW_STORAGE) === "list" ? "list" : "grid";
  } catch {
    return "grid";
  }
}
function releaseKey(entry: CommunityRegistryEntry): string {
  return `${entry.owner_handle}/${entry.slug}/${entry.version}`;
}

export function CommunityPage({
  section = "discover",
  owner,
  slug,
  versionId,
}: {
  section?: CommunitySection;
  owner?: string;
  slug?: string;
  versionId?: string;
}) {
  const { locale } = useLocale();
  const { api, account } = useAuth();
  const { api: localApi, projects, refresh: refreshProjects } = useProjectWorkspace();
  const zh = locale === "zh";
  const isDetail = Boolean(owner && slug);
  const [entries, setEntries] = useState<CommunityRegistryEntry[]>([]);
  const [plugins, setPlugins] = useState<CommunityPluginEntry[]>([]);
  const [discoverFilter, setDiscoverFilter] = useState<CatalogFilter>("all");
  const [starredFilter, setStarredFilter] = useState<CatalogFilter>("all");
  const [viewMode, setViewMode] = useState<CommunityViewMode>(readCommunityViewMode);
  const [starredKeys, setStarredKeys] = useState<Set<string>>(() => new Set());
  const [selected, setSelected] = useState<CommunityRegistryEntry | null>(null);
  const [versions, setVersions] = useState<CommunityRegistryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [collectionQuery, setCollectionQuery] = useState("");
  const [sort, setSort] = useState<CommunitySort>("recent");
  const [releaseFilter, setReleaseFilter] = useState<ReleaseFilter>("all");
  const [publishKind, setPublishKind] = useState<"agent" | "plugin">("agent");
  const [notice, setNotice] = useState("");

  const copy = zh ? {
    search: "搜索 Agent 名称或描述",
    sort: "排序",
    recent: "最近发布",
    stars: "收藏数",
    rating: "评分",
    refresh: "刷新",
    noAgents: "还没有发布的 Agent",
    noAgentsDetail: "发布前会先在本机预览并确认，Community 只保存版本，不执行 Agent。",
    noPublished: "你还没有发布 Agent 版本",
    noPublishedDetail: "先从本地 Project 选择一个 Agent，检查预览后再发布。发布包不包含 Run 历史或 Knowledge 正文。",
    noStarred: "还没有收藏版本",
    noStarredDetail: "在发现页或版本详情中收藏 Agent，之后可以从这里回来。",
    minePublish: "发布到社区",
    minePublishDetail: "从本机 Project 选择 Agent，检查权限、依赖和来源后再发布。Community 只保存不可变版本，不执行 Agent。",
    publishedRecords: "查看已发布",
    filters: { all: "全部", published: "已发布", quarantined: "审核中", rejected: "已拒绝" },
    publishedCount: "已发布",
    reviewCount: "审核中",
    rejectedCount: "已拒绝",
    starTotal: "总收藏",
    releases: "版本记录",
    noMatches: "没有匹配的 Agent",
    retry: "重试",
    publishQueued: "版本已进入审核队列，审核通过后才会公开。",
    publishComplete: "Agent 版本已发布。",
    sectionApiUnavailable: "当前 Community 服务尚未提供此列表接口；更新服务后可重试。",
  } : {
    search: "Search Agent names or descriptions",
    sort: "Sort",
    recent: "Recently published",
    stars: "Most starred",
    rating: "Top rated",
    refresh: "Refresh",
    noAgents: "No published Agents yet",
    noAgentsDetail: "Review and confirm the local publication preview. Community stores immutable releases and never executes Agents.",
    noPublished: "You have not published an Agent release yet",
    noPublishedDetail: "Choose an Agent from a local Project, inspect its preview, then publish it. Run history and Knowledge bodies are not part of the package.",
    noStarred: "No starred releases yet",
    noStarredDetail: "Star an Agent from Discover or its release page to save it here.",
    minePublish: "Publish to Community",
    minePublishDetail: "Choose an Agent from a local Project and review permissions, dependencies, and provenance before publishing. Community stores immutable releases and never executes Agents.",
    publishedRecords: "View published",
    filters: { all: "All", published: "Published", quarantined: "In review", rejected: "Rejected" },
    publishedCount: "Published",
    reviewCount: "In review",
    rejectedCount: "Rejected",
    starTotal: "Total stars",
    releases: "Release history",
    noMatches: "No Agents match this search",
    retry: "Retry",
    publishQueued: "The release is in the moderation queue and will appear publicly after approval.",
    publishComplete: "Agent release published.",
    sectionApiUnavailable: "This Community service has not loaded the Published/Starred list API yet. Update the service, then retry.",
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (isDetail && owner && slug) {
        const [entry, history] = await Promise.all([
          api.getRegistryAgent(owner, slug, versionId),
          api.listRegistryAgentVersions(owner, slug),
        ]);
        setSelected(entry);
        setVersions(history);
        setEntries([]);
      } else {
        setSelected(null);
        setVersions([]);
        const releases = section === "published" || section === "mine"
          ? await api.listMyRegistryAgents()
          : section === "starred"
            ? await api.listStarredRegistryAgents()
            : await api.listRegistryAgents(query);
        setEntries(releases);
        if (section === "discover") {
          try {
            setPlugins(await api.listRegistryPlugins(query));
          } catch {
            setPlugins([]);
          }
        } else {
          setPlugins([]);
        }
        if (section === "starred") {
          setStarredKeys(new Set(releases.map(releaseKey)));
        } else {
          try {
            const starred = await api.listStarredRegistryAgents();
            setStarredKeys(new Set(starred.map(releaseKey)));
          } catch {
            // Lists remain usable when the account Star endpoint is unavailable.
            setStarredKeys(new Set());
          }
        }
      }
    } catch (cause) {
      const missingSectionApi = (section === "published" || section === "starred")
        && cause instanceof CommunityApiError
        && cause.status === 404;
      setError(missingSectionApi
        ? copy.sectionApiUnavailable
        : cause instanceof Error
          ? cause.message
          : (zh ? "Community 注册表暂时不可用。" : "The Community registry is unavailable."));
      setSelected(null);
      setEntries([]);
      setPlugins([]);
      setStarredKeys(new Set());
    } finally {
      setLoading(false);
    }
  }, [api, isDetail, owner, query, section, slug, versionId, zh]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, section === "discover" && query.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, query, section]);

  useEffect(() => {
    try {
      window.localStorage.setItem(COMMUNITY_VIEW_STORAGE, viewMode);
    } catch {
      // View preference is optional; the page remains usable without storage.
    }
  }, [viewMode]);

  const visibleEntries = useMemo(() => {
    const filtered = section === "published" && releaseFilter !== "all"
      ? entries.filter((entry) => entry.status === releaseFilter)
      : section === "starred" && collectionQuery.trim()
        ? entries.filter((entry) => `${entry.name} ${entry.description} ${entry.owner_handle}`.toLowerCase().includes(collectionQuery.trim().toLowerCase()))
        : entries;
    if (section !== "discover" && section !== "starred") return filtered;
    return [...filtered].sort((left, right) => sort === "stars"
      ? right.star_count - left.star_count
      : sort === "rating"
        ? right.average_rating - left.average_rating || right.review_count - left.review_count
        : (right.published_at ?? right.created_at).localeCompare(left.published_at ?? left.created_at));
  }, [collectionQuery, entries, releaseFilter, section, sort]);

  const starEntry = async (entry: CommunityRegistryEntry) => {
    try {
      const feedback = await api.starRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      setEntries((current) => current.map((item) => item.owner_handle === entry.owner_handle && item.slug === entry.slug && item.version === entry.version
        ? { ...item, star_count: feedback.star_count, review_count: feedback.review_count, average_rating: feedback.average_rating }
        : item));
      setStarredKeys((current) => new Set(current).add(releaseKey(entry)));
      toast.success(zh ? "已收藏这个版本。" : "Release starred.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "收藏失败。" : "Could not star this release."));
      throw cause;
    }
  };

  const unstarEntry = async (entry: CommunityRegistryEntry, removeFromList = true) => {
    try {
      const feedback = await api.unstarRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      setEntries((current) => removeFromList
        ? current.filter((item) => !(item.owner_handle === entry.owner_handle && item.slug === entry.slug && item.version === entry.version))
        : current.map((item) => item.owner_handle === entry.owner_handle && item.slug === entry.slug && item.version === entry.version
          ? { ...item, star_count: feedback.star_count, review_count: feedback.review_count, average_rating: feedback.average_rating }
          : item));
      setStarredKeys((current) => {
        const next = new Set(current);
        next.delete(releaseKey(entry));
        return next;
      });
      toast.success(zh ? "已取消收藏。" : "Release unstarred.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "取消收藏失败。" : "Could not remove this Star."));
      throw cause;
    }
  };

  const onPublished = (entry: CommunityRegistryEntry) => {
    setEntries((current) => [entry, ...current.filter((item) => !(item.owner_handle === entry.owner_handle && item.slug === entry.slug && item.version === entry.version))]);
    if (entry.status === "published") {
      setNotice(copy.publishComplete);
      window.location.hash = communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version);
    } else {
      setNotice(copy.publishQueued);
    }
  };

  if (isDetail && loading) return <div className="community-workspace"><CommunitySectionNav active="discover" /><Panel><ListSkeleton label={zh ? "正在读取社区 Agent…" : "Loading Community release…"} /></Panel></div>;
  if (isDetail && (!selected || error)) return <NotFoundPage backHref={communityRoutePaths.catalog} backLabel={zh ? "返回发现" : "Back to Discover"} />;

  const publishedCount = entries.filter((entry) => entry.status === "published").length;
  const reviewCount = entries.filter((entry) => entry.status === "quarantined").length;
  const rejectedCount = entries.filter((entry) => entry.status === "rejected").length;
  const starTotal = entries.reduce((sum, entry) => sum + (entry.star_count ?? 0), 0);
  const reviewTotal = entries.reduce((sum, entry) => sum + (entry.review_count ?? 0), 0);
  const recentMine = [...entries]
    .sort((left, right) => (right.published_at ?? right.created_at).localeCompare(left.published_at ?? left.created_at))
    .slice(0, 4);
  const releaseStatusLabel = (status: CommunityRegistryEntry["status"]) => status === "quarantined"
    ? copy.filters.quarantined
    : status === "rejected"
      ? copy.filters.rejected
      : copy.filters.published;
  const releaseStatusTone = (status: CommunityRegistryEntry["status"]) => status === "published"
    ? "good"
    : status === "quarantined"
      ? "warn"
      : "bad";
  const pendingItems = [
    reviewCount > 0 ? {
      key: "review",
      tone: "warn" as const,
      text: zh ? `${reviewCount} 个版本审核中` : `${reviewCount} release${reviewCount === 1 ? "" : "s"} in review`,
      href: communityRoutePaths.published,
    } : null,
    rejectedCount > 0 ? {
      key: "rejected",
      tone: "bad" as const,
      text: zh ? `${rejectedCount} 个版本被拒绝，等待修改` : `${rejectedCount} rejected release${rejectedCount === 1 ? "" : "s"} need changes`,
      href: communityRoutePaths.published,
    } : null,
  ].filter((item): item is NonNullable<typeof item> => item !== null);
  const toAgentCards = (list: CommunityRegistryEntry[], saved: boolean) => list.map((entry) => agentCatalogCard(entry, {
    starred: saved || starredKeys.has(releaseKey(entry)),
    onToggleStar: async () => {
      if (saved || starredKeys.has(releaseKey(entry))) await unstarEntry(entry, saved);
      else await starEntry(entry);
    },
  }));
  const discoverPool = [...toAgentCards(entries, false), ...plugins.map(pluginCatalogCard)];
  const discoverCards = discoverPool
    .filter((card) => discoverFilter === "all" || card.kind === discoverFilter)
    .sort((left, right) => sort === "stars"
      ? (right.starCount ?? 0) - (left.starCount ?? 0)
      : sort === "rating"
        ? right.rating - left.rating
        : (right.publishedAt ?? "").localeCompare(left.publishedAt ?? ""));
  const pageCards = toAgentCards(visibleEntries, section === "starred").sort((left, right) => sort === "stars"
    ? (right.starCount ?? 0) - (left.starCount ?? 0)
    : sort === "rating"
      ? right.rating - left.rating
      : (right.publishedAt ?? "").localeCompare(left.publishedAt ?? ""));
  const resultBar = <div className="community-result-bar">
    <div className="community-view-toggle" role="group" aria-label={zh ? "切换显示方式" : "Change view mode"}>
      <button type="button" className={viewMode === "grid" ? "is-active" : ""} aria-label={zh ? "卡片显示" : "Grid view"} aria-pressed={viewMode === "grid"} onClick={() => setViewMode("grid")}><LayoutGrid size={16} aria-hidden="true" /></button>
      <button type="button" className={viewMode === "list" ? "is-active" : ""} aria-label={zh ? "按行显示" : "List view"} aria-pressed={viewMode === "list"} onClick={() => setViewMode("list")}><ListIcon size={16} aria-hidden="true" /></button>
    </div>
    <select className="community-sort-select" aria-label={copy.sort} value={sort} onChange={(event) => setSort(event.target.value as CommunitySort)}><option value="recent">{section === "starred" ? (zh ? "最新收藏" : "Recently starred") : (zh ? "最新发布" : "Latest")}</option><option value="stars">{copy.stars}</option><option value="rating">{copy.rating}</option></select>
  </div>;
  const categoryTabs = (cards: CatalogCard[], active: CatalogFilter, onSelect: (kind: CatalogFilter) => void) => {
    const counts = {
      all: cards.length,
      agent: cards.filter((card) => card.kind === "agent").length,
      plugin: cards.filter((card) => card.kind === "plugin").length,
      workflow: 0,
      skill: 0,
      tool: 0,
    };
    const labels = { all: zh ? "全部" : "All", agent: "Agent", plugin: "Plugin Pack", workflow: "Workflow", skill: "Skill", tool: zh ? "工具" : "Tools" };
    return <div className="community-category-tabs" aria-label={zh ? "资源类型" : "Resource types"}>{(["all", "agent", "plugin", "workflow", "skill", "tool"] as const).map((kind) => <button type="button" key={kind} className={active === kind ? "is-active" : ""} onClick={() => onSelect(kind)}>{labels[kind]} {counts[kind]}</button>)}</div>;
  };
  const starredCards = pageCards.filter((card) => starredFilter === "all" || card.kind === starredFilter);
  const showCards = (cards: CatalogCard[]) => viewMode === "list"
    ? <CommunityCatalogTable cards={cards} locale={locale} />
    : <div className="community-resource-grid">{cards.map((card, index) => <div className="community-card-motion" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }} key={card.id}><CommunityCatalogCard card={card} /></div>)}</div>;

  const navSearch = !isDetail && section === "discover"
    ? <label className="community-search community-nav-search" htmlFor="community-agent-search"><Search size={16} aria-hidden="true" /><input id="community-agent-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索名称或作者" : "Search name or author"} /></label>
    : !isDetail && section === "starred"
      ? <label className="community-search community-nav-search" htmlFor="community-starred-search"><Search size={16} aria-hidden="true" /><input id="community-starred-search" value={collectionQuery} onChange={(event) => setCollectionQuery(event.target.value)} placeholder={zh ? "搜索收藏" : "Search saved"} /></label>
      : null;

  return <div className="community-workspace community-stage">
    <div className="community-nav-row">
      <CommunitySectionNav active={section} />
      {navSearch}
    </div>

    {notice ? <Panel className="community-inline-notice"><p>{notice}</p></Panel> : null}

    {isDetail && selected ? <>
      <LinkButton href={communityRoutePaths.catalog} size="sm" variant="ghost">{zh ? "← 返回发现" : "← Back to Discover"}</LinkButton>
      <CommunityReleaseDetail entry={selected} versions={versions} projects={projects} communityApi={api} localApi={localApi} refreshProjects={refreshProjects} />
    </> : null}

    {!isDetail && section === "discover" ? <section className="community-catalog">
      <div className="community-filter-row">
        {categoryTabs(discoverPool, discoverFilter, setDiscoverFilter)}
        {resultBar}
      </div>
      {loading ? <Panel><ListSkeleton label={zh ? "正在读取已发布的 Agent…" : "Loading published Agents…"} /></Panel> : error ? <ErrorState message={error} onRetry={() => void load()} /> : discoverCards.length ? showCards(discoverCards) : <Panel><EmptyState icon={Search} title={copy.noMatches} detail={copy.noAgentsDetail} /></Panel>}
      <CommunityModerationPanel communityApi={api} />
      <CommunityPluginModerationPanel communityApi={api} />
    </section> : null}

    {!isDetail && section === "published" ? <section className="community-catalog">
      {!loading && !error ? <div className="community-filter-row"><div className="community-status-filters"><button type="button" className={releaseFilter === "all" ? "is-active" : ""} onClick={() => setReleaseFilter("all")}>{zh ? "全部" : "All"} {entries.length}</button><button type="button" className={releaseFilter === "published" ? "is-active" : ""} onClick={() => setReleaseFilter("published")}>{zh ? "公开" : "Public"} {publishedCount}</button><button type="button" className={releaseFilter === "quarantined" ? "is-active" : ""} onClick={() => setReleaseFilter("quarantined")}>{copy.filters.quarantined} {reviewCount}</button><button type="button" className={releaseFilter === "rejected" ? "is-active" : ""} onClick={() => setReleaseFilter("rejected")}>{copy.filters.rejected} {rejectedCount}</button></div>{resultBar}</div> : null}
      {loading ? <Panel><ListSkeleton label={zh ? "正在读取已发布版本…" : "Loading your releases…"} /></Panel> : error ? <ErrorState message={error} onRetry={() => void load()} /> : pageCards.length ? showCards(pageCards) : <Panel><EmptyState icon={PackageCheck} title={copy.noPublished} detail={copy.noPublishedDetail} /></Panel>}
    </section> : null}

    {!isDetail && section === "starred" ? <section className="community-catalog">
      <div className="community-filter-row">
        {categoryTabs(pageCards, starredFilter, setStarredFilter)}
        {resultBar}
      </div>
      {loading ? <Panel><ListSkeleton label={zh ? "正在读取收藏…" : "Loading starred releases…"} /></Panel> : error ? <ErrorState message={error} onRetry={() => void load()} /> : starredCards.length ? showCards(starredCards) : <Panel><EmptyState icon={Bookmark} title={copy.noStarred} detail={copy.noStarredDetail} /></Panel>}
    </section> : null}

    {!isDetail && section === "mine" ? <section className="community-catalog community-creator-center">
      <header className="community-creator-lead">
        <div className="community-creator-profile">
          <div className={`community-creator-avatar${account?.avatar_url ? " has-photo" : ""}`} aria-hidden="true">
            {account?.avatar_url
              ? <img src={account.avatar_url} alt="" />
              : <span>{account ? accountInitials(account.display_name, account.handle) : (zh ? "未" : "?")}</span>}
          </div>
          <div className="community-creator-identity">
            <div className="community-creator-name-row">
              <h1>{account?.display_name || account?.handle || (zh ? "未登录" : "Not signed in")}</h1>
              {account ? <span className="community-creator-connected"><i aria-hidden="true" />{zh ? "账号已连接" : "Account connected"}</span> : null}
            </div>
            {account ? <div className="community-creator-meta">
              <span>@{account.handle}</span>
              <span><Mail size={13} aria-hidden="true" />{account.email}</span>
            </div> : null}
            <p>{zh
              ? "管理公开资料与发布身份；Project 与 Agent 仍在本机运行。"
              : "Manage your public profile and publishing identity. Projects and Agents still run locally."}</p>
          </div>
        </div>
        <div className="community-creator-ornament" aria-hidden="true">
          <span /><span /><span /><span /><span />
        </div>
      </header>

      {!loading && !error ? <div className="community-creator-metrics" aria-label={zh ? "创作者概览" : "Creator overview"}>
        <div><Bot size={16} aria-hidden="true" /><strong>{publishedCount}</strong><span>{copy.publishedCount}</span></div>
        <div><Clock3 size={16} aria-hidden="true" /><strong>{reviewCount}</strong><span>{copy.reviewCount}</span></div>
        <div><CircleAlert size={16} aria-hidden="true" /><strong>{rejectedCount}</strong><span>{copy.rejectedCount}</span></div>
        <div><Star size={16} aria-hidden="true" /><strong>{starTotal}</strong><span>{copy.starTotal}</span></div>
      </div> : null}

      <div className="community-mine-layout">
        <div className="community-publish-column">
          <section id="community-publish-studio" className="community-creator-block community-publish-studio">
            <div className="community-publish-studio-head">
              <div className="community-section-title">
                <span className="community-section-kicker">{zh ? "发布中心" : "Release studio"}</span>
                <h2>{zh ? "选择要发布的内容" : "Choose what to publish"}</h2>
                <p>{zh ? "先选择资源类型，再在同一块工作区完成来源选择、检查和确认。" : "Choose a resource type, then select its source, inspect it, and confirm in the same workspace."}</p>
              </div>
              <span className="community-live-lanes"><span aria-hidden="true" />{zh ? "2 种已接通发布" : "2 live publish lanes"}</span>
            </div>
            <div className="community-publish-options">
              <button type="button" className={`community-publish-option is-available${publishKind === "agent" ? " is-selected" : ""}`} onClick={() => setPublishKind("agent")}>
                <span className="community-publish-option-icon agent"><Bot size={22} aria-hidden="true" /></span>
                <span><strong>Agent</strong><small>{zh ? "发布不可变 Agent 版本" : "Immutable Agent release"}</small></span>
                <em className="community-lane-status is-live">{zh ? "可发布" : "Live"}</em>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
              <button type="button" className="community-publish-option is-planned" disabled aria-disabled="true">
                <span className="community-publish-option-icon project"><FolderKanban size={22} aria-hidden="true" /></span>
                <span><strong>Project</strong><small>{zh ? "完整工作空间包；本地导出已存在" : "Workspace package; local export exists"}</small></span>
                <em className="community-lane-status">{zh ? "社区接口待接入" : "Registry planned"}</em>
              </button>
              <button type="button" className="community-publish-option is-planned" disabled aria-disabled="true">
                <span className="community-publish-option-icon workflow"><Workflow size={22} aria-hidden="true" /></span>
                <span><strong>Workflow</strong><small>{zh ? "固定 Agent 版本的工作流" : "Workflow with pinned Agent versions"}</small></span>
                <em className="community-lane-status">{zh ? "设计范围" : "Planned"}</em>
              </button>
              <button type="button" className={`community-publish-option is-available${publishKind === "plugin" ? " is-selected" : ""}`} onClick={() => setPublishKind("plugin")}>
                <span className="community-publish-option-icon plugin"><PackageOpen size={22} aria-hidden="true" /></span>
                <span><strong>Plugin Pack</strong><small>{zh ? "声明式 Skill + MCP 包" : "Declarative Skill + MCP pack"}</small></span>
                <em className="community-lane-status is-live">{zh ? "可发布" : "Live"}</em>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
              <button type="button" className="community-publish-option is-planned" disabled aria-disabled="true">
                <span className="community-publish-option-icon template"><LayoutTemplate size={22} aria-hidden="true" /></span>
                <span><strong>Template</strong><small>{zh ? "可复用的起点与配置" : "Reusable starting point"}</small></span>
                <em className="community-lane-status">{zh ? "设计范围" : "Planned"}</em>
              </button>
              <button type="button" className="community-publish-option is-planned" disabled aria-disabled="true">
                <span className="community-publish-option-icon resource"><Boxes size={22} aria-hidden="true" /></span>
                <span><strong>{zh ? "可复用资源" : "Reusable resources"}</strong><small>{zh ? "Component、Tool 与独立 Skill" : "Component, Tool, and standalone Skill"}</small></span>
                <em className="community-lane-status">{zh ? "后续扩展" : "Later"}</em>
              </button>
            </div>
            <div className="community-publish-editor">
              <div className="community-publish-editor-head">
                <div>
                  <span>{zh ? "当前类型" : "Current type"}</span>
                  <strong>{publishKind === "agent" ? "Agent" : "Plugin Pack"}</strong>
                </div>
                <p>{publishKind === "agent"
                  ? (zh ? "本地检查通过后才上传，不包含 Run、聊天记录或 Knowledge 正文。" : "Upload starts only after local checks. Runs, chats, and Knowledge bodies stay local.")
                  : (zh ? "Community 保存不可变包与清单，但不会执行 Skill 指令或启动 MCP。" : "Community stores the immutable package and manifest, but never runs Skills or starts MCP.")}</p>
              </div>
              {publishKind === "agent" ? <div id="community-publish-panel" className="community-publish-stack"><CommunityPublishPanel projects={projects} localApi={localApi} communityApi={api} onPublished={onPublished} /></div> : null}
              {publishKind === "plugin" ? <div id="community-plugin-lane"><CommunityPluginPanel communityApi={api} localApi={localApi} /></div> : null}
            </div>
          </section>
        </div>

        <aside className="community-mine-side">
          <section className="community-side-panel">
            <div className="community-side-section-heading">
              <h2>{zh ? "最近发布" : "Recent releases"}</h2>
              <LinkButton href={communityRoutePaths.published} size="sm" variant="ghost">{zh ? "查看全部" : "View all"}</LinkButton>
            </div>
            {loading ? <p className="community-muted-line">{zh ? "正在读取…" : "Loading…"}</p>
              : error ? <p className="community-muted-line">{error}</p>
                : recentMine.length ? <ul className="community-release-activity">
                  {recentMine.map((entry) => <li key={releaseKey(entry)}>
                    <a href={communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version)}>
                      <strong>{entry.name}</strong>
                      <small>Agent · v{entry.version}</small>
                      <span className="community-release-activity-meta">
                        <StatusBadge label={releaseStatusLabel(entry.status)} tone={releaseStatusTone(entry.status)} />
                        <time dateTime={entry.published_at ?? entry.created_at}>{(entry.published_at ?? entry.created_at) ? new Date(entry.published_at ?? entry.created_at).toLocaleDateString(locale) : "—"}</time>
                      </span>
                    </a>
                  </li>)}
                </ul>
                  : <div className="community-empty-soft">
                    <strong>{zh ? "暂无发布记录" : "No releases yet"}</strong>
                    <p>{zh ? "发布第一个资源后，它会出现在这里。" : "Your first published resource will show up here."}</p>
                  </div>}
          </section>

          <section className="community-side-panel">
            <div className="community-side-section-heading"><h2>{zh ? "待处理" : "Needs attention"}</h2></div>
            {loading ? <p className="community-muted-line">{zh ? "正在读取…" : "Loading…"}</p>
              : pendingItems.length ? <ul className="community-pending-list">
                {pendingItems.map((item) => <li key={item.key} className={`is-${item.tone}`}>
                  <a href={item.href}>{item.tone === "warn" ? <Clock3 size={14} aria-hidden="true" /> : item.tone === "bad" ? <CircleAlert size={14} aria-hidden="true" /> : <FilePenLine size={14} aria-hidden="true" />}<span>{item.text}</span></a>
                </li>)}
              </ul>
                : <p className="community-pending-clear"><CheckCircle2 size={15} aria-hidden="true" />{zh ? "暂无待处理事项" : "Nothing needs attention"}</p>}
          </section>

          <section className="community-side-panel">
            <div className="community-side-section-heading"><h2>{zh ? "社区反馈" : "Community feedback"}</h2></div>
            {loading ? <p className="community-muted-line">{zh ? "正在读取…" : "Loading…"}</p>
              : (starTotal > 0 || reviewTotal > 0) ? <ul className="community-feedback-summary">
                <li><Star size={14} aria-hidden="true" /><span>{zh ? `总收藏：${starTotal}` : `Total stars: ${starTotal}`}</span></li>
                <li><MessageSquare size={14} aria-hidden="true" /><span>{zh ? `评价：${reviewTotal}` : `Reviews: ${reviewTotal}`}</span></li>
              </ul>
                : <div className="community-empty-soft">
                  <strong>{zh ? "还没有新的社区反馈" : "No community feedback yet"}</strong>
                  <p>{zh ? "当别人收藏或评价你的资源时，摘要会出现在这里。" : "Stars and reviews on your releases will appear here."}</p>
                </div>}
          </section>
        </aside>
      </div>
    </section> : null}
  </div>;
}
