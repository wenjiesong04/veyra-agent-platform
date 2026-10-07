import { useState } from "react";
import type { WorkflowRunResponse } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { RunEvidence } from "../runs/RunDetail";

export function WorkflowEvidence({ run, locale, api }: { run: WorkflowRunResponse; locale: "zh" | "en"; api: LocalProjectApi }) {
  const [open, setOpen] = useState(false);
  return <details className="workflow-app-evidence" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{locale === "zh" ? "运行详情" : "Run details"}</summary>
    {open ? <RunEvidence run={run} locale={locale} api={api} showResult={false} /> : null}
  </details>;
}
