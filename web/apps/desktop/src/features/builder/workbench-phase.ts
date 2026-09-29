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
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const done = STAGE_DONE[events[index]?.kind ?? ""];
    if (done && !seen.has(done)) return events[index]?.created_at ?? null;
  }
  return null;
}

export function runningClock(startedAt: string, now: number, locale: "zh" | "en"): string {
  const start = Date.parse(startedAt);
  if (!Number.isFinite(start)) return "";
  const seconds = Math.max(0, Math.floor((now - start) / 1000));
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return locale === "zh" ? `已进行 ${clock}` : `Running ${clock}`;
}

export function planFacts(events: BuilderOperationEvent[]): Record<string, string> {
  const completed = [...events].reverse().find((item) => item.kind === "builder.specification.completed" || item.kind === "builder.semantic_plan.completed");
  return completed?.facts ?? {};
}
