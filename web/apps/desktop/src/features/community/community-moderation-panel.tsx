import type { CommunityRegistryEntry, CommunityRegistryModerationRequest } from "@veyra/api-contracts";
import { CommunityApiError, type CommunityApi } from "@veyra/connected-account";
import { Button, ErrorState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";

export function CommunityModerationPanel({ communityApi }: { communityApi: CommunityApi }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [entries, setEntries] = useState<CommunityRegistryEntry[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!communityApi.hasRefreshEvidence()) return;
    try {
      setEntries(await communityApi.listRegistryModerationQueue());
    } catch (cause) {
      if (cause instanceof CommunityApiError && [401, 403].includes(cause.status)) return;
      setError(cause instanceof Error ? cause.message : (zh ? "无法读取审核队列。" : "Could not load the moderation queue."));
    }
  }, [communityApi, zh]);

  useEffect(() => { void load(); }, [load]);

  const decide = async (entry: CommunityRegistryEntry, action: CommunityRegistryModerationRequest["action"]) => {
    if (!communityApi.moderateRegistryAgent || !reason.trim()) return;
    const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`;
    setBusy(key);
    setError("");
    try {
      await communityApi.moderateRegistryAgent(entry.owner_handle, entry.slug, entry.version, { action, reason: reason.trim() });
      setReason("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "审核操作失败。" : "Moderation failed."));
    } finally {
      setBusy(null);
    }
  };

  if (!entries.length) return null;
  return (
    <Panel className="community-moderation-panel">
      <SectionHeading eyebrow={zh ? "审核队列" : "Moderation queue"} title={`${entries.length} ${zh ? "个待审核版本" : "pending versions"}`} detail={zh ? "只有配置的 moderator 可以发布或拒绝；每次决定都会留下原因记录。" : "Only configured moderators can publish or reject; every decision records a reason."} />
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      <label><span>{zh ? "审核理由" : "Decision reason"}</span><input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={4_000} placeholder={zh ? "例如：已检查权限和来源" : "For example: permissions and provenance checked"} /></label>
      <div className="run-list">
        {entries.map((entry) => {
          const key = `${entry.owner_handle}/${entry.slug}/${entry.version}`;
          return <div className="run-row" key={key}><span className="row-copy"><strong>{entry.name}</strong><small>@{entry.owner_handle}/{entry.slug} · v{entry.version}</small></span>{entry.scan?.risk_level ? <Tag>{zh ? `风险 ${entry.scan.risk_level}` : `risk ${entry.scan.risk_level}`}</Tag> : null}{entry.scan?.status === "warning" ? <Tag>{zh ? `${entry.scan.warnings.length} 个扫描提示` : `${entry.scan.warnings.length} scan warnings`}</Tag> : null}<StatusBadge label={entry.status} tone="warn" /><Button size="sm" disabled={busy !== null || !reason.trim()} onClick={() => void decide(entry, "publish")}>{zh ? "发布" : "Publish"}</Button><Button size="sm" variant="danger" disabled={busy !== null || !reason.trim()} onClick={() => void decide(entry, "reject")}>{zh ? "拒绝" : "Reject"}</Button></div>;
        })}
      </div>
    </Panel>
  );
}
