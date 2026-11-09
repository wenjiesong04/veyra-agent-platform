import { LocalApiClientError } from "../../api/local-client";

type Locale = "zh" | "en";

const PRODUCT: Record<string, { zh: string; en: string }> = {
  work_item_command_required: {
    zh: "此运行由任务调度管理。请回到监控页重试任务，保留固定版本和执行记录。",
    en: "This Run is managed by a WorkItem. Retry it from Monitor to retain its pinned version and execution history.",
  },
  workflow_execution_failed: {
    zh: "工作流执行发生内部错误。已完成的子 Agent 结果仍可查看。",
    en: "The Workflow encountered an internal error. Results from completed child Agents are still available.",
  },
  output_invalid: {
    zh: "结果不符合声明的输出字段。请在 Studio 检查输出定义。",
    en: "The result does not match the declared output fields. Review the outputs in Studio.",
  },
  output_type_invalid: {
    zh: "结果类型与输出定义不一致。请在 Studio 检查字段类型和文件输出。",
    en: "The result type does not match its output definition. Review field types and file outputs in Studio.",
  },
  runtime_not_configured: {
    zh: "尚未配置运行模型。",
    en: "Runtime model is not configured.",
  },
  runtime_timeout: {
    zh: "模型服务请求超时，未获得完整响应。请在运行详情查看失败阶段与超时设置，再检查服务状态。运行记录已保留；请勿直接重复已执行的外部操作。",
    en: "The model service request timed out before a complete response was received. Inspect the failed phase and timeout settings in Run details, then check service availability. Run records are retained; do not blindly repeat completed external actions.",
  },
  runtime_permission_denied: {
    zh: "模型服务拒绝访问（HTTP 403）。仅凭该状态无法确定具体原因。请核对模型、地域、工作空间和密钥配置，并查看执行记录。",
    en: "The model service refused access (HTTP 403). This status alone does not establish the cause. Check the model, region, workspace and key configuration, then inspect the execution record.",
  },
  runtime_invalid_response: {
    zh: "模型服务没有返回可用的回答。可以重试；已执行的工具记录仍可查看。",
    en: "The model service did not return a usable answer. You can retry; completed Tool records remain available.",
  },
  runtime_output_truncated: {
    zh: "模型在完成回答前达到输出上限。本轮未执行新动作；请缩小本次任务，或提高运行模型的输出额度后重试。",
    en: "The model reached its output limit before finishing. No new action was executed for this response. Reduce the task or raise the runtime output budget before retrying.",
  },
  needs_configuration: {
    zh: "这个 Agent 运行前还需要配置集成。",
    en: "This Agent needs configuration before it can run.",
  },
  resource_unbound: {
    zh: "所需资源尚未绑定到当前项目。",
    en: "A required resource is not bound to this Project.",
  },
  resource_identity_conflict: {
    zh: "固定的资源身份与当前 Agent 不一致。",
    en: "Pinned resource identity does not match this Agent.",
  },
  agent_has_no_committed_version: {
    zh: "这个 Agent 还是草稿。请先在 Studio 提交版本，再使用应用。",
    en: "This Agent is still a draft. Commit it in Studio before using the App.",
  },
  agent_version_not_found: {
    zh: "找不到可运行的 Agent 版本。",
    en: "Committed Agent version not found.",
  },
  conversation_version_mismatch: {
    zh: "这条对话固定在另一个 Agent 版本上。",
    en: "This conversation is pinned to a different Agent version.",
  },
  approval_rejected: {
    zh: "工具审批已被拒绝。",
    en: "Tool approval was rejected.",
  },
  agent_max_turns_exceeded: {
    zh: "Agent 已达到最大轮次。",
    en: "The Agent reached its maximum number of turns.",
  },
  agent_no_progress: {
    zh: "Agent 连续重复同一个工具调用而没有利用结果，已停止且没有再次执行。可在运行记录查看具体调用。",
    en: "The Agent repeated the same tool call without using its result, so the run stopped without running it again. Inspect the call in the run record.",
  },
  agent_finalization_budget_exhausted: {
    zh: "候选结果尚未完成要求的交付检查，剩余轮次不足，因此没有作为最终结果交付。",
    en: "The candidate was not delivered because no turn remains for its required review.",
  },
  agent_finalization_no_progress: {
    zh: "相同候选重复出现相同检查问题，已停止无进展的修改。可在运行记录查看具体反馈。",
    en: "The same candidate repeated the same review defects. Inspect the feedback in the run record.",
  },
  agent_finalization_uncertain: {
    zh: "现有证据不足以完成要求的检查，候选结果尚未交付。可在运行记录查看缺少的证据。",
    en: "Available evidence cannot establish the required checks. Inspect the missing evidence in the run record.",
  },
  agent_finalization_review_invalid: {
    zh: "检查模型未返回完整、有效的审查结果，候选结果尚未交付。",
    en: "The review model returned an invalid or incomplete assessment. The candidate was not delivered.",
  },
  tool_network_denied: {
    zh: "网络工具未被允许。",
    en: "This network tool is not permitted.",
  },
};

export function productError(error: unknown, locale: Locale): { message: string; code?: string } {
  const code = error instanceof LocalApiClientError ? error.code : undefined;
  const mapped = code ? PRODUCT[code] : undefined;
  if (mapped) return { message: mapped[locale], code };
  const message = error instanceof Error ? error.message : (locale === "zh" ? "本地运行失败。" : "The local run failed.");
  return { message, code };
}

export function productRunError(code: string | undefined, fallback: string, locale: Locale): string {
  if (!code) return fallback;
  return PRODUCT[code]?.[locale] ?? fallback;
}
