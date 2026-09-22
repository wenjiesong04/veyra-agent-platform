import * as React from "react";
import type {
  BuilderConversationOperation,
  BuilderConversationSnapshot,
  CustomComponentProposal,
} from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";

type Props = {
  api: LocalProjectApi;
  projectId: string;
  conversationId: string;
  operation: BuilderConversationOperation;
  locale: "zh" | "en";
  onSnapshot: (snapshot: BuilderConversationSnapshot) => void;
};

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? String(value);
}

export function BuilderComponentProposal({
  api,
  projectId,
  conversationId,
  operation,
  locale,
  onSnapshot,
}: Props) {
  const zh = locale === "zh";
  const proposalId = operation.proposal_id;
  const [proposal, setProposal] = React.useState<CustomComponentProposal | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let current = true;
    setProposal(null);
    setLoading(true);
    setError("");
    if (!proposalId || !api.getBuilderComponentProposal) {
      setLoading(false);
      setError(zh ? "当前 Local sidecar 不支持读取 Component 提案，请先更新。" : "This Local sidecar cannot read Component proposals. Update it first.");
      return () => { current = false; };
    }
    void api.getBuilderComponentProposal(projectId, proposalId)
      .then((result) => { if (current) setProposal(result); })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, projectId, proposalId, zh]);

  const command = async (action: "apply" | "reject") => {
    if (!proposalId || !api.commandBuilderComponentProposal || busy) return;
    setBusy(true);
    setError("");
    try {
      const snapshot = await api.commandBuilderComponentProposal(
        projectId,
        conversationId,
        operation.operation_id,
        proposalId,
        { command: action, confirm: true, locale },
      );
      onSnapshot(snapshot);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <section className="builder-component-proposal"><p>{zh ? "正在读取组件提案…" : "Loading Component proposal…"}</p></section>;
  if (!proposal) return <section className="builder-component-proposal">{error ? <Alert type="error">{error}</Alert> : null}</section>;

  const plan = proposal.component_plan;
  const isReview = proposal.state === "review";
  const readiness = plan.readiness_expectation === "ready"
    ? (zh ? "确认后可用" : "Ready after publish")
    : (zh ? "发布后仍需 Runtime 配置" : "Runtime configuration still required after publish");

  return (
    <section className="builder-component-proposal" aria-label={zh ? "Custom Component 提案" : "Custom Component proposal"} aria-busy={busy}>
      <header>
        <div>
          <p className="builder-component-eyebrow">{zh ? "待确认的可复用能力" : "Reusable capability for review"}</p>
          <h3>{plan.display_name}</h3>
          <p>{plan.description}</p>
        </div>
        <span className={`builder-component-state is-${proposal.state}`}>
          {proposal.state === "review" ? (zh ? "等待确认" : "Needs confirmation") : proposal.state === "applied" ? (zh ? "已发布" : "Published") : (zh ? "已拒绝" : "Rejected")}
        </span>
      </header>

      <dl className="detail-list">
        <div><dt>{zh ? "能力目标" : "Capability"}</dt><dd>{plan.capability_requirement}</dd></div>
        {plan.agent_step ? <div><dt>{zh ? "Agent 中对应步骤" : "Agent step"}</dt><dd>{plan.agent_step}</dd></div> : null}
        <div><dt>{zh ? "实现类型" : "Implementation"}</dt><dd><code>{String(plan.implementation.kind ?? "unknown")}</code></dd></div>
        <div><dt>{zh ? "就绪情况" : "Readiness"}</dt><dd>{readiness}</dd></div>
      </dl>

      <div className="builder-component-io">
        <section>
          <h4>{zh ? "输入" : "Inputs"}</h4>
          {Object.keys(plan.inputs).length ? <dl>{Object.entries(plan.inputs).map(([name, field]) => <div key={name}><dt>{name}</dt><dd><code>{displayValue(field)}</code></dd></div>)}</dl> : <p>{zh ? "未声明" : "Not declared"}</p>}
        </section>
        <section>
          <h4>{zh ? "输出" : "Outputs"}</h4>
          {Object.keys(plan.outputs).length ? <dl>{Object.entries(plan.outputs).map(([name, field]) => <div key={name}><dt>{name}</dt><dd><code>{displayValue(field)}</code></dd></div>)}</dl> : <p>{zh ? "未声明" : "Not declared"}</p>}
        </section>
      </div>

      <details>
        <summary>{zh ? "查看依赖、权限与实现细节" : "Review dependencies, permissions, and implementation"}</summary>
        <h4>{zh ? "精确依赖" : "Exact dependencies"}</h4>
        {plan.dependencies.length ? <ul>{plan.dependencies.map((dependency) => <li key={dependency.reference}><code>{dependency.reference}</code><small>{dependency.content_hash}</small></li>)}</ul> : <p>{zh ? "无外部依赖" : "No external dependencies"}</p>}
        <h4>{zh ? "所需权限" : "Required permissions"}</h4>
        <pre>{JSON.stringify(plan.required_permissions, null, 2)}</pre>
        <h4>{zh ? "实现配置" : "Implementation details"}</h4>
        <pre>{JSON.stringify(plan.implementation, null, 2)}</pre>
        {plan.why ? <p>{plan.why}</p> : null}
      </details>

      {proposal.stale && isReview ? <Alert type="warning">{zh ? "Project 依赖或 Runtime 状态已变化。请重新生成提案；此提案不能应用。" : "Project dependencies or Runtime readiness changed. Generate a new proposal; this one cannot be applied."}</Alert> : null}
      {proposal.created_component ? <Alert type="info">{zh ? `已发布 ${proposal.created_component.reference}，内容 hash ${proposal.created_component.content_hash}。` : `Published ${proposal.created_component.reference} with content hash ${proposal.created_component.content_hash}.`}</Alert> : null}
      {proposal.state === "rejected" ? <Alert type="info">{zh ? "提案已拒绝，未创建组件。" : "The proposal was rejected; no Component was created."}</Alert> : null}
      {error ? <Alert type="error">{error}</Alert> : null}
      {isReview ? (
        <div className="builder-component-actions">
          <Button variant="secondary" disabled={busy} onClick={() => void command("reject")}>{zh ? "拒绝，不创建" : "Reject, create nothing"}</Button>
          <Button disabled={busy || proposal.stale} onClick={() => void command("apply")}>
            {busy ? (zh ? "正在验证并发布…" : "Validating and publishing…") : (zh ? "确认创建并发布组件" : "Confirm and publish Component")}
          </Button>
        </div>
      ) : null}
      <small>{zh ? "确认只会创建、验证并发布这个 Custom Component。Agent 不会在此操作中创建；下一步会重新解析原方案，并单独等待 Agent Draft 确认。" : "Confirmation only creates, validates, and publishes this Custom Component. It does not create an Agent; the original plan is then re-resolved and Agent Draft creation remains a separate confirmation."}</small>
    </section>
  );
}
