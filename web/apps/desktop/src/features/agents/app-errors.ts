import { LocalApiClientError } from "../../api/local-client";

type Locale = "zh" | "en";

const PRODUCT: Record<string, { zh: string; en: string }> = {
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
