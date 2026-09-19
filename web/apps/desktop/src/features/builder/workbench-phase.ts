import type { BuilderConversationOperation, BuilderOperationEvent, FactorySession } from "@veyra/api-contracts";

export type WorkbenchPhase =
  | "understanding"
  | "planning"
  | "compiling"
  | "validating"
  | "review"
  | "missing"
  | "completed";

export function workbenchPhase(
  operation: BuilderConversationOperation | undefined,
  session: FactorySession | null,
  createdAgentId: string | null,
): WorkbenchPhase {
  if (createdAgentId || session?.state === "completed") return "completed";
  if (session?.state === "missing_capability" || operation?.error_code === "factory_missing_capability") return "missing";
  if (session?.state === "review") return "review";
  const kinds = new Set((operation?.events ?? []).map((item) => item.kind));
  if (kinds.has("builder.proposal.ready")) return "review";
  if (kinds.has("builder.validation.started") && !kinds.has("builder.validation.completed")) return "validating";
  if (kinds.has("builder.compile.started") || kinds.has("builder.capabilities.started")) return "compiling";
  if (kinds.has("builder.semantic_plan.started")) return "planning";
  return "understanding";
}

export function planFacts(events: BuilderOperationEvent[]): Record<string, string> {
  const completed = [...events].reverse().find((item) => item.kind === "builder.semantic_plan.completed");
  return completed?.facts ?? {};
}
