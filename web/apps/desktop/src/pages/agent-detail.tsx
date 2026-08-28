import { useLocale } from "@veyra/ui";

/** Route and shell identity intentionally remain while the Agent surface is introduced. */
export function AgentDetailPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  return <section className="agent-detail-placeholder" aria-label={locale === "zh" ? `Agent ${agentId}（项目 ${projectId}）` : `Agent ${agentId} in Project ${projectId}`} />;
}
