import * as React from "react";
import { Gauge } from "lucide-react";
import type { AgentRunResponse } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LoadingState, MetricCard, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";

const copy = {
  zh: {
    eyebrow: "项目数据分析", title: "数据分析", description: "汇总这个项目下全部 Agent 的本机运行指标。",
    metricsEyebrow: "运行指标", metricsTitle: "项目运行概览", metricsDetail: "所有数字均来自持久化 Run 记录。",
    emptyTitle: "暂无可分析的运行记录", emptyDetail: "项目中的 Agent 完成测试运行后，指标会自动出现在这里。",
    unavailable: "本地 Runtime 尚未提供运行历史。", loading: "正在读取运行记录…", retry: "无法读取运行记录。",
    total: "全部运行", verified: "已验证", failed: "失败", interrupted: "中断", unverified: "未验证", recent: "最近运行",
  },
  en: {
    eyebrow: "Project data analysis", title: "Data analysis", description: "Aggregated local run metrics across every Agent in this Project.",
    metricsEyebrow: "Run metrics", metricsTitle: "Project run overview", metricsDetail: "Every number is derived from durable Run records.",
    emptyTitle: "No runs available to analyze", emptyDetail: "Metrics appear here after Agents in this Project complete test runs.",
    unavailable: "The local Runtime does not expose run history yet.", loading: "Loading run history…", retry: "Run history could not be loaded.",
    total: "Total runs", verified: "Verified", failed: "Failed", interrupted: "Interrupted", unverified: "Unverified", recent: "Recent runs",
  },
} as const;

export function ProjectAnalysisPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const { api } = useProjectWorkspace();
  const current = copy[locale];
  const [runs, setRuns] = React.useState<AgentRunResponse[]>([]);
  const [status, setStatus] = React.useState<"loading" | "ready" | "error">("loading");
  const load = React.useCallback(async () => {
    if (!api.listAgentRuns) { setStatus("error"); return; }
    setStatus("loading");
    try {
      const project = await api.getProject(projectId);
      const batches = await Promise.all(project.agents.map((agent) => api.listAgentRuns!(projectId, agent.agent_id)));
      const merged = batches.flatMap((batch) => batch.runs).sort((left, right) => right.created_at.localeCompare(left.created_at));
      setRuns(merged);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, [api, projectId]);
  React.useEffect(() => { void load(); }, [load]);
  const verified = runs.filter((run) => run.status === "verified").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const interrupted = runs.filter((run) => run.status === "interrupted").length;
  const unverified = runs.filter((run) => run.status === "unverified").length;
  return (
    <div className="page-stack agent-analysis-page" data-project-id={projectId}>
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
            <MetricCard label={current.interrupted} value={String(interrupted)} tone="bad" />
          </div>
          <div className="agent-run-history">
            <SectionHeading eyebrow={current.recent} title={current.recent} detail={runs[0]?.finished_at ?? runs[0]?.created_at} />
            <ol>{runs.slice(0, 20).map((run) => <li key={run.run_id}><span><strong>{run.run_id.slice(0, 8)}</strong><small>{run.created_at}</small></span><StatusBadge label={run.status} tone={run.status === "verified" ? "good" : run.status === "failed" || run.status === "interrupted" ? "bad" : "warn"} /></li>)}</ol>
          </div>
        </> : null}
      </Panel>
    </div>
  );
}
