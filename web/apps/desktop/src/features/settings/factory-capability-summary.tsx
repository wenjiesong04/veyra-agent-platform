import { Server } from "lucide-react";
import { Button, Panel, StatusBadge } from "@veyra/ui";
import type { FactoryStatus } from "@veyra/api-contracts";

export function FactoryCapabilitySummary({ status, locale, busy, onRecheck }: {
  status: FactoryStatus | null;
  locale: "zh" | "en";
  busy: boolean;
  onRecheck?: () => void;
}) {
  const zh = locale === "zh";
  const profile = status?.capability_profile;
  const summary = profile?.summary;
  const configured = Boolean(status?.configured);
  const tone = profile?.status === "known" ? "good" : profile?.status === "failed" || profile?.status === "inconclusive" ? "warn" : "neutral";
  const checked = summary?.checked_at ? new Date(summary.checked_at) : null;
  const checkedLabel = checked && !Number.isNaN(checked.getTime()) ? checked.toLocaleString(zh ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }) : (zh ? "尚无记录" : "No record yet");
  return <Panel className="platform-provider-panel">
    <div className="platform-provider-header"><span className="platform-provider-icon"><Server size={20} aria-hidden="true" /></span><div className="platform-provider-copy"><h2>{zh ? "助手使用的模型" : "Assistant model"}</h2><p>{zh ? "当你在聊天中描述想法时，Veyra 使用它帮助创建和修改 Agent。你在“我的 API”中添加的模型，用于 Agent 执行任务。" : "Veyra uses this model when you describe ideas in chat to create or edit Agents. Models in My APIs run their tasks."}</p></div><StatusBadge label={configured ? (zh ? "助手可用" : "Assistant configured") : (zh ? "未配置" : "Not configured")} tone={configured ? "good" : "warn"} /></div>
    {summary ? <>
      <dl className="platform-service-summary"><div><dt>{zh ? "服务提供方" : "Provider"}</dt><dd translate="no">{summary.provider}</dd></div><div><dt>{zh ? "模型" : "Model"}</dt><dd translate="no">{summary.model}</dd></div><div><dt>{zh ? "最近检查" : "Last checked"}</dt><dd>{checkedLabel}</dd></div></dl>
      <details className="platform-protocol-details"><summary>{zh ? "详细连接信息（高级）" : "Advanced connection details"}</summary><dl><div><dt>{zh ? "结构化输出" : "Structured output"}</dt><dd>{summary.structured_output}</dd></div><div><dt>Schema</dt><dd>{summary.schema_profile}</dd></div><div><dt>JSON object fallback</dt><dd>{summary.json_object_fallback}</dd></div><div><dt>{zh ? "检查结果" : "Check result"}</dt><dd><StatusBadge label={summary.status} tone={tone} /></dd></div></dl></details>
    </> : <p className="settings-note" role="status">{status ? (zh ? "尚无服务检查记录。" : "No service check recorded yet.") : (zh ? "正在读取服务状态…" : "Loading service status…")}</p>}
    {onRecheck ? <div className="platform-provider-footer"><Button disabled={busy || !configured} onClick={onRecheck}>{busy ? (zh ? "检测中…" : "Checking…") : (zh ? "重新检测" : "Recheck")}</Button><span>{zh ? "检查创作助手能否连接到模型服务。" : "Check whether the creation assistant can reach its model service."}</span></div> : null}
  </Panel>;
}
