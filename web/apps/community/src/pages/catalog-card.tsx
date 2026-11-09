import { Bookmark, Bot, Download, GitBranch, PackageOpen, Star } from "lucide-react";
import { useState } from "react";
import { communityRoutePaths, type CommunityPluginEntry, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { toast, useLocale } from "@veyra/ui";
import { useAuth } from "@veyra/connected-account";

export type CatalogResource = { kind: "agent"; entry: CommunityRegistryEntry } | { kind: "plugin"; entry: CommunityPluginEntry };
export function catalogKey(resource: CatalogResource): string {
  return `${resource.kind}/${resource.entry.owner_handle}/${resource.entry.slug}/${resource.entry.version}`;
}

export function CatalogCard({ resource, starred, onToggleStar }: { resource: CatalogResource; starred: boolean; onToggleStar?: () => Promise<void> }) {
  const { locale } = useLocale();
  const { api } = useAuth();
  const zh = locale === "zh";
  const { entry } = resource;
  const agent = resource.kind === "agent" ? resource.entry : null;
  const href = agent ? communityRoutePaths.version(entry.owner_handle, entry.slug, entry.version) : null;
  const risk = agent?.capabilities?.risk_level ?? agent?.scan?.risk_level;
  const [busy, setBusy] = useState(false);
  const label = starred ? (zh ? "取消收藏" : "Unstar") : (zh ? "收藏" : "Star");
  const toggle = async () => {
    if (!onToggleStar) return;
    setBusy(true);
    try { await onToggleStar(); } finally { setBusy(false); }
  };
  const downloadPack = async () => {
    setBusy(true);
    try {
      const blob = await api.downloadRegistryPlugin(entry.owner_handle, entry.slug, entry.version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = `${entry.slug}-${entry.version}.vplugin.zip`; link.click(); URL.revokeObjectURL(url);
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : (zh ? "下载失败。" : "Download failed.")); }
    finally { setBusy(false); }
  };
  return <article className="registry-card">
    <div className="registry-card-top"><div className="registry-card-tags">
      <span>{agent ? "Agent" : "Plugin Pack"}</span>
      {risk ? <span className={`registry-risk-${risk}`}>{zh ? { low: "低风险", medium: "中风险", high: "高风险" }[risk] : `${risk} risk`}</span> : null}
      {entry.status !== "published" ? <span>{entry.status === "quarantined" ? (zh ? "审核中" : "In review") : (zh ? "已拒绝" : "Rejected")}</span> : null}
    </div>{onToggleStar ? <button type="button" className="registry-save" aria-label={`${label} ${entry.name}`} aria-pressed={starred} disabled={busy} onClick={() => void toggle()}><Bookmark size={18} fill={starred ? "currentColor" : "none"} /></button> : resource.kind === "plugin" && entry.status === "published" ? <button type="button" className="registry-save" aria-label={`${zh ? "下载插件包" : "Download Plugin Pack"} ${entry.name}`} title={zh ? "下载插件包，在桌面版导入" : "Download this pack to import in Desktop"} disabled={busy} onClick={() => void downloadPack()}><Download size={18} /></button> : null}</div>
    <div className={`registry-cover registry-cover-${resource.kind}`} aria-hidden="true"><span className="registry-cover-node">{agent ? <Bot size={26} /> : <PackageOpen size={26} />}</span><i /><i /></div>
    <div className="registry-card-copy"><h2>{href ? <a href={href}>{entry.name}</a> : entry.name}</h2><p>{entry.description}</p></div>
    <div className="registry-card-author">{entry.owner_avatar_url ? <img src={entry.owner_avatar_url} alt="" /> : <span aria-hidden="true">{(entry.owner_display_name || entry.owner_handle).slice(0, 1).toUpperCase()}</span>}{entry.owner_display_name || entry.owner_handle}</div>
    <div className="registry-card-metrics">{agent ? <><span><Star size={14} />{agent.star_count}</span><span><GitBranch size={14} />{agent.capabilities?.node_count ?? 0} {zh ? "个节点" : "nodes"}</span></> : <span>{resource.kind === "plugin" ? `${resource.entry.skill_count} Skills · ${resource.entry.mcp_count} MCP` : null}</span>}<span>v{entry.version}</span></div>
  </article>;
}
