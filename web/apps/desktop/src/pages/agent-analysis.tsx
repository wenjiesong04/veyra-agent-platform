import { Gauge } from "lucide-react";
import { EmptyState, Panel, SectionHeading, useLocale } from "@veyra/ui";

const copy = {
  zh: {
    eyebrow: "Agent 数据分析",
    title: "数据分析",
    description: "这里将呈现这个 Agent 的真实运行指标和验证结果。",
    metricsEyebrow: "运行指标",
    metricsTitle: "等待服务端运行数据",
    metricsDetail: "运行历史接入后，指标会从持久化 Run 记录生成。",
    emptyTitle: "暂无可分析的运行记录",
    emptyDetail: "当前不会使用浏览器历史或模拟数据填充分析面板。",
  },
  en: {
    eyebrow: "Agent data analysis",
    title: "Data analysis",
    description: "This space will present real run metrics and verification outcomes for this Agent.",
    metricsEyebrow: "Run metrics",
    metricsTitle: "Waiting for server-backed runs",
    metricsDetail: "Metrics will be derived from durable Run records once run history is connected.",
    emptyTitle: "No runs available to analyze",
    emptyDetail: "This panel does not fill itself with browser history or simulated data.",
  },
} as const;

export function AgentAnalysisPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const current = copy[locale];
  return (
    <div className="page-stack agent-analysis-page" data-agent-id={agentId} data-project-id={projectId}>
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{current.eyebrow}</span>
          <h2>{current.title}</h2>
          <p>{current.description}</p>
        </div>
      </div>
      <Panel className="agent-analysis-panel">
        <SectionHeading eyebrow={current.metricsEyebrow} title={current.metricsTitle} detail={current.metricsDetail} />
        <div className="agent-analysis-empty">
          <EmptyState icon={Gauge} title={current.emptyTitle} detail={current.emptyDetail} />
        </div>
      </Panel>
    </div>
  );
}
