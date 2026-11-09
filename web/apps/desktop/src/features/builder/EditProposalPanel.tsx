import * as React from "react";
import type { EditProposal, EditProposalChange, EditProposalCommand, EditTargetKind, KnowledgeBindingPlan, ResourceBindingPlan, ValidationRepairPlan } from "@veyra/api-contracts";
import { Alert, Button, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { DependencyReport } from "../studio/DependencyReport";

type Props = {
  api: LocalProjectApi;
  projectId: string;
  targetKind: EditTargetKind;
  targetId: string;
  revision: number;
  etag: string;
  blocked: boolean;
  disabled?: boolean;
  refreshKey?: string;
  locale: "zh" | "en";
  onCommand: (proposal: EditProposal, command: EditProposalCommand) => Promise<EditProposal>;
  onConflict: () => void;
  incoming?: EditProposal;
  targetName: string;
};

export function EditProposalPanel({ api, projectId, targetKind, targetId, revision, etag, blocked, disabled = false, refreshKey, locale, onCommand, onConflict, incoming, targetName }: Props) {
  const zh = locale === "zh";
  const [proposals, setProposals] = React.useState<EditProposal[]>([]);
  const [busy, setBusy] = React.useState(true);
  const [error, setError] = React.useState("");
  const [reload, setReload] = React.useState(0);
  const inFlight = React.useRef(false);
  const adopted = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    let active = true;
    setBusy(true); setError("");
    void api.listEditProposals!(projectId, targetKind, targetId).then((result) => {
      if (active) setProposals(result.proposals);
    }).catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [api, projectId, targetKind, targetId, reload, refreshKey]);
  React.useEffect(() => {
    if (incoming && !busy && adopted.current !== incoming.proposal_id) {
      adopted.current = incoming.proposal_id;
      setProposals((items) => [incoming, ...items.filter((item) => item.proposal_id !== incoming.proposal_id)]);
    }
  }, [incoming, busy]);

  const perform = async (operation: () => Promise<EditProposal>) => {
    if (busy || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const proposal = await operation();
      setProposals((items) => [proposal, ...items.filter((item) => item.proposal_id !== proposal.proposal_id)]);
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "draft_conflict") onConflict();
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { inFlight.current = false; setBusy(false); }
  };
  return <Panel className="studio-edit-proposals">
    <SectionHeading eyebrow="Veyra Builder · Chat" title={zh ? "修改项目内容" : "Change Project content"} detail={zh ? "计划：读取已保存目标与项目资源 → 优先复用资源 → 提案与差异 → 你确认后应用并验证。只改一个 Draft，不提交版本、不运行。生成会发送项目元数据、资源描述与目标源码，不读取文件正文。" : "Plan: inspect the saved target and Project resources → reuse resources → propose and diff → apply and validate only after your confirmation. One Draft; no versions or runs. Generation sends Project metadata, resource descriptors and target source, not file contents."} />
    {blocked ? <Alert type="warning">{zh ? "请重新加载当前草稿并处理冲突后再生成、应用或撤销。仍可查看和拒绝提案。" : "Reload the current Draft and resolve the conflict before generating, applying, or undoing. You can still inspect and reject proposals."}</Alert> : null}
    {error ? <Alert type="error">{error}</Alert> : null}
    <div className="studio-edit-actions">
      <Button disabled={busy} onClick={() => setReload((value) => value + 1)}>{zh ? "刷新提案" : "Refresh proposals"}</Button>
      {busy ? <span role="status">{zh ? "正在处理…" : "Working…"}</span> : null}
    </div>
    {!busy && !proposals.length ? <p>{zh ? "暂无提案。生成不会改变草稿。" : "No proposals yet. Generating does not change the Draft."}</p> : null}
    {proposals.map((proposal) => {
      const stale = proposal.stale || (proposal.state === "review" && (proposal.base_revision !== revision || proposal.base_etag !== etag)) || (proposal.state === "applied" && proposal.applied_revision !== revision);
      const states = { review: zh ? "待审查" : "Review", applied: zh ? "已应用" : "Applied", rejected: zh ? "已拒绝" : "Rejected", undone: zh ? "已撤销" : "Undone" };
      return <article key={proposal.proposal_id} aria-label={proposal.instruction}>
        <h3>{proposal.instruction}</h3>
        <p>{zh ? "将修改：" : "Will modify: "}{proposal.target_kind === "agent" ? "Agent" : "Workflow"} · {targetName}</p>
        <p>{states[proposal.state]} · {zh ? "基于修订" : "Base revision"} {proposal.base_revision} · {proposal.created_at}</p>
        <p>{proposal.target_kind} <code>{proposal.target_id}</code> · {zh ? "影响范围：仅当前 Draft；不可变版本与 Run 不变。" : "Impact: this Draft only; immutable versions and Runs unchanged."}</p>
        {stale ? <Alert type="warning">{zh ? "提案已过期，不能覆盖后续修改。请重新生成；仍可拒绝。" : "This proposal is stale and cannot overwrite later edits. Generate a new proposal; rejection is still available."}</Alert> : null}
        {proposal.knowledge_binding ? <KnowledgeBindingSummary plan={proposal.knowledge_binding} zh={zh} /> : null}
        {proposal.resource_binding ? <ResourceBindingSummary plan={proposal.resource_binding} zh={zh} /> : null}
        {proposal.validation_repair ? <ValidationRepairSummary plan={proposal.validation_repair} zh={zh} /> : null}
        <ChangeList title={zh ? "源码差异" : "Source changes"} changes={proposal.changes} zh={zh} />
        <ChangeList title={zh ? "权限差异" : "Permission changes"} changes={proposal.permission_changes} zh={zh} />
        <DependencyReport validation={proposal.validation} locale={locale} />
        {proposal.validation.agent_calls ? <section><h4>{zh ? "固定 Agent 版本调用" : "Pinned Agent calls"}</h4>{proposal.validation.agent_calls.length ? <ul>{proposal.validation.agent_calls.map((call) => <li key={call.node_id}><code>{call.node_id}: {call.agent_id}@{call.version_id}</code></li>)}</ul> : <p>{zh ? "没有 AgentCall 依赖。" : "No AgentCall dependencies."}</p>}</section> : null}
        <details><summary>{zh ? "候选源码与版本锁" : "Candidate source and locks"}</summary><pre>{JSON.stringify(proposal.candidate_source, null, 2)}</pre></details>
        <small>{zh ? "结构验证不是实际运行验收。确认前服务端会重新检查修订和依赖。" : "Structural validation is not runtime verification. Revision and dependencies are checked again on confirmation."}</small>
        <div className="studio-edit-actions">
          {proposal.state === "review" ? <>
            <Button disabled={busy || blocked || disabled || stale} onClick={() => void perform(() => onCommand(proposal, "apply"))}>{zh ? "确认应用提案" : "Confirm apply proposal"}</Button>
            <Button disabled={busy} onClick={() => void perform(() => onCommand(proposal, "reject"))}>{zh ? "拒绝提案" : "Reject proposal"}</Button>
          </> : null}
          {proposal.state === "applied" ? <Button disabled={busy || blocked || disabled || stale} onClick={() => void perform(() => onCommand(proposal, "undo"))}>{zh ? "确认撤销应用" : "Confirm undo application"}</Button> : null}
        </div>
      </article>;
    })}
  </Panel>;
}

function KnowledgeBindingSummary({ plan, zh }: { plan: KnowledgeBindingPlan; zh: boolean }) {
  const readiness = {
    indexed: zh ? "已建立索引" : "Indexed",
    not_indexed: zh ? "未建立索引" : "Not indexed",
    stale: zh ? "需重建" : "Needs rebuild",
    failed: zh ? "索引失败" : "Index failed",
  }[plan.index_status];
  const action = plan.required_action === "build_index"
    ? (zh ? "运行前需要先在知识库点“构建索引”。绑定不会自动建索引。" : "Build the index in Knowledge before running. Binding never builds it for you.")
    : plan.required_action === "rebuild_index"
      ? (zh ? "内容已变化，运行前需要先重建索引。绑定不会自动重建。" : "Content changed; rebuild the index before running. Binding never rebuilds it for you.")
      : null;
  return (
    <section aria-label={zh ? "Knowledge 绑定" : "Knowledge binding"}>
      <h4>{zh ? "Knowledge 绑定" : "Knowledge binding"}</h4>
      <p>{zh ? "将绑定：" : "Will bind: "}<strong>{plan.name}</strong></p>
      <dl className="detail-list">
        <div><dt>{zh ? "身份" : "Identity"}</dt><dd><code>{plan.reference}</code></dd></div>
        <div><dt>{zh ? "锁定内容 hash" : "Locked content hash"}</dt><dd><code>{plan.source_file_hash}</code></dd></div>
        <div><dt>{zh ? "检索就绪" : "Retrieval readiness"}</dt><dd><StatusBadge label={readiness} tone={plan.runnable ? "good" : "warn"} /></dd></div>
        {plan.chunk_count == null ? null : <div><dt>{zh ? "片段数" : "Chunk count"}</dt><dd>{plan.chunk_count}</dd></div>}
      </dl>
      {action ? <Alert type="warning">{action}</Alert> : null}
      {plan.failure_reason ? <Alert type="error">{plan.failure_reason}</Alert> : null}
      <small>{zh ? "只改当前 Draft；已提交版本不变，Runtime 要在新版本或新运行后才使用这份知识。" : "This changes the Draft only. Committed versions are unchanged, and the Runtime uses this Knowledge only after a new version or run."}</small>
    </section>
  );
}

function ResourceBindingSummary({ plan, zh }: { plan: ResourceBindingPlan; zh: boolean }) {
  const labels: Record<ResourceBindingPlan["readiness"], [string, string]> = {
    ready: ["就绪", "Ready"],
    requires_configuration: ["需要配置", "Needs configuration"],
    design_only: ["仅设计", "Design only"],
    unavailable: ["不可用", "Unavailable"],
    quarantined: ["隔离待审", "Quarantined"],
    unsupported: ["Runtime 不支持", "Runtime unsupported"],
    stale: ["Project pin 已漂移", "Project pin stale"],
  };
  const tone = plan.readiness === "ready"
    ? "good" as const
    : plan.readiness === "requires_configuration" || plan.readiness === "stale"
      ? "warn" as const
      : "bad" as const;
  return (
    <section aria-label={zh ? "Project Resource 绑定" : "Project Resource binding"}>
      <h4>{zh ? "Project Resource 绑定" : "Project Resource binding"}</h4>
      <p>{zh ? "将使用：" : "Will use: "}<strong>{plan.name}</strong></p>
      <dl className="detail-list">
        <div><dt>Resource</dt><dd><code>{plan.reference}</code></dd></div>
        <div><dt>Project pin</dt><dd><code>{plan.bound_content_hash}</code></dd></div>
        {plan.binding_status === "stale" ? <div><dt>{zh ? "当前 Catalog hash" : "Current Catalog hash"}</dt><dd><code>{plan.catalog_content_hash}</code></dd></div> : null}
        <div><dt>{zh ? "就绪状态" : "Readiness"}</dt><dd><StatusBadge label={labels[plan.readiness][zh ? 0 : 1]} tone={tone} /></dd></div>
        <div><dt>{zh ? "Runtime 状态" : "Runtime status"}</dt><dd>{plan.runtime_status}</dd></div>
      </dl>
      <h5>{zh ? "需要增加的最小权限" : "Minimum required permissions"}</h5>
      <pre>{JSON.stringify(plan.required_permissions, null, 2)}</pre>
      {plan.blocking_reasons.length ? <ul>{plan.blocking_reasons.map((reason) => <li key={reason.code}><code>{reason.code}</code> · {reason.message}</li>)}</ul> : null}
      {plan.readiness !== "ready" ? <Alert type="warning">{zh ? "Resource 已属于当前 Project，但还不能执行。Builder 不会配置密钥、升级 pin 或绕过 Runtime 检查。" : "This Resource belongs to the Project but is not executable yet. Builder will not configure secrets, upgrade the pin, or bypass Runtime checks."}</Alert> : null}
      <small>{zh ? "只改 Agent Draft；Project Resource 和不可变版本不变。source.lock 使用 Project pin，不会自动升级到当前 Catalog hash。" : "Only the Agent Draft changes. The Project Resource and immutable versions stay unchanged. source.lock uses the Project pin and never auto-upgrades to the current Catalog hash."}</small>
    </section>
  );
}

function ValidationRepairSummary({ plan, zh }: { plan: ValidationRepairPlan; zh: boolean }) {
  return (
    <section aria-label={zh ? "验证修复" : "Validation repair"}>
      <h4>{zh ? "验证修复" : "Validation repair"}</h4>
      <p>{zh ? "将修复：" : "Will repair: "}<strong>{plan.name}</strong> · <code>{plan.code}</code></p>
      <dl className="detail-list">
        <div><dt>Resource</dt><dd><code>{plan.reference}</code></dd></div>
        {plan.bound_content_hash ? <div><dt>Project pin</dt><dd><code>{plan.bound_content_hash}</code></dd></div> : null}
        {plan.content_hash ? <div><dt>{zh ? "当前 Project hash" : "Current Project hash"}</dt><dd><code>{plan.content_hash}</code></dd></div> : null}
        {plan.locked_hash ? <div><dt>{zh ? "当前 Agent lock" : "Current Agent lock"}</dt><dd><code>{plan.locked_hash}</code></dd></div> : null}
      </dl>
      {plan.required_permissions ? <pre>{JSON.stringify(plan.required_permissions, null, 2)}</pre> : null}
      <Alert type="info">{plan.impact}</Alert>
      <small>{zh ? "确认前草稿不变。不会静默升级 Catalog、不会自动加入 Project、不会配置密钥。" : "The Draft is unchanged until you confirm. No silent Catalog upgrade, Project add, or secret configuration."}</small>
    </section>
  );
}

function ChangeList({ title, changes, zh }: { title: string; changes: EditProposalChange[]; zh: boolean }) {
  return <section><h4>{title}</h4>{changes.length ? <ul>{changes.map((change) => <li key={change.path}><code>{change.operation} {change.path}</code><div className="studio-edit-diff"><div><strong>{zh ? "之前" : "Before"}</strong><pre>{JSON.stringify(change.before, null, 2)}</pre></div><div><strong>{zh ? "之后" : "After"}</strong><pre>{JSON.stringify(change.after, null, 2)}</pre></div></div></li>)}</ul> : <p>{zh ? "没有变化。" : "No changes."}</p>}</section>;
}
