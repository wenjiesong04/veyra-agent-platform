import { libraryRoutePaths, type RuntimeEvent } from "@veyra/api-contracts";
import { projectFileId } from "../../projects/agent-tree";

export function GeneratedProjectFiles({ events, projectId, locale }: { events?: RuntimeEvent[]; projectId: string; locale: "zh" | "en" }) {
  const paths = [...new Set((events ?? []).flatMap((event) => {
    const path = event.payload.relative_path;
    if (event.kind !== "tool.completed" || event.payload.adapter !== "veyra.runtime.filesystem.write" || typeof path !== "string") return [];
    const segments = path.split("/");
    return /^(assets|knowledge)\//.test(path) && !/[\\\u0000-\u001f\u007f]/.test(path) && !segments.some((part) => !part || part === "." || part === "..") ? [path] : [];
  }))];
  if (!paths.length) return null;
  const title = locale === "zh" ? "已生成的项目文件" : "Generated Project files";
  return <section className="agent-generated-files" aria-label={title}>
    <strong>{title}</strong>
    <ul>{paths.map((path) => <li key={path}><a href={libraryRoutePaths.file(projectFileId(projectId, path))}>{path.split("/").at(-1)}</a><small>{path}</small></li>)}</ul>
  </section>;
}
