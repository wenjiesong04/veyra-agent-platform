import { Server, ShieldCheck } from "lucide-react";
import { Button, Panel, StatusBadge } from "@veyra/ui";
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
  const platformConfigured = Boolean(status?.configured);
  return (
    <Panel className="platform-provider-panel">
      <div className="platform-provider-header">
        <span className="platform-provider-icon"><Server size={20} /></span>
        <div className="platform-provider-copy">
          <span className="ui-eyebrow">{zh ? "Veyra 平台服务" : "VEYRA PLATFORM"}</span>
          <h2>{zh ? "Builder 模型服务" : "Builder model service"}</h2>
          <p>{zh ? "用于 Builder 对话、意图识别、方案生成和 Proposal。它不是账号的 Agent Runtime API。" : "Used by Builder conversation, intent detection, plan generation, and Proposals. It is not an account Agent Runtime API."}</p>
        </div>
        <StatusBadge label={platformConfigured ? (zh ? "平台已配置" : "Platform configured") : (zh ? "未配置" : "Not configured")} tone={platformConfigured ? "good" : "warn"} />
      </div>
      <div className="platform-provider-boundary"><ShieldCheck size={16} /><span>{zh ? "Platform credential 只在 Veyra 本地服务中使用，不会显示、导出，也不会作为 Runtime fallback。" : "The Platform credential stays inside the Veyra local service. It is never displayed, exported, or used as a Runtime fallback."}</span></div>
      {summary ? (
        <div className="platform-provider-facts">
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
        <p className="settings-secret-message">{zh ? "正在读取 Platform Provider 状态…" : "Reading Platform Provider status…"}</p>
      )}
      {onRecheck ? (
        <div className="platform-provider-footer">
          <Button variant="secondary" disabled={busy || !status?.configured} onClick={onRecheck}>
            {zh ? "重新检测" : "Recheck"}
          </Button>
          <span>{zh ? "这里只检测平台 Provider 的请求协议，不会生成 Agent 或产生 Runtime 调用。" : "This only probes the Platform Provider protocol. It does not generate an Agent or call Runtime."}</span>
        </div>
      ) : null}
    </Panel>
  );
}
