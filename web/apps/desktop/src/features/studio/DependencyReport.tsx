import type { AgentDependencyCheck, ValidateResponse } from "@veyra/api-contracts";
import { StatusBadge } from "@veyra/ui";

const statusCopy: Record<AgentDependencyCheck["status"], { zh: string; en: string }> = {
  ready: { zh: "就绪", en: "Ready" },
  missing: { zh: "找不到", en: "Missing" },
  lock_missing: { zh: "未锁定", en: "Not locked" },
  lock_mismatch: { zh: "锁不匹配", en: "Lock mismatch" },
  kind_mismatch: { zh: "类型不匹配", en: "Kind mismatch" },
  configuration_required: { zh: "需要配置", en: "Needs configuration" },
  runtime_unavailable: { zh: "Runtime 不可用", en: "Runtime unavailable" },
  review_required: { zh: "等待审核", en: "Review required" },
  permission_denied: { zh: "权限不足", en: "Permission denied" },
  secret_declaration_missing: { zh: "未声明密钥", en: "Secret not declared" },
  context_not_declared: { zh: "未声明上下文", en: "Context not declared" },
  context_too_large: { zh: "上下文过大", en: "Context too large" },
  project_binding_stale: { zh: "项目绑定已过期", en: "Project binding stale" },
};

export function DependencyReport({ validation, locale }: { validation: ValidateResponse; locale: "zh" | "en" }) {
  const dependencies = validation.dependencies;
  const summary = validation.dependency_summary;
  if (!dependencies || !summary) return null;
  const zh = locale === "zh";
  const healthy = validation.runtime_ready === true;
  return (
    <div className="studio-dependency-report" role="status" aria-label={zh ? "Agent 依赖检查" : "Agent dependency check"}>
      <div className="studio-dependency-heading">
        <strong>{zh ? "运行前依赖检查" : "Pre-run dependency check"}</strong>
        <StatusBadge label={healthy ? (zh ? "依赖已就绪" : "Dependencies ready") : (zh ? "需要处理" : "Attention needed")} tone={healthy ? "good" : "warn"} />
      </div>
      <small>{zh ? `${summary.total} 项依赖 · ${summary.ready} 项就绪 · ${summary.attention} 项需要处理。模型 API Key 和主机密钥仍会在真正运行时检查。` : `${summary.total} dependencies · ${summary.ready} ready · ${summary.attention} need attention. The model API key and host secrets are still checked at execution time.`}</small>
      {dependencies.length ? <ul className="studio-dependency-list">{dependencies.map((dependency) => <li key={dependency.reference} className={dependency.status === "ready" ? "is-ready" : "is-attention"}><span><strong>{dependency.name}</strong><code>{dependency.reference}</code></span><StatusBadge label={statusCopy[dependency.status][locale]} tone={dependency.status === "ready" ? "good" : "warn"} /><p>{dependency.detail}{dependency.project_binding_status === "stale" ? ` · ${zh ? "请在项目资源页和 Agent 中重新绑定" : "Rebind it in Project resources and the Agent"}` : ""}</p></li>)}</ul> : <p className="studio-dependency-empty">{zh ? "这个 Agent 没有额外的 Tool、Skill 或 Knowledge 依赖。" : "This Agent has no additional Tool, Skill, or Knowledge dependencies."}</p>}
    </div>
  );
}
