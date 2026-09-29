import type { AgentRunResponse, JsonObject, RuntimeEvent } from "@veyra/api-contracts";

export type AppActivityItem = {
  id: string;
  label: string;
};

type Locale = "zh" | "en";

export function appActivity(events: RuntimeEvent[] | undefined, locale: Locale): AppActivityItem[] {
  const items: AppActivityItem[] = [];
  let skills = 0;
  for (const event of events ?? []) {
    if (event.kind === "skill.loaded") {
      skills += 1;
      continue;
    }
    const label = activityLabel(event, locale);
    if (label) items.push({ id: `${event.sequence}:${event.kind}`, label });
  }
  if (skills > 0) {
    items.unshift({
      id: "skills",
      label: locale === "zh" ? `已加载 ${skills} 个技能` : `Loaded ${skills} skills`,
    });
  }
  return items;
}

export function knowledgeSources(events: RuntimeEvent[] | undefined, locale: Locale): string[] {
  const event = [...(events ?? [])].reverse().find((item) => item.kind === "knowledge.retrieved");
  if (!event) return [];
  const refs = Array.isArray(event.payload.knowledge_refs)
    ? event.payload.knowledge_refs.filter((item): item is string => typeof item === "string")
    : [];
  if (refs.length) return refs.map((ref) => safeKnowledgeLabel(ref));
  const count = typeof event.payload.source_count === "number" ? event.payload.source_count : 0;
  if (!count) return [];
  return [locale === "zh" ? `使用了 ${count} 个项目来源` : `Used ${count} project sources`];
}

export function approvalCard(run: AgentRunResponse | null): {
  prompt: string;
  action: string;
  target: string;
  tool: string;
  reason: string;
} | null {
  if (run?.status !== "waiting") return null;
  const event = [...(run.events ?? [])].reverse().find((item) => item.kind === "approval.requested");
  if (!event) return null;
  const summary = asRecord(event.payload.approval_summary);
  const prompt = typeof event.payload.prompt === "string" ? event.payload.prompt : "";
  return {
    prompt,
    action: text(summary?.action) || (prompt ? "Approve tool" : "Approval required"),
    target: text(summary?.target),
    tool: text(summary?.tool) || text(event.payload.tool_reference),
    reason: text(summary?.reason) || prompt,
  };
}

function activityLabel(event: RuntimeEvent, locale: Locale): string | null {
  const zh = locale === "zh";
  if (event.kind === "run.started") return zh ? "正在启动 Agent" : "Starting Agent";
  if (event.kind === "node.started" && event.payload.phase === "model") return zh ? "正在思考" : "Thinking";
  if (event.kind === "model.delta" && !event.payload.delta) return zh ? "正在思考" : "Thinking";
  if (event.kind === "knowledge.retrieved") {
    return zh ? "正在阅读知识" : "Reading Knowledge";
  }
  if (event.kind === "approval.requested") return zh ? "等待审批" : "Waiting for approval";
  if (event.kind === "run.completed") return zh ? "已生成结果" : "Generated result";
  if (event.kind === "run.failed") return zh ? "运行失败" : "Failed";
  if (event.kind === "run.cancelled") return zh ? "已取消" : "Cancelled";
  if (event.kind === "tool.started" || event.kind === "tool.completed") {
    return toolLabel(String(event.payload.tool_reference ?? ""), event.payload, locale, event.kind === "tool.completed");
  }
  return null;
}

function toolLabel(reference: string, payload: JsonObject, locale: Locale, completed: boolean): string {
  const zh = locale === "zh";
  const identity = reference.split("@", 1)[0] ?? reference;
  const target = text(payload.path) || text(payload.relative_path) || text(payload.query);
  if (identity.includes("web.search") || (identity.endsWith(".search") && identity.includes("web"))) {
    return completed ? (zh ? "已搜索网页" : "Searched the web") : (zh ? "正在使用网页搜索" : "Using Web Search");
  }
  if (identity.includes("filesystem.search")) {
    return completed ? (zh ? "已搜索项目文件" : "Searched project files") : (zh ? "正在搜索项目文件" : "Searching project files");
  }
  if (identity.includes("filesystem.read")) {
    return completed ? (zh ? `已读取 ${target || "文件"}` : `Read ${target || "file"}`) : (zh ? `正在读取 ${target || "文件"}` : `Reading ${target || "file"}`);
  }
  if (identity.includes("filesystem.write")) {
    return completed ? (zh ? `已写入 ${target || "文件"}` : `Wrote ${target || "file"}`) : (zh ? `正在写入 ${target || "文件"}` : `Writing ${target || "file"}`);
  }
  if (identity.includes("shell.exec")) {
    return completed ? (zh ? "已运行命令" : "Ran a command") : (zh ? "正在运行命令" : "Running a command");
  }
  if (identity.includes("filesystem.list")) {
    return completed ? (zh ? "已列出文件" : "Listed files") : (zh ? "正在列出文件" : "Listing files");
  }
  if (identity.includes("github")) {
    return completed ? (zh ? "已请求 GitHub" : "Used GitHub") : (zh ? "正在请求 GitHub" : "Using GitHub");
  }
  if (completed) return zh ? "已使用工具" : "Used a tool";
  return zh ? "正在使用工具" : "Using a tool";
}

function safeKnowledgeLabel(reference: string): string {
  const tail = reference.split("/").pop() ?? reference;
  return tail.replace(/@[0-9.]+$/, "") || "Source";
}

function asRecord(value: unknown): JsonObject | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as JsonObject;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
