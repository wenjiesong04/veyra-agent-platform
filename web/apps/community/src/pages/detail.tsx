import { ArrowLeft, Download } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { communityRoutePaths, type CommunityRegistryEntry } from "@veyra/api-contracts";
import { Button, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useAuth } from "@veyra/connected-account";
import { CommunityNotFoundPage } from "./not-found";

export function EntryDetailPage({ owner, slug, versionId }: { owner: string; slug: string; versionId?: string }) {
  const { locale } = useLocale();
  const { api } = useAuth();
  const zh = locale === "zh";
  const copy = zh ? {
    back: "返回目录", loading: "正在读取 Agent 版本…", unavailable: "无法读取此 Community 版本。", retry: "重试", download: "下载 Agent YAML", downloading: "正在下载…", hashes: "版本哈希", source: "Source SHA-256", behavior: "Behavior SHA-256", lock: "Lock SHA-256", published: "发布时间", noCapabilities: "此版本没有能力摘要。", capabilityDetail: "基于不可变 Agent Source 生成；这些声明不代表本机已经绑定依赖或授予权限。", tools: "工具", skills: "Skills", policies: "Policies", knowledge: "Knowledge 引用", permissions: "权限声明", network: "网络主机", read: "读取范围", write: "写入范围", secrets: "Secret 引用", none: "无", scan: "发布扫描", warnings: "扫描提示", versions: "可用版本", downloaded: "下载已开始。", downloadError: "下载失败。", noScan: "无扫描记录",
  } : {
    back: "Back to catalog", loading: "Loading Agent version…", unavailable: "This Community version could not be loaded.", retry: "Retry", download: "Download Agent YAML", downloading: "Downloading…", hashes: "Version hashes", source: "Source SHA-256", behavior: "Behavior SHA-256", lock: "Lock SHA-256", published: "Published", noCapabilities: "No capability summary is available for this version.", capabilityDetail: "Derived from the immutable Agent source; declarations do not mean dependencies are locally bound or permissions granted.", tools: "Tools", skills: "Skills", policies: "Policies", knowledge: "Knowledge refs", permissions: "Declared permissions", network: "Network hosts", read: "Read roots", write: "Write roots", secrets: "Secret refs", none: "None", scan: "Publication scan", warnings: "Scan warnings", versions: "Available versions", downloaded: "Download started.", downloadError: "Download failed.", noScan: "Not scanned",
  };
  const [entry, setEntry] = useState<CommunityRegistryEntry | null>(null);
  const [versions, setVersions] = useState<CommunityRegistryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [detail, history] = await Promise.all([
        api.getRegistryAgent(owner, slug, versionId),
        api.listRegistryAgentVersions(owner, slug),
      ]);
      setEntry(detail);
      setVersions(history);
    } catch (cause) {
      setEntry(null);
      setError(cause instanceof Error ? cause.message : copy.unavailable);
    } finally {
      setLoading(false);
    }
  }, [api, copy.unavailable, owner, slug, versionId]);

  useEffect(() => { void load(); }, [load]);

  const download = async () => {
    if (!entry) return;
    setDownloading(true);
    try {
      const blob = await api.downloadRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${entry.slug}-${entry.version}.vagent.yaml`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.downloadError);
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <LoadingState label={copy.loading} />;
  if (!entry) {
    if (/not found|404|registry_entry_not_found/i.test(error)) return <CommunityNotFoundPage message={zh ? "找不到此已发布 Agent 或版本。" : "Community Agent or version not found."} />;
    return <div className="community-page-stack"><ErrorState message={`${copy.unavailable} ${error}`} onRetry={() => void load()} /><Button onClick={() => void load()}>{copy.retry}</Button></div>;
  }

  const capabilities = entry.capabilities;
  const values = (items: string[] | undefined) => items?.length ? items.join(", ") : copy.none;
  return <div className="community-page-stack">
    <LinkButton href={communityRoutePaths.catalog} icon={ArrowLeft} variant="ghost" size="sm">{copy.back}</LinkButton>
    <div className="detail-hero"><div>
      <span className="ui-eyebrow">Community Agent / {entry.slug}</span><h2>{entry.name}</h2><p>{entry.description}</p>
      <div className="detail-author"><span className="author-avatar">{entry.owner_handle[0]?.toUpperCase() ?? "V"}</span><span>Published by <strong>@{entry.owner_handle}</strong></span><Tag>v{entry.version}</Tag><StatusBadge label={entry.scan?.status ?? copy.noScan} tone={entry.scan?.status === "passed" ? "good" : "warn"} /></div>
    </div><Button icon={Download} variant="primary" disabled={downloading} onClick={() => void download()}>{downloading ? copy.downloading : copy.download}</Button></div>

    <Panel>
      <SectionHeading eyebrow={copy.hashes} title={`${entry.slug} · v${entry.version}`} />
      <div className="definition-preview"><div><span><strong>{copy.source}</strong><small>{entry.source_hash}</small></span></div><div><span><strong>{copy.behavior}</strong><small>{entry.behavior_hash}</small></span></div><div><span><strong>{copy.lock}</strong><small>{entry.lock_hash}</small></span></div><div><span><strong>{copy.published}</strong><small>{entry.published_at ?? entry.created_at}</small></span></div></div>
      {entry.fork_of ? <p className="detail-note">Forked from @{entry.fork_of.owner_handle}/{entry.fork_of.slug} v{entry.fork_of.version} · {entry.fork_of.source_hash}</p> : null}
    </Panel>

    {capabilities ? <Panel><SectionHeading eyebrow={copy.permissions} title={copy.permissions} detail={copy.capabilityDetail} />
      <div className="definition-preview"><div><span><strong>{copy.tools}</strong><small>{values(capabilities.tools)}</small></span></div><div><span><strong>{copy.skills}</strong><small>{values(capabilities.skills)}</small></span></div><div><span><strong>{copy.policies}</strong><small>{values(capabilities.policies)}</small></span></div><div><span><strong>{copy.knowledge}</strong><small>{values(capabilities.knowledge)}</small></span></div><div><span><strong>{copy.network}</strong><small>{values(capabilities.permissions.network_hosts)}</small></span></div><div><span><strong>{copy.read}</strong><small>{values(capabilities.permissions.filesystem_read_roots)}</small></span></div><div><span><strong>{copy.write}</strong><small>{values(capabilities.permissions.filesystem_write_roots)}</small></span></div><div><span><strong>{copy.secrets}</strong><small>{values(capabilities.secret_refs)}</small></span></div></div>
      {entry.scan ? <div className="community-scan-summary"><div className="resource-card-meta"><StatusBadge label={entry.scan.status} tone={entry.scan.status === "passed" ? "good" : "warn"} /><Tag>{entry.scan.risk_level} risk</Tag></div>{entry.scan.warnings.map((warning) => <small key={warning.code} className="community-scan-detail">{copy.warnings}: {warning.code}{warning.details.length ? ` · ${warning.details.join(", ")}` : ""}</small>)}</div> : null}
    </Panel> : <Panel><p>{copy.noCapabilities}</p></Panel>}

    {versions.length > 1 ? <Panel><SectionHeading eyebrow={copy.versions} title={copy.versions} /><div className="community-version-list">{versions.map((item) => <a key={item.version} href={communityRoutePaths.version(item.owner_handle, item.slug, item.version)} className={item.version === entry.version ? "is-current" : ""}>v{item.version} · {item.source_hash.slice(0, 12)}</a>)}</div></Panel> : null}
  </div>;
}
