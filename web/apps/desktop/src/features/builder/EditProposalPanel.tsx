import * as React from "react";
import type { EditProposal, EditProposalChange, EditProposalCommand, EditTargetKind } from "@veyra/api-contracts";
import { Alert, Button, Panel, SectionHeading } from "@veyra/ui";
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
  locale: "zh" | "en";
  onCommand: (proposal: EditProposal, command: EditProposalCommand) => Promise<EditProposal>;
  onConflict: () => void;
  incoming?: EditProposal;
  targetName: string;
};

export function EditProposalPanel({ api, projectId, targetKind, targetId, revision, etag, blocked, locale, onCommand, onConflict, incoming, targetName }: Props) {
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
  }, [api, projectId, targetKind, targetId, reload]);
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
        <ChangeList title={zh ? "源码差异" : "Source changes"} changes={proposal.changes} zh={zh} />
        <ChangeList title={zh ? "权限差异" : "Permission changes"} changes={proposal.permission_changes} zh={zh} />
        <DependencyReport validation={proposal.validation} locale={locale} />
        {proposal.validation.agent_calls ? <section><h4>{zh ? "固定 Agent 版本调用" : "Pinned Agent calls"}</h4>{proposal.validation.agent_calls.length ? <ul>{proposal.validation.agent_calls.map((call) => <li key={call.node_id}><code>{call.node_id}: {call.agent_id}@{call.version_id}</code></li>)}</ul> : <p>{zh ? "没有 AgentCall 依赖。" : "No AgentCall dependencies."}</p>}</section> : null}
        <details><summary>{zh ? "候选源码与版本锁" : "Candidate source and locks"}</summary><pre>{JSON.stringify(proposal.candidate_source, null, 2)}</pre></details>
        <small>{zh ? "结构验证不是实际运行验收。确认前服务端会重新检查修订和依赖。" : "Structural validation is not runtime verification. Revision and dependencies are checked again on confirmation."}</small>
        <div className="studio-edit-actions">
          {proposal.state === "review" ? <>
            <Button disabled={busy || blocked || stale} onClick={() => void perform(() => onCommand(proposal, "apply"))}>{zh ? "确认应用提案" : "Confirm apply proposal"}</Button>
            <Button disabled={busy} onClick={() => void perform(() => onCommand(proposal, "reject"))}>{zh ? "拒绝提案" : "Reject proposal"}</Button>
          </> : null}
          {proposal.state === "applied" ? <Button disabled={busy || blocked || stale} onClick={() => void perform(() => onCommand(proposal, "undo"))}>{zh ? "确认撤销应用" : "Confirm undo application"}</Button> : null}
        </div>
      </article>;
    })}
  </Panel>;
}

function ChangeList({ title, changes, zh }: { title: string; changes: EditProposalChange[]; zh: boolean }) {
  return <section><h4>{title}</h4>{changes.length ? <ul>{changes.map((change) => <li key={change.path}><code>{change.operation} {change.path}</code><div className="studio-edit-diff"><div><strong>{zh ? "之前" : "Before"}</strong><pre>{JSON.stringify(change.before, null, 2)}</pre></div><div><strong>{zh ? "之后" : "After"}</strong><pre>{JSON.stringify(change.after, null, 2)}</pre></div></div></li>)}</ul> : <p>{zh ? "没有变化。" : "No changes."}</p>}</section>;
}
