import { Bookmark, LayoutGrid, List, LogIn, Search, UserRound } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, toast, useLocale } from "@veyra/ui";
import { useAuth, type CommunitySection } from "@veyra/connected-account";
import { CatalogCard, catalogKey, type CatalogResource } from "./catalog-card";

type Filter = "all" | "agent" | "plugin" | "workflow" | "skill" | "tool";
type Sort = "recent" | "stars" | "rating";
const viewStorage = "veyra.community-view-mode.v1";

export function CatalogPage({ section = "discover" }: { section?: CommunitySection }) {
  const { locale } = useLocale();
  const { api, account, status } = useAuth();
  const zh = locale === "zh";
  const [resources, setResources] = useState<CatalogResource[]>([]);
  const [starred, setStarred] = useState<Set<string>>(new Set());
  const [starsReady, setStarsReady] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const [view, setView] = useState(() => {
    try { return window.localStorage.getItem(viewStorage) === "list" ? "list" : "grid"; } catch { return "grid"; }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const request = useRef(0);
  const privateSection = section !== "discover";
  const title = zh ? { discover: "发现", published: "已发布", starred: "已收藏", mine: "我的" }[section] : { discover: "Discover", published: "Published", starred: "Starred", mine: "Mine" }[section];

  useEffect(() => {
    const current = ++request.current;
    if (status === "booting") return;
    setResources([]);
    setError("");
    setNotice("");
    setStarsReady(false);
    if (privateSection && !account) { setLoading(false); return; }
    setLoading(true);
    const load = async () => {
      const [agents, plugins, saved] = await Promise.allSettled([
        section === "discover" ? api.listRegistryAgents() : section === "starred" ? api.listStarredRegistryAgents() : api.listMyRegistryAgents(),
        section === "discover" ? api.listRegistryPlugins() : section === "published" ? api.listMyRegistryPlugins() : Promise.resolve([]),
        account && section !== "starred" ? api.listStarredRegistryAgents() : Promise.resolve([]),
      ]);
      if (current !== request.current) return;
      if (agents.status === "rejected") {
        setError(zh ? "无法读取社区列表，请重试。" : "Could not load this Community list. Try again.");
      } else {
        setResources([
          ...agents.value.map((entry): CatalogResource => ({ kind: "agent", entry })),
          ...(plugins.status === "fulfilled" ? plugins.value.map((entry): CatalogResource => ({ kind: "plugin", entry })) : []),
        ]);
      }
      const savedEntries = section === "starred" && agents.status === "fulfilled" ? agents.value : saved.status === "fulfilled" ? saved.value : [];
      setStarred(new Set(savedEntries.map((entry) => catalogKey({ kind: "agent", entry }))));
      setStarsReady(!account || section === "starred" || saved.status === "fulfilled");
      if (plugins.status === "rejected") setNotice(zh ? "Plugin Pack 列表暂时不可用。" : "Plugin Packs are temporarily unavailable.");
      else if (saved.status === "rejected") setNotice(zh ? "暂时无法读取收藏状态，请刷新后重试。" : "Saved status is unavailable. Refresh to try again.");
      setLoading(false);
    };
    void load();
    return () => { request.current++; };
  }, [api, account, status, privateSection, section, refresh, zh]);

  useEffect(() => {
    try { window.localStorage.setItem(viewStorage, view); } catch { /* View preference is optional. */ }
  }, [view]);

  const searched = useMemo(() => {
    const text = query.trim().toLocaleLowerCase();
    return resources.filter(({ entry }) => !text || `${entry.name} ${entry.description} ${entry.owner_handle} ${entry.owner_display_name ?? ""}`.toLocaleLowerCase().includes(text));
  }, [resources, query]);
  const visible = useMemo(() => searched.filter((item) => filter === "all" || item.kind === filter).sort((left, right) => {
    const a = left.entry, b = right.entry;
    if (sort === "stars") return ("star_count" in b ? b.star_count : 0) - ("star_count" in a ? a.star_count : 0);
    if (sort === "rating") return ("average_rating" in b ? b.average_rating : 0) - ("average_rating" in a ? a.average_rating : 0);
    return (b.published_at ?? b.created_at).localeCompare(a.published_at ?? a.created_at);
  }), [searched, filter, sort]);

  const toggleStar = async (resource: CatalogResource) => {
    if (!account) { window.location.hash = "#/login"; return; }
    const { entry } = resource;
    const key = catalogKey(resource);
    try {
      const feedback = starred.has(key)
        ? await api.unstarRegistryAgent(entry.owner_handle, entry.slug, entry.version)
        : await api.starRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      setStarred((previous) => {
        const next = new Set(previous);
        if (feedback.starred) next.add(key); else next.delete(key);
        return next;
      });
      setResources((previous) => previous.flatMap((item) => {
        if (catalogKey(item) !== key || item.kind !== "agent") return [item];
        if (section === "starred" && !feedback.starred) return [];
        return [{ ...item, entry: { ...item.entry, star_count: feedback.star_count } }];
      }));
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : zh ? "无法更新收藏。" : "Could not update this Star.");
    }
  };
  const categories: { kind: Filter; label: string }[] = [
    { kind: "all", label: zh ? "全部" : "All" }, { kind: "agent", label: "Agent" }, { kind: "plugin", label: "Plugin Pack" },
    { kind: "workflow", label: "Workflow" }, { kind: "skill", label: "Skill" }, { kind: "tool", label: zh ? "工具" : "Tools" },
  ];

  if (status === "booting") return <LoadingState label={zh ? "正在读取账号…" : "Loading account…"} />;
  if (privateSection && !account) return <div className="registry-sign-in"><h1>{title}</h1><Panel><EmptyState icon={LogIn} title={zh ? "登录后查看你的社区内容" : "Sign in to see your Community content"} detail={zh ? "已发布版本、收藏和个人资料会显示在这里。" : "Your releases, saved versions, and profile appear here."} /><LinkButton href="#/login" variant="primary">{zh ? "登录社区" : "Sign in"}</LinkButton></Panel></div>;

  return <div className="registry-catalog">
    {section === "mine" && account ? <section className="registry-profile" aria-label={zh ? "我的社区资料" : "My Community profile"}>
      <UserRound size={26} /><div><h1>{account.display_name || account.handle}</h1><p>@{account.handle}</p></div><LinkButton href="#/account" variant="secondary">{zh ? "管理账号" : "Manage account"}</LinkButton>
      <p className="registry-profile-note">{zh ? "在这里查看社区版本与收藏。创建、发布和导入资源，请在 Veyra 桌面工作台操作。" : "Keep track of your releases and saved resources here. Create, publish, and import resources in the Veyra desktop workspace."}</p>
    </section> : null}
    <div className="registry-heading">{section === "mine" ? <h2 className="registry-visually-hidden">{zh ? "我的版本" : "My releases"}</h2> : <h1>{title}</h1>}
      <label className="registry-search"><Search size={18} aria-hidden="true" /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索名称或作者" : "Search names or authors"} aria-label={zh ? "搜索名称或作者" : "Search names or authors"} /></label>
    </div>
    <div className="registry-toolbar"><div className="registry-filters" aria-label={zh ? "资源类型" : "Resource types"}>
      {categories.map(({ kind, label }) => <button type="button" key={kind} aria-pressed={filter === kind} onClick={() => setFilter(kind)}>{label} <span>{kind === "all" ? searched.length : searched.filter((item) => item.kind === kind).length}</span></button>)}
    </div><div className="registry-display-controls"><div className="registry-view" aria-label={zh ? "展示方式" : "Display mode"}>
      <button type="button" aria-label={zh ? "卡片视图" : "Grid view"} aria-pressed={view === "grid"} onClick={() => setView("grid")}><LayoutGrid size={18} /></button><button type="button" aria-label={zh ? "列表视图" : "List view"} aria-pressed={view === "list"} onClick={() => setView("list")}><List size={18} /></button>
    </div><select aria-label={zh ? "排序" : "Sort"} value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="recent">{zh ? "最新发布" : "Newest"}</option><option value="stars">{zh ? "收藏最多" : "Most starred"}</option><option value="rating">{zh ? "评分最高" : "Top rated"}</option></select></div></div>
    {notice ? <p className="registry-notice" role="status">{notice}<Button size="sm" variant="ghost" onClick={() => setRefresh((value) => value + 1)}>{zh ? "刷新" : "Refresh"}</Button></p> : null}
    {loading ? <LoadingState label={zh ? "正在读取社区资源…" : "Loading Community resources…"} /> : error ? <ErrorState message={error} onRetry={() => setRefresh((value) => value + 1)} /> : visible.length ? <div className={`registry-cards is-${view}`}>{visible.map((resource) => <CatalogCard key={catalogKey(resource)} resource={resource} starred={starred.has(catalogKey(resource))} onToggleStar={resource.kind === "agent" && starsReady ? () => toggleStar(resource) : undefined} />)}</div> : <Panel><EmptyState icon={section === "starred" ? Bookmark : Search} title={zh ? "暂无匹配的资源" : "No matching resources"} detail={query ? (zh ? "试试其他名称或作者。" : "Try another name or author.") : section === "published" || section === "mine" ? (zh ? "在桌面工作台发布的 Agent 版本会显示在这里。" : "Agent versions you publish from the desktop workspace appear here.") : section === "starred" ? (zh ? "在发现页收藏一个版本，之后可以从这里回来。" : "Save a release in Discover to find it here later.") : (zh ? "可以切换分类查看其他资源。" : "Choose another category to explore resources.")} /></Panel>}
  </div>;
}
