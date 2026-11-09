import type { AgentDependencyCheck } from "@veyra/api-contracts";
import { Alert, Button, StatusBadge } from "@veyra/ui";
import { issueDetail, issueNextAction, issueTitle, type BuilderValidationIssue } from "./validation-feedback";

export function BuilderValidationIssues({
  issues,
  locale,
  disabled,
  onRepair,
}: {
  issues: BuilderValidationIssue[];
  locale: "zh" | "en";
  disabled: boolean;
  onRepair?: (issue: BuilderValidationIssue) => void;
}) {
  if (!issues.length) return null;
  const zh = locale === "zh";
  return (
    <ul className="builder-validation-issues">
      {issues.map((issue) => (
        <li key={`${issue.code}:${issue.reference}`}>
          <div>
            <strong>{issueTitle(issue.code as AgentDependencyCheck["status"], locale)}</strong>
            <StatusBadge label={issue.repairable ? (zh ? "可修复" : "Repairable") : (zh ? "需手动处理" : "Needs action")} tone={issue.repairable ? "warn" : "bad"} />
          </div>
          <p><strong>{issue.name}</strong></p>
          <code>{issue.reference}</code>
          {issue.bound_content_hash ? <p>{zh ? "期望 Project pin：" : "Expected Project pin: "}<code>{issue.bound_content_hash}</code></p> : null}
          {issue.kind === "knowledge" && issue.content_hash ? <p>{zh ? "当前 Project hash：" : "Current Project hash: "}<code>{issue.content_hash}</code></p> : null}
          {issue.locked_hash ? <p>{zh ? "当前 Agent lock：" : "Current Agent lock: "}<code>{issue.locked_hash}</code></p> : null}
          {issueDetail(issue.message) ? <p>{issueDetail(issue.message)}</p> : null}
          {issue.repairable && onRepair ? (
            <Button disabled={disabled} onClick={() => onRepair(issue)}>{zh ? "创建修复提案" : "Create repair proposal"}</Button>
          ) : <Alert type="warning">{issueNextAction(issue, locale)}</Alert>}
        </li>
      ))}
    </ul>
  );
}
