import * as React from "react";
import { Gauge } from "lucide-react";
import type { AgentRunResponse } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LoadingState, MetricCard, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";

const copy = {
  zh: {
    eyebrow: "Agent 数据分析", title: "数据分析", description: "这里呈现这个 Agent 的真实本机运行指标和验证结果。",
    metricsEyebrow: "运行指标", metricsTitle: "本机运行概览", metricsDetail: "所有数字均来自持久化 Run 记录。",
    emptyTitle: "暂无可分析的运行记录", emptyDetail: "在编排页面完成一次测试运行后，指标会自动出现在这里。",
    unavailable: "本地 Runtime 尚未提供运行历史。", loading: "正在读取运行记录…", retry: "无法读取运行记录。",
    total: "全部运行", verified: "已验证", failed: "失败", unverified: "未验证", recent: "最近运行", latest: "最近一次",
  },
  en: {
    eyebrow: "Agent data analysis", title: "Data analysis", description: "This page presents real local run metrics and verification outcomes for this Agent.",
    metricsEyebrow: "Run metrics", metricsTitle: "Local run overview", metricsDetail: "Every number is derived from durable Run records.",
    emptyTitle: "No runs available to analyze", emptyDetail: "Complete a test run in Orchestration and its metrics will appear here.",
    unavailable: "The local Runtime does not expose run history yet.", loading: "Loading run history…", retry: "Run history could not be loaded.",
    total: "Total runs", verified: "Verified", failed: "Failed", unverified: "Unverified", recent: "Recent runs", latest: "Latest",
  },
} as const;

export function AgentAnalysisPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const { api } = useProjectWorkspace();
  const current = copy[locale];
  const [runs, setRuns] = React.useState<AgentRunResponse[]>([]);
  const [status, setStatus] = React.useState<"loading" | "ready" | "error">("loading");
  const load = React.useCallback(async () => {
    if (!api.listAgentRuns) { setStatus("error"); return; }
    setStatus("loading");
    try { const response = await api.listAgentRuns(projectId, agentId); setRuns(response.runs); setStatus("ready"); }
    catch { setStatus("error"); }
  }, [api, projectId, agentId]);
  React.useEffect(() => { void load(); }, [load]);
  const verified = runs.filter((run) => run.status === "verified").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const unverified = runs.filter((run) => run.status === "unverified").length;
  const latest = runs[0];
  return (
    <div className="page-stack agent-analysis-page" data-agent-id={agentId} data-project-id={projectId}>
      <div className="page-intro"><div><span className="ui-eyebrow">{current.eyebrow}</span><h2>{current.title}</h2><p>{current.description}</p></div></div>
      <Panel className="agent-analysis-panel">
        <SectionHeading eyebrow={current.metricsEyebrow} title={current.metricsTitle} detail={current.metricsDetail} />
        {status === "loading" ? <LoadingState label={current.loading} /> : null}
        {status === "error" ? <ErrorState message={api.listAgentRuns ? current.retry : current.unavailable} onRetry={api.listAgentRuns ? () => void load() : undefined} /> : null}
        {status === "ready" && !runs.length ? <div className="agent-analysis-empty"><EmptyState icon={Gauge} title={current.emptyTitle} detail={current.emptyDetail} /></div> : null}
        {status === "ready" && runs.length ? <>
          <div className="agent-analysis-metrics">
            <MetricCard label={current.total} value={String(runs.length)} />
            <MetricCard label={current.verified} value={String(verified)} tone="good" />
            <MetricCard label={current.unverified} value={String(unverified)} tone="warn" />
            <MetricCard label={current.failed} value={String(failed)} tone="bad" />
          </div>
          <div className="agent-run-history">
            <SectionHeading eyebrow={current.latest} title={current.recent} detail={latest?.finished_at ?? latest?.created_at} />
            <ol>{runs.slice(0, 20).map((run) => <li key={run.run_id}><span><strong>{run.run_id.slice(0, 8)}</strong><small>{run.created_at}</small></span><StatusBadge label={run.status} tone={run.status === "verified" ? "good" : run.status === "failed" ? "bad" : "warn"} /></li>)}</ol>
          </div>
        </> : null}
      </Panel>
    </div>
  );
}
