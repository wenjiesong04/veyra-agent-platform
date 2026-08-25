import { ArrowLeft, FileCode2, FolderOpen } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths } from "@veyra/api-contracts";
import { LinkButton, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

const files = [
  { id: "review-agent", name: "review-agent.vagent.yaml", summary: "Agent source definition", version: "v0.4", status: "synced" as const },
  { id: "release-check", name: "release-check.vagent.yaml", summary: "Agent source definition", version: "v0.2", status: "synced" as const },
  { id: "workspace-rules", name: "workspace-rules.yaml", summary: "Project-scoped policy", version: "draft", status: "draft" as const },
];

export function FilesPage({ fileId }: { fileId?: string }) {
  if (fileId) {
    const file = files.find((item) => item.id === fileId);
    if (!file) return <div className="project-missing"><StatusBadge label="File not found" tone="bad" /><p>The requested File is not available in this local library.</p><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="primary">Back to Files</LinkButton></div>;
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">File / {file.id}</span><h2>{file.name}</h2><p>{file.summary}</p></div><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="ghost">All Files</LinkButton></div><Panel><SectionHeading eyebrow="Source file" title="File identity" /><div className="settings-facts"><div><span>Revision</span><strong>{file.version}</strong></div><div><span>Status</span><StatusBadge label={file.status} tone={file.status === "synced" ? "good" : "warn"} /></div><div><span>Storage</span><strong>Project library</strong></div><div><span>Format</span><Tag>YAML</Tag></div></div></Panel></div>;
  }

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Library</span><h2>Files</h2><p>Source files and project resources remain separate from mutable run state.</p></div><LinkButton href={projectRoutePaths.project("signal-review")} icon={FolderOpen} variant="primary">Open Project</LinkButton></div><Panel><SectionHeading eyebrow="Project library" title={`${files.length} Files`} /><div className="project-agent-list">{files.map((file) => <a className="project-agent-row" href={libraryRoutePaths.file(file.id)} key={file.id}><span className="row-icon"><FileCode2 size={17} /></span><span className="row-copy"><strong>{file.name}</strong><small>{file.summary}</small><em><Tag>{file.version}</Tag></em></span><StatusBadge label={file.status} tone={file.status === "synced" ? "good" : "warn"} /></a>)}</div></Panel></div>;
}
