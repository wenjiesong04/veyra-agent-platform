import { ArrowLeft, ArrowUpRight, Download, GitFork, Globe2, ShieldCheck, Star } from "lucide-react";
import { communityEntries, communityRoutePaths, type CommunityEntry } from "@veyra/api-contracts";
import { LinkButton, Panel, StatusBadge, Tag } from "@veyra/ui";
import { NotFoundPage } from "./not-found";

export function CommunityPage({ owner, slug, versionId }: { owner?: string; slug?: string; versionId?: string }) {
  const entry = owner && slug ? communityEntries.find((item) => item.owner === owner && item.slug === slug) : undefined;
  if (owner && slug && !entry) return <NotFoundPage backHref={communityRoutePaths.catalog} backLabel="Back to Community" />;
  if (entry && versionId && !entry.versions.some((version) => version.id === versionId)) return <NotFoundPage backHref={communityRoutePaths.entry(entry.owner, entry.slug)} backLabel="Back to Entry" />;
  const entries: CommunityEntry[] = communityEntries;
  return (
    <div className="page-stack">
      {entry ? <div className="page-intro"><div><span className="ui-eyebrow">Community entry / {entry.category}</span><h2>{entry.name}</h2><p>{entry.summary}</p></div><div className="intro-actions"><LinkButton href={communityRoutePaths.catalog} icon={ArrowLeft} variant="ghost">Back to Community</LinkButton><LinkButton href={communityRoutePaths.version(entry.owner, entry.slug, entry.versionId)} icon={ArrowUpRight} variant="primary">Open current version</LinkButton></div></div> : <div className="page-intro"><div><span className="ui-eyebrow">Version-aware catalog</span><h2>Find something worth importing.</h2><p>Inspect source, behavior, permissions, and lineage before a package enters your local library.</p></div><LinkButton href={communityRoutePaths.catalog} icon={Globe2} variant="primary">Open catalog</LinkButton></div>}
      {entry ? <Panel><div className="community-detail-facts"><div><span>Owner</span><strong>{entry.owner}</strong></div><div><span>Version</span><strong>{versionId ?? entry.version}</strong></div><div><span>Behavior hash</span><strong>{entry.versions.find((version) => version.id === (versionId ?? entry.versionId))?.behaviorHash}</strong></div><div><span>Claim</span><StatusBadge label={entry.verified ? "Verified claim" : "Unverified"} tone={entry.verified ? "good" : "warn"} /></div></div></Panel> : null}
      <div className="catalog-toolbar"><span>Featured Agents</span><div><Tag tone="good">Local import</Tag><Tag>{entries.length} results</Tag></div></div>
      {!entry ? <div className="community-grid">{entries.map((entry) => <Panel className="community-card" key={entry.id}><div className="community-card-top"><span className="entry-icon"><Globe2 size={18} /></span><StatusBadge label={entry.verified ? "Verified claim" : "Unverified"} tone={entry.verified ? "good" : "warn"} /></div><h3>{entry.name}</h3><p>{entry.summary}</p><div className="entry-meta"><span>{entry.author}</span><span>{entry.category}</span><span>{entry.version}</span></div><div className="entry-footer"><span><Download size={13} /> {entry.installs} imports</span><span><Star size={13} /> 4.8</span><LinkButton href={communityRoutePaths.entry(entry.owner, entry.slug)} icon={ArrowUpRight} size="sm" variant="ghost">Inspect</LinkButton></div></Panel>)}</div> : null}
      <Panel className="lineage-panel"><div className="boundary-mark"><GitFork size={17} /></div><div><strong>Import is a second validation boundary.</strong><p>Packages carry hashes, permissions, compatibility, and provenance; local import checks them again before use.</p></div><ShieldCheck size={19} /></Panel>
    </div>
  );
}
