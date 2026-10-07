import * as React from "react";
import { compactFieldType, fieldIsRequired, type JsonValue, type TypedFields, type WorkflowRunResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { requiredArtifactsReady } from "../runtime/RuntimeInputForm";
import { initialSourceInputs, RunInputFields } from "./studio-run-ui";

function requiredValuesReady(schema: TypedFields, values: Record<string, JsonValue>): boolean {
  return requiredArtifactsReady(schema, values) && Object.entries(schema).every(([name, spec]) => {
    if (!fieldIsRequired(spec)) return true;
    const value = values[name];
    if (value === undefined || value === null) return false;
    const type = compactFieldType(spec);
    if (type === "string") return typeof value === "string" && value.trim().length > 0;
    if (type === "number" || type === "integer") return typeof value === "number" && Number.isFinite(value);
    if (type === "array" || type === "table") return Array.isArray(value) && value.length > 0;
    return true;
  });
}

export function WorkflowInputReplyBar({ run, schema, locale, disabled = false, onReply, api, projectId }: {
  run: WorkflowRunResponse;
  schema: TypedFields;
  locale: "zh" | "en";
  disabled?: boolean;
  onReply: (inputs: Record<string, JsonValue>) => void;
  api?: LocalProjectApi;
  projectId?: string;
}) {
  const [values, setValues] = React.useState<Record<string, JsonValue>>(() => initialSourceInputs(schema));
  const signature = JSON.stringify(schema);
  React.useEffect(() => { setValues(initialSourceInputs(schema)); }, [run.run_id, run.waiting?.node_id, signature]);
  if (run.status !== "waiting" || run.waiting?.kind !== "input") return null;
  const zh = locale === "zh";
  return <section className="run-approval-bar" role="region" aria-label={zh ? "补充运行输入" : "Provide run input"}>
    <strong>{zh ? "等待你补充信息" : "Waiting for your input"}</strong>
    {run.waiting.prompt ? <p className="studio-run-note">{run.waiting.prompt}</p> : null}
    <RunInputFields schema={schema} values={values} onChange={setValues} emptyLabel={zh ? "此步骤没有声明输入字段。" : "This step has no declared input fields."} locale={locale} api={api} projectId={projectId} />
    <div className="studio-run-actions">
      <Button variant="primary" disabled={disabled || !Object.keys(schema).length || !requiredValuesReady(schema, values)} onClick={() => onReply(values)}>{zh ? "提交并继续" : "Submit and continue"}</Button>
    </div>
  </section>;
}
