import { ArrowUpRight, Download, Filter, Search, ShieldCheck, Star } from "lucide-react";
import { useState } from "react";
import { communityEntries, communityRoutePaths } from "@veyra/api-contracts";
import { Button, EmptyState, LinkButton, Panel, StatusBadge, Tag, useLocale } from "@veyra/ui";

export function CatalogPage() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "导入前检查", title: "让 Agent 清晰可理解。", description: "浏览可移植定义，查看哈希、权限、兼容性和来源关系。", entries: "个条目", search: "搜索条目", filters: "筛选", agent: "Agent", anyVersion: "所有版本", verified: "已验证声明", unverified: "未验证", by: "作者", checked: "已检查", claimed: "已声明", inspect: "检查", noMatch: "没有匹配条目。", broaden: "尝试更宽泛的关键词，或清除搜索。",
  } : {
    eyebrow: "Inspect before import", title: "Agents built to be understood.", description: "Browse portable definitions with visible hashes, permissions, compatibility, and lineage.", entries: "entries", search: "Search entries", filters: "Filters", agent: "Agent", anyVersion: "Any version", verified: "Verified claim", unverified: "Unverified", by: "by", checked: "Checked", claimed: "Claimed", inspect: "Inspect", noMatch: "No matching entries.", broaden: "Try a broader term or clear the search.",
  };
  const [query, setQuery] = useState("");
  const filtered = communityEntries.filter((entry) => `${entry.name} ${entry.summary} ${entry.category}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><Tag tone="good">{filtered.length} {copy.entries}</Tag></div><div className="catalog-toolbar"><label className="search-box" htmlFor="catalog-search"><Search size={16} /><input id="catalog-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.search} /></label><div className="catalog-filters"><Button icon={Filter} size="sm">{copy.filters}</Button><Tag>{copy.agent}</Tag><Tag>{copy.anyVersion}</Tag></div></div><div className="community-entry-grid">{filtered.map((entry) => <Panel className="community-entry-card" key={entry.id}><div className="entry-card-header"><span className="entry-icon"><Search size={18} /></span><StatusBadge label={entry.verified ? copy.verified : copy.unverified} tone={entry.verified ? "good" : "warn"} /></div><h3>{entry.name}</h3><p>{entry.summary}</p><div className="entry-meta"><span>{copy.by} {entry.author}</span><span>{entry.category}</span><span>{entry.version}</span></div><div className="entry-stats"><span><Download size={13} /> {entry.installs}</span><span><Star size={13} /> 4.8</span><span><ShieldCheck size={13} /> {entry.verified ? copy.checked : copy.claimed}</span></div><LinkButton href={communityRoutePaths.entry(entry.owner, entry.slug)} icon={ArrowUpRight} variant="secondary" size="sm">{copy.inspect} {entry.name}</LinkButton></Panel>)}</div>{filtered.length === 0 ? <Panel><EmptyState icon={Search} title={copy.noMatch} detail={copy.broaden} /></Panel> : null}</div>;
}
