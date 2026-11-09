import type { AgentDependencyCheck, ValidateResponse } from "@veyra/api-contracts";

export type BuilderValidationIssue = {
  code: AgentDependencyCheck["status"];
  kind: string;
  reference: string;
  name: string;
  message: string;
  blocking: true;
  repairable: boolean;
  locked_hash?: string;
  bound_content_hash?: string;
  content_hash?: string;
  version?: string;
  required_permissions?: AgentDependencyCheck["required_permissions"];
  next_action: string | null;
};

const nextAction: Partial<Record<AgentDependencyCheck["status"], { zh: string; en: string }>> = {
  resource_unbound: {
    zh: "请先在 Project Resources 中显式添加该 Tool。Builder 不会从 Catalog 自动添加。",
    en: "Add this Tool in Project Resources first. Builder will not add it from the Catalog.",
  },
  missing: {
    zh: "当前 Project 没有这份依赖。请选择已拥有的资源，不要猜测。",
    en: "This dependency is not available in the current Project. Choose an owned resource instead of guessing.",
  },
  configuration_required: {
    zh: "请先在资源库配置主机凭据。Builder 不会保存密钥。",
    en: "Configure the host credential in Resource Library. Builder will not store secrets.",
  },
  runtime_unavailable: {
    zh: "该资源无法在本地 Runtime 执行。",
    en: "This resource cannot run on the local Runtime.",
  },
  review_required: {
    zh: "请先审核发现的 MCP Tool。",
    en: "Review the discovered MCP tool before using it.",
  },
  project_binding_stale: {
    zh: "请在 Project Resources 中显式重新绑定 pin。Builder 不会把 Agent lock 静默升级到 Catalog hash。",
    en: "Rebind the Project Resource pin explicitly. Builder will not silently upgrade the Agent lock to the Catalog hash.",
  },
  kind_mismatch: {
    zh: "Catalog 类型与当前 Agent 用法不匹配。",
    en: "The Catalog kind does not match this Agent usage.",
  },
  secret_declaration_missing: {
    zh: "请在 Studio 声明密钥引用。Builder 不会配置主机密钥。",
    en: "Declare the secret reference in Studio. Builder will not configure host secrets.",
  },
  context_not_declared: {
    zh: "请在 Agent source 中声明 Knowledge 引用。",
    en: "Declare the Knowledge reference in the Agent source.",
  },
  context_too_large: {
    zh: "请减少 Knowledge 文档数量直到符合上限。",
    en: "Remove Knowledge documents until the Agent is within the limit.",
  },
};

const titles: Record<AgentDependencyCheck["status"], { zh: string; en: string }> = {
  ready: { zh: "就绪", en: "Ready" },
  missing: { zh: "找不到依赖", en: "Missing dependency" },
  lock_missing: { zh: "未锁定 Resource", en: "Resource not locked" },
  lock_mismatch: { zh: "锁与 Project pin 不一致", en: "Resource lock mismatch" },
  kind_mismatch: { zh: "类型不匹配", en: "Kind mismatch" },
  configuration_required: { zh: "需要配置", en: "Needs configuration" },
  runtime_unavailable: { zh: "Runtime 不可用", en: "Runtime unavailable" },
  review_required: { zh: "等待审核", en: "Review required" },
  permission_denied: { zh: "缺少所需权限", en: "Permission missing" },
  secret_declaration_missing: { zh: "未声明密钥", en: "Secret not declared" },
  context_not_declared: { zh: "未声明知识上下文", en: "Knowledge not declared" },
  context_too_large: { zh: "知识上下文过大", en: "Knowledge context too large" },
  project_binding_stale: { zh: "Project pin 已漂移", en: "Project binding stale" },
  resource_unbound: { zh: "尚未加入当前 Project", en: "Not bound to this Project" },
};

export function builderValidationFailed(validation: Omit<ValidateResponse, "file_hash">): boolean {
  if (validation.valid !== true) return true;
  if (validation.runtime_ready === false) return true;
  return (validation.dependencies ?? []).some((item) => item.status !== "ready");
}

export function builderValidationIssues(validation: Omit<ValidateResponse, "file_hash">): BuilderValidationIssue[] {
  return (validation.dependencies ?? []).flatMap((dependency) => {
    if (dependency.status === "ready") return [];
    const repairable = isRepairable(dependency);
    return [{
      code: dependency.status,
      kind: dependency.kind,
      reference: dependency.reference,
      name: dependency.name,
      message: dependency.detail,
      blocking: true,
      repairable,
      ...(dependency.locked_hash ? { locked_hash: dependency.locked_hash } : {}),
      ...(dependency.bound_content_hash ? { bound_content_hash: dependency.bound_content_hash } : {}),
      ...(dependency.content_hash ? { content_hash: dependency.content_hash } : {}),
      ...(dependency.version ? { version: dependency.version } : {}),
      ...(dependency.required_permissions ? { required_permissions: dependency.required_permissions } : {}),
      next_action: repairable ? null : nextAction[dependency.status]?.en ?? null,
    }];
  });
}

export function issueTitle(code: AgentDependencyCheck["status"], locale: "zh" | "en"): string {
  return titles[code][locale];
}

export function issueNextAction(issue: BuilderValidationIssue, locale: "zh" | "en"): string | null {
  if (issue.repairable) return null;
  return nextAction[issue.code]?.[locale] ?? issue.next_action;
}

export function issueDetail(message: string): string | null {
  const text = message.trim();
  if (!text) return null;
  if (/traceback/i.test(text) || /file ".+", line \d+/i.test(text)) return null;
  return text;
}

function isDigest(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function isRepairable(dependency: AgentDependencyCheck): boolean {
  if (dependency.status === "permission_denied") {
    return Boolean(dependency.required_permissions && typeof dependency.required_permissions === "object");
  }
  if (dependency.status !== "lock_mismatch" && dependency.status !== "lock_missing") return false;
  if (dependency.kind === "knowledge") {
    return isDigest(dependency.content_hash) && Boolean(dependency.version && dependency.reference.endsWith(`@${dependency.version}`));
  }
  return isDigest(dependency.bound_content_hash);
}
