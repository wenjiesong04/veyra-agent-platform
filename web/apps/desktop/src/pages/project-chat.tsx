import { NewChatPage } from "./new-chat";

export function ProjectChatPage({ projectId, conversationId }: { projectId: string; conversationId?: string }) {
  return <NewChatPage projectId={projectId} conversationId={conversationId} />;
}
