import { ArrowUpRight, Download, Filter, GitFork, Search, ShieldCheck, Star } from "lucide-react";
import { useState } from "react";
import type { CommunityEntry } from "@veyra/api-contracts";
import { Button, LinkButton, Panel, StatusBadge, Tag } from "@veyra/ui";

const entries: CommunityEntry[] = [
  { id: "research-brief", name: "Research Brief", author: "north-star", summary: "Turn a bounded question into a sourced, reviewable brief.", version: "v1.3", category: "Research", installs: "2.4k", verified: true },
  { id: "issue-triage", name: "Issue Triage", author: "signal-lab", summary: "Sort incoming issues, request approval, and record a checked response.", version: "v0.9", category: "Operations", installs: "1.8k", verified: true },
  { id: "release-notes", name: "Release Notes", author: "paper-plane", summary: "Collect changes and prepare a release note with explicit review points.", version: "v0.6", category: "Writing", installs: "940", verified: false },
  { id: "meeting-synthesis", name: "Meeting Synthesis", author: "clear-room", summary: "Turn notes into decisions, open questions, and follow-up work.", version: "v0.4", category: "Communication", installs: "730", verified: true },
];

export function CatalogPage({ collection }: { collection: "all" | "collections" }) {
  const [query, setQuery] = useState("");
  const filtered = entries.filter((entry) => `${entry.name} ${entry.summary} ${entry.category}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">Inspect before import</span><h2>{collection === "collections" ? "Curated collections" : "Agents built to be understood."}</h2><p>Browse portable definitions with visible hashes, permissions, compatibility, and lineage.</p></div><Tag tone="good">{filtered.length} entries</Tag></div><div className="catalog-toolbar"><label className="search-box" htmlFor="catalog-search"><Search size={16} /><input id="catalog-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search entries" /></label><div className="catalog-filters"><Button icon={Filter} size="sm">Filters</Button><Tag>Agent</Tag><Tag>Any version</Tag></div></div><div className="community-entry-grid">{filtered.map((entry) => <Panel className="community-entry-card" key={entry.id}><div className="entry-card-header"><span className="entry-icon"><GitFork size={18} /></span><StatusBadge label={entry.verified ? "Verified claim" : "Unverified"} tone={entry.verified ? "good" : "warn"} /></div><h3>{entry.name}</h3><p>{entry.summary}</p><div className="entry-meta"><span>by {entry.author}</span><span>{entry.category}</span><span>{entry.version}</span></div><div className="entry-stats"><span><Download size={13} /> {entry.installs}</span><span><Star size={13} /> 4.8</span><span><ShieldCheck size={13} /> {entry.verified ? "Checked" : "Claimed"}</span></div><LinkButton href={`#/entry/${entry.id}`} icon={ArrowUpRight} variant="secondary" size="sm">Inspect entry</LinkButton></Panel>)}</div>{filtered.length === 0 ? <Panel><div className="community-empty"><Search size={20} /><strong>No matching entries.</strong><span>Try a broader term or clear the search.</span></div></Panel> : null}</div>;
}
