import * as React from "react";
import { desktopRoutePaths, projectRoutePaths } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../../../api/project-workspace";
import { writePendingFactoryPrompt } from "./pending-factory-prompt";

export type ChatTarget =
  | { kind: "new" }
  | { kind: "project"; projectId: string; name: string }
  | { kind: "agent"; projectId: string; agentId: string; name: string; projectName: string };

export function folderLabel(rootPath: string): string {
  const parts = rootPath.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || rootPath;
}

export function chatTargetHref(target: ChatTarget): string {
  if (target.kind === "agent") return `${projectRoutePaths.projectChat(target.projectId)}?target=agent:${encodeURIComponent(target.agentId)}`;
  if (target.kind === "project") return projectRoutePaths.projectChat(target.projectId);
  return desktopRoutePaths.chat;
}

export function navigateChatTarget(target: ChatTarget): void {
  window.location.hash = chatTargetHref(target);
}

export function sameChatTarget(left: ChatTarget, right: ChatTarget): boolean {
  if (left.kind !== right.kind) return false;
  if (left.kind === "new") return true;
  if (left.kind === "project" && right.kind === "project") return left.projectId === right.projectId;
  return left.kind === "agent" && right.kind === "agent" && left.agentId === right.agentId;
}

export function useChatScopeNavigation() {
  const { api, upsertProject } = useProjectWorkspace();

  const createProject = React.useCallback(async () => {
    const created = await api.createProject({ description: "" });
    upsertProject(created);
    window.location.hash = projectRoutePaths.projectChat(created.project_id);
  }, [api, upsertProject]);

  const select = React.useCallback((target: ChatTarget) => {
    navigateChatTarget(target);
  }, []);

  const start = React.useCallback(async (target: ChatTarget, prompt: string) => {
    const trimmed = prompt.trim();
    if (trimmed) writePendingFactoryPrompt(trimmed);
    if (target.kind === "new") {
      await createProject();
      return;
    }
    navigateChatTarget(target);
  }, [createProject]);

  return { select, createProject, start };
}
