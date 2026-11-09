export type ConversationAttachment = {
  id: string;
  name: string;
  size: number;
  kind: "text" | "document" | "image";
  mediaType?: string;
  previewUrl?: string;
  text?: string;
};

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml", ".html", ".xml", ".log"]);
const DOCUMENT_EXTENSIONS = new Set([".pdf", ".docx"]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif"]);
const IMAGE_MIME_EXTENSIONS: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "image/gif": ".gif",
};
const SAFE_MIME_EXTENSIONS: Record<string, string> = {
  ...IMAGE_MIME_EXTENSIONS,
  "application/pdf": ".pdf",
  "text/plain": ".txt",
  "text/markdown": ".md",
  "text/csv": ".csv",
  "application/json": ".json",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
};
const TEXT_LIMIT = 80_000;
export const MAX_CONVERSATION_FILE_BYTES = 25_000_000;

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function ensureClipboardFileName(file: File, index = 1): File {
  if (file.name && file.name !== "blob") return file;
  const extension = SAFE_MIME_EXTENSIONS[file.type] ?? ".bin";
  return new File([file], `pasted-file-${Date.now()}-${index}${extension}`, { type: file.type || "application/octet-stream", lastModified: file.lastModified });
}

export function clipboardFiles(data: DataTransfer): File[] {
  const fromItems = Array.from(data.items)
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((item): item is File => Boolean(item));
  const candidates = fromItems.length ? fromItems : Array.from(data.files ?? []);
  const seen = new Set<File>();
  return candidates.filter((file) => {
    if (seen.has(file)) return false;
    seen.add(file);
    return true;
  });
}

export function clipboardCaption(text: string, files: File[]): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (files.some((file) => file.name && trimmed === file.name)) return "";
  if (/^file:\/\//i.test(trimmed)) return "";
  if (/^[A-Za-z]:[\\/]/.test(trimmed) || /^\\\\/.test(trimmed)) return "";
  if (/^\/(?:Users|private|home|tmp|Volumes|var|etc|opt|Applications)\//.test(trimmed)) return "";
  return text;
}

export function isConversationFile(name: string, mediaType = ""): boolean {
  const extension = extensionOf(name);
  return TEXT_EXTENSIONS.has(extension) || DOCUMENT_EXTENSIONS.has(extension) || IMAGE_EXTENSIONS.has(extension) || Boolean(IMAGE_MIME_EXTENSIONS[mediaType]);
}

async function readFileText(file: File): Promise<string> {
  if (typeof file.arrayBuffer === "function") {
    return new TextDecoder().decode(await file.arrayBuffer());
  }
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("The file could not be read."));
    reader.readAsText(file);
  });
}

export async function readConversationFile(file: File, id: string): Promise<ConversationAttachment> {
  const extension = extensionOf(file.name);
  if (TEXT_EXTENSIONS.has(extension) || file.type.startsWith("text/")) {
    const raw = await readFileText(file);
    const text = raw.slice(0, TEXT_LIMIT);
    return { id, name: file.name, size: file.size, kind: "text", text };
  }
  if (IMAGE_EXTENSIONS.has(extension) || Boolean(IMAGE_MIME_EXTENSIONS[file.type])) {
    let previewUrl: string | undefined;
    if (typeof URL.createObjectURL === "function") {
      try { previewUrl = URL.createObjectURL(file); } catch { previewUrl = undefined; }
    }
    const mediaType = file.type || Object.entries(IMAGE_MIME_EXTENSIONS).find(([, value]) => value === extension)?.[0] || "image/*";
    return { id, name: file.name, size: file.size, kind: "image", mediaType, previewUrl };
  }
  return { id, name: file.name, size: file.size, kind: "document", mediaType: file.type || "application/octet-stream" };
}

export function attachmentsToPrompt(attachments: ConversationAttachment[], locale: "zh" | "en"): string {
  if (!attachments.length) return "";
  const blocks = attachments.map((item) => {
    if (item.kind === "text" && item.text) {
      return locale === "zh"
        ? `附件「${item.name}」正文：\n${item.text}`
        : `Attached file "${item.name}":\n${item.text}`;
    }
    if (item.kind === "image") {
      return locale === "zh"
        ? `图片附件「${item.name}」（${item.mediaType || "image"}，${item.size} 字节）。当前 Builder 只记录图片文件信息，不会分析图片内容；不要根据图片推断任何事实。`
        : `Image attachment "${item.name}" (${item.mediaType || "image"}, ${item.size} bytes). Builder records the file metadata only and does not analyze image pixels; do not infer anything from the image.`;
    }
    return locale === "zh"
      ? `附件「${item.name}」是 ${extensionOf(item.name).slice(1).toUpperCase() || "document"} 文件（${item.size} 字节）。对话框尚未抽取正文；把它当作这个 Agent 应该处理的输入格式示例，不要编造文件内容。`
      : `Attached file "${item.name}" is a ${extensionOf(item.name).slice(1).toUpperCase() || "document"} (${item.size} bytes). This chat did not extract its body; treat it as an example of the input format the Agent should handle, and do not invent the file contents.`;
  });
  return blocks.join("\n\n");
}

export function composeFactoryPrompt(message: string, attachments: ConversationAttachment[], locale: "zh" | "en"): string {
  const prompt = message.trim();
  const attached = attachmentsToPrompt(attachments, locale);
  if (prompt && attached) return `${prompt}\n\n${attached}`;
  return prompt || attached;
}
