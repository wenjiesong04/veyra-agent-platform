export type ConversationAttachment = {
  id: string;
  name: string;
  size: number;
  kind: "text" | "document";
  text?: string;
};

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml", ".html", ".xml", ".log"]);
const DOCUMENT_EXTENSIONS = new Set([".pdf", ".docx"]);
const TEXT_LIMIT = 80_000;

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

export function isConversationFile(name: string): boolean {
  const extension = extensionOf(name);
  return TEXT_EXTENSIONS.has(extension) || DOCUMENT_EXTENSIONS.has(extension);
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
  return { id, name: file.name, size: file.size, kind: "document" };
}

export function attachmentsToPrompt(attachments: ConversationAttachment[], locale: "zh" | "en"): string {
  if (!attachments.length) return "";
  const blocks = attachments.map((item) => {
    if (item.kind === "text" && item.text) {
      return locale === "zh"
        ? `附件「${item.name}」正文：\n${item.text}`
        : `Attached file "${item.name}":\n${item.text}`;
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
