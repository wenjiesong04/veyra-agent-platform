import { ArrowLeft, FileCode2, FolderOpen } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths, type ProjectFileRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useEffect, useMemo, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";
import { parseProjectFileId, projectFileId } from "../features/projects/agent-tree";

export function FilesPage({ fileId, projectId }: { fileId?: string; projectId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects, status } = useProjectWorkspace();
  const scopedProjects = useMemo(
    () => (projectId ? projects.filter((project) => project.project_id === projectId) : projects),
    [projectId, projects],
  );
  const copy = zh ? {
    missing: "找不到文件", missingDetail: "请求的文件在已索引的项目源中不可用。", back: "返回文件", file: "文件", all: "全部文件", library: "知识库", title: "文件", description: "这里只列出项目里已索引的源文件、README、测试和 resources，不包含运行状态或密钥。", openProject: "打开项目", projectLibrary: "项目文件", count: "个文件", empty: "还没有项目文件", emptyDetail: "创建或打开一个项目后，这里会显示它的源文件树。", preview: "预览", identity: "文件身份", kind: "类型", size: "大小", project: "项目", path: "路径",
  } : {
    missing: "File not found", missingDetail: "The requested file is not available in the indexed Project sources.", back: "Back to Files", file: "File", all: "All Files", library: "Knowledge base", title: "Files", description: "Indexed source files, READMEs, tests, and resources stay separate from run state and secrets.", openProject: "Open Project", projectLibrary: "Project files", count: "Files", empty: "No Project files yet", emptyDetail: "Create or open a Project to see its source file tree here.", preview: "Preview", identity: "File identity", kind: "Kind", size: "Size", project: "Project", path: "Path",
  };
  const [listings, setListings] = useState<Record<string, ProjectFileRecord[]>>({});
  const [listingError, setListingError] = useState<string | null>(null);
  const selected = fileId ? parseProjectFileId(fileId) : null;

  useEffect(() => {
    if (!api.listProjectFiles) return;
    let current = true;
    void Promise.all(scopedProjects.map(async (project) => {
      const response = await api.listProjectFiles!(project.project_id);
      return [project.project_id, response.files] as const;
    })).then((entries) => {
      if (!current) return;
      setListings(Object.fromEntries(entries));
      setListingError(null);
    }).catch((cause: unknown) => {
      if (current) setListingError(cause instanceof Error ? cause.message : copy.missingDetail);
    });
    return () => { current = false; };
  }, [api, copy.missingDetail, scopedProjects]);

  const allFiles = useMemo(() => {
    return scopedProjects.flatMap((project) => (listings[project.project_id] ?? []).map((file) => ({ project, file })));
  }, [listings, scopedProjects]);

  if (fileId) {
    return <FilePreviewPage fileId={fileId} selected={selected} projects={scopedProjects} copy={copy} />;
  }

  if (status === "loading" && !scopedProjects.length) return <LoadingState label={zh ? "正在加载文件…" : "Loading files…"} />;
  if (status === "error") return <ErrorState message={listingError || copy.missingDetail} />;
  const firstProject = scopedProjects[0];

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.library}</span><h2>{copy.title}</h2><p>{copy.description}</p></div>{firstProject ? <LinkButton href={projectRoutePaths.project(firstProject.project_id)} icon={FolderOpen} variant="primary">{copy.openProject}</LinkButton> : null}</div>
    {listingError ? <ErrorState message={listingError} /> : null}
    {allFiles.length === 0 ? <Panel><EmptyState icon={FileCode2} title={copy.empty} detail={copy.emptyDetail} /></Panel> : scopedProjects.map((project) => {
      const files = listings[project.project_id] ?? [];
      if (!files.length) return null;
      return <Panel key={project.project_id}><SectionHeading eyebrow={project.name} title={`${files.length} ${copy.count}`} /><div className="project-agent-list">{files.map((file) => <a className="project-agent-row" href={libraryRoutePaths.file(projectFileId(project.project_id, file.path))} key={file.path}><span className="row-icon"><FileCode2 size={17} /></span><span className="row-copy"><strong>{file.path.split("/").at(-1)}</strong><small>{file.path}</small></span><Tag>{file.kind}</Tag></a>)}</div></Panel>;
    })}
  </div>;
}

function FilePreviewPage({
  fileId,
  selected,
  projects,
  copy,
}: {
  fileId: string;
  selected: { projectId: string; path: string } | null;
  projects: ProjectSummaryResponse[];
  copy: Record<string, string>;
}) {
  const { api } = useProjectWorkspace();
  const [text, setText] = useState<string | null>(null);
  const [meta, setMeta] = useState<ProjectFileRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const project = selected ? projects.find((item) => item.project_id === selected.projectId) : undefined;

  useEffect(() => {
    if (!selected || !api.getProjectFile) {
      setError(copy.missing);
      return;
    }
    let current = true;
    void api.getProjectFile(selected.projectId, selected.path).then((response) => {
      if (!current) return;
      setMeta(response);
      setText(response.text);
      setError(null);
    }).catch((cause: unknown) => {
      if (current) setError(cause instanceof Error ? cause.message : copy.missing);
    });
    return () => { current = false; };
  }, [api, copy.missing, selected]);

  if (!selected) {
    return <div className="project-missing"><StatusBadge label={copy.missing} tone="bad" /><p>{copy.missingDetail}</p><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  }
  if (error && !meta) {
    return <div className="project-missing"><ErrorState message={error} /><p>{copy.missingDetail}</p><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  }
  if (!meta) return <LoadingState label={copy.file} />;
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.file} / {fileId}</span><h2>{meta.path.split("/").at(-1)}</h2><p>{meta.path}</p></div><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="ghost">{copy.all}</LinkButton></div>
    <Panel><SectionHeading eyebrow={copy.preview} title={copy.identity} /><div className="settings-facts"><div><span>{copy.kind}</span><strong>{meta.kind}</strong></div><div><span>{copy.size}</span><strong>{meta.byte_length}</strong></div><div><span>{copy.project}</span><strong>{project?.name ?? selected.projectId}</strong></div><div><span>{copy.path}</span><strong>{meta.path}</strong></div></div>{text !== null ? <pre className="project-file-preview">{text}</pre> : null}</Panel>
  </div>;
}
