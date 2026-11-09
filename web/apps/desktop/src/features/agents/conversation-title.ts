export type ConversationTitleLocale = "zh" | "en";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PLACEHOLDERS = new Set(["", "new conversation", "agent conversation", "chat", "新对话"]);

function structuredInputTitle(value: string, locale: ConversationTitleLocale): string | null {
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const entries = Object.entries(parsed as Record<string, unknown>);
    const chatText = entries.find(([name, item]) => /^(message|prompt|request|query|task|instruction|text)$/i.test(name) && typeof item === "string" && item.trim());
    if (chatText && typeof chatText[1] === "string") return chatText[1].trim().split(/\s+/).join(" ").slice(0, 80);

    const artifacts = entries.flatMap(([, item]) => {
      const values = Array.isArray(item) ? item : [item];
      return values.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry) && (entry as Record<string, unknown>).kind === "artifact");
    });
    const hasImage = artifacts.some((item) => typeof item.media_type === "string" && item.media_type.startsWith("image/"));
    if (entries.length > 1) {
      const run = locale === "zh" ? "多字段运行" : "Multi-field run";
      const file = hasImage ? (locale === "zh" ? "图片附件" : "image attachment") : artifacts.length ? (locale === "zh" ? "文件附件" : "file attachment") : "";
      return file ? `${run} · ${file}` : run;
    }
    if (artifacts.length) return hasImage ? (locale === "zh" ? "图片附件" : "Image attachment") : (locale === "zh" ? "文件附件" : "File attachment");
    return null;
  } catch {
    if (/^\s*[{[]/.test(value)) {
      const chatField = value.match(/"(?:message|prompt|request|query|task|instruction|text)"\s*:\s*"((?:\\.|[^"\\])*)"/i);
      if (chatField?.[1]) {
        try {
          const text = JSON.parse(`"${chatField[1]}"`) as string;
          if (text.trim() && !looksLikeIdentity(text.trim())) return text.trim().split(/\s+/).join(" ").slice(0, 80);
        } catch {
          // A truncated title can still contain a safe, bounded chat field.
        }
      }
      const run = locale === "zh" ? "多字段运行" : "Multi-field run";
      const hasArtifact = /"artifact_id"\s*:/.test(value);
      if (hasArtifact) return `${run} · ${locale === "zh" ? "文件附件" : "file attachment"}`;
      return run;
    }
    return null;
  }
}

export function looksLikeIdentity(value: string | null | undefined): boolean {
  return UUID.test((value ?? "").trim());
}

export function displayConversationTitle(
  title: string | null | undefined,
  locale: ConversationTitleLocale,
  fallbackMessage?: string | null,
): string {
  const empty = locale === "zh" ? "新对话" : "New conversation";
  const compact = (title ?? "").trim();
  if (compact && !looksLikeIdentity(compact) && !PLACEHOLDERS.has(compact.toLowerCase())) {
    const structured = structuredInputTitle(compact, locale);
    if (structured) return structured;
    return compact;
  }
  const fallback = (fallbackMessage ?? "").trim();
  const excerpt = structuredInputTitle(fallback, locale) ?? fallback.split(/\s+/).join(" ").slice(0, 80);
  if (excerpt && !looksLikeIdentity(excerpt)) return excerpt;
  return empty;
}
