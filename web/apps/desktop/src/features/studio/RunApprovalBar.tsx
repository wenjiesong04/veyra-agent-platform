import type { AgentRunResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import { approvalPrompt } from "./live-run";

export function RunApprovalBar({
  run,
  locale,
  disabled,
  onCommand,
}: {
  run: AgentRunResponse | null;
  locale: "zh" | "en";
  disabled?: boolean;
  onCommand: (command: "approve" | "reject" | "stop") => void;
}) {
  if (run?.status !== "waiting") return null;
  const zh = locale === "zh";
  const prompt = approvalPrompt(run);
  return (
    <div className="run-approval-bar" role="region" aria-label={zh ? "运行审批" : "Run approval"}>
      {prompt ? <p className="studio-run-note">{prompt}</p> : null}
      <div className="studio-run-actions">
        <Button variant="primary" disabled={disabled} onClick={() => onCommand("approve")}>{zh ? "批准" : "Approve"}</Button>
        <Button variant="ghost" disabled={disabled} onClick={() => onCommand("reject")}>{zh ? "拒绝" : "Reject"}</Button>
        <Button variant="ghost" disabled={disabled} onClick={() => onCommand("stop")}>{zh ? "停止" : "Stop"}</Button>
      </div>
    </div>
  );
}
