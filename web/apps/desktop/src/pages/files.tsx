import { ArrowLeft, FileCode2, FolderOpen } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths, type ProjectFileRecord, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LinkButton, ListSkeleton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useEffect, useMemo, useRef, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";
import { parseProjectFileId, projectFileId } from "../features/projects/agent-tree";
import { ProjectFileImport } from "../features/projects/ProjectFileImport";

export function ProjectFilesPanel({ projectId, projectName }: { projectId: string; projectName: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api } = useProjectWorkspace();
  const [files, setFiles] = useState<ProjectFileRecord[] | undefined>();
  const [error, setError] = useState<string | null>(null);
  const listingGeneration = useRef(0);
  const copy = zh
    ? { files: "文件", count: "个文件", empty: "还没有项目文件", emptyDetail: "导入任务材料，或在这里浏览索引后的项目源文件。", loading: "正在加载文件…" }
    : { files: "Files", count: "Files", empty: "No Project files yet", emptyDetail: "Import task materials or browse indexed Project sources here.", loading: "Loading files…" };

  useEffect(() => {
    setFiles(undefined);
    setError(null);
    const generation = ++listingGeneration.current;
    if (!api.listProjectFiles) {
      setFiles([]);
      return;
    }
    let current = true;
    void api.listProjectFiles(projectId).then((response) => {
      if (!current || generation !== listingGeneration.current) return;
      setFiles(response.files);
      setError(null);
    }).catch((cause: unknown) => {
      if (current && generation === listingGeneration.current) setError(cause instanceof Error ? cause.message : copy.emptyDetail);
    });
    return () => { current = false; };
  }, [api, copy.emptyDetail, projectId]);

  return (
    <Panel>
      <SectionHeading eyebrow={projectName} title={files === undefined ? copy.files : `${files.length} ${copy.count}`} />
      <ProjectFileImport api={api} projectId={projectId} onFilesChange={(next) => { listingGeneration.current += 1; setFiles(next); setError(null); }} />
      {error ? <ErrorState message={error} /> : null}
      {files === undefined && !error ? <ListSkeleton label={copy.loading} /> : null}
      {files && files.length === 0 && !error ? <EmptyState icon={FileCode2} title={copy.empty} detail={copy.emptyDetail} /> : null}
      {files && files.length > 0 ? (
        <div className="project-agent-list">
          {files.map((file) => (
            <a className="project-agent-row" href={libraryRoutePaths.file(projectFileId(projectId, file.path))} key={file.path}>
              <span className="row-icon"><FileCode2 size={17} aria-hidden="true" /></span>
              <span className="row-copy"><strong>{file.path.split("/").at(-1)}</strong><small>{file.path}</small></span>
              <Tag>{file.kind}</Tag>
            </a>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

export function FilesPage({ fileId, projectId }: { fileId?: string; projectId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects, status } = useProjectWorkspace();
  const scopedProjects = useMemo(
    () => (projectId ? projects.filter((project) => project.project_id === projectId) : projects),
    [projectId, projects],
  );
  const copy = zh ? {
    missing: "找不到文件", missingDetail: "请求的文件在已索引的项目源中不可用。", back: "返回文件", file: "文件", all: "全部文件", library: "知识库", title: "文件", description: "导入任务材料，浏览项目里已索引的文件。", openProject: "打开项目", projectLibrary: "项目文件", count: "个文件", empty: "还没有项目文件", emptyDetail: "选择项目并导入文件，或打开已有项目查看文件。", loading: "正在加载文件…", preview: "预览", identity: "文件身份", kind: "类型", size: "大小", project: "项目", path: "路径", runtime: "Runtime", useInAgent: "在 Agent 中使用此文件", useInAgentDetail: "只会把相对路径预填到 Agent 的 path/file/document 输入；是否读取由 Agent 的 Filesystem Tool 权限决定。", chooseAgent: "选择 Agent", openStudio: "打开 Agent Studio", noAgents: "此 Project 还没有 Agent。", importFiles: "导入文件", importProject: "保存到项目", chooseProject: "选择项目", chooseProjectDetail: "选择一个项目，再导入任务材料。",
  } : {
    missing: "File not found", missingDetail: "The requested file is not available in the indexed Project sources.", back: "Back to Files", file: "File", all: "All Files", library: "Knowledge base", title: "Files", description: "Import task materials and browse indexed Project files.", openProject: "Open Project", projectLibrary: "Project files", count: "Files", empty: "No Project files yet", emptyDetail: "Choose a Project to import files, or open an existing Project to browse its files.", loading: "Loading files…", preview: "Preview", identity: "File identity", kind: "Kind", size: "Size", project: "Project", path: "Path", runtime: "Runtime", useInAgent: "Use this file in an Agent", useInAgentDetail: "Only the relative path is prefilled into a path/file/document input; reading still depends on the Agent's authorized Filesystem Tool.", chooseAgent: "Choose an Agent", openStudio: "Open Agent Studio", noAgents: "This Project has no Agent yet.", importFiles: "Import Files", importProject: "Save to Project", chooseProject: "Choose a Project", chooseProjectDetail: "Choose a Project, then import your task materials.",
  };
  const [listings, setListings] = useState<Record<string, ProjectFileRecord[]>>({});
  const [listingError, setListingError] = useState<string | null>(null);
  const [importProjectId, setImportProjectId] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const selected = useMemo(() => fileId ? parseProjectFileId(fileId) : null, [fileId]);
  const importProject = scopedProjects.find((project) => project.project_id === (projectId ?? importProjectId));

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

  const waitingForListings = Boolean(api.listProjectFiles) && scopedProjects.length > 0 && !listingError && scopedProjects.some((project) => listings[project.project_id] === undefined);

  if (fileId) {
    return <FilePreviewPage key={fileId} fileId={fileId} selected={selected} projects={scopedProjects} copy={copy} />;
  }

  if ((status === "loading" && !scopedProjects.length) || waitingForListings) {
    return (
      <div className="page-stack">
        <div className="page-intro">
          <div>
            <span className="ui-eyebrow">{copy.library}</span>
            <h2>{copy.title}</h2>
            <p>{copy.description}</p>
          </div>
        </div>
        <Panel><ListSkeleton label={copy.loading} /></Panel>
      </div>
    );
  }
  if (status === "error") return <ErrorState message={listingError || copy.missingDetail} />;
  const firstProject = scopedProjects[0];

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.library}</span><h2>{copy.title}</h2><p>{copy.description}</p></div>{firstProject ? <LinkButton href={projectRoutePaths.project(firstProject.project_id)} icon={FolderOpen} variant="primary">{copy.openProject}</LinkButton> : null}</div>
    {scopedProjects.length ? <Panel>
      <SectionHeading title={copy.importFiles} />
      {!projectId ? <label className="project-file-import-target"><span>{copy.importProject}</span><select name="import_project" autoComplete="off" disabled={importBusy} value={importProject?.project_id ?? ""} onChange={(event) => setImportProjectId(event.target.value)}><option value="">{copy.chooseProject}</option>{scopedProjects.map((project) => <option value={project.project_id} key={project.project_id}>{project.name}</option>)}</select></label> : null}
      {importProject ? <ProjectFileImport key={importProject.project_id} api={api} projectId={importProject.project_id} projectName={importProject.name} onBusyChange={setImportBusy} onFilesChange={(files) => { setListings((current) => ({ ...current, [importProject.project_id]: files })); setListingError(null); }} /> : <p className="project-file-import-hint">{copy.chooseProjectDetail}</p>}
    </Panel> : null}
    {listingError ? <ErrorState message={listingError} /> : null}
    {allFiles.length === 0 ? <Panel><EmptyState icon={FileCode2} title={copy.empty} detail={copy.emptyDetail} /></Panel> : scopedProjects.map((project) => {
      const files = listings[project.project_id] ?? [];
      if (!files.length) return null;
      return <Panel key={project.project_id}><SectionHeading eyebrow={project.name} title={`${files.length} ${copy.count}`} /><div className="project-agent-list">{files.map((file) => <a className="project-agent-row" href={libraryRoutePaths.file(projectFileId(project.project_id, file.path))} key={file.path}><span className="row-icon"><FileCode2 size={17} aria-hidden="true" /></span><span className="row-copy"><strong>{file.path.split("/").at(-1)}</strong><small>{file.path}</small></span><Tag>{file.kind}</Tag></a>)}</div></Panel>;
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
  const [targetAgentId, setTargetAgentId] = useState(project?.default_agent_id ?? project?.agents[0]?.agent_id ?? "");

  useEffect(() => {
    if (!project?.agents.some((agent) => agent.agent_id === targetAgentId)) {
      setTargetAgentId(project?.default_agent_id ?? project?.agents[0]?.agent_id ?? "");
    }
  }, [project, targetAgentId]);

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
  const studioHref = project && targetAgentId
    ? `${projectRoutePaths.agentDesign(project.project_id, targetAgentId)}?file=${encodeURIComponent(meta.path)}`
    : null;
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.file} / {fileId}</span><h2>{meta.path.split("/").at(-1)}</h2><p>{meta.path}</p></div><LinkButton href={desktopRoutePaths.files} icon={ArrowLeft} variant="ghost">{copy.all}</LinkButton></div>
    <Panel><SectionHeading eyebrow={copy.preview} title={copy.identity} /><div className="settings-facts"><div><span>{copy.kind}</span><strong>{meta.kind}</strong></div><div><span>{copy.size}</span><strong>{meta.byte_length}</strong></div><div><span>{copy.project}</span><strong>{project?.name ?? selected.projectId}</strong></div><div><span>{copy.path}</span><strong>{meta.path}</strong></div></div>{text !== null ? <pre className="project-file-preview">{text}</pre> : null}</Panel>
    <Panel><SectionHeading eyebrow={copy.runtime} title={copy.useInAgent} detail={copy.useInAgentDetail} />{project?.agents.length && studioHref ? <div className="button-row"><select aria-label={copy.chooseAgent} name="target_agent" autoComplete="off" value={targetAgentId} onChange={(event) => setTargetAgentId(event.target.value)}>{project.agents.map((agent) => <option value={agent.agent_id} key={agent.agent_id}>{agent.name || agent.slug}</option>)}</select><LinkButton href={studioHref} icon={FolderOpen} variant="primary">{copy.openStudio}</LinkButton></div> : <p className="project-file-preview">{copy.noAgents}</p>}</Panel>
  </div>;
}
