import { FolderKanban, LockKeyhole, Sparkles } from "lucide-react";
import { Button, ErrorState, LoadingState, Panel, SectionHeading, Tag, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../api/project-workspace";

export function FactoryPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const zh = locale === "zh";
  const copy = zh ? { loading: "正在加载项目…", unavailable: "无法读取这个项目。", title: "添加 Agent", detail: "Factory 是在这个项目中开始 Agent 创建的明确入口。", project: "项目", empty: "此项目还没有 Agent", emptyDetail: "先描述你想构建的 Agent。生成服务可用后，会把草稿交给你检查，而不会静默创建 Agent。", requirement: "这个 Agent 应该做什么？", placeholder: "例如：收集证据，准备简报，并在外部写入前请求审批。", pending: "Factory 生成服务尚未连接", boundary: "权限与验证始终需要明确确认。" } : { loading: "Loading Project…", unavailable: "This Project could not be read.", title: "Add Agent", detail: "Factory is the explicit entry point for starting Agent creation in this Project.", project: "Project", empty: "This Project has no Agents yet", emptyDetail: "Describe the Agent you want to build first. When the generation service is available, it will give you a draft to review; it will never silently create an Agent.", requirement: "What should this Agent do?", placeholder: "For example: collect evidence, prepare a brief, and request approval before an external write.", pending: "Factory generation service is not connected yet", boundary: "Permissions and verification always require an explicit decision." };

  useEffect(() => {
    let current = true;
    setLoading(true);
    void api.getProject(projectId).then((next) => { if (current) { setProject(next); upsertProject(next); } }).catch(() => { if (current) setError(copy.unavailable); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, copy.unavailable, projectId, upsertProject]);
  if (loading) return <LoadingState label={copy.loading} />;
  if (error || !project) return <ErrorState message={error ?? copy.unavailable} />;
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.project}</span><h2>{copy.title}</h2><p>{copy.detail}</p></div><Tag>{project.name}</Tag></div><div className="factory-layout"><Panel className="factory-prompt-panel"><SectionHeading eyebrow="01" title={copy.requirement} /><label className="field-label" htmlFor="factory-prompt">{copy.requirement}</label><textarea id="factory-prompt" className="factory-textarea" placeholder={copy.placeholder} rows={8} /><div className="factory-form-footer"><span><LockKeyhole size={14} />{copy.boundary}</span><Button icon={Sparkles} variant="primary" disabled>{copy.pending}</Button></div></Panel><Panel className="factory-result-panel"><SectionHeading eyebrow="02" title={copy.empty} /><div className="factory-empty"><span><FolderKanban size={22} /></span><strong>{copy.empty}</strong><p>{copy.emptyDetail}</p></div></Panel></div></div>;
}
