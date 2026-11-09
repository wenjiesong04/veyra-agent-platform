import { memo, type ReactNode } from "react";
import { Image as ImageIcon } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

function OutputLink({ href, title, children }: { href?: string; title?: string; children: ReactNode }) {
  return href
    ? <a href={href} title={title} target="_blank" rel="noreferrer noopener">{children}</a>
    : <span>{children}</span>;
}

export const RuntimeMarkdown = memo(function RuntimeMarkdown({ value, locale }: { value: string; locale: "zh" | "en" }) {
  return <div className="runtime-reading-markdown">
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="runtime-reading-text">{children}</p>,
        a: ({ href, title, children }) => <OutputLink href={href} title={title}>{children}</OutputLink>,
        // Generated text must not silently fetch remote images. ArtifactRefs keep their own preview path.
        img: ({ src, alt, title }) => <OutputLink href={src} title={title}>
          <span className="runtime-reading-image-link"><ImageIcon size={16} aria-hidden="true" />{alt || (locale === "zh" ? "图片" : "Image")}</span>
        </OutputLink>,
        table: ({ children }) => <div className="runtime-reading-table-wrap" role="region" tabIndex={0} aria-label={locale === "zh" ? "报告表格，可左右滚动" : "Report table, scroll horizontally"}>
          <table className="runtime-reading-table" aria-label={locale === "zh" ? "报告表格" : "Report table"}>{children}</table>
        </div>,
      }}
    >{value}</Markdown>
  </div>;
});
