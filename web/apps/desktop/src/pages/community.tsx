import { ArrowUpRight, Download, GitFork, Globe2, ShieldCheck, Star } from "lucide-react";
import type { CommunityEntry } from "@veyra/api-contracts";
import { LinkButton, Panel, StatusBadge, Tag } from "@veyra/ui";

const entries: CommunityEntry[] = [
  { id: "research-brief", name: "Research Brief", author: "north-star", summary: "Turn a bounded question into a sourced, reviewable brief.", version: "v1.3", category: "Research", installs: "2.4k", verified: true },
  { id: "issue-triage", name: "Issue Triage", author: "signal-lab", summary: "Sort incoming issues, request approval, and record a checked response.", version: "v0.9", category: "Operations", installs: "1.8k", verified: true },
  { id: "release-notes", name: "Release Notes", author: "paper-plane", summary: "Collect changes and prepare a release note with explicit review points.", version: "v0.6", category: "Writing", installs: "940", verified: false },
];

export function CommunityPage() {
  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">Version-aware catalog</span><h2>Find something worth importing.</h2><p>Inspect source, behavior, permissions, and lineage before a package enters your local library.</p></div><LinkButton href="#/community" icon={Globe2} variant="primary">Open catalog</LinkButton></div>
      <div className="catalog-toolbar"><span>Featured Agents</span><div><Tag tone="good">Local import</Tag><Tag>3 results</Tag></div></div>
      <div className="community-grid">{entries.map((entry) => <Panel className="community-card" key={entry.id}><div className="community-card-top"><span className="entry-icon"><Globe2 size={18} /></span><StatusBadge label={entry.verified ? "Verified claim" : "Unverified"} tone={entry.verified ? "good" : "warn"} /></div><h3>{entry.name}</h3><p>{entry.summary}</p><div className="entry-meta"><span>{entry.author}</span><span>{entry.category}</span><span>{entry.version}</span></div><div className="entry-footer"><span><Download size={13} /> {entry.installs} imports</span><span><Star size={13} /> 4.8</span><LinkButton href={`#/community/${entry.id}`} icon={ArrowUpRight} size="sm" variant="ghost">Inspect</LinkButton></div></Panel>)}</div>
      <Panel className="lineage-panel"><div className="boundary-mark"><GitFork size={17} /></div><div><strong>Import is a second validation boundary.</strong><p>Packages carry hashes, permissions, compatibility, and provenance; local import checks them again before use.</p></div><ShieldCheck size={19} /></Panel>
    </div>
  );
}
