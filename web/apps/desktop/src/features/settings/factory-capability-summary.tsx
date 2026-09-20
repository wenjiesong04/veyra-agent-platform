import { Button, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import type { FactoryStatus } from "@veyra/api-contracts";

export function FactoryCapabilitySummary({
  status,
  locale,
  busy,
  onRecheck,
}: {
  status: FactoryStatus | null;
  locale: "zh" | "en";
  busy: boolean;
  onRecheck?: () => void;
}) {
  const zh = locale === "zh";
  const profile = status?.capability_profile;
  const summary = profile?.summary;
  const tone = profile?.status === "known"
    ? "good"
    : profile?.status === "inconclusive" || profile?.status === "failed"
      ? "warn"
      : "neutral";
  return (
    <Panel>
      <SectionHeading
        eyebrow={zh ? "Factory" : "Factory"}
        title={zh ? "模型请求协议" : "Provider request protocol"}
        detail={zh
          ? "只描述当前 Provider、模型和端点支持怎样发请求。不改变 Agent 语义。"
          : "Describes the request protocol for this provider, model, and endpoint. It does not define Agent semantics."}
      />
      {summary ? (
        <div className="settings-facts">
          <div><span>Provider</span><strong>{summary.provider}</strong></div>
          <div><span>Model</span><strong>{summary.model}</strong></div>
          <div><span>{zh ? "结构化输出" : "Structured output"}</span><strong>{summary.structured_output}</strong></div>
          <div><span>Schema</span><strong>{summary.schema_profile}</strong></div>
          <div><span>JSON object fallback</span><strong>{summary.json_object_fallback}</strong></div>
          <div>
            <span>{zh ? "状态" : "Profile status"}</span>
            <StatusBadge label={summary.status} tone={tone} />
          </div>
          {summary.checked_at ? <div><span>{zh ? "检查时间" : "Checked"}</span><strong>{summary.checked_at}</strong></div> : null}
        </div>
      ) : (
        <p className="settings-secret-message">{zh ? "正在读取 Factory 状态…" : "Reading Factory status…"}</p>
      )}
      {onRecheck ? (
        <div className="accessibility-row">
          <Button variant="secondary" disabled={busy || !status?.configured} onClick={onRecheck}>
            {zh ? "重新检测" : "Recheck"}
          </Button>
          <span>{zh ? "只在设置变化或需要确认能力时检测。" : "Probe only after settings change or an explicit recheck."}</span>
        </div>
      ) : null}
    </Panel>
  );
}
