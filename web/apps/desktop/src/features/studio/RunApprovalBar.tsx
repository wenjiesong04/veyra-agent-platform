import type { AgentRunResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import { approvalPrompt } from "./live-run";
import { approvalCard } from "../agents/app-activity";
import { BudgetContinuation, isBudgetWaiting } from "./BudgetContinuation";

export function RunApprovalBar({
  run,
  locale,
  disabled,
  onCommand,
  onExtendBudget,
}: {
  run: AgentRunResponse | null;
  locale: "zh" | "en";
  disabled?: boolean;
  onCommand: (command: "approve" | "reject" | "stop") => void;
  onExtendBudget?: (additionalTurns: number) => void;
}) {
  if (run?.status !== "waiting") return null;
  if (isBudgetWaiting(run)) return <BudgetContinuation run={run} locale={locale} disabled={disabled || !onExtendBudget} onContinue={(turns) => onExtendBudget?.(turns)} onStop={() => onCommand("stop")} />;
  if (run.events?.filter((event) => event.kind === "approval.requested").at(-1)?.payload.kind === "input") return null;
  const zh = locale === "zh";
  const prompt = approvalPrompt(run);
  const card = approvalCard(run);
  return (
    <div className="run-approval-bar" role="region" aria-label={zh ? "运行审批" : "Run approval"}>
      {prompt ? <p className="studio-run-note">{prompt}</p> : null}
      {card?.target ? <p className="studio-run-note">{card.action}: {card.target}</p> : null}
      <div className="studio-run-actions">
        <Button variant="primary" disabled={disabled} onClick={() => onCommand("approve")}>{zh ? "批准" : "Approve"}</Button>
        <Button variant="ghost" disabled={disabled} onClick={() => onCommand("reject")}>{zh ? "拒绝" : "Reject"}</Button>
        <Button variant="ghost" disabled={disabled} onClick={() => onCommand("stop")}>{zh ? "停止" : "Stop"}</Button>
      </div>
    </div>
  );
}
