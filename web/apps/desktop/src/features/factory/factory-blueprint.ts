import type { JsonObject, JsonValue } from "@veyra/api-contracts";

export type BlueprintGraphNode = { id: string; component_type: string };
export type BlueprintGraphEdge = { from: string; port: string; to: string };

function isRecord(value: JsonValue | null | undefined): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function blueprintGraph(blueprint: JsonObject | null | undefined): {
  nodes: BlueprintGraphNode[];
  transitions: BlueprintGraphEdge[];
} {
  if (!blueprint) return { nodes: [], transitions: [] };
  const nodes: BlueprintGraphNode[] = [];
  if (Array.isArray(blueprint.nodes)) {
    for (const item of blueprint.nodes) {
      if (!isRecord(item)) continue;
      if (typeof item.id === "string" && typeof item.component_type === "string") {
        nodes.push({ id: item.id, component_type: item.component_type });
      }
    }
  }
  const transitions: BlueprintGraphEdge[] = [];
  if (Array.isArray(blueprint.transitions)) {
    for (const item of blueprint.transitions) {
      if (!isRecord(item)) continue;
      if (typeof item.from === "string" && typeof item.to === "string") {
        transitions.push({
          from: item.from,
          port: typeof item.port === "string" ? item.port : "next",
          to: item.to,
        });
      }
    }
  }
  return { nodes, transitions };
}

export function blueprintPresentation(blueprint: JsonObject | null | undefined): {
  labels: Record<string, string>;
  note?: { text: string; width: number; color: string };
} {
  const ui = blueprint && isRecord(blueprint.ui_suggestions) ? blueprint.ui_suggestions : null;
  if (!ui) return { labels: {} };
  const labels: Record<string, string> = {};
  if (isRecord(ui.labels)) {
    for (const [id, label] of Object.entries(ui.labels)) {
      if (typeof label === "string") labels[id] = label;
    }
  }
  const notes = isRecord(ui.notes) ? ui.notes : null;
  const intro = notes && isRecord(notes.note_intro) ? notes.note_intro : null;
  if (!intro || typeof intro.text !== "string") return { labels };
  const width = typeof intro.width === "number" && Number.isFinite(intro.width)
    ? Math.min(640, Math.max(160, intro.width))
    : 420;
  return {
    labels,
    note: {
      text: intro.text,
      width,
      color: typeof intro.color === "string" ? intro.color : "amber",
    },
  };
}

export function revisionFactoryGoal(input: {
  agentName: string;
  agentId: string;
  description: string;
  prompt: string;
  locale: "zh" | "en";
}): string {
  const description = input.description.trim() || (input.locale === "zh" ? "（无描述）" : "(no description)");
  if (input.locale === "zh") {
    return [
      `请根据用户要求修改现有 Agent「${input.agentName}」（${input.agentId}）。`,
      "生成可审核的 Blueprint；确认创建 Draft 时把它作为该 Agent 的子版本。",
      "只引用资源库中已登记且可选的能力。缺失能力写成隔离草稿，不可执行。",
      `当前描述：${description}`,
      `用户要求：${input.prompt.trim()}`,
    ].join("\n");
  }
  return [
    `Revise the existing Agent "${input.agentName}" (${input.agentId}).`,
    "Produce a reviewable Blueprint; applying the Draft should create a child of this Agent.",
    "Reference only registered, selectable catalog resources. Missing capabilities become quarantined, non-executable drafts.",
    `Current description: ${description}`,
    `User request: ${input.prompt.trim()}`,
  ].join("\n");
}
