import type { BuilderConversationOperation, BuilderOperationEvent, FactorySession } from "@veyra/api-contracts";

export type WorkbenchPhase =
  | "understanding"
  | "planning"
  | "compiling"
  | "validating"
  | "review"
  | "missing"
  | "completed"
  | "blocked"
  | "failed"
  | "finished";

export function isBlockedCreation(
  operation: BuilderConversationOperation | undefined,
  session: FactorySession | null,
): boolean {
  if (session?.state === "missing_capability" || operation?.error_code === "factory_missing_capability") return false;
  return Boolean(session?.blocked_reason?.trim())
    || operation?.error_code === "factory_generation_blocked"
    || Boolean(operation?.events.some((event) => (
      event.kind === "builder.specification.completed" || event.kind === "builder.semantic_plan.completed"
    ) && (event.facts.target_kind === "blocked" || Boolean(event.facts.blocked_reason?.trim()))));
}

export function isUnsupportedCreate(operation: BuilderConversationOperation): boolean {
  return operation.status === "succeeded"
    && (operation.kind === "create_agent" || operation.kind === "create_workflow")
    && operation.events.some((event) => event.kind === "builder.intent.resolved" && event.facts.status === "unsupported");
}

export function isCreationApplyFailure(operation: BuilderConversationOperation): boolean {
  return operation.status === "failed" && Boolean(operation.proposal_id)
    && (operation.kind === "create_agent" || operation.kind === "create_workflow")
    && ["agent_creation_apply", "workflow_creation_apply"].includes(operation.diagnostic.stage ?? "");
}

export function workbenchPhase(
  operation: BuilderConversationOperation | undefined,
  session: FactorySession | null,
  createdAgentId: string | null,
): WorkbenchPhase {
  if (createdAgentId || session?.state === "completed") return "completed";
  if (session?.state === "missing_capability" || operation?.error_code === "factory_missing_capability") return "missing";
  if (isBlockedCreation(operation, session)) return "blocked";
  if (session?.state === "review" && operation?.factory_session_id === session.session_id && isCreationApplyFailure(operation)) return "review";
  if (operation?.status === "failed") return "failed";
  if (operation?.status === "rejected" || session?.state === "abandoned") return "finished";
  if (session?.state === "review") return "review";
  const kinds = new Set((operation?.events ?? []).map((item) => item.kind));
  if (kinds.has("builder.operation.failed")) return "failed";
  if (kinds.has("builder.proposal.ready")) return "review";
  if (operation?.status === "succeeded" || kinds.has("builder.operation.completed")) return "finished";
  if (kinds.has("builder.validation.started") && !kinds.has("builder.validation.completed")) return "validating";
  if (kinds.has("builder.compile.started") || kinds.has("builder.capabilities.started")) return "compiling";
  if (kinds.has("builder.specification.started") || kinds.has("builder.semantic_plan.started")) return "planning";
  return "understanding";
}

const STAGE_DONE: Record<string, string> = {
  "builder.intent.started": "builder.intent.resolved",
  "builder.specification.started": "builder.specification.completed",
  "builder.semantic_plan.started": "builder.semantic_plan.completed",
  "builder.capabilities.started": "builder.capabilities.resolved",
  "builder.compile.started": "builder.compile.completed",
  "builder.validation.started": "builder.validation.completed",
};

export function openStageStartedAt(events: Array<{ kind: string; created_at: string }>): string | null {
  const seen = new Set(events.map((event) => event.kind));
  if (seen.has("builder.operation.completed") || seen.has("builder.operation.failed")) return null;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const done = STAGE_DONE[events[index]?.kind ?? ""];
    if (done && !seen.has(done)) return events[index]?.created_at ?? null;
  }
  return null;
}

export function runningClock(startedAt: string, now: number, locale: "zh" | "en", scope: "stage" | "operation" = "stage"): string {
  const start = Date.parse(startedAt);
  if (!Number.isFinite(start)) return "";
  const seconds = Math.max(0, Math.floor((now - start) / 1000));
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  if (scope === "operation") return locale === "zh" ? `总耗时 ${clock}` : `Total elapsed ${clock}`;
  return locale === "zh" ? `已进行 ${clock}` : `Running ${clock}`;
}

export function planFacts(events: BuilderOperationEvent[]): Record<string, string> {
  const completed = [...events].reverse().find((item) => item.kind === "builder.specification.completed" || item.kind === "builder.semantic_plan.completed");
  return completed?.facts ?? {};
}
