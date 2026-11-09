import * as React from "react";
import { FileImage, FileText, X } from "lucide-react";
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
  const previewUrls = React.useRef(new Set<string>());
  React.useEffect(() => {
    const next = new Set(items.flatMap((item) => item.previewUrl ? [item.previewUrl] : []));
    for (const url of previewUrls.current) {
      if (!next.has(url)) URL.revokeObjectURL?.(url);
    }
    previewUrls.current = next;
  }, [items]);
  React.useEffect(() => () => {
    for (const url of previewUrls.current) URL.revokeObjectURL?.(url);
    previewUrls.current.clear();
  }, []);
  if (!items.length) return null;
  return (
    <ul className="agent-convo-attachments">
      {items.map((item) => (
        <li key={item.id} className={item.kind === "image" ? "is-image-attachment" : undefined}>
          {item.kind === "image" && item.previewUrl ? <img src={item.previewUrl} alt={item.name} /> : item.kind === "image" ? <FileImage size={13} aria-hidden="true" /> : <FileText size={13} aria-hidden="true" />}
          <span>
            {item.name}
            {item.kind === "document" ? <small>{locale === "zh" ? "未抽取正文" : "Body not extracted"}</small> : null}
            {item.kind === "image" ? <small>{locale === "zh" ? "Builder 只记录文件信息，不会分析图片内容" : "Builder records metadata only; it cannot analyze pixels"}</small> : null}
            <small>{item.mediaType ? `${item.mediaType} · ` : ""}{formatSize(item.size, locale)}</small>
          </span>
          <button type="button" aria-label={locale === "zh" ? `移除 ${item.name}` : `Remove ${item.name}`} onClick={() => onRemove(item.id)}>
            <X size={12} aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function formatSize(size: number, locale: "zh" | "en"): string {
  if (size < 1024) return locale === "zh" ? `${size} 字节` : `${size} bytes`;
  const kilobytes = size / 1024;
  if (kilobytes < 1024) return `${kilobytes.toFixed(kilobytes < 10 ? 1 : 0)} KB`;
  return `${(kilobytes / 1024).toFixed(1)} MB`;
}
