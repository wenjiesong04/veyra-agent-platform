import { useState, type ReactNode } from "react";
import { projectRoutePaths } from "@veyra/api-contracts";
import { LinkButton } from "@veyra/ui";
import "./project-file-selection.css";

/** Explicit Project paths become visible context in the declared chat input. */
export function ProjectFileSelection({ paths, selected, onChange, projectId, locale, disabled = false, children }: {
  paths: string[];
  selected: string[];
  onChange: (paths: string[]) => void;
  projectId: string;
  locale: "zh" | "en";
  disabled?: boolean;
  children?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const materials = paths.filter((path) => /^(assets|knowledge)\//.test(path));
  const matches = materials.filter((path) => path.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <details className="agent-project-files">
    <summary>{locale === "zh" ? "选择项目文件" : "Choose Project files"}{selected.length ? ` · ${selected.length}` : ""}</summary>
    <p>{locale === "zh" ? "选择这次任务使用的材料。文件路径会随消息发送，原文件保留在项目中。" : "Select materials for this task. Their Project paths accompany your message; originals stay in the Project."}</p>
    {materials.length > 10 ? <input name="project-file-search" autoComplete="off" aria-label={locale === "zh" ? "查找项目文件" : "Find Project files"} placeholder={locale === "zh" ? "文件名…" : "Filename…"} value={query} onChange={(event) => setQuery(event.target.value)} /> : null}
    {matches.length ? <ul>{matches.slice(0, 50).map((path) => <li key={path}><label>
      <input type="checkbox" disabled={disabled} checked={selected.includes(path)} onChange={(event) => onChange(event.target.checked ? [...selected, path] : selected.filter((item) => item !== path))} />
      <span>{path}</span>
    </label></li>)}</ul> : <p>{locale === "zh" ? (materials.length ? "没有匹配的文件。" : "项目中还没有材料，请先导入文件。") : (materials.length ? "No matching files." : "Import files to add materials to this Project.")}</p>}
    {matches.length > 50 ? <small>{locale === "zh" ? "显示前 50 个结果，请输入文件名缩小范围。" : "Showing the first 50 matches. Search to narrow the list."}</small> : null}
    {children}
    <LinkButton href={projectRoutePaths.files(projectId)} size="sm" variant="ghost">{locale === "zh" ? "管理项目文件" : "Manage Project files"}</LinkButton>
  </details>;
}
