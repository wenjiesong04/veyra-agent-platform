import { Download, PackageOpen, Upload } from "lucide-react";
import type { CommunityPluginEntry } from "@veyra/api-contracts";
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

export function CommunityPluginPanel({ communityApi, localApi }: { communityApi: CommunityApi; localApi: LocalProjectApi }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [entries, setEntries] = useState<CommunityPluginEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setEntries(await communityApi.listRegistryPlugins());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件目录暂时不可用。" : "The Plugin registry is unavailable."));
    } finally {
      setLoading(false);
    }
  }, [communityApi, zh]);

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
      <div className="community-plugin-list">
        {entries.map((entry) => {
          const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`;
          return <article className="community-plugin-card" key={key}><div className="community-plugin-card-head"><PackageOpen size={18} aria-hidden="true" /><span className="row-copy"><strong>{entry.name}</strong><small>@{entry.owner_handle} · {entry.plugin_id} · v{entry.version}</small></span><StatusBadge label={statusLabel(entry.status, zh)} tone={statusTone(entry.status)} /></div><p>{entry.description}</p><div className="plugin-pack-facts"><Tag>{`${entry.skill_count} ${zh ? "个 Skill" : entry.skill_count === 1 ? "Skill" : "Skills"}`}</Tag><Tag>{`${entry.mcp_count} MCP`}</Tag>{entry.license ? <Tag>{entry.license}</Tag> : null}</div>{entry.status === "published" ? <div className="button-row"><Button size="sm" variant="ghost" icon={Download} disabled={busy !== null} onClick={() => void download(entry, false)}>{busy === `download:${key}` ? "…" : (zh ? "下载" : "Download")}</Button>{localApi.importPluginPack ? <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void download(entry, true)}>{busy === `import:${key}` ? "…" : (zh ? "下载并导入本机" : "Download and import locally")}</Button> : null}</div> : null}</article>;
        })}
      </div>
    </Panel>
  );
}
