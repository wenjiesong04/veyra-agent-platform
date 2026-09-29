import { isArtifactRef, type AgentRunResponse, type AgentSource, type JsonObject, type JsonValue } from "@veyra/api-contracts";

export type ConversationCanvasKind = "run" | "table" | "result" | "document";

export type ConversationCanvasSpec = {
  kind: ConversationCanvasKind;
  title: string;
};

const titles = {
  zh: { run: "运行画布", table: "数据表", result: "结果画布", document: "文档画布" },
  en: { run: "Run canvas", table: "Data table", result: "Result canvas", document: "Document canvas" },
} as const;

export function isJsonObject(value: JsonValue | null | undefined): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function scalarResultText(result: JsonValue | null | undefined): string | null {
  if (typeof result === "string") return result;
  if (!isJsonObject(result)) return null;
  const entries = Object.entries(result);
  if (entries.length === 1 && typeof entries[0][1] === "string") return entries[0][1];
  return null;
}

export function tableRows(result: JsonValue | null | undefined): JsonObject[] | null {
  if (Array.isArray(result) && result.length > 0 && result.every(isJsonObject)) return result;
  if (isJsonObject(result)) {
    for (const item of Object.values(result)) {
      if (Array.isArray(item) && item.length > 0 && item.every(isJsonObject)) return item;
    }
  }
  return null;
}

function isArtifactValue(value: JsonValue | null | undefined): boolean {
  if (isArtifactRef(value)) return true;
  return Array.isArray(value) && value.length > 0 && value.every(isArtifactRef);
}

export function containsArtifacts(value: JsonValue | null | undefined): boolean {
  if (value == null) return false;
  if (isArtifactRef(value)) return true;
  if (Array.isArray(value)) return value.some((item) => containsArtifacts(item));
  if (typeof value === "object") return Object.values(value).some((item) => containsArtifacts(item));
  return false;
}

export function isMediaResult(result: JsonValue | null | undefined): boolean {
  if (isArtifactValue(result)) return true;
  if (!isJsonObject(result)) return false;
  const entries = Object.entries(result);
  return entries.length > 0 && entries.every(([, item]) => isArtifactValue(item));
}

export function isStructuredResult(result: JsonValue | null | undefined): boolean {
  if (result == null || isMediaResult(result)) return false;
  if (Array.isArray(result)) return result.length > 0;
  if (!isJsonObject(result)) return false;
  const entries = Object.entries(result);
  if (entries.length === 0) return false;
  if (entries.length === 1 && typeof entries[0][1] === "string") return false;
  return true;
}

export function isDocumentResult(result: JsonValue | null | undefined): boolean {
  const text = scalarResultText(result);
  if (!text) return false;
  return text.length >= 600 || text.includes("\n## ") || text.includes("```");
}

export function hasRunGraph(source: AgentSource | null): boolean {
  return (source?.nodes.length ?? 0) >= 2;
}

/** ChatGPT/Gemini/Codex: keep short replies in the thread; open a canvas for live work, tables, structured objects, or long documents. */
export function conversationCanvas(input: {
  locale: "zh" | "en";
  source: AgentSource | null;
  run: AgentRunResponse | null;
}): ConversationCanvasSpec | null {
  const { locale, source, run } = input;
  if (!run) return null;
  const label = titles[locale];
  const inFlight = run.status === "running" || run.status === "waiting";
  if (hasRunGraph(source)) {
    if (!inFlight && run.result) {
      if (tableRows(run.result)) return { kind: "table", title: label.table };
      if (isStructuredResult(run.result)) return { kind: "result", title: label.result };
      if (isDocumentResult(run.result)) return { kind: "document", title: label.document };
    }
    return { kind: "run", title: label.run };
  }
  if (!run.result) return null;
  if (tableRows(run.result)) return { kind: "table", title: label.table };
  if (isStructuredResult(run.result)) return { kind: "result", title: label.result };
  if (isDocumentResult(run.result)) return { kind: "document", title: label.document };
  return null;
}

export function workingCaption(run: AgentRunResponse | null, locale: "zh" | "en"): string {
  if (!run) return locale === "zh" ? "正在思考…" : "Thinking…";
  if (run.status === "waiting") return locale === "zh" ? "等待审批…" : "Waiting for approval…";
  const last = [...(run.events ?? [])].reverse().find((event) => (
    Boolean(event.node_id) && (event.kind === "node.started" || event.kind === "node.waiting")
  ));
  if (last?.node_id) return locale === "zh" ? `正在运行 ${last.node_id}…` : `Running ${last.node_id}…`;
  return locale === "zh" ? "正在运行…" : "Working…";
}

export function assistantPreview(result: JsonValue | null | undefined, spec: ConversationCanvasSpec | null, locale: "zh" | "en"): { text: string | null; openedInCanvas: boolean } {
  const text = scalarResultText(result);
  if (!spec) return { text, openedInCanvas: false };
  if (text && text.length < 280 && (spec.kind === "run" || spec.kind === "document")) {
    return { text, openedInCanvas: spec.kind !== "run" };
  }
  if (text && spec.kind === "run") return { text, openedInCanvas: false };
  return {
    text: locale === "zh" ? "结果已在画布中打开。" : "Opened in canvas.",
    openedInCanvas: true,
  };
}
