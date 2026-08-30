import { ErrorState, LoadingState, Tag, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../api/project-workspace";
import { FactoryConversation } from "../features/factory/factory-conversation";

export function FactoryPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const zh = locale === "zh";
  const copy = zh
    ? { loading: "正在加载项目…", unavailable: "无法读取这个项目。", project: "项目" }
    : { loading: "Loading Project…", unavailable: "This Project could not be read.", project: "Project" };

  useEffect(() => {
    let current = true;
    setLoading(true);
    void api.getProject(projectId)
      .then((next) => { if (current) { setProject(next); upsertProject(next); } })
      .catch(() => { if (current) setError(copy.unavailable); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, copy.unavailable, projectId, upsertProject]);

  if (loading) return <LoadingState label={copy.loading} />;
  if (error || !project) return <ErrorState message={error ?? copy.unavailable} />;
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.project}</span>
          <h2>{zh ? "添加 Agent" : "Add Agent"}</h2>
          <p>{zh ? "通过 Factory 对话，用资源库组装一个可检查的 Agent Draft。" : "Use a Factory conversation to assemble an inspectable Agent Draft from the catalog."}</p>
        </div>
        <Tag>{project.name}</Tag>
      </div>
      <FactoryConversation api={api} projectId={projectId} locale={locale} />
    </div>
  );
}
