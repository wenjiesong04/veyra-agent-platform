import { FileText, X } from "lucide-react";
import type { ConversationAttachment } from "./conversation-attachment";

export function ConversationAttachmentList({
  items,
  locale,
  onRemove,
}: {
  items: ConversationAttachment[];
  locale: "zh" | "en";
  onRemove: (id: string) => void;
}) {
  if (!items.length) return null;
  return (
    <ul className="agent-convo-attachments">
      {items.map((item) => (
        <li key={item.id}>
          <FileText size={13} aria-hidden="true" />
          <span>
            {item.name}
            {item.kind === "document" ? <small>{locale === "zh" ? "未抽取正文" : "Body not extracted"}</small> : null}
          </span>
          <button type="button" aria-label={locale === "zh" ? `移除 ${item.name}` : `Remove ${item.name}`} onClick={() => onRemove(item.id)}>
            <X size={12} aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}
