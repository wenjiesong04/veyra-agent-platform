import { useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { AgentChatSurface } from "../features/agents/chat/AgentChatSurface";

export function AgentDetailPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const { api } = useProjectWorkspace();
  return <AgentChatSurface api={api} projectId={projectId} agentId={agentId} locale={locale} />;
}
