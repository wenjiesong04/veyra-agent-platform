import type { AgentSummary, ProjectSummary } from "@veyra/api-contracts";
import { NewChatPage } from "./new-chat";

export const projects: ProjectSummary[] = [];
export const agents: AgentSummary[] = [];
export function defaultAgentForProject(_projectId: string): AgentSummary | undefined { return undefined; }

/** Legacy route compatibility: Projects now renders the normal chat surface. */
export function ProjectsPage() { return <NewChatPage />; }
