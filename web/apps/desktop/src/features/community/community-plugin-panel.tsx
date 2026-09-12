import { ArrowLeft, Download, PackageOpen, Upload } from "lucide-react";
import type { CommunityPluginEntry, PluginPack } from "@veyra/api-contracts";
import type { CommunityApi } from "@veyra/connected-account";
import { Button, EmptyState, ErrorState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import type { LocalProjectApi } from "../../api/local-client";

function statusLabel(status: CommunityPluginEntry["status"], zh: boolean): string {
  return zh
    ? { published: "已发布", quarantined: "审核中", rejected: "已拒绝" }[status]
    : { published: "Published", quarantined: "Under review", rejected: "Rejected" }[status];
}

function statusTone(status: CommunityPluginEntry["status"]): "good" | "warn" | "bad" {
  return status === "published" ? "good" : status === "rejected" ? "bad" : "warn";
}

function compareVersions(left: string, right: string): number {
  const parse = (value: string) => value.split(/[.+-]/).map((part) => Number.parseInt(part, 10) || 0);
  const a = parse(left);
  const b = parse(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const difference = (a[index] ?? 0) - (b[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

function localMatch(entry: CommunityPluginEntry, localPlugins: PluginPack[]): PluginPack | null {
  return localPlugins
    .filter((plugin) => plugin.plugin_id === entry.plugin_id)
    .sort((left, right) => compareVersions(left.version, right.version))
    .at(-1) ?? null;
}

export function CommunityPluginPanel({ communityApi, localApi }: { communityApi: CommunityApi; localApi: LocalProjectApi }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [entries, setEntries] = useState<CommunityPluginEntry[]>([]);
  const [localPlugins, setLocalPlugins] = useState<PluginPack[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<CommunityPluginEntry | null>(null);
  const [versions, setVersions] = useState<CommunityPluginEntry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setEntries(await communityApi.listRegistryPlugins());
      if (localApi.listPluginPacks) {
        try {
          setLocalPlugins((await localApi.listPluginPacks()).plugins);
        } catch {
          setLocalPlugins([]);
        }
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件目录暂时不可用。" : "The Plugin registry is unavailable."));
    } finally {
      setLoading(false);
    }
  }, [communityApi, localApi, zh]);

  useEffect(() => { void load(); }, [load]);

  const publish = async (file: File | null) => {
    if (!file) return;
    setBusy("publish");
    setError("");
    setMessage("");
    try {
      const entry = await communityApi.publishRegistryPlugin(file);
      setEntries((current) => [entry, ...current.filter((item) => !(item.owner_handle === entry.owner_handle && item.slug === entry.slug && item.version === entry.version))]);
      setMessage(entry.status === "published" ? (zh ? "插件包已发布。" : "Plugin Pack published.") : (zh ? "插件包已进入审核队列。" : "Plugin Pack submitted for review."));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包发布失败。" : "Plugin Pack publication failed."));
    } finally {
      setBusy(null);
    }
  };

  const download = async (entry: CommunityPluginEntry, importLocal: boolean) => {
    const key = `${importLocal ? "import" : "download"}:${entry.owner_handle}/${entry.slug}/${entry.version}`;
    setBusy(key);
    setError("");
    setMessage("");
    try {
      const blob = await communityApi.downloadRegistryPlugin(entry.owner_handle, entry.slug, entry.version);
      if (importLocal && localApi.importPluginPack) {
        await localApi.importPluginPack(new File([blob], `${entry.slug}-${entry.version}.vplugin.zip`, { type: "application/zip" }));
        if (localApi.listPluginPacks) setLocalPlugins((await localApi.listPluginPacks()).plugins);
        window.location.hash = "#/resources?tab=plugin";
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${entry.slug}-${entry.version}.vplugin.zip`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包下载失败。" : "Plugin Pack download failed."));
    } finally {
      setBusy(null);
    }
  };

  const openDetail = async (entry: CommunityPluginEntry) => {
    const key = `detail:${entry.owner_handle}/${entry.slug}`;
    setBusy(key);
    setError("");
    try {
      const [detail, history] = await Promise.all([
        communityApi.getRegistryPlugin(entry.owner_handle, entry.slug, entry.version),
        communityApi.listRegistryPluginVersions(entry.owner_handle, entry.slug),
      ]);
      setSelected(detail);
      setVersions(history);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件详情加载失败。" : "Plugin details could not be loaded."));
    } finally {
      setBusy(null);
    }
  };

  const switchVersion = async (version: string) => {
    if (!selected || version === selected.version) return;
    const key = `version:${selected.owner_handle}/${selected.slug}/${version}`;
    setBusy(key);
    setError("");
    try {
      setSelected(await communityApi.getRegistryPlugin(selected.owner_handle, selected.slug, version));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件版本加载失败。" : "Plugin version could not be loaded."));
    } finally {
      setBusy(null);
    }
  };

  const localStatus = (entry: CommunityPluginEntry): { label: string; tone: "good" | "warn" | "neutral"; detail: string } => {
    const installed = localMatch(entry, localPlugins);
    if (!installed) return { label: zh ? "本机未安装" : "Not installed locally", tone: "neutral", detail: zh ? "可以下载并导入本机。" : "Download and import it locally." };
    if (installed.content_hash === entry.package_hash) return { label: zh ? "本机已同步" : "Installed and synced", tone: "good", detail: `${zh ? "本机" : "Local"} v${installed.version}` };
    const comparison = compareVersions(installed.version, entry.version);
    return comparison < 0
      ? { label: zh ? "有可用更新" : "Update available", tone: "warn", detail: `${zh ? "本机" : "Local"} v${installed.version} → v${entry.version}` }
      : { label: zh ? "本机版本较新" : "Local version is newer", tone: "neutral", detail: `${zh ? "本机" : "Local"} v${installed.version}` };
  };

  const selectedLocalStatus = selected ? localStatus(selected) : null;
  const detail = selected ? <article className="community-plugin-detail">
    <div className="community-plugin-detail-toolbar"><Button size="sm" variant="ghost" icon={ArrowLeft} onClick={() => { setSelected(null); setVersions([]); }}>{zh ? "返回插件列表" : "Back to Plugin Packs"}</Button><StatusBadge label={statusLabel(selected.status, zh)} tone={statusTone(selected.status)} /></div>
    <div className="community-plugin-card-head"><PackageOpen size={20} aria-hidden="true" /><span className="row-copy"><strong>{selected.name}</strong><small>@{selected.owner_handle} · {selected.plugin_id}</small></span></div>
    <p>{selected.description}</p>
    <div className="community-plugin-detail-facts"><div><span>{zh ? "版本" : "Version"}</span><select value={selected.version} onChange={(event) => void switchVersion(event.target.value)} disabled={busy !== null}>{versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}</select></div><div><span>Package SHA-256</span><code>{selected.package_hash}</code></div><div><span>{zh ? "Skill" : "Skills"}</span><strong>{selected.skill_count}</strong></div><div><span>MCP</span><strong>{selected.mcp_count}</strong></div></div>
    {selectedLocalStatus ? <div className="community-plugin-local-state"><StatusBadge label={selectedLocalStatus.label} tone={selectedLocalStatus.tone} /><span>{selectedLocalStatus.detail}</span></div> : null}
    {selected.skills.length ? <div className="community-plugin-detail-section"><strong>{zh ? "包含的 Skill" : "Included Skills"}</strong>{selected.skills.map((skill) => <div key={skill.reference}><b>{skill.name}</b><small>{skill.reference} · {skill.description}</small></div>)}</div> : null}
    {selected.mcp_servers.length ? <div className="community-plugin-detail-section"><strong>{zh ? "包含的 MCP" : "Included MCP"}</strong>{selected.mcp_servers.map((server) => <div key={server.name}><b>{server.name}</b><small>{server.transport === "stdio" ? (zh ? "本地进程" : "Local process") : server.url}</small></div>)}</div> : null}
    {selected.status === "published" ? <div className="button-row"><Button size="sm" variant="ghost" icon={Download} disabled={busy !== null} onClick={() => void download(selected, false)}>{zh ? "下载包" : "Download"}</Button>{localApi.importPluginPack ? <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void download(selected, true)}>{selectedLocalStatus?.label === (zh ? "有可用更新" : "Update available") ? (zh ? "下载并更新本机" : "Download and update locally") : (zh ? "下载并导入本机" : "Download and import locally")}</Button> : null}</div> : null}
  </article> : null;

  return (
    <Panel className="community-plugin-panel">
      <div className="community-plugin-heading">
        <SectionHeading eyebrow={zh ? "Plugin Packs" : "Plugin Packs"} title={zh ? "社区插件包" : "Community Plugin Packs"} detail={zh ? "发布和发现 Skill + MCP 包。Community 只保存不可变包，不执行其中内容。" : "Publish and discover Skill + MCP packs. Community stores immutable packages and never executes their contents."} />
        <>
          <input ref={inputRef} className="sidebar-import-input" type="file" accept=".vplugin.zip,.zip,application/zip" tabIndex={-1} onChange={(event) => { const file = event.target.files?.item(0) ?? null; event.target.value = ""; void publish(file); }} />
          <Button icon={Upload} variant="primary" disabled={busy !== null} onClick={() => inputRef.current?.click()}>{busy === "publish" ? "…" : (zh ? "发布插件包" : "Publish Pack")}</Button>
        </>
      </div>
      {message ? <p className="plugin-pack-message" role="status">{message}</p> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <p className="resource-detail-muted">{zh ? "正在读取社区插件…" : "Loading Community Plugins…"}</p> : null}
      {!loading && !error && !entries.length ? <EmptyState icon={PackageOpen} title={zh ? "还没有公开插件包" : "No public Plugin Packs yet"} detail={zh ? "可以发布第一个可审查的 Skill + MCP 包。" : "Publish the first reviewable Skill + MCP pack."} /> : null}
      {detail}
      {!selected ? <div className="community-plugin-list">
        {entries.map((entry) => {
          const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`;
          const local = localStatus(entry);
          return <article className="community-plugin-card" key={key}><div className="community-plugin-card-head"><PackageOpen size={18} aria-hidden="true" /><span className="row-copy"><strong>{entry.name}</strong><small>@{entry.owner_handle} · {entry.plugin_id} · v{entry.version}</small></span><StatusBadge label={statusLabel(entry.status, zh)} tone={statusTone(entry.status)} /></div><p>{entry.description}</p><div className="plugin-pack-facts"><Tag>{`${entry.skill_count} ${zh ? "个 Skill" : entry.skill_count === 1 ? "Skill" : "Skills"}`}</Tag><Tag>{`${entry.mcp_count} MCP`}</Tag><StatusBadge label={local.label} tone={local.tone} />{entry.license ? <Tag>{entry.license}</Tag> : null}</div><small className="community-plugin-local-detail">{local.detail}</small><div className="button-row"><Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void openDetail(entry)}>{busy === `detail:${entry.owner_handle}/${entry.slug}` ? "…" : (zh ? "查看详情" : "View details")}</Button>{entry.status === "published" ? <><Button size="sm" variant="ghost" icon={Download} disabled={busy !== null} onClick={() => void download(entry, false)}>{busy === `download:${key}` ? "…" : (zh ? "下载" : "Download")}</Button>{localApi.importPluginPack ? <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void download(entry, true)}>{busy === `import:${key}` ? "…" : (local.label === (zh ? "有可用更新" : "Update available") ? (zh ? "更新本机" : "Update locally") : (zh ? "导入本机" : "Import locally"))}</Button> : null}</> : null}</div></article>;
        })}
      </div> : null}
    </Panel>
  );
}
