import { NewChatPage } from "./new-chat";

export function ProjectChatPage({ projectId }: { projectId: string }) {
  return <NewChatPage projectId={projectId} />;
}
