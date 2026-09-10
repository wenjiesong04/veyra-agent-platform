import { ArrowLeft, Download, GitFork, Globe2, RefreshCw, ShieldCheck } from "lucide-react";
import { communityRoutePaths, desktopRoutePaths, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useAuth } from "@veyra/connected-account";
import { useCallback, useEffect, useState } from "react";
import { NotFoundPage } from "./not-found";

export function CommunityPage({ owner, slug, versionId }: { owner?: string; slug?: string; versionId?: string }) {
  const { locale } = useLocale();
  const { api } = useAuth();
  const zh = locale === "zh";
  const copy = zh ? {
    backCommunity: "返回社区",
    eyebrow: "社区注册表",
    title: "社区 Agent 注册表",
    unavailableTitle: "社区目录暂时不可用。",
    description: "浏览已发布的 Agent 版本，先检查来源和哈希，再下载到本机 Project 导入。Community 不会执行下载的 Agent。",
    openAccount: "打开账号",
    emptyTitle: "还没有已发布的 Agent",
    emptyDetail: "发布后的 Agent 版本会出现在这里。下载后仍需在本机 Project 中再次导入和校验。",
    lineageTitle: "导入是第二道验证边界。",
    lineageDetail: "包会携带哈希、权限、兼容性和来源信息；本机导入前会再次检查。现在没有可检查的远程条目。",
  } : {
    backCommunity: "Back to Community",
    eyebrow: "Community registry",
    title: "Community Agent registry",
    unavailableTitle: "The Community catalog is not connected.",
    description: "Browse published Agent versions, inspect provenance and hashes, then download them for local Project import. Community never executes downloaded Agents.",
    openAccount: "Open account",
    emptyTitle: "No published Agents yet",
    emptyDetail: "Published Agent versions will appear here. Downloaded packages still require local Project import and validation.",
    lineageTitle: "Import is a second validation boundary.",
    lineageDetail: "Packages carry hashes, permissions, compatibility, and provenance; local import checks them again before use. There is nothing remote to inspect yet.",
  };
  const [entries, setEntries] = useState<CommunityRegistryEntry[]>([]);
  const [selected, setSelected] = useState<CommunityRegistryEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (owner && slug) {
        setSelected(await api.getRegistryAgent(owner, slug, versionId));
      } else {
        setSelected(null);
        setEntries(await api.listRegistryAgents());
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "Community 注册表暂时不可用。" : "The Community registry is unavailable."));
    } finally {
      setLoading(false);
    }
  }, [api, owner, slug, versionId, zh]);
  useEffect(() => { void load(); }, [load]);

  const download = async () => {
    if (!selected) return;
    setDownloading(true);
    try {
      const blob = await api.downloadRegistryAgent(selected.owner_handle, selected.slug, selected.version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${selected.slug}-${selected.version}.vagent.yaml`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "下载失败。" : "Download failed."));
    } finally {
      setDownloading(false);
    }
  };
  if (owner || slug || versionId) {
    if (loading) return <LoadingState label={zh ? "正在读取社区 Agent…" : "Loading Community Agent…"} />;
    if (error || !selected) return <NotFoundPage backHref={communityRoutePaths.catalog} backLabel={copy.backCommunity} />;
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{selected.name}</h2><p>{selected.description}</p></div><LinkButton href={communityRoutePaths.catalog} icon={ArrowLeft} variant="ghost">{copy.backCommunity}</LinkButton></div><Panel><div className="community-entry-header"><div><strong>{selected.owner_display_name || selected.owner_handle}</strong><small>@{selected.owner_handle} / {selected.slug}</small></div><Tag>v{selected.version}</Tag><StatusBadge label={selected.status} tone="good" /></div><SectionHeading eyebrow={zh ? "版本证据" : "Version evidence"} title={zh ? "发布哈希" : "Published hashes"} detail={zh ? "下载前先核对不可变来源；导入时本机还会再次校验。" : "Check the immutable provenance before download; local import validates it again."} /><div className="settings-facts"><div><span>Source SHA-256</span><strong>{selected.source_hash}</strong></div><div><span>Behavior SHA-256</span><strong>{selected.behavior_hash}</strong></div><div><span>Lock SHA-256</span><strong>{selected.lock_hash}</strong></div><div><span>{zh ? "发布时间" : "Published"}</span><strong>{selected.published_at || selected.created_at}</strong></div></div><div className="button-row"><Button icon={Download} variant="primary" disabled={downloading} onClick={() => void download()}>{downloading ? "…" : (zh ? "下载 Agent" : "Download Agent")}</Button></div>{error ? <ErrorState message={error} onRetry={() => void load()} /> : null}</Panel></div>;
  }
  return (
    <div className="page-stack">
        <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{error ? copy.unavailableTitle : copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions"><Button icon={RefreshCw} variant="ghost" onClick={() => void load()} disabled={loading}>{zh ? "刷新" : "Refresh"}</Button><LinkButton href={desktopRoutePaths.account} icon={Globe2} variant="ghost">{copy.openAccount}</LinkButton></div>
      </div>
      {loading ? <Panel><LoadingState label={zh ? "正在读取社区目录…" : "Loading Community registry…"} /></Panel> : error ? <><ErrorState message={error} onRetry={() => void load()} /><Panel><EmptyState icon={Globe2} title={copy.emptyTitle} detail={copy.emptyDetail} /></Panel></> : entries.length ? <Panel><SectionHeading eyebrow={zh ? "已发布" : "Published"} title={`${entries.length} ${zh ? "个版本" : "versions"}`} /><div className="run-list">{entries.map((entry) => <a className="run-row" href={communityRoutePaths.entry(entry.owner_handle, entry.slug)} key={`${entry.owner_handle}/${entry.slug}/${entry.version}`}><span className="run-state-icon"><Globe2 size={17} /></span><span className="row-copy"><strong>{entry.name}</strong><small>@{entry.owner_handle} · {entry.slug} · v{entry.version}</small><em>{entry.description}</em></span><StatusBadge label={entry.status} tone="good" /></a>)}</div></Panel> : <EmptyState icon={Globe2} title={copy.emptyTitle} detail={copy.emptyDetail} />}
      <Panel className="lineage-panel">
        <div className="boundary-mark"><GitFork size={17} /></div>
        <div><strong>{copy.lineageTitle}</strong><p>{copy.lineageDetail}</p></div>
        <ShieldCheck size={19} />
      </Panel>
    </div>
  );
}
