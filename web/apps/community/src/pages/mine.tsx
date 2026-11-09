import { ArrowRight, Bot, CheckCircle2, CircleAlert, Clock3, FolderKanban, LayoutTemplate, LogIn, MessageSquare, PackageOpen, Settings2, Star, Workflow } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { communityRoutePaths, type CommunityPluginEntry, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { useAuth } from "@veyra/connected-account";
import { EmptyState, ErrorState, LinkButton, LoadingState, Panel, StatusBadge, useLocale } from "@veyra/ui";
import { PublicationUpload } from "./publication";
import type { PublicationKind } from "./publication-file";
import "./mine.css";

type Release = CommunityRegistryEntry | CommunityPluginEntry;
const releaseKey = (entry: Release) => `${"source_hash" in entry ? "agent" : "plugin"}/${entry.owner_handle}/${entry.slug}/${entry.version}`;

export function MyCommunityPage() {
  const { locale } = useLocale();
  const { api, account, status } = useAuth();
  const zh = locale === "zh";
  const [entries, setEntries] = useState<CommunityRegistryEntry[] | null>(null);
  const [plugins, setPlugins] = useState<CommunityPluginEntry[] | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [kind, setKind] = useState<PublicationKind>("agent");
  const request = useRef(0);
  const confirmedReleases = useRef<Release[]>([]);
  useEffect(() => {
    const current = ++request.current;
    setEntries(null); setPlugins(null); setError("");
    if (!account) return;
    void Promise.allSettled([api.listMyRegistryAgents(), api.listMyRegistryPlugins()]).then(([agents, packs]) => {
      if (current !== request.current) return;
      if (agents.status === "fulfilled") {
        const keys = new Set(agents.value.map(releaseKey));
        setEntries([...agents.value, ...confirmedReleases.current.filter((entry): entry is CommunityRegistryEntry => "source_hash" in entry && !keys.has(releaseKey(entry)))]);
      }
      else setError(zh ? "无法读取你的发布记录，请重试。" : "Your releases could not be loaded. Try again.");
      if (packs.status === "fulfilled") {
        const owned = packs.value, keys = new Set(owned.map(releaseKey));
        setPlugins([...owned, ...confirmedReleases.current.filter((entry): entry is CommunityPluginEntry => "package_hash" in entry && !keys.has(releaseKey(entry)))]);
      } else setError(zh ? "暂时无法读取插件发布记录，请重试。" : "Plugin release records are temporarily unavailable. Try again.");
    });
    return () => { request.current++; };
  }, [api, account, refresh, zh]);
  const recent = useMemo(() => [...(entries ?? []), ...(plugins ?? [])].sort((a, b) => (b.published_at ?? b.created_at).localeCompare(a.published_at ?? a.created_at)).slice(0, 4), [entries, plugins]);
  const stars = entries?.reduce((sum, entry) => sum + entry.star_count, 0);
  const reviews = entries?.reduce((sum, entry) => sum + entry.review_count, 0);
  const releases = entries && plugins && !error ? [...entries, ...plugins] : null;
  const published = releases?.filter((entry) => entry.status === "published").length;
  const pending = releases?.filter((entry) => entry.status === "quarantined").length;
  const rejected = releases?.filter((entry) => entry.status === "rejected").length;
  const onPublished = (entry: Release) => {
    confirmedReleases.current = [entry, ...confirmedReleases.current.filter((old) => releaseKey(old) !== releaseKey(entry))];
    if ("source_hash" in entry) setEntries((current) => [entry, ...(current ?? []).filter((old) => releaseKey(old) !== releaseKey(entry))]);
    else setPlugins((current) => [entry, ...(current ?? []).filter((old) => releaseKey(old) !== releaseKey(entry))]);
  };
  if (status === "booting") return <LoadingState label={zh ? "正在读取账号…" : "Loading account…"} />;
  if (!account) return <div className="registry-sign-in"><h1>{zh ? "我的" : "Mine"}</h1><Panel><EmptyState icon={LogIn} title={zh ? "登录后查看你的社区内容" : "Sign in to see your Community content"} detail={zh ? "管理发布、收藏、公开资料与账号安全。" : "Manage releases, saved resources, your profile, and account security."} /><LinkButton href="#/login" variant="primary">{zh ? "登录社区" : "Sign in"}</LinkButton></Panel></div>;

  const resourceCards = [
    { id: "agent", name: "Agent", icon: Bot, detail: zh ? "桌面版导出的 Agent 定义" : "An Agent definition exported from Desktop", label: zh ? "可上传" : "Upload", enabled: true },
    { id: "project", name: "Project", icon: FolderKanban, detail: zh ? "完整工作空间，包含项目资料" : "A full workspace including project material", label: zh ? "暂未开放" : "Not available", enabled: false },
    { id: "workflow", name: "Workflow", icon: Workflow, detail: zh ? "固定版本 Agent 的编排流程" : "Orchestration of pinned Agent versions", label: zh ? "分享包待接通" : "Sharing not connected", enabled: false },
    { id: "plugin", name: "Plugin Pack", icon: PackageOpen, detail: zh ? "声明式 Skill 与 MCP 插件包" : "A declarative Skill and MCP package", label: zh ? "可上传" : "Upload", enabled: true },
    { id: "template", name: "Template", icon: LayoutTemplate, detail: zh ? "可复用的起点与配置" : "Reusable starting points and configuration", label: zh ? "暂未开放" : "Not available", enabled: false },
    { id: "resources", name: zh ? "可复用资源" : "Resources", icon: PackageOpen, detail: zh ? "独立 Skill 与 Tool 资源" : "Standalone Skills and Tools", label: zh ? "可随插件包发布" : "Share in a Plugin Pack", enabled: false },
  ];
  const statusLabel = (entry: Release) => entry.status === "published" ? (zh ? "已发布" : "Published") : entry.status === "quarantined" ? (zh ? "审核中" : "In review") : (zh ? "已拒绝" : "Rejected");
  return <div className="creator-page">
    <section className="creator-identity" aria-label={zh ? "我的社区资料" : "My Community profile"}>
      <div className="creator-avatar">{account.avatar_url ? <img src={account.avatar_url} alt="" /> : (account.display_name || account.handle).slice(0, 1).toUpperCase()}</div>
      <div className="creator-identity-copy"><div><h1>{account.display_name || account.handle}</h1><StatusBadge label={zh ? "已登录" : "Signed in"} tone="good" /></div><p>@{account.handle}</p><p>{zh ? "从桌面导出，在这里发布。只上传你明确选择的资源包。" : "Export on Desktop. Publish here. Upload only the resource packages you choose."}</p></div>
      <LinkButton icon={Settings2} href="#/community/mine/settings" variant="ghost">{zh ? "资料与安全" : "Profile and security"}</LinkButton>
    </section>
    <section className="creator-stats" aria-label={zh ? "版本统计" : "Release statistics"}>
      {[{ icon: Bot, label: zh ? "已发布版本" : "Published versions", value: published }, { icon: Clock3, label: zh ? "审核中" : "In review", value: pending }, { icon: CircleAlert, label: zh ? "已拒绝" : "Rejected", value: rejected }, { icon: Star, label: zh ? "版本获收藏" : "Release stars", value: stars }].map(({ icon: Icon, label, value }) => <div key={label}><Icon size={19} aria-hidden="true" /><strong>{value ?? "—"}</strong><span>{label}</span></div>)}
    </section>
    {error ? <ErrorState message={error} retryLabel={zh ? "重试" : "Retry"} onRetry={() => setRefresh((value) => value + 1)} /> : null}
    <div className="creator-columns"><section className="creator-publish-panel" aria-labelledby="creator-publish-title">
      <div className="creator-section-heading"><p>{zh ? "发布中心" : "Publishing"}</p><h2 id="creator-publish-title">{zh ? "选择要发布的内容" : "Choose what to publish"}</h2><span>{zh ? "从桌面版导出文件，先检查内容，再确认上传。" : "Export a file from Desktop, inspect it here, then confirm the upload."}</span></div>
      <div className="creator-resource-types" role="group" aria-label={zh ? "发布资源类型" : "Publication type"}>{resourceCards.map(({ id, name, icon: Icon, detail, label, enabled }) => <button key={id} type="button" disabled={!enabled} aria-pressed={enabled ? kind === id : undefined} onClick={() => setKind(id as PublicationKind)}><Icon size={25} aria-hidden="true" /><strong>{name}</strong><span>{detail}</span><small>{label}</small>{enabled ? <ArrowRight size={17} className="creator-resource-arrow" aria-hidden="true" /> : null}</button>)}</div>
      <PublicationUpload key={kind} kind={kind} onPublished={onPublished} />
    </section><aside className="creator-summary">
      <section><div className="creator-summary-heading"><h2>{zh ? "最近版本" : "Recent releases"}</h2><a href={communityRoutePaths.published}>{zh ? "查看全部" : "View all"}</a></div>{!entries && !error ? <p>{zh ? "正在读取…" : "Loading…"}</p> : recent.length ? recent.map((entry) => <article key={releaseKey(entry)}><strong>{"source_hash" in entry ? <a href={communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version)}>{entry.name}</a> : entry.name}</strong><p>{"source_hash" in entry ? "Agent" : "Plugin Pack"} · v{entry.version}</p><StatusBadge label={statusLabel(entry)} tone={entry.status === "published" ? "good" : entry.status === "quarantined" ? "warn" : "bad"} /></article>) : <p>{zh ? "还没有发布记录。" : "No releases yet."}</p>}</section>
      <section><h2>{zh ? "待处理" : "Needs attention"}</h2>{!releases ? <p>{zh ? "读取发布记录后显示" : "Available after releases load"}</p> : pending || rejected ? <p><a href={communityRoutePaths.published}>{zh ? `${pending ?? 0} 个版本审核中，${rejected ?? 0} 个版本需修改` : `${pending ?? 0} in review, ${rejected ?? 0} need changes`}</a></p> : <p><CheckCircle2 size={16} />{zh ? "暂无待处理事项" : "Nothing needs attention"}</p>}</section>
      <section><h2>{zh ? "社区反馈" : "Community feedback"}</h2><p><Star size={16} />{zh ? "版本获收藏" : "Release stars"}：{stars ?? "—"}</p><p><MessageSquare size={16} />{zh ? "评价" : "Reviews"}：{reviews ?? "—"}</p></section>
    </aside></div>
  </div>;
}
