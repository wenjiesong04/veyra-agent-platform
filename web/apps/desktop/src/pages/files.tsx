import { ArrowLeft, FileCode2, FolderOpen } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths } from "@veyra/api-contracts";
import { LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

const files = [
  { id: "review-agent", name: "review-agent.vagent.yaml", summary: "Agent source definition", version: "v0.4", status: "synced" as const },
  { id: "release-check", name: "release-check.vagent.yaml", summary: "Agent source definition", version: "v0.2", status: "synced" as const },
  { id: "workspace-rules", name: "workspace-rules.yaml", summary: "Project-scoped policy", version: "draft", status: "draft" as const },
];

export function FilesPage({ fileId }: { fileId?: string }) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    missing: "找不到文件", missingDetail: "请求的文件在本机库中不可用。", back: "返回文件", file: "文件", all: "全部文件", library: "组件库", title: "文件", description: "源文件和项目资源与可变的运行状态保持分离。", openProject: "打开项目", projectLibrary: "项目库", count: "个文件", source: "源文件", identity: "文件身份", revision: "修订", status: "状态", storage: "存储", projectStorage: "项目库", format: "格式", synced: "已同步", draft: "草稿",
  } : {
    missing: "File not found", missingDetail: "The requested File is not available in this local library.", back: "Back to Files", file: "File", all: "All Files", library: "Library", title: "Files", description: "Source files and project resources remain separate from mutable run state.", openProject: "Open Project", projectLibrary: "Project library", count: "Files", source: "Source file", identity: "File identity", revision: "Revision", status: "Status", storage: "Storage", projectStorage: "Project library", format: "Format", synced: "synced", draft: "draft",
  };
  const statusLabel = (status: "synced" | "draft") => status === "synced" ? copy.synced : copy.draft;
  if (fileId) {
    const file = files.find((item) => item.id === fileId);
    if (!file) return <div className="project-missing"><StatusBadge label={copy.missing} tone="bad" /><p>{copy.missingDetail}</p><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.file} / {file.id}</span><h2>{file.name}</h2><p>{file.summary}</p></div><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="ghost">{copy.all}</LinkButton></div><Panel><SectionHeading eyebrow={copy.source} title={copy.identity} /><div className="settings-facts"><div><span>{copy.revision}</span><strong>{file.version}</strong></div><div><span>{copy.status}</span><StatusBadge label={statusLabel(file.status)} tone={file.status === "synced" ? "good" : "warn"} /></div><div><span>{copy.storage}</span><strong>{copy.projectStorage}</strong></div><div><span>{copy.format}</span><Tag>YAML</Tag></div></div></Panel></div>;
  }

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.library}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><LinkButton href={projectRoutePaths.project("signal-review")} icon={FolderOpen} variant="primary">{copy.openProject}</LinkButton></div><Panel><SectionHeading eyebrow={copy.projectLibrary} title={`${files.length} ${copy.count}`} /><div className="project-agent-list">{files.map((file) => <a className="project-agent-row" href={libraryRoutePaths.file(file.id)} key={file.id}><span className="row-icon"><FileCode2 size={17} /></span><span className="row-copy"><strong>{file.name}</strong><small>{file.summary}</small><em><Tag>{file.version}</Tag></em></span><StatusBadge label={statusLabel(file.status)} tone={file.status === "synced" ? "good" : "warn"} /></a>)}</div></Panel></div>;
}
