import type { CommunityPluginEntry, CommunityPluginModerationRequest } from "@veyra/api-contracts";
import { CommunityApiError, type CommunityApi } from "@veyra/connected-account";
import { Button, ErrorState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";

export function CommunityPluginModerationPanel({ communityApi }: { communityApi: CommunityApi }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [entries, setEntries] = useState<CommunityPluginEntry[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setEntries(await communityApi.listRegistryPluginModerationQueue());
    } catch (cause) {
      if (cause instanceof CommunityApiError && [401, 403, 404].includes(cause.status)) return;
      setError(cause instanceof Error ? cause.message : (zh ? "插件审核队列暂时不可用。" : "The Plugin moderation queue is unavailable."));
    }
  }, [communityApi, zh]);

  useEffect(() => { void load(); }, [load]);

  const decide = async (entry: CommunityPluginEntry, action: CommunityPluginModerationRequest["action"]) => {
    if (!reason.trim()) return;
    const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`;
    setBusy(key);
    setError("");
    try {
      await communityApi.moderateRegistryPlugin(entry.owner_handle, entry.slug, entry.version, { action, reason: reason.trim() });
      setReason("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件审核失败。" : "Plugin moderation failed."));
    } finally {
      setBusy(null);
    }
  };

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!entries.length) return null;
  return <Panel className="community-plugin-moderation-panel"><SectionHeading eyebrow={zh ? "审核队列" : "Moderation queue"} title={zh ? `${entries.length} 个插件待审核` : `${entries.length} Plugin Pack(s) awaiting review`} detail={zh ? "审核只改变公开状态，不会在 Community 执行包。" : "Moderation changes publication state only; Community never executes the pack."} /><label className="community-plugin-reason"><span>{zh ? "审核理由" : "Review reason"}</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} placeholder={zh ? "说明发布或拒绝原因" : "Explain the publish or reject decision"} /></label><div className="community-plugin-moderation-list">{entries.map((entry) => { const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`; return <article key={key}><div><strong>{entry.name}</strong><small>@{entry.owner_handle} · v{entry.version}</small><div><Tag>{`${entry.skill_count} Skill`}</Tag><Tag>{`${entry.mcp_count} MCP`}</Tag></div></div><div className="button-row"><Button size="sm" variant="primary" disabled={busy !== null || !reason.trim()} onClick={() => void decide(entry, "publish")}>{busy === key ? "…" : (zh ? "发布" : "Publish")}</Button><Button size="sm" variant="danger" disabled={busy !== null || !reason.trim()} onClick={() => void decide(entry, "reject")}>{busy === key ? "…" : (zh ? "拒绝" : "Reject")}</Button><StatusBadge label={zh ? "审核中" : "Pending"} tone="warn" /></div></article>; })}</div></Panel>;
}
