import { ArrowLeft, ArrowUpRight, Download, GitFork, Globe2, ShieldCheck, Star } from "lucide-react";
import { communityEntries, communityRoutePaths, type CommunityEntry } from "@veyra/api-contracts";
import { LinkButton, Panel, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { NotFoundPage } from "./not-found";

export function CommunityPage({ owner, slug, versionId }: { owner?: string; slug?: string; versionId?: string }) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    backCommunity: "返回社区", backEntry: "返回条目", eyebrow: "版本化目录", entryEyebrow: "社区条目", title: "找到值得导入的内容。", description: "在包进入本机库前，检查源文件、行为、权限和来源关系。", openCatalog: "打开目录", currentVersion: "打开当前版本", owner: "所有者", version: "版本", behaviorHash: "行为哈希", claim: "声明", verified: "已验证声明", unverified: "未验证", featured: "精选 Agent", localImport: "本机导入", results: "个结果", inspect: "检查", imports: "次导入", lineageTitle: "导入是第二道验证边界。", lineageDetail: "包会携带哈希、权限、兼容性和来源信息；本机导入前会再次检查。",
  } : {
    backCommunity: "Back to Community", backEntry: "Back to Entry", eyebrow: "Version-aware catalog", entryEyebrow: "Community entry", title: "Find something worth importing.", description: "Inspect source, behavior, permissions, and lineage before a package enters your local library.", openCatalog: "Open catalog", currentVersion: "Open current version", owner: "Owner", version: "Version", behaviorHash: "Behavior hash", claim: "Claim", verified: "Verified claim", unverified: "Unverified", featured: "Featured Agents", localImport: "Local import", results: "results", inspect: "Inspect", imports: "imports", lineageTitle: "Import is a second validation boundary.", lineageDetail: "Packages carry hashes, permissions, compatibility, and provenance; local import checks them again before use.",
  };
  const entry = owner && slug ? communityEntries.find((item) => item.owner === owner && item.slug === slug) : undefined;
  if (owner && slug && !entry) return <NotFoundPage backHref={communityRoutePaths.catalog} backLabel={copy.backCommunity} />;
  if (entry && versionId && !entry.versions.some((version) => version.id === versionId)) return <NotFoundPage backHref={communityRoutePaths.entry(entry.owner, entry.slug)} backLabel={copy.backEntry} />;
  const entries: CommunityEntry[] = communityEntries;
  return (
    <div className="page-stack">
      {entry ? <div className="page-intro"><div><span className="ui-eyebrow">{copy.entryEyebrow} / {entry.category}</span><h2>{entry.name}</h2><p>{entry.summary}</p></div><div className="intro-actions"><LinkButton href={communityRoutePaths.catalog} icon={ArrowLeft} variant="ghost">{copy.backCommunity}</LinkButton><LinkButton href={communityRoutePaths.version(entry.owner, entry.slug, entry.versionId)} icon={ArrowUpRight} variant="primary">{copy.currentVersion}</LinkButton></div></div> : <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><LinkButton href={communityRoutePaths.catalog} icon={Globe2} variant="primary">{copy.openCatalog}</LinkButton></div>}
      {entry ? <Panel><div className="community-detail-facts"><div><span>{copy.owner}</span><strong>{entry.owner}</strong></div><div><span>{copy.version}</span><strong>{versionId ?? entry.version}</strong></div><div><span>{copy.behaviorHash}</span><strong>{entry.versions.find((version) => version.id === (versionId ?? entry.versionId))?.behaviorHash}</strong></div><div><span>{copy.claim}</span><StatusBadge label={entry.verified ? copy.verified : copy.unverified} tone={entry.verified ? "good" : "warn"} /></div></div></Panel> : null}
      <div className="catalog-toolbar"><span>{copy.featured}</span><div><Tag tone="good">{copy.localImport}</Tag><Tag>{entries.length} {copy.results}</Tag></div></div>
      {!entry ? <div className="community-grid">{entries.map((entry) => <Panel className="community-card" key={entry.id}><div className="community-card-top"><span className="entry-icon"><Globe2 size={18} /></span><StatusBadge label={entry.verified ? copy.verified : copy.unverified} tone={entry.verified ? "good" : "warn"} /></div><h3>{entry.name}</h3><p>{entry.summary}</p><div className="entry-meta"><span>{entry.author}</span><span>{entry.category}</span><span>{entry.version}</span></div><div className="entry-footer"><span><Download size={13} /> {entry.installs} {copy.imports}</span><span><Star size={13} /> 4.8</span><LinkButton href={communityRoutePaths.entry(entry.owner, entry.slug)} icon={ArrowUpRight} size="sm" variant="ghost">{copy.inspect}</LinkButton></div></Panel>)}</div> : null}
      <Panel className="lineage-panel"><div className="boundary-mark"><GitFork size={17} /></div><div><strong>{copy.lineageTitle}</strong><p>{copy.lineageDetail}</p></div><ShieldCheck size={19} /></Panel>
    </div>
  );
}
